import base64
import uuid
from functools import wraps

from flask import current_app, jsonify, redirect, render_template, request, send_from_directory, session, url_for
from werkzeug.security import check_password_hash

from .db import get_db_connection
from .services import (
    classify_node,
    compute_average_speed_kmh,
    extract_plate,
    hash_plate,
    levenshtein_distance,
    normalize_plate,
    parse_timestamp,
    paystack_initialize_transaction,
    paystack_verify_transaction,
    save_image,
    utc_now_iso,
)


def _relative_path(path):
    base_dir = current_app.config["BASE_DIR"]
    data_dir = current_app.config["DATA_DIR"]

    try:
        return str(path.relative_to(base_dir))
    except ValueError:
        pass

    try:
        return str(path.relative_to(data_dir))
    except ValueError:
        return str(path)


def cleanup_tracking_buffer(db, cutoff_ts):
    db.execute("DELETE FROM tracking_buffer WHERE entry_time < ?", (cutoff_ts,))


def record_event(db, *, event_id, node_id, plate, image_path, event_ts, doppler_frequency):
    db.execute(
        """
        INSERT INTO vehicle_events (
            event_id, node_id, raw_plate, normalized_plate, plate_hash,
            image_path, timestamp, doppler_frequency, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_id,
            node_id,
            plate,
            normalize_plate(plate),
            hash_plate(plate) if plate else None,
            _relative_path(image_path),
            event_ts,
            doppler_frequency,
            utc_now_iso(),
        ),
    )


def store_entry_record(db, *, event_id, plate, image_path, event_ts):
    db.execute(
        """
        INSERT OR REPLACE INTO tracking_buffer (
            event_id, normalized_plate, image_path, entry_time, created_at
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (
            event_id,
            plate,
            _relative_path(image_path),
            event_ts,
            utc_now_iso(),
        ),
    )


def find_best_entry_match(db, exit_plate):
    rows = db.execute(
        """
        SELECT id, event_id, normalized_plate, image_path, entry_time
        FROM tracking_buffer
        ORDER BY entry_time ASC
        """
    ).fetchall()

    best_row = None
    best_distance = None
    for row in rows:
        distance = levenshtein_distance(exit_plate, row["normalized_plate"])
        if best_distance is None or distance < best_distance:
            best_distance = distance
            best_row = row

    if best_row is None or best_distance is None or best_distance > 1:
        return None
    return best_row


def create_violation(db, *, plate, entry_row, exit_image_path, exit_time, speed):
    ticket_id = f"TKT-{uuid.uuid4().hex[:10].upper()}"
    db.execute(
        """
        INSERT INTO violations (
            ticket_id, plate_hash, active_plate, entry_time, exit_time, speed,
            speed_limit, status, fine, evidence_entry_path, evidence_exit_path,
            created_at, paid_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ticket_id,
            hash_plate(plate),
            plate,
            entry_row["entry_time"],
            exit_time,
            speed,
            current_app.config["DEFAULT_SPEED_LIMIT_KMH"],
            "UNPAID",
            current_app.config["DEFAULT_FINE"],
            entry_row["image_path"],
            _relative_path(exit_image_path),
            utc_now_iso(),
            None,
        ),
    )
    return ticket_id


def clear_entry_record(db, tracking_id):
    db.execute("DELETE FROM tracking_buffer WHERE id = ?", (tracking_id,))


def find_active_ticket(db, gate_plate):
    rows = db.execute(
        """
        SELECT ticket_id, active_plate, fine, speed, speed_limit, created_at, status
        FROM violations
        WHERE status = 'UNPAID'
        ORDER BY created_at DESC
        """
    ).fetchall()

    best_row = None
    best_distance = None
    for row in rows:
        distance = levenshtein_distance(gate_plate, row["active_plate"])
        if best_distance is None or distance < best_distance:
            best_distance = distance
            best_row = row

    if best_row is None or best_distance is None or best_distance > 1:
        return None
    return best_row


def list_dashboard_tickets(db):
    return db.execute(
        """
        SELECT ticket_id, active_plate, speed, speed_limit, fine, status, created_at, paid_at
        FROM violations
        ORDER BY created_at DESC
        """
    ).fetchall()


def find_tickets_by_plate(db, plate):
    return db.execute(
        """
        SELECT ticket_id, active_plate, speed, speed_limit, fine, status, created_at, paid_at
        FROM violations
        WHERE active_plate = ?
        ORDER BY created_at DESC
        """,
        (plate,),
    ).fetchall()


def find_ticket_by_id_and_plate(db, ticket_id, plate):
    return db.execute(
        """
        SELECT ticket_id, active_plate, speed, speed_limit, fine, status, created_at, paid_at
        FROM violations
        WHERE ticket_id = ? AND active_plate = ?
        """,
        (ticket_id, plate),
    ).fetchone()


def create_payment_transaction(db, *, ticket_id, plate, email, amount, reference, authorization_url, access_code):
    db.execute(
        """
        INSERT INTO payment_transactions (
            ticket_id, plate, email, provider, reference, amount, status,
            authorization_url, access_code, gateway_response, created_at, paid_at
        ) VALUES (?, ?, ?, 'paystack', ?, ?, 'initialized', ?, ?, NULL, ?, NULL)
        """,
        (
            ticket_id,
            plate,
            email,
            reference,
            amount,
            authorization_url,
            access_code,
            utc_now_iso(),
        ),
    )


def mark_payment_transaction(db, *, reference, status, gateway_response, paid_at=None):
    db.execute(
        """
        UPDATE payment_transactions
        SET status = ?, gateway_response = ?, paid_at = ?
        WHERE reference = ?
        """,
        (status, gateway_response, paid_at, reference),
    )


def fetch_payment_transaction(db, reference):
    return db.execute(
        """
        SELECT ticket_id, plate, email, provider, reference, amount, status, paid_at
        FROM payment_transactions
        WHERE reference = ?
        """,
        (reference,),
    ).fetchone()


def get_dashboard_stats(db):
    stats = db.execute(
        """
        SELECT
            (SELECT COUNT(*) FROM vehicle_events) AS total_events,
            (SELECT COUNT(*) FROM tracking_buffer) AS active_tracks,
            (SELECT COUNT(*) FROM violations) AS total_tickets,
            (SELECT COUNT(*) FROM violations WHERE status = 'UNPAID') AS unpaid_tickets,
            (SELECT COUNT(*) FROM violations WHERE status = 'PAID') AS paid_tickets
        """
    ).fetchone()
    return stats


def admin_logged_in():
    return session.get("admin_authenticated") is True


def admin_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if not admin_logged_in():
            return redirect(url_for("admin_login", next=request.path))
        return view(*args, **kwargs)

    return wrapped_view


def register_routes(app):
    @app.get("/uploads/<path:filename>")
    def uploaded_file(filename):
        return send_from_directory(current_app.config["UPLOAD_DIR"], filename)

    @app.get("/")
    def public_portal():
        plate = normalize_plate(request.args.get("plate", ""))
        success = request.args.get("success") == "1"
        error = request.args.get("error", "")
        with get_db_connection(current_app) as db:
            tickets = find_tickets_by_plate(db, plate) if plate else []

        return render_template(
            "public_portal.html",
            plate=plate,
            tickets=tickets,
            success=success,
            error=error,
            paystack_public_key=current_app.config["PAYSTACK_PUBLIC_KEY"],
        )

    @app.get("/admin")
    @admin_required
    def dashboard():
        with get_db_connection(current_app) as db:
            stats = get_dashboard_stats(db)
            tickets = list_dashboard_tickets(db)

        return render_template("dashboard.html", stats=stats, tickets=tickets)

    @app.route("/admin/login", methods=["GET", "POST"])
    def admin_login():
        error = ""
        next_url = request.args.get("next") or request.form.get("next") or url_for("dashboard")

        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            configured_username = current_app.config["ADMIN_USERNAME"]
            configured_password = current_app.config["ADMIN_PASSWORD"]

            if configured_password.startswith("pbkdf2:") or configured_password.startswith("scrypt:"):
                password_ok = check_password_hash(configured_password, password)
            else:
                password_ok = configured_password == password

            if username == configured_username and password_ok:
                session.clear()
                session["admin_authenticated"] = True
                session["admin_username"] = username
                return redirect(next_url)

            error = "Invalid admin credentials"

        return render_template("admin_login.html", error=error, next_url=next_url)

    @app.post("/admin/logout")
    def admin_logout():
        session.clear()
        return redirect(url_for("admin_login"))

    @app.post("/tickets/<ticket_id>/pay")
    @admin_required
    def pay_ticket_from_dashboard(ticket_id):
        with get_db_connection(current_app) as db:
            updated = db.execute(
                """
                UPDATE violations
                SET status = 'PAID', paid_at = ?
                WHERE ticket_id = ? AND status = 'UNPAID'
                """,
                (utc_now_iso(), ticket_id),
            )

        if updated.rowcount == 0:
            return redirect(url_for("dashboard"))

        return redirect(url_for("dashboard"))

    @app.post("/portal/tickets/<ticket_id>/pay")
    def pay_ticket_from_portal(ticket_id):
        plate = normalize_plate(request.form.get("plate", ""))
        email = request.form.get("email", "").strip().lower()
        if not plate or not email:
            return redirect(url_for("public_portal", plate=plate, error="Plate and email are required"))

        secret_key = current_app.config["PAYSTACK_SECRET_KEY"]
        if not secret_key:
            return redirect(url_for("public_portal", plate=plate, error="Paystack is not configured yet"))

        with get_db_connection(current_app) as db:
            ticket = find_ticket_by_id_and_plate(db, ticket_id, plate)
            if ticket is None or ticket["status"] != "UNPAID":
                return redirect(url_for("public_portal", plate=plate, error="Ticket not found or already paid"))

            reference = f"UNILAG-{ticket_id}-{uuid.uuid4().hex[:10].upper()}"
            callback_url = f"{current_app.config['APP_BASE_URL'].rstrip('/')}/portal/paystack/callback"
            metadata = {"ticket_id": ticket_id, "plate": plate}
            try:
                response = paystack_initialize_transaction(
                    secret_key=secret_key,
                    base_url=current_app.config["PAYSTACK_BASE_URL"],
                    email=email,
                    amount_kobo=int(ticket["fine"] * 100),
                    reference=reference,
                    callback_url=callback_url,
                    metadata=metadata,
                )
            except ValueError:
                return redirect(url_for("public_portal", plate=plate, error="Unable to initialize payment"))

            if not response.get("status"):
                return redirect(url_for("public_portal", plate=plate, error="Unable to initialize payment"))

            data = response.get("data", {})
            create_payment_transaction(
                db,
                ticket_id=ticket_id,
                plate=plate,
                email=email,
                amount=int(ticket["fine"] * 100),
                reference=data["reference"],
                authorization_url=data.get("authorization_url"),
                access_code=data.get("access_code"),
            )

        return redirect(data["authorization_url"])

    @app.get("/portal/paystack/callback")
    def paystack_callback():
        reference = request.args.get("reference", "").strip()
        if not reference:
            return redirect(url_for("public_portal", error="Missing payment reference"))

        secret_key = current_app.config["PAYSTACK_SECRET_KEY"]
        if not secret_key:
            return redirect(url_for("public_portal", error="Paystack is not configured yet"))

        try:
            verification = paystack_verify_transaction(
                secret_key=secret_key,
                base_url=current_app.config["PAYSTACK_BASE_URL"],
                reference=reference,
            )
        except ValueError:
            return redirect(url_for("public_portal", error="Payment verification failed"))

        data = verification.get("data", {})
        metadata = data.get("metadata") or {}
        plate = normalize_plate(metadata.get("plate", ""))
        ticket_id = metadata.get("ticket_id", "")

        with get_db_connection(current_app) as db:
            payment_row = fetch_payment_transaction(db, reference)
            if payment_row is None:
                return redirect(url_for("public_portal", plate=plate, error="Payment record not found"))

            if verification.get("status") and data.get("status") == "success":
                mark_payment_transaction(
                    db,
                    reference=reference,
                    status="success",
                    gateway_response=data.get("gateway_response", "Successful"),
                    paid_at=data.get("paid_at") or utc_now_iso(),
                )
                db.execute(
                    """
                    UPDATE violations
                    SET status = 'PAID', paid_at = ?
                    WHERE ticket_id = ? AND active_plate = ? AND status = 'UNPAID'
                    """,
                    (data.get("paid_at") or utc_now_iso(), ticket_id, plate),
                )
                return redirect(url_for("public_portal", plate=plate, success=1))

            mark_payment_transaction(
                db,
                reference=reference,
                status=data.get("status", "failed"),
                gateway_response=data.get("gateway_response", "Verification failed"),
                paid_at=None,
            )

        return redirect(url_for("public_portal", plate=plate, error="Payment was not successful"))

    @app.post("/api/v1/log_event")
    def log_event():
        payload = request.form.to_dict() if request.files else (request.get_json(silent=True) or {})
        node_id = payload.get("node_id")
        if not node_id:
            return jsonify({"error": "node_id is required"}), 400

        try:
            node_type = classify_node(node_id)
            event_ts = parse_timestamp(payload.get("timestamp"))
            doppler_frequency = payload.get("doppler_frequency")
            doppler_frequency = float(doppler_frequency) if doppler_frequency not in (None, "") else None
            image_path = save_image(current_app, payload, request.files)
            plate_override = payload.get("plate_text_override")
            event_id = uuid.uuid4().hex
            plate = extract_plate(image_path, plate_override=plate_override)
        except (ValueError, TypeError, base64.binascii.Error) as exc:
            return jsonify({"error": str(exc)}), 400

        with get_db_connection(current_app) as db:
            cleanup_tracking_buffer(db, event_ts - current_app.config["ACTIVE_TRACKING_WINDOW_SECONDS"])
            record_event(
                db,
                event_id=event_id,
                node_id=node_id,
                plate=plate,
                image_path=image_path,
                event_ts=event_ts,
                doppler_frequency=doppler_frequency,
            )

            if node_type == "entry":
                store_entry_record(
                    db,
                    event_id=event_id,
                    plate=plate,
                    image_path=image_path,
                    event_ts=event_ts,
                )
                return jsonify(
                    {
                        "status": "RECORDED",
                        "node_type": "entry",
                        "plate": plate,
                        "event_id": event_id,
                    }
                ), 201

            if node_type == "exit":
                entry_row = find_best_entry_match(db, plate)
                if entry_row is None:
                    return jsonify(
                        {
                            "status": "NO_MATCH",
                            "node_type": "exit",
                            "plate": plate,
                            "event_id": event_id,
                        }
                    ), 202

                speed = compute_average_speed_kmh(
                    current_app.config["SECTION_DISTANCE_METERS"],
                    entry_row["entry_time"],
                    event_ts,
                )
                clear_entry_record(db, entry_row["id"])

                if speed > current_app.config["DEFAULT_SPEED_LIMIT_KMH"]:
                    ticket_id = create_violation(
                        db,
                        plate=plate,
                        entry_row=entry_row,
                        exit_image_path=image_path,
                        exit_time=event_ts,
                        speed=speed,
                    )
                    return jsonify(
                        {
                            "status": "VIOLATION",
                            "ticket_id": ticket_id,
                            "plate": plate,
                            "speed": round(speed, 2),
                            "speed_limit": current_app.config["DEFAULT_SPEED_LIMIT_KMH"],
                            "fine": current_app.config["DEFAULT_FINE"],
                        }
                    ), 201

                return jsonify(
                    {
                        "status": "CLEAR",
                        "plate": plate,
                        "speed": round(speed, 2),
                        "speed_limit": current_app.config["DEFAULT_SPEED_LIMIT_KMH"],
                    }
                ), 200

            active_ticket = find_active_ticket(db, plate)
            if active_ticket is None:
                return jsonify({"status": "PASS"}), 200

            return jsonify(
                {
                    "status": "DENY",
                    "fine": active_ticket["fine"],
                    "ticket_id": active_ticket["ticket_id"],
                    "plate": active_ticket["active_plate"],
                    "speed": round(active_ticket["speed"], 2),
                }
            ), 200

    @app.get("/api/v1/check_ticket")
    def check_ticket():
        plate = normalize_plate(request.args.get("plate", ""))
        if not plate:
            return jsonify({"error": "plate query parameter is required"}), 400

        with get_db_connection(current_app) as db:
            active_ticket = find_active_ticket(db, plate)

        if active_ticket is None:
            return jsonify({"status": "PASS"}), 200

        return jsonify(
            {
                "status": "DENY",
                "fine": active_ticket["fine"],
                "ticket_id": active_ticket["ticket_id"],
                "plate": active_ticket["active_plate"],
                "speed": round(active_ticket["speed"], 2),
            }
        ), 200

    @app.post("/api/v1/tickets/<ticket_id>/pay")
    @admin_required
    def pay_ticket(ticket_id):
        with get_db_connection(current_app) as db:
            updated = db.execute(
                """
                UPDATE violations
                SET status = 'PAID', paid_at = ?
                WHERE ticket_id = ? AND status = 'UNPAID'
                """,
                (utc_now_iso(), ticket_id),
            )

        if updated.rowcount == 0:
            return jsonify({"error": "ticket not found or already paid"}), 404

        return jsonify({"status": "PAID", "ticket_id": ticket_id}), 200

    @app.get("/api/v1/tickets")
    @admin_required
    def list_tickets():
        with get_db_connection(current_app) as db:
            tickets = list_dashboard_tickets(db)

        return jsonify(
            {
                "tickets": [
                    {
                        "ticket_id": row["ticket_id"],
                        "plate": row["active_plate"],
                        "speed": round(row["speed"], 2),
                        "speed_limit": row["speed_limit"],
                        "fine": row["fine"],
                        "status": row["status"],
                        "created_at": row["created_at"],
                        "paid_at": row["paid_at"],
                    }
                    for row in tickets
                ]
            }
        ), 200

    @app.get("/api/v1/public/tickets")
    def public_ticket_lookup():
        plate = normalize_plate(request.args.get("plate", ""))
        if not plate:
            return jsonify({"error": "plate query parameter is required"}), 400

        with get_db_connection(current_app) as db:
            tickets = find_tickets_by_plate(db, plate)

        return jsonify(
            {
                "plate": plate,
                "tickets": [
                    {
                        "ticket_id": row["ticket_id"],
                        "plate": row["active_plate"],
                        "speed": round(row["speed"], 2),
                        "speed_limit": row["speed_limit"],
                        "fine": row["fine"],
                        "status": row["status"],
                        "created_at": row["created_at"],
                        "paid_at": row["paid_at"],
                    }
                    for row in tickets
                ],
            }
        ), 200

    @app.get("/api/v1/health")
    def health():
        return jsonify({"status": "ok"}), 200
