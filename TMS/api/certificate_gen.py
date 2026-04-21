import io
from django.template.loader import render_to_string
from weasyprint import HTML, CSS

def generate_batch_certificate_pdf(batch, financial_year, master_user, role_label):
    """
    Drop-in replacement for the ReportLab generator using WeasyPrint.
    Perfectly renders Hindi Devanagari ligatures and matras.
    """
    
    # 1. Gather all the exact same data
    tr = batch.request
    plan = tr.training_plan if tr else None
    theme = plan.theme if plan else None
    training_type = tr.training_type if tr else "BENEFICIARY"
    
    LEVEL_HI = {"BLOCK": "ब्लॉक", "DISTRICT": "जिला", "STATE": "राज्य", "VILLAGE": "ग्राम"}
    TYPE_HI = {"BENEFICIARY": "लाभार्थी", "TRAINER": "मास्टर ट्रेनर"}
    PLAN_TYPE_HI = {
        "RES": "आवासीय",
        "NON RES": "गैर-आवासीय",
        "OTHER": "अन्य",
    }
    
    level_hi = LEVEL_HI.get(tr.level if tr else "BLOCK", tr.level if tr else "BLOCK")
    type_hi = TYPE_HI.get(training_type, training_type)
    plan_type_hi = PLAN_TYPE_HI.get(plan.type_of_training if plan else None, "—")
    
    # Participant Logic (With Attendance Percentage added)
    participants = []
    if training_type == "BENEFICIARY":
        # select_related का उपयोग करके attendance_summary को भी साथ में फेच करें
        bbs = batch.beneficiary_participations.select_related('beneficiary', 'attendance_summary').filter(
            attendance_summary__is_successful=True, 
            is_active=True
        )
        for bb in bbs:
            if bb.beneficiary:
                # डायनामिक रूप से उपस्थिति प्रतिशत जोड़ें
                bb.beneficiary.attendance_pct = bb.attendance_summary.attendance_percentage if hasattr(bb, 'attendance_summary') else 0
                participants.append(bb.beneficiary)
    else:
        bts = batch.trainer_participations.select_related('trainer').filter(attended=True, is_active=True)
        for bt in bts:
            if bt.trainer:
                # ट्रेनर्स के लिए केवल attend=True होता है, इसलिए उन्हें डिफ़ॉल्ट 100% दिया गया है
                bt.trainer.attendance_pct = 100
                participants.append(bt.trainer)

    master_trainers = batch.master_trainer_participations.filter(is_active=True)

    # 2. Build Context for HTML
    context = {
        'batch': batch,
        'financial_year': financial_year,
        'username': master_user.username if master_user else "—",
        'role_label': role_label,
        'level_hi': level_hi,
        'type_hi': type_hi,
        'theme_name': theme.theme_name if theme else "—",
        'plan_name': plan.training_name if plan else "—",
        'plan_type_hi': plan_type_hi,
        'no_of_days': plan.no_of_days if plan else "—",
        'start_str': batch.start_date.strftime("%d/%m/%Y") if batch.start_date else "—",
        'end_str': batch.end_date.strftime("%d/%m/%Y") if batch.end_date else "—",
        'block_name': tr.block.block_name_en if (tr and tr.block) else "—",
        'district_name': tr.district.district_name_en if (tr and tr.district) else "—",
        'participants': participants,
        'training_type': training_type,
        'master_trainers': [mt.master_trainer for mt in master_trainers if mt.master_trainer],
    }

    # 3. Render HTML string
    html_string = render_to_string('tms/pdf/certificate_template.html', context)

    # 4. Generate PDF buffer using WeasyPrint
    pdf_buffer = io.BytesIO()
    HTML(string=html_string).write_pdf(pdf_buffer)
    pdf_buffer.seek(0)
    
    return pdf_buffer