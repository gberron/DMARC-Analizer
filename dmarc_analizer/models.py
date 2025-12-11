from __future__ import annotations

from datetime import datetime
from typing import Optional

from . import db


class Report(db.Model):
    __tablename__ = "reports"

    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(db.String(255), unique=True, nullable=False)
    org_name = db.Column(db.String(255), nullable=True)
    email = db.Column(db.String(255), nullable=True)
    extra_contact_info = db.Column(db.String(255), nullable=True)
    date_range_start = db.Column(db.DateTime, nullable=False)
    date_range_end = db.Column(db.DateTime, nullable=False)
    domain = db.Column(db.String(255), nullable=False)
    adkim = db.Column(db.String(10), nullable=True)
    aspf = db.Column(db.String(10), nullable=True)
    p = db.Column(db.String(50), nullable=True)
    sp = db.Column(db.String(50), nullable=True)
    pct = db.Column(db.Integer, nullable=True)
    filename = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    records = db.relationship("ReportRecord", backref="report", lazy=True, cascade="all, delete-orphan")

    @property
    def summary_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for record in self.records:
            disposition = record.disposition or "unknown"
            counts[disposition] = counts.get(disposition, 0) + record.count
        return counts


class ReportRecord(db.Model):
    __tablename__ = "report_records"

    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(db.Integer, db.ForeignKey("reports.id"), nullable=False)
    source_ip = db.Column(db.String(45), nullable=False)
    count = db.Column(db.Integer, nullable=False)
    disposition = db.Column(db.String(50), nullable=True)
    dkim_aligned = db.Column(db.String(10), nullable=True)
    spf_aligned = db.Column(db.String(10), nullable=True)
    header_from = db.Column(db.String(255), nullable=True)
    envelope_from = db.Column(db.String(255), nullable=True)
    auth_dkim_domain = db.Column(db.String(255), nullable=True)
    auth_spf_domain = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def alignment_status(self) -> str:
        dkim = self.dkim_aligned or "?"
        spf = self.spf_aligned or "?"
        return f"dkim:{dkim} / spf:{spf}"

    @property
    def identifier(self) -> str:
        return self.header_from or self.envelope_from or "Unknown"


class UploadError(Exception):
    def __init__(self, message: str, filename: Optional[str] = None) -> None:
        super().__init__(message)
        self.filename = filename


class MailSettings(db.Model):
    __tablename__ = "mail_settings"

    id = db.Column(db.Integer, primary_key=True)
    mail_server = db.Column(db.String(255), nullable=True)
    mail_port = db.Column(db.Integer, nullable=True)
    connection_type = db.Column(db.String(20), nullable=True)  # IMAP o POP3
    username = db.Column(db.String(255), nullable=True)
    password = db.Column(db.String(255), nullable=True)
    use_ssl = db.Column(db.Boolean, default=True)
    smtp_server = db.Column(db.String(255), nullable=True)
    smtp_port = db.Column(db.Integer, nullable=True)
    use_tls = db.Column(db.Boolean, default=True)
    sender = db.Column(db.String(255), nullable=True)

    @classmethod
    def get_or_create(cls) -> "MailSettings":
        settings = cls.query.first()
        if not settings:
            settings = cls()
            db.session.add(settings)
            db.session.commit()
        return settings


class ScheduledReport(db.Model):
    __tablename__ = "scheduled_reports"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    recipient = db.Column(db.String(255), nullable=False)
    domain_filter = db.Column(db.String(255), nullable=True)
    days_back = db.Column(db.Integer, default=7)
    frequency = db.Column(db.String(20), default="semanal")
    last_sent_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
