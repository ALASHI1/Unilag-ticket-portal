import base64
import hashlib
import json
import re
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

try:
    from PIL import Image, ImageOps
except ImportError:  # pragma: no cover
    Image = None
    ImageOps = None

try:
    import pytesseract
except ImportError:  # pragma: no cover
    pytesseract = None


PLATE_PATTERN = re.compile(r"[^A-Z0-9]")
NODE_ENTRY = {"A", "ENTRY", "NODE_A"}
NODE_EXIT = {"B", "EXIT", "NODE_B"}
NODE_GATE = {"C", "GATE", "NODE_C"}


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def normalize_plate(plate_text):
    if not plate_text:
        return ""
    return PLATE_PATTERN.sub("", str(plate_text).upper()).strip()


def hash_plate(plate):
    return hashlib.sha256(f"unilag::{plate}".encode("utf-8")).hexdigest()


def levenshtein_distance(left, right):
    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)

    previous_row = list(range(len(right) + 1))
    for i, left_char in enumerate(left, start=1):
        current_row = [i]
        for j, right_char in enumerate(right, start=1):
            insertions = previous_row[j] + 1
            deletions = current_row[j - 1] + 1
            substitutions = previous_row[j - 1] + (left_char != right_char)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]


def parse_timestamp(raw_timestamp):
    if raw_timestamp is None or raw_timestamp == "":
        return datetime.now(timezone.utc).timestamp()
    return float(raw_timestamp)


def classify_node(node_id):
    normalized = str(node_id or "").strip().upper()
    if normalized in NODE_ENTRY:
        return "entry"
    if normalized in NODE_EXIT:
        return "exit"
    if normalized in NODE_GATE:
        return "gate"
    raise ValueError(f"Unsupported node_id '{node_id}'")


def save_image(app, payload, files):
    upload_dir = app.config["UPLOAD_DIR"]

    if "plate_image" in files:
        image_file = files["plate_image"]
        extension = Path(image_file.filename or "capture.jpg").suffix or ".jpg"
        filename = f"{uuid.uuid4().hex}{extension.lower()}"
        output_path = upload_dir / filename
        image_file.save(output_path)
        return output_path

    image_b64 = payload.get("plate_image_base64")
    if not image_b64:
        raise ValueError("No image payload supplied")

    if "," in image_b64:
        image_b64 = image_b64.split(",", 1)[1]

    image_bytes = base64.b64decode(image_b64)
    filename = f"{uuid.uuid4().hex}.jpg"
    output_path = upload_dir / filename
    output_path.write_bytes(image_bytes)
    return output_path


def preprocess_image(image_path):
    if Image is None or ImageOps is None:
        return image_path

    image = Image.open(image_path)
    grayscale = ImageOps.grayscale(image)
    thresholded = grayscale.point(lambda pixel: 255 if pixel > 128 else 0)
    processed_path = image_path.with_name(f"{image_path.stem}_processed{image_path.suffix}")
    thresholded.save(processed_path)
    return processed_path


def run_ocr(image_path):
    processed_path = preprocess_image(image_path)
    if pytesseract is None or Image is None:
        return normalize_plate(Path(image_path).stem)

    text = pytesseract.image_to_string(
        Image.open(processed_path),
        config="--psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
    )
    return normalize_plate(text)


def extract_plate(image_path, plate_override=None):
    if plate_override:
        return normalize_plate(plate_override)
    return run_ocr(image_path)


def compute_average_speed_kmh(distance_meters, entry_time, exit_time):
    elapsed_seconds = max(exit_time - entry_time, 0.001)
    meters_per_second = distance_meters / elapsed_seconds
    return meters_per_second * 3.6


def paystack_initialize_transaction(*, secret_key, base_url, email, amount_kobo, reference, callback_url, metadata):
    payload = json.dumps(
        {
            "email": email,
            "amount": str(amount_kobo),
            "reference": reference,
            "callback_url": callback_url,
            "metadata": metadata,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        urllib.parse.urljoin(base_url.rstrip("/") + "/", "transaction/initialize"),
        data=payload,
        headers={
            "Authorization": f"Bearer {secret_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "UNILAG-Traffic-Monitor/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        raise ValueError(body or str(exc)) from exc


def paystack_verify_transaction(*, secret_key, base_url, reference):
    request = urllib.request.Request(
        urllib.parse.urljoin(base_url.rstrip("/") + "/", f"transaction/verify/{reference}"),
        headers={
            "Authorization": f"Bearer {secret_key}",
            "Accept": "application/json",
            "User-Agent": "UNILAG-Traffic-Monitor/1.0",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        raise ValueError(body or str(exc)) from exc
