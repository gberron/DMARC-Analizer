from __future__ import annotations

import smtplib
import ssl
from datetime import datetime, timedelta
from email.message import EmailMessage

from sqlalchemy import func

from . import db
from .models import MailSettings, Report, ReportRecord, ScheduledReport


def _build_summary(schedule: ScheduledReport) -> tuple[str, int]:
    start_date = datetime.utcnow() - timedelta(days=schedule.days_back or 7)
    record_query = db.session.query(
        ReportRecord.disposition, func.sum(ReportRecord.count)
    ).join(Report)
    report_query = Report.query.filter(Report.date_range_start >= start_date)

    if schedule.domain_filter:
        record_query = record_query.filter(Report.domain == schedule.domain_filter)
        report_query = report_query.filter(Report.domain == schedule.domain_filter)

    record_query = (
        record_query.filter(Report.date_range_start >= start_date)
        .group_by(ReportRecord.disposition)
        .order_by(func.sum(ReportRecord.count).desc())
    )

    disposition_rows = record_query.all()
    report_count = report_query.count()

    lines = [
        f"Reporte programado: {schedule.name}",
        f"Rango: últimos {schedule.days_back} días",  # pragma: no cover - string formatting
        f"Filtro de dominio: {schedule.domain_filter or 'todos'}",
        f"Total de reportes: {report_count}",
        "",
        "Resumen por disposición:",
    ]

    if disposition_rows:
        for disposition, total in disposition_rows:
            label = disposition or "desconocida"
            lines.append(f"- {label}: {total}")
    else:
        lines.append("Sin registros en el rango indicado.")

    return "\n".join(lines), report_count


def _build_message(schedule: ScheduledReport, settings: MailSettings) -> EmailMessage:
    body, _ = _build_summary(schedule)
    msg = EmailMessage()
    msg["Subject"] = f"Reporte DMARC - {schedule.name}"
    msg["From"] = settings.sender or settings.username or "dmarc@example.com"
    msg["To"] = schedule.recipient
    msg.set_content(body)
    return msg


def send_scheduled_report(schedule: ScheduledReport, settings: MailSettings) -> str:
    if not settings.mail_server:
        raise ValueError("Configura el servidor de correo antes de enviar reportes.")

    message = _build_message(schedule, settings)
    host = settings.smtp_server or settings.mail_server
    port = settings.smtp_port or (465 if settings.use_ssl else 587)

    if settings.use_ssl:
        context = ssl.create_default_context()
        server = smtplib.SMTP_SSL(host, port, context=context)
    else:
        server = smtplib.SMTP(host, port)
        if settings.use_tls:
            server.starttls()

    with server:
        if settings.username and settings.password:
            server.login(settings.username, settings.password)
        server.send_message(message)

    schedule.last_sent_at = datetime.utcnow()
    db.session.commit()
    return f"Correo enviado a {schedule.recipient} con el resumen programado."
