from __future__ import annotations

import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate


db = SQLAlchemy()
migrate = Migrate()


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=False)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev"),
        SQLALCHEMY_DATABASE_URI=os.environ.get(
            "DATABASE_URL", f"sqlite:///{os.path.join(app.root_path, '..', 'data', 'dmarc.db')}"
        ),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )

    if test_config:
        app.config.update(test_config)

    db.init_app(app)
    migrate.init_app(app, db)

    from . import routes  # noqa: WPS433

    app.register_blueprint(routes.bp)

    with app.app_context():
        db.create_all()

    @app.cli.command("send-scheduled")
    def send_scheduled() -> None:
        """Envía todos los correos programados usando la configuración almacenada."""

        from .emailer import send_scheduled_report
        from .models import MailSettings, ScheduledReport

        settings = MailSettings.get_or_create()
        schedules = ScheduledReport.query.all()
        for schedule in schedules:
            send_scheduled_report(schedule, settings)

    return app
