import sqlite3


def get_db_connection(app):
    connection = sqlite3.connect(app.config["DB_PATH"])
    connection.row_factory = sqlite3.Row
    return connection


def init_db(app):
    app.config["DATA_DIR"].mkdir(parents=True, exist_ok=True)
    app.config["UPLOAD_DIR"].mkdir(parents=True, exist_ok=True)

    with get_db_connection(app) as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS vehicle_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                node_id TEXT NOT NULL,
                raw_plate TEXT,
                normalized_plate TEXT,
                plate_hash TEXT,
                image_path TEXT NOT NULL,
                timestamp REAL NOT NULL,
                doppler_frequency REAL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tracking_buffer (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                normalized_plate TEXT NOT NULL,
                image_path TEXT NOT NULL,
                entry_time REAL NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS violations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id TEXT NOT NULL UNIQUE,
                plate_hash TEXT NOT NULL,
                active_plate TEXT NOT NULL,
                entry_time REAL NOT NULL,
                exit_time REAL NOT NULL,
                speed REAL NOT NULL,
                speed_limit REAL NOT NULL,
                status TEXT NOT NULL,
                fine INTEGER NOT NULL,
                evidence_entry_path TEXT,
                evidence_exit_path TEXT,
                created_at TEXT NOT NULL,
                paid_at TEXT
            );

            CREATE TABLE IF NOT EXISTS payment_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id TEXT NOT NULL,
                plate TEXT NOT NULL,
                email TEXT NOT NULL,
                provider TEXT NOT NULL,
                reference TEXT NOT NULL UNIQUE,
                amount INTEGER NOT NULL,
                status TEXT NOT NULL,
                authorization_url TEXT,
                access_code TEXT,
                gateway_response TEXT,
                created_at TEXT NOT NULL,
                paid_at TEXT,
                FOREIGN KEY (ticket_id) REFERENCES violations(ticket_id)
            );
            """
        )
