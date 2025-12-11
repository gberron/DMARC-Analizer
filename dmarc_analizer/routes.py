from __future__ import annotations

import io
from datetime import datetime, timedelta
from typing import Any

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from sqlalchemy import func

from . import db
from .emailer import send_scheduled_report
from .models import MailSettings, Report, ReportRecord, ScheduledReport, UploadError
from .parser import parse_report_file

bp = Blueprint("web", __name__)


@bp.route("/")
def index() -> str:
    # últimas cuatro semanas
    now = datetime.utcnow()
    start_range = now - timedelta(days=30)

    domain_summary = (
        db.session.query(Report.domain, func.sum(ReportRecord.count))
        .join(ReportRecord)
        .filter(Report.date_range_start >= start_range)
        .group_by(Report.domain)
        .order_by(func.sum(ReportRecord.count).desc())
        .all()
    )

    disposition_summary = (
        db.session.query(ReportRecord.disposition, func.sum(ReportRecord.count))
        .group_by(ReportRecord.disposition)
        .order_by(func.sum(ReportRecord.count).desc())
        .all()
    )

    latest_reports = (
        Report.query.order_by(Report.date_range_end.desc()).limit(5).all()
    )

    return render_template(
        "index.html",
        domain_summary=domain_summary,
        disposition_summary=disposition_summary,
        latest_reports=latest_reports,
    )


@bp.route("/upload", methods=["GET", "POST"])
def upload() -> str:
    if request.method == "POST":
        file = request.files.get("report")
        if not file or file.filename == "":
            flash("Sube un archivo XML, GZ o ZIP con reportes DMARC.", "warning")
            return redirect(url_for("web.upload"))

        reports_saved = 0
        try:
            for report in parse_report_file(file.stream, file.filename):
                existing = Report.query.filter_by(report_id=report.report_id).first()
                if existing:
                    flash(f"El reporte {report.report_id} ya está cargado.", "info")
                    continue
                db.session.add(report)
                reports_saved += 1
            db.session.commit()
            flash(f"Se cargaron {reports_saved} reportes.", "success")
        except UploadError as exc:
            db.session.rollback()
            current_app.logger.exception("Error al cargar reporte")
            flash(str(exc), "danger")
        except Exception as exc:  # pragma: no cover - defensive logging
            db.session.rollback()
            current_app.logger.exception("Error inesperado")
            flash(f"Error inesperado: {exc}", "danger")

        return redirect(url_for("web.upload"))

    return render_template("upload.html")


@bp.route("/reports")
def reports() -> str:
    domain = request.args.get("domain")
    start_date = request.args.get("start")
    end_date = request.args.get("end")

    query = Report.query.order_by(Report.date_range_start.desc())

    if domain:
        query = query.filter(Report.domain == domain)

    def _parse_date(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            return None

    if start_date:
        start_dt = _parse_date(start_date)
        if start_dt:
            query = query.filter(Report.date_range_start >= start_dt)
    if end_date:
        end_dt = _parse_date(end_date)
        if end_dt:
            query = query.filter(Report.date_range_end <= end_dt)

    available_domains = [item[0] for item in db.session.query(Report.domain).distinct().all()]

    return render_template(
        "reports.html", reports=query.all(), available_domains=available_domains
    )


@bp.route("/reports/<int:report_id>")
def report_detail(report_id: int) -> str:
    report = Report.query.get_or_404(report_id)
    return render_template("report_detail.html", report=report)


@bp.route("/export/csv")
def export_csv() -> Any:
    output = io.StringIO()
    output.write("report_id,org,domain,source_ip,count,disposition,dkim,spf\n")
    rows = (
        db.session.query(
            Report.report_id,
            Report.org_name,
            Report.domain,
            ReportRecord.source_ip,
            ReportRecord.count,
            ReportRecord.disposition,
            ReportRecord.dkim_aligned,
            ReportRecord.spf_aligned,
        )
        .join(ReportRecord)
        .all()
    )
    for row in rows:
        output.write(
            f"{row.report_id},{row.org_name or ''},{row.domain},{row.source_ip},{row.count},{row.disposition or ''},{row.dkim_aligned or ''},{row.spf_aligned or ''}\n"
        )

    return current_app.response_class(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=dmarc-resumen.csv"},
    )


@bp.route("/settings", methods=["GET", "POST"])
def settings() -> str:
    settings = MailSettings.get_or_create()

    if request.method == "POST" and request.form.get("form_type") == "mail":
        settings.mail_server = request.form.get("mail_server") or settings.mail_server
        settings.mail_port = int(request.form.get("mail_port") or settings.mail_port or 0) or None
        settings.connection_type = request.form.get("connection_type") or settings.connection_type
        settings.username = request.form.get("username") or settings.username
        password = request.form.get("password")
        if password:
            settings.password = password
        settings.use_ssl = bool(request.form.get("use_ssl"))
        settings.smtp_server = request.form.get("smtp_server") or settings.smtp_server
        settings.smtp_port = int(request.form.get("smtp_port") or settings.smtp_port or 0) or None
        settings.use_tls = bool(request.form.get("use_tls"))
        settings.sender = request.form.get("sender") or settings.sender
        db.session.commit()
        flash("Configuración de correo guardada.", "success")
        return redirect(url_for("web.settings"))

    schedules = ScheduledReport.query.order_by(ScheduledReport.created_at.desc()).all()
    return render_template("settings.html", settings=settings, schedules=schedules)


@bp.route("/settings/schedule", methods=["POST"])
def create_schedule() -> str:
    name = request.form.get("name")
    recipient = request.form.get("recipient")
    days_back = int(request.form.get("days_back") or 7)
    frequency = request.form.get("frequency") or "semanal"
    domain_filter = request.form.get("domain_filter") or None

    if not name or not recipient:
        flash("Completa el nombre y el destinatario.", "warning")
        return redirect(url_for("web.settings"))

    schedule = ScheduledReport(
        name=name,
        recipient=recipient,
        days_back=days_back,
        frequency=frequency,
        domain_filter=domain_filter,
    )
    db.session.add(schedule)
    db.session.commit()
    flash("Reporte programado creado.", "success")
    return redirect(url_for("web.settings"))


@bp.route("/settings/schedule/<int:schedule_id>/delete", methods=["POST"])
def delete_schedule(schedule_id: int) -> str:
    schedule = ScheduledReport.query.get_or_404(schedule_id)
    db.session.delete(schedule)
    db.session.commit()
    flash("Reporte programado eliminado.", "info")
    return redirect(url_for("web.settings"))


@bp.route("/settings/schedule/<int:schedule_id>/send", methods=["POST"])
def send_schedule_now(schedule_id: int) -> str:
    schedule = ScheduledReport.query.get_or_404(schedule_id)
    settings = MailSettings.get_or_create()
    try:
        message = send_scheduled_report(schedule, settings)
        flash(message, "success")
    except Exception as exc:  # pragma: no cover - defensive logging
        current_app.logger.exception("No se pudo enviar el correo")
        flash(str(exc), "danger")
        db.session.rollback()
    return redirect(url_for("web.settings"))
