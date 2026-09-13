"""Print-ready A4 discharge card PDF, mirroring the paper template:
blank top space (for pre-printed letterhead stationery), patient/
admission grid, examination findings, clinical sections, medicine
tables, advice, follow-up, warning signs, signature block."""
from __future__ import annotations

import io
from datetime import date, datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .. import config, models

# Blank space left at the top of the card for pre-printed letterhead
# stationery (sized to the old letterhead block, plus a little, plus 20%
# extra breathing room for taller letterheads).
LETTERHEAD_SPACE = 25 * mm * 1.2

SIGNS = (
    ("Pallor", "pallor"),
    ("Icterus", "icterus"),
    ("Rash", "rash"),
    ("Cyanosis", "cyanosis"),
    ("Meningeal signs", "meningeal_signs"),
    ("Dehydration signs", "dehydration_signs"),
)
SYSTEMS = (
    ("Throat findings", "throat_findings"),
    ("Respiratory system", "respiratory_system"),
    ("CVS system", "cvs_system"),
    ("Abdominal examination", "abdominal_exam"),
    ("CNS system", "cns_system"),
)

INK = colors.HexColor("#1c1c1f")
MUTED = colors.HexColor("#55555c")
LINE = colors.HexColor("#9a9a97")
LIGHT_LINE = colors.HexColor("#c8c8c5")

STYLES = {
    "doc_title": ParagraphStyle("doc_title", fontName="Helvetica-Bold", fontSize=12, leading=15,
                                alignment=1, textColor=INK, spaceBefore=4),
    "label": ParagraphStyle("label", fontName="Helvetica-Bold", fontSize=8.5, leading=11, textColor=MUTED),
    "value": ParagraphStyle("value", fontName="Helvetica", fontSize=10, leading=13, textColor=INK),
    "section": ParagraphStyle("section", fontName="Helvetica-Bold", fontSize=10.5, leading=13,
                              textColor=INK, spaceBefore=8, spaceAfter=2),
    "subhead": ParagraphStyle("subhead", fontName="Helvetica-Bold", fontSize=9, leading=12,
                              textColor=MUTED, spaceBefore=6, spaceAfter=2),
    "body": ParagraphStyle("body", fontName="Helvetica", fontSize=10, leading=13.5, textColor=INK),
    "table_head": ParagraphStyle("table_head", fontName="Helvetica-Bold", fontSize=8.5, leading=11, textColor=MUTED),
    "table_cell": ParagraphStyle("table_cell", fontName="Helvetica", fontSize=9.5, leading=12, textColor=INK),
    "sign": ParagraphStyle("sign", fontName="Helvetica", fontSize=10, leading=13, alignment=2, textColor=INK),
}


def _fmt_dt(value: datetime | None) -> str:
    return value.strftime("%d %b %Y, %I:%M %p") if value else ""


def _fmt_d(value: date | None) -> str:
    return value.strftime("%d %b %Y") if value else ""


def _esc(text: str | None) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _kv(label: str, value: str | None) -> list:
    return [Paragraph(label.upper(), STYLES["label"]), Paragraph(_esc(value) or "-", STYLES["value"])]


def _draft_watermark(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica-Bold", 90)
    canvas.setFillColor(colors.Color(0.86, 0.86, 0.86, alpha=0.5))
    canvas.translate(A4[0] / 2, A4[1] / 2)
    canvas.rotate(45)
    canvas.drawCentredString(0, 0, "DRAFT")
    canvas.restoreState()


def _tx_table(items: list[models.TreatmentItem], width: float) -> Table:
    head = ["", "Medicine", "Dose", "Route", "Frequency", "Duration", "Instructions"]
    rows = [[Paragraph(h.upper(), STYLES["table_head"]) for h in head]]
    for i, item in enumerate(items, start=1):
        rows.append([
            Paragraph(str(i), STYLES["table_cell"]),
            Paragraph(_esc(item.drug), STYLES["table_cell"]),
            Paragraph(_esc(item.dose), STYLES["table_cell"]),
            Paragraph(_esc(item.route), STYLES["table_cell"]),
            Paragraph(_esc(item.frequency), STYLES["table_cell"]),
            Paragraph(_esc(item.duration), STYLES["table_cell"]),
            Paragraph(_esc(item.instructions), STYLES["table_cell"]),
        ])
    widths = [w * width for w in (0.05, 0.28, 0.11, 0.09, 0.14, 0.12, 0.21)]
    table = Table(rows, colWidths=widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, 0), 0.7, LINE),
        ("LINEBELOW", (0, 1), (-1, -1), 0.3, LIGHT_LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    return table


def render_discharge_pdf(record: models.DischargeRecord) -> bytes:
    clinic = config.clinic_info()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=16 * mm,
        title=f"Discharge card - {record.patient.name}",
        author=clinic.get("clinic_name", ""),
    )
    width = doc.width
    story = []

    # --- Blank space for pre-printed letterhead stationery
    story.append(Spacer(1, LETTERHEAD_SPACE))
    story.append(Paragraph("DISCHARGE CARD", STYLES["doc_title"]))
    story.append(Spacer(1, 6))

    # --- Patient / admission grid
    patient = record.patient
    sex_age = " / ".join(x for x in (patient.sex, record.age_at_admission) if x)
    grid_rows = [
        [_kv("Patient name", patient.name), _kv("Sex / Age", sex_age), _kv("IPD number", record.ipd_number)],
        [_kv("Admitted on", _fmt_dt(record.admission_date)),
         _kv("Discharged on", _fmt_dt(record.discharge_date)),
         _kv("Ward", record.ward)],
        [_kv("Weight", record.weight), _kv("Height", record.height), _kv("", "")],
    ]
    info = Table(grid_rows, colWidths=[width / 3.0] * 3)
    info.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOX", (0, 0), (-1, -1), 0.7, LINE),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, LIGHT_LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(info)

    # --- Clinical narrative: diagnosis first, then history
    if record.diagnosis:
        story.append(Paragraph("Diagnosis", STYLES["section"]))
        story.append(Paragraph(_esc(record.diagnosis).replace("\n", "<br/>"), STYLES["body"]))
    if record.history:
        story.append(Paragraph("History", STYLES["section"]))
        story.append(Paragraph(_esc(record.history).replace("\n", "<br/>"), STYLES["body"]))

    # --- Examination findings: vitals row, "Others" row (signs), then
    # Systemic examination (open-ended per-system findings)
    story.append(Paragraph("Examination findings", STYLES["section"]))
    vitals = [
        ("Temp", record.temperature), ("Pulse", record.pulse), ("BP", record.bp),
        ("Resp rate", record.resp_rate), ("SpO2", record.spo2),
    ]
    vit_cells = [_kv(label, value) for label, value in vitals]
    vit = Table([vit_cells], colWidths=[width / 5.0] * 5)
    vit.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOX", (0, 0), (-1, -1), 0.7, LINE),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, LIGHT_LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(vit)

    # All six signs print as pertinent negatives: ticked = Yes, else No.
    story.append(Paragraph("Others", STYLES["subhead"]))
    sign_cells = [
        _kv(label, "Yes" if getattr(record, attr) == "yes" else "No")
        for label, attr in SIGNS
    ]
    signs = Table([sign_cells], colWidths=[width / 6.0] * 6)
    signs.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOX", (0, 0), (-1, -1), 0.7, LINE),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, LIGHT_LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(signs)

    exam_lines = [(label, getattr(record, attr)) for label, attr in SYSTEMS]
    exam_lines.append(("General examination", record.examination_findings))
    if any(text for _, text in exam_lines):
        story.append(Paragraph("Systemic examination", STYLES["subhead"]))
        for label, text in exam_lines:
            if text:
                story.append(Paragraph(
                    f"<b>{label}:</b> {_esc(text)}".replace("\n", "<br/>"),
                    ParagraphStyle("exam_line", parent=STYLES["body"], spaceBefore=3),
                ))

    # --- Remaining clinical sections
    sections = [
        ("Investigations", record.investigations),
        ("Course in hospital", record.course_in_hospital),
    ]
    for title, text in sections:
        if text:
            story.append(Paragraph(title, STYLES["section"]))
            story.append(Paragraph(_esc(text).replace("\n", "<br/>"), STYLES["body"]))

    hospital_items = [t for t in record.treatment_items if t.category == "hospital"]
    discharge_items = [t for t in record.treatment_items if t.category == "discharge"]
    if hospital_items:
        story.append(Paragraph("Treatment given in hospital", STYLES["section"]))
        story.append(_tx_table(hospital_items, width))
    if discharge_items:
        story.append(Paragraph("Medicines on discharge", STYLES["section"]))
        story.append(_tx_table(discharge_items, width))

    if record.advice:
        story.append(Paragraph("Advice", STYLES["section"]))
        story.append(Paragraph(_esc(record.advice).replace("\n", "<br/>"), STYLES["body"]))

    follow_up = " ".join(
        x for x in (_fmt_d(record.follow_up_date), _esc(record.follow_up_notes)) if x
    )
    if follow_up:
        story.append(Paragraph("Follow-up", STYLES["section"]))
        story.append(Paragraph(follow_up, STYLES["body"]))

    # --- Warning signs (always printed; text editable in data/clinic.json)
    warning_text = clinic.get("warning_signs") or config.DEFAULT_WARNING_SIGNS
    head_part, sep, rest = warning_text.partition(":")
    if sep:
        warning_markup = f"<b>{_esc(head_part)}:</b>{_esc(rest)}"
    else:
        warning_markup = _esc(warning_text)
    warning = Table(
        [[Paragraph(warning_markup, ParagraphStyle(
            "warning", parent=STYLES["body"], fontSize=9, leading=12))]],
        colWidths=[width],
    )
    warning.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.7, LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(Spacer(1, 10))
    story.append(warning)

    # --- Signature (kept together so the line never separates from the name)
    doctor = record.doctor_name or clinic.get("doctor_name") or ""
    story.append(KeepTogether([
        Spacer(1, 26),
        HRFlowable(width=60 * mm, thickness=0.7, color=INK, hAlign="RIGHT"),
        Spacer(1, 2),
        Paragraph(_esc(doctor) if doctor else "Signature", STYLES["sign"]),
    ]))

    decorate = _draft_watermark if record.status == "draft" else (lambda c, d: None)
    doc.build(story, onFirstPage=decorate, onLaterPages=decorate)
    return buffer.getvalue()
