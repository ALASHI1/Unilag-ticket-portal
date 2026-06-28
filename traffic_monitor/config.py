from pathlib import Path
import os


class Config:
    BASE_DIR = Path(__file__).resolve().parent.parent
    DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE_DIR))).resolve()
    STATIC_DIR = BASE_DIR / "static"
    UPLOAD_DIR = DATA_DIR / "uploads"
    DB_PATH = DATA_DIR / "traffic_monitor.db"
    SECTION_DISTANCE_METERS = 80.0
    DEFAULT_SPEED_LIMIT_KMH = 30.0
    DEFAULT_FINE = 5000
    ACTIVE_TRACKING_WINDOW_SECONDS = 300
    SECRET_KEY = os.getenv("SECRET_KEY", "unilag-speed-enforcement-dev")
    APP_BASE_URL = os.getenv("APP_BASE_URL", "http://127.0.0.1:5000")
    PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY", "")
    PAYSTACK_PUBLIC_KEY = os.getenv("PAYSTACK_PUBLIC_KEY", "")
    PAYSTACK_BASE_URL = os.getenv("PAYSTACK_BASE_URL", "https://api.paystack.co")
    ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "change-me")
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = os.getenv("SESSION_COOKIE_SAMESITE", "Lax")
    SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "0") == "1"
