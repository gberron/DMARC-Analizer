from __future__ import annotations

import gzip
import io
import zipfile
from datetime import datetime
from typing import Iterable
from xml.etree import ElementTree as ET

from .models import Report, ReportRecord, UploadError


def _parse_xml(xml_bytes: bytes, filename: str) -> Report:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:  # pragma: no cover - defensive programming
        raise UploadError(f"No se pudo interpretar el XML en {filename}") from exc

    metadata = root.find("report_metadata") or ET.Element("report_metadata")
    policy = root.find("policy_published") or ET.Element("policy_published")

    def _find_text(parent: ET.Element, path: str) -> str | None:
        element = parent.find(path)
        return element.text if element is not None else None

    def _ts(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.utcfromtimestamp(int(value))
        except ValueError:
            return None

    date_start = _ts(_find_text(metadata, "date_range/begin"))
    date_end = _ts(_find_text(metadata, "date_range/end"))
    if not date_start or not date_end:
        raise UploadError("El informe no contiene un rango de fechas válido", filename)

    report = Report(
        report_id=_find_text(metadata, "report_id") or filename,
        org_name=_find_text(metadata, "org_name"),
        email=_find_text(metadata, "email"),
        extra_contact_info=_find_text(metadata, "extra_contact_info"),
        date_range_start=date_start,
        date_range_end=date_end,
        domain=_find_text(policy, "domain") or "desconocido",
        adkim=_find_text(policy, "adkim"),
        aspf=_find_text(policy, "aspf"),
        p=_find_text(policy, "p"),
        sp=_find_text(policy, "sp"),
        pct=int(_find_text(policy, "pct") or 0),
        filename=filename,
    )

    for record_element in root.findall("record"):
        source_ip = _find_text(record_element, "row/source_ip") or ""
        if not source_ip:
            continue

        record = ReportRecord(
            source_ip=source_ip,
            count=int(_find_text(record_element, "row/count") or 0),
            disposition=_find_text(record_element, "row/policy_evaluated/disposition"),
            dkim_aligned=_find_text(record_element, "row/policy_evaluated/dkim"),
            spf_aligned=_find_text(record_element, "row/policy_evaluated/spf"),
            header_from=_find_text(record_element, "identifiers/header_from"),
            envelope_from=_find_text(record_element, "identifiers/envelope_from"),
            auth_dkim_domain=_find_text(record_element, "auth_results/dkim/domain"),
            auth_spf_domain=_find_text(record_element, "auth_results/spf/domain"),
        )
        report.records.append(record)

    if not report.records:
        raise UploadError("El informe no contiene registros de tráfico", filename)

    return report


def parse_report_file(file_stream: io.BufferedIOBase, filename: str) -> Iterable[Report]:
    lower_name = filename.lower()
    data = file_stream.read()

    if lower_name.endswith(".gz"):
        try:
            data = gzip.decompress(data)
        except OSError as exc:
            raise UploadError("El archivo .gz está dañado o no es válido", filename) from exc
        yield _parse_xml(data, filename)
    elif lower_name.endswith(".zip"):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                for info in zf.infolist():
                    if info.filename.endswith("/"):
                        continue
                    with zf.open(info.filename) as member:
                        yield _parse_xml(member.read(), info.filename)
        except (zipfile.BadZipFile, KeyError) as exc:
            raise UploadError("El archivo .zip está dañado o vacío", filename) from exc
    else:
        yield _parse_xml(data, filename)
