# UNILAG Traffic Monitoring Backend

Flask backend for the UNILAG intelligent traffic monitoring project, covering section-control speed enforcement, ticket creation, and gate re-entry checks.

## Implemented features

- Flask app factory in `traffic_monitor/`
- `POST /api/v1/log_event`
  - Accepts `multipart/form-data` with `plate_image`
  - Accepts JSON with `plate_image_base64`
  - Optional `plate_text_override` for development and testing without live OCR
- `GET /api/v1/check_ticket?plate=ABC123XY`
- `POST /api/v1/tickets/<ticket_id>/pay`
- `GET /api/v1/tickets`
- `GET /api/v1/health`
- `GET /` dashboard for ticket and system status
- `GET /` public offender portal with plate search
- `GET /admin` admin dashboard

## Project structure

- `app.py`: development entrypoint
- `wsgi.py`: production entrypoint for `gunicorn`
- `traffic_monitor/config.py`: app configuration
- `traffic_monitor/db.py`: SQLite setup
- `traffic_monitor/services.py`: OCR, matching, speed, and node helpers
- `traffic_monitor/routes.py`: API and dashboard routes
- `traffic_monitor/templates/dashboard.html`: admin dashboard
- `tests/test_app.py`: basic end-to-end backend tests
- `deploy/`: sample Raspberry Pi `systemd` and `nginx` configs
- `esp32/`: Arduino-style node request examples for Nodes A, B, and C
- `render.yaml`: internet test deployment blueprint for Render

## Current behavior

- Stores uploaded images in `static/uploads/`
- Runs grayscale + threshold preprocessing before OCR
- Uses Levenshtein tolerance `<= 1` for Node B matching and gate checks
- Computes section speed across an `80 m` zone
- Uses a `30 km/h` enforcement speed limit by default
- Creates unpaid tickets for overspeed events
- Blocks re-entry for vehicles with unpaid tickets
- Marks tickets as paid through the API
- Supports Paystack payment initialization and callback verification for the public portal

## Run

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python app.py
```

## Test

```bash
python3 -m unittest discover -s tests
```

## Raspberry Pi deployment outline

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
gunicorn --workers 2 --bind 0.0.0.0:5000 wsgi:app
```

Deployment samples are provided in:

- `deploy/unilag-traffic-monitor.service`
- `deploy/nginx-unilag-traffic-monitor.conf`
- `deploy/RENDER.md`

The SQLite database file is created automatically as `traffic_monitor.db`.

## Paystack configuration

Set these environment variables before running the app:

```bash
export PAYSTACK_SECRET_KEY=sk_test_xxx
export PAYSTACK_PUBLIC_KEY=pk_test_xxx
export APP_BASE_URL=http://127.0.0.1:5000
```

For internet deployment, set `APP_BASE_URL` to your public HTTPS domain.

The public portal now uses Paystack's server-side transaction flow:

- initialize transaction from the backend
- redirect the user to Paystack checkout
- handle callback on the backend
- verify the reference with Paystack before marking the ticket paid

Source used for implementation:

- Paystack Transactions API: initialize transaction and verify transaction

## Internet test deployment

For a quick public test deployment, use Render with:

- `render.yaml`
- a persistent disk mounted at `/opt/render/project/src/storage`
- `DATA_DIR=/opt/render/project/src/storage`

This keeps both `traffic_monitor.db` and uploaded files out of the ephemeral filesystem.

## OCR environment status

Local verification confirmed:

- Python dependencies install correctly in `.venv`
- backend tests pass
- `tesseract` is available on the machine and `pytesseract` can see version `5.5.1`
