"""
Certificate PDF generator for Pragati Setu TMS.
Generates a Hindi Govt-style certificate for a closed batch.

Dependencies:
  - reportlab  (pip install reportlab)
  - NotoSansDevanagari-Regular.ttf  → {BASE_DIR}/static/fonts/
  - NotoSansDevanagari-Bold.ttf     → {BASE_DIR}/static/fonts/

Usage:
  buffer = generate_batch_certificate_pdf(batch, financial_year, master_user, role_label)
"""

import io
import os

from django.conf import settings
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ─────────────────────────────────────────────────────────────────────────────
# 1.  FONT REGISTRATION  (runs once per process)
# ─────────────────────────────────────────────────────────────────────────────

_FONTS_REGISTERED = False


def _ensure_fonts():
    global _FONTS_REGISTERED
    if _FONTS_REGISTERED:
        return
    font_dir = os.path.join(settings.BASE_DIR, "static", "fonts")
    reg = os.path.join(font_dir, "NotoSansDevanagari-Regular.ttf")
    bold = os.path.join(font_dir, "NotoSansDevanagari-Bold.ttf")
    for path, name in [(reg, "Deva"), (bold, "Deva-Bold")]:
        if not os.path.isfile(path):
            raise RuntimeError(
                f"Required font not found: {path}\n"
                "Download NotoSansDevanagari from https://fonts.google.com/noto/specimen/Noto+Sans+Devanagari "
                f"and place the TTF files in {font_dir}/"
            )
        pdfmetrics.registerFont(TTFont(name, path))
    _FONTS_REGISTERED = True


# ─────────────────────────────────────────────────────────────────────────────
# 2.  COLOR PALETTE  (UP Govt / NIC style)
# ─────────────────────────────────────────────────────────────────────────────

C_NAVY       = colors.HexColor("#1a3a6b")   # Primary deep blue
C_GOLD       = colors.HexColor("#b8860b")   # Accent gold
C_LIGHT_BLUE = colors.HexColor("#eaf0fb")   # Table alt row / card bg
C_BORDER     = colors.HexColor("#2e5da6")   # Border
C_TEXT       = colors.HexColor("#1a1a2e")   # Body text
C_MUTED      = colors.HexColor("#4a5568")   # Muted / footer
C_GREEN_DARK = colors.HexColor("#1a472a")   # Signature stripe
C_WHITE      = colors.white
C_OFF_WHITE  = colors.HexColor("#fafcff")


# ─────────────────────────────────────────────────────────────────────────────
# 3.  STYLE FACTORY
# ─────────────────────────────────────────────────────────────────────────────

def _styles():
    _ensure_fonts()
    return {
        "cert_title": ParagraphStyle(
            "cert_title", fontName="Deva-Bold", fontSize=24,
            leading=30, textColor=C_NAVY, alignment=TA_CENTER, spaceAfter=2,
        ),
        "org_name": ParagraphStyle(
            "org_name", fontName="Deva-Bold", fontSize=10,
            leading=14, textColor=C_GOLD, alignment=TA_CENTER, spaceAfter=1,
        ),
        "sub_title": ParagraphStyle(
            "sub_title", fontName="Deva", fontSize=9,
            leading=13, textColor=C_MUTED, alignment=TA_CENTER, spaceAfter=0,
        ),
        "sender": ParagraphStyle(
            "sender", fontName="Deva", fontSize=10,
            leading=15, textColor=C_TEXT, alignment=TA_LEFT,
        ),
        "sender_bold": ParagraphStyle(
            "sender_bold", fontName="Deva-Bold", fontSize=10,
            leading=15, textColor=C_TEXT, alignment=TA_LEFT,
        ),
        "date_right": ParagraphStyle(
            "date_right", fontName="Deva", fontSize=10,
            leading=14, textColor=C_TEXT, alignment=TA_RIGHT,
        ),
        "subject": ParagraphStyle(
            "subject", fontName="Deva", fontSize=10,
            leading=16, textColor=C_NAVY, alignment=TA_JUSTIFY, spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "body", fontName="Deva", fontSize=10,
            leading=17, textColor=C_TEXT, alignment=TA_JUSTIFY, spaceAfter=5,
        ),
        "section_h": ParagraphStyle(
            "section_h", fontName="Deva-Bold", fontSize=11,
            leading=15, textColor=C_NAVY, spaceAfter=5, spaceBefore=4,
        ),
        "th": ParagraphStyle(
            "th", fontName="Deva-Bold", fontSize=8.5,
            leading=12, textColor=C_WHITE, alignment=TA_CENTER,
        ),
        "td": ParagraphStyle(
            "td", fontName="Deva", fontSize=8.5,
            leading=13, textColor=C_TEXT, alignment=TA_LEFT,
        ),
        "td_c": ParagraphStyle(
            "td_c", fontName="Deva", fontSize=8.5,
            leading=13, textColor=C_TEXT, alignment=TA_CENTER,
        ),
        "sig_title": ParagraphStyle(
            "sig_title", fontName="Deva-Bold", fontSize=9,
            leading=13, textColor=C_WHITE, alignment=TA_CENTER, spaceAfter=6,
        ),
        "sig_line": ParagraphStyle(
            "sig_line", fontName="Deva", fontSize=9,
            leading=14, textColor=C_TEXT, spaceAfter=1,
        ),
        "footer": ParagraphStyle(
            "footer", fontName="Deva", fontSize=8,
            leading=11, textColor=C_MUTED, alignment=TA_CENTER,
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 4.  PAGE CALLBACKS  (watermark + border)
# ─────────────────────────────────────────────────────────────────────────────

def _on_page(canvas_obj, doc):
    _ensure_fonts()
    w, h = A4

    # ── Double border ──────────────────────────────────────────────────────
    m_outer = 10 * mm
    m_inner = 13 * mm
    canvas_obj.saveState()
    canvas_obj.setStrokeColor(C_NAVY)
    canvas_obj.setLineWidth(2.8)
    canvas_obj.rect(m_outer, m_outer, w - 2 * m_outer, h - 2 * m_outer)

    canvas_obj.setStrokeColor(C_GOLD)
    canvas_obj.setLineWidth(0.9)
    canvas_obj.rect(m_inner, m_inner, w - 2 * m_inner, h - 2 * m_inner)
    canvas_obj.restoreState()

    # ── Diagonal watermark ─────────────────────────────────────────────────
    canvas_obj.saveState()
    canvas_obj.setFont("Deva", 58)
    canvas_obj.setFillColor(colors.Color(0.75, 0.82, 0.93, alpha=0.055))
    canvas_obj.translate(w / 2, h / 2)
    canvas_obj.rotate(42)
    canvas_obj.drawCentredString(0, 30, "प्रगति सेतु")
    canvas_obj.drawCentredString(0, -50, "UPSRLM")
    canvas_obj.restoreState()


# ─────────────────────────────────────────────────────────────────────────────
# 5.  TRANSLATION MAPS
# ─────────────────────────────────────────────────────────────────────────────

LEVEL_HI = {
    "BLOCK": "ब्लॉक",
    "DISTRICT": "जिला",
    "STATE": "राज्य",
    "VILLAGE": "ग्राम",
    "SHG": "स्वयं सहायता समूह",
    "CLF": "क्लस्टर स्तर महासंघ (CLF)",
    "BLOCK_DISTRICT": "ब्लॉक / जिला",
    "CMTC/BLOCK": "CMTC / ब्लॉक",
    "WITHIN_STATE": "राज्य के भीतर",
    "OUTSIDE_STATE": "राज्य के बाहर",
}

TYPE_HI = {
    "BENEFICIARY": "लाभार्थी",
    "TRAINER": "मास्टर ट्रेनर",
}


# ─────────────────────────────────────────────────────────────────────────────
# 6.  HELPER BUILDERS
# ─────────────────────────────────────────────────────────────────────────────

def _hr(color=C_GOLD, thickness=1.2, space_before=4, space_after=6):
    return HRFlowable(
        width="100%", thickness=thickness, color=color,
        spaceBefore=space_before, spaceAfter=space_after,
    )


def _beneficiary_table(participants, S):
    cols = [0.8*cm, 4.2*cm, 1*cm, 2.8*cm, 2*cm, 2.4*cm, 1.8*cm, 2.3*cm]
    headers = ["क्र.", "नाम", "आयु", "पदनाम", "PLD स्थिति", "सामाजिक श्रेणी", "धर्म", "मोबाइल"]

    data = [[Paragraph(h, S["th"]) for h in headers]]
    for i, p in enumerate(participants, 1):
        mobile = p.mobile if p.mobile else None
        row = [
            Paragraph(str(i), S["td_c"]),
            Paragraph(p.member_name or "—", S["td"]),
            Paragraph(str(p.age) if p.age else "—", S["td_c"]),
            Paragraph(p.designation or "सदस्य", S["td"]),
            Paragraph(p.pld_status or "—", S["td"]),
            Paragraph(p.social_category or "—", S["td"]),
            Paragraph(p.religion or "—", S["td"]),
            Paragraph(mobile or "—", S["td"]),
        ]
        data.append(row)

    return _styled_table(data, cols)


def _trainer_table(participants, S):
    cols = [0.9*cm, 8.5*cm, 4*cm]
    headers = ["क्र.", "नाम", "मोबाइल"]

    data = [[Paragraph(h, S["th"]) for h in headers]]
    for i, p in enumerate(participants, 1):
        name = p.full_name or (p.trainer.full_name if p.trainer else "—")
        mobile = p.mobile_no or (p.trainer.mobile_no if p.trainer else None) or "—"
        data.append([
            Paragraph(str(i), S["td_c"]),
            Paragraph(name, S["td"]),
            Paragraph(mobile, S["td"]),
        ])

    return _styled_table(data, cols)


def _styled_table(data, col_widths):
    """Build a zebra-striped table with standard govt styling."""
    n_rows = len(data)
    style = [
        # Header row
        ("BACKGROUND", (0, 0), (-1, 0), C_NAVY),
        ("LINEBELOW",  (0, 0), (-1, 0), 1.8, C_GOLD),
        ("BOX",        (0, 0), (-1, -1), 1.5, C_BORDER),
        ("GRID",       (0, 0), (-1, -1), 0.4, colors.HexColor("#c0cfe0")),
        ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 5),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 5),
    ]
    # Zebra rows
    for r in range(1, n_rows):
        bg = C_LIGHT_BLUE if r % 2 == 0 else C_OFF_WHITE
        style.append(("BACKGROUND", (0, r), (-1, r), bg))

    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle(style))
    return t


def _signatory_box(label_text, level_text, S):
    """
    Returns a single signatory cell (Table) with a dark header stripe.
    """
    header_row = [[Paragraph(f"<b>{label_text}</b>", S["sig_title"])]]
    header = Table(header_row, colWidths=["100%"])
    header.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), C_NAVY),
        ("TOPPADDING",    (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
        ("LINEBELOW",     (0, 0), (-1, -1), 1.5, C_GOLD),
    ]))

    lines = [
        header,
        Spacer(1, 6),
        Paragraph(f"स्तर: {level_text}", S["sig_line"]),
        Paragraph("पदनाम: _______________________________", S["sig_line"]),
        Paragraph("कार्यालय: _______________________________", S["sig_line"]),
        Paragraph("निर्गमन तिथि: ____________________________", S["sig_line"]),
        Spacer(1, 1.4 * cm),
        Paragraph("___________________________________", S["sig_line"]),
        Paragraph("अधिकृत हस्ताक्षरकर्ता", S["sig_line"]),
        Paragraph(
            "<font color='#4a5568' size='8'>अधिकृत अधिकारी, UPSRLM / जिला प्रशासन</font>",
            S["sig_line"]
        ),
        Spacer(1, 4),
    ]

    outer = Table([[lines]], colWidths=["100%"])
    outer.setStyle(TableStyle([
        ("BOX",           (0, 0), (-1, -1), 1.2, C_BORDER),
        ("BACKGROUND",    (0, 0), (-1, -1), C_OFF_WHITE),
        ("TOPPADDING",    (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING",   (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
    ]))
    return outer


def _signatories(role_label, S):
    """Returns [Table] with two signatory boxes side by side."""
    if role_label == "bmmu":
        left  = _signatory_box("प्रथम जारीकर्ता", "ब्लॉक स्तर", S)
        right = _signatory_box("द्वितीय जारीकर्ता", "जिला स्तर", S)
    else:  # dmmu / smmu
        left  = _signatory_box("प्रथम जारीकर्ता", "जिला स्तर", S)
        right = _signatory_box("द्वितीय जारीकर्ता", "राज्य स्तर", S)

    sig_table = Table(
        [[left, Spacer(0.4 * cm, 1), right]],
        colWidths=["47%", "6%", "47%"],
    )
    sig_table.setStyle(TableStyle([
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING",    (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("LEFTPADDING",   (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
    ]))
    return sig_table


# ─────────────────────────────────────────────────────────────────────────────
# 7.  MAIN PUBLIC FUNCTION
# ─────────────────────────────────────────────────────────────────────────────

def generate_batch_certificate_pdf(batch, financial_year, master_user, role_label):
    """
    Returns an io.BytesIO PDF buffer.

    Args:
        batch           – Batch instance (fully prefetched)
        financial_year  – str e.g. "2024-25"
        master_user     – MasterUser instance of the requesting officer
        role_label      – "bmmu" | "dmmu" | "smmu"
    """
    _ensure_fonts()
    S = _styles()

    # ── Gather core data ─────────────────────────────────────────────────────
    tr            = batch.request
    plan          = tr.training_plan if tr else None
    theme         = plan.theme if plan else None
    training_type = tr.training_type if tr else "BENEFICIARY"
    level_raw     = tr.level if tr else "BLOCK"
    level_hi      = LEVEL_HI.get(level_raw, level_raw)
    type_hi       = TYPE_HI.get(training_type, training_type)
    no_of_days    = plan.no_of_days if plan else "—"
    theme_name    = theme.theme_name if theme else "—"
    plan_name     = plan.training_name if plan else "—"
    block         = tr.block if tr else None
    district      = tr.district if tr else None
    block_name    = (block.block_name_en or "—") if block else "—"
    district_name = (district.district_name_en or "—") if district else "—"
    start_str     = batch.start_date.strftime("%d/%m/%Y") if batch.start_date else "—"
    end_str       = batch.end_date.strftime("%d/%m/%Y")   if batch.end_date   else "—"
    username      = master_user.username if master_user else "—"

    # Sender location line & geo phrase in body
    if role_label == "bmmu":
        location_line = f"ब्लॉक: {block_name}"
        geo_phrase    = f"ब्लॉक <b>{block_name}</b> में"
    else:
        location_line = f"जिला: {district_name}"
        geo_phrase    = f"जिला <b>{district_name}</b> में"

    # ── Participants ──────────────────────────────────────────────────────────
    if training_type == "BENEFICIARY":
        bbs = (
            batch.beneficiary_participations
            .filter(attendance_summary__is_successful=True, is_active=True)
        )
        participants = [bb.beneficiary for bb in bbs if bb.beneficiary]
    else:
        bts = batch.trainer_participations.filter(attended=True, is_active=True)
        participants = [bt.trainer for bt in bts if bt.trainer]

    total_count = len(participants)

    # ── Master Trainers ───────────────────────────────────────────────────────
    master_trainer_rows = batch.master_trainer_participations.filter(is_active=True)

    # ══════════════════════════════════════════════════════════════════════════
    # BUILD STORY
    # ══════════════════════════════════════════════════════════════════════════
    story = []

    # ── HEADER CARD ───────────────────────────────────────────────────────────
    header_inner = [
        Paragraph("उत्तर प्रदेश राज्य ग्रामीण आजीविका मिशन (UPSRLM)", S["org_name"]),
        Spacer(1, 3),
        Paragraph("प्रमाण पत्र", S["cert_title"]),
        Spacer(1, 2),
        Paragraph("प्रगति सेतु – प्रशिक्षण प्रबंधन प्रणाली", S["sub_title"]),
    ]
    header_table = Table([[header_inner]], colWidths=["100%"])
    header_table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), C_LIGHT_BLUE),
        ("BOX",           (0, 0), (-1, -1), 2, C_NAVY),
        ("LINEBELOW",     (0, 0), (-1, -1), 3, C_GOLD),
        ("TOPPADDING",    (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ("LEFTPADDING",   (0, 0), (-1, -1), 10),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 0.45 * cm))

    # ── SENDER + DATE ─────────────────────────────────────────────────────────
    sender_date = Table(
        [[
            [
                Paragraph("<b>प्रेषक,</b>", S["sender_bold"]),
                Paragraph(username, S["sender"]),
                Paragraph(location_line, S["sender"]),
            ],
            Paragraph(f"<b>दिनांक:</b> {end_str}", S["date_right"]),
        ]],
        colWidths=["65%", "35%"],
    )
    sender_date.setStyle(TableStyle([
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING",    (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("LEFTPADDING",   (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
    ]))
    story.append(sender_date)
    story.append(Spacer(1, 0.2 * cm))
    story.append(_hr(C_BORDER, thickness=0.6))

    # ── SUBJECT ───────────────────────────────────────────────────────────────
    subject = (
        f"<b>विषय:</b> वित्तीय वर्ष <b>{financial_year}</b> के अंतर्गत "
        f"<b>{theme_name}</b> थीम – <b>{plan_name}</b> मॉड्यूल के अंतर्गत "
        f"प्रशिक्षण कराये जाने के संबंध में।"
    )
    story.append(Paragraph(subject, S["subject"]))
    story.append(_hr(C_GOLD, thickness=1.2))

    # ── BODY PARAGRAPHS ───────────────────────────────────────────────────────
    body_paras = [
        (
            f"यह प्रमाणित किया जाता है कि संबंधित प्रतिभागियों ने "
            f"<b>{type_hi}</b> के स्तर <b>{level_hi}</b> के अंतर्गत, "
            f"<b>{plan_name}</b> शीर्षक से आयोजित <b>{no_of_days} दिवसीय</b> "
            f"प्रशिक्षण कार्यक्रम में वित्तीय वर्ष <b>{financial_year}</b> के "
            f"अंतर्गत सफलतापूर्वक सहभागिता की है।"
        ),
        (
            f"उक्त प्रशिक्षण कार्यक्रम का आयोजन <b>{start_str}</b> से "
            f"<b>{end_str}</b> तक {geo_phrase} किया गया।"
        ),
        (
            "यह प्रशिक्षण उत्तर प्रदेश राज्य ग्रामीण आजीविका मिशन (UPSRLM) के "
            "दिशा-निर्देशों के अंतर्गत आयोजित किया गया, जिसमें नेतृत्व क्षमता विकास, "
            "संस्थागत सुदृढ़ीकरण एवं सामुदायिक विकास से संबंधित विषयों पर प्रशिक्षण "
            "प्रदान किया गया।"
        ),
        "प्रशिक्षण के दौरान प्रतिभागियों द्वारा संतोषजनक सहभागिता एवं सक्रिय योगदान किया गया।",
        "यह प्रमाण पत्र प्रशिक्षण में सफल सहभागिता के उपरांत निर्गत किया जा रहा है।",
    ]
    for para in body_paras:
        story.append(Paragraph(para, S["body"]))

    story.append(Spacer(1, 0.2 * cm))

    # ── PARTICIPANT SECTION ───────────────────────────────────────────────────
    story.append(_hr(C_GOLD, thickness=1.2))
    story.append(Paragraph(
        f"<b>कुल प्रतिभागियों की संख्या: {total_count}</b>",
        S["section_h"]
    ))

    if not participants:
        story.append(Paragraph("कोई सफल प्रतिभागी इस बैच में नहीं मिला।", S["body"]))
    elif training_type == "BENEFICIARY":
        story.append(_beneficiary_table(participants, S))
    else:
        story.append(_trainer_table(participants, S))

    story.append(Spacer(1, 0.35 * cm))

    # ── MASTER TRAINERS ───────────────────────────────────────────────────────
    if master_trainer_rows.exists():
        story.append(_hr(C_BORDER, thickness=0.6))
        story.append(Paragraph("<b>प्रशिक्षण बैच के मास्टर ट्रेनर:</b>", S["section_h"]))

        mt_data = [
            [
                Paragraph("क्र.", S["th"]),
                Paragraph("नाम", S["th"]),
                Paragraph("मोबाइल", S["th"]),
                Paragraph("पदनाम", S["th"]),
            ]
        ]
        for idx, bmt in enumerate(master_trainer_rows, 1):
            mt = bmt.master_trainer
            if mt:
                mt_data.append([
                    Paragraph(str(idx), S["td_c"]),
                    Paragraph(mt.full_name or "—", S["td"]),
                    Paragraph(mt.mobile_no or "—", S["td"]),
                    Paragraph(mt.designation or "—", S["td_c"]),
                ])

        if len(mt_data) > 1:
            mt_table = _styled_table(mt_data, [0.8*cm, 6*cm, 4*cm, 2.5*cm])
            story.append(mt_table)

        story.append(Spacer(1, 0.3 * cm))

    # ── SIGNATORY BLOCKS ──────────────────────────────────────────────────────
    story.append(_hr(C_GOLD, thickness=1.5, space_before=6, space_after=10))
    story.append(_signatories(role_label, S))

    # ── FOOTER ────────────────────────────────────────────────────────────────
    story.append(Spacer(1, 0.5 * cm))
    story.append(_hr(C_BORDER, thickness=0.5, space_before=0, space_after=4))
    story.append(Paragraph(
        "प्रगति सेतु – प्रशिक्षण प्रबंधन प्रणाली द्वारा जनरेटेड",
        S["footer"]
    ))
    story.append(Paragraph(
        "प्रेरणा पहल | उत्तर प्रदेश राज्य ग्रामीण आजीविका मिशन (UPSRLM)",
        S["footer"]
    ))

    # ── RENDER ────────────────────────────────────────────────────────────────
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=2.4 * cm,
        rightMargin=2.4 * cm,
        topMargin=2.4 * cm,
        bottomMargin=2.4 * cm,
        title=f"प्रमाण पत्र – बैच {batch.code or batch.id}",
        author="प्रगति सेतु TMS",
        subject=f"वित्तीय वर्ष {financial_year} प्रशिक्षण प्रमाण पत्र",
        creator="Pragati Setu TMS | UPSRLM",
    )
    doc.build(story, onFirstPage=_on_page, onLaterPages=_on_page)
    buf.seek(0)
    return buf