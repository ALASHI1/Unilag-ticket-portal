from flask import Flask

from .config import Config
from .db import init_db
from .routes import register_routes


def create_app(test_config=None):
    app = Flask(__name__, template_folder="templates", static_folder="../static")
    app.config.from_object(Config())

    if test_config:
        app.config.update(test_config)

    init_db(app)
    register_routes(app)
    return app
