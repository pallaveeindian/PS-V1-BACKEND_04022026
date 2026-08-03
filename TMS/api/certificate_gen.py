import io
from django.conf import settings
from pathlib import Path
from django.template.loader import render_to_string
from weasyprint import HTML, CSS

left_logo = Path(settings.BASE_DIR) / "templates" / "tms" / "logos" / "left.png"
right_logo = Path(settings.BASE_DIR) / "templates" / "tms" / "logos" / "right.png"

def generate_batch_certificate_pdf(batch, financial_year, master_user, role_label):
    """
    Drop-in replacement for the ReportLab generator using WeasyPrint.
    Perfectly renders Hindi Devanagari ligatures and matras.
    Includes comprehensive attendance metrics and participant costings.
    """
    
    # 1. Gather all the exact same data natively from Batch (No TR Dependency)
    plan = batch.training_plan
    theme = plan.theme if plan else None
    training_type = batch.participant_type or "BENEFICIARY"
    
    LEVEL_HI = {
        "BLOCK": "ब्लॉक", "DISTRICT": "जिला", "STATE": "राज्य", 
        "VILLAGE": "ग्राम", "SHG": "एसएचजी", "CLF": "सीएलएफ"
    }
    TYPE_HI = {"BENEFICIARY": "लाभार्थी", "TRAINER": "मास्टर ट्रेनर", "STAFF": "स्टाफ"}
    PLAN_TYPE_HI = {
        "RES": "आवासीय",
        "NON RES": "गैर-आवासीय",
        "OTHER": "अन्य",
    }
    
    raw_level = plan.level_of_training if plan else "BLOCK"
    level_hi = LEVEL_HI.get(raw_level, raw_level)
    type_hi = TYPE_HI.get(training_type, training_type)
    plan_type_hi = PLAN_TYPE_HI.get(plan.type_of_training if plan else None, "—")
    
    # --- SURGICAL ADDITION: Map Line-Item Costs to Participants ---
    # Try fetching prefetched list, otherwise evaluate query
    cost_breakups = getattr(batch, 'participant_costs', None)
    if cost_breakups is not None:
        cost_list = cost_breakups.all() if hasattr(cost_breakups, 'all') else cost_breakups
    else:
        cost_list = batch.participant_costs.filter(is_active=True)

    cost_map = {}
    for c in cost_list:
        key = c.batch_beneficiary_id or c.batch_trainer_id or c.batch_staff_id
        if key:
            cost_map[key] = c

    # Participant Logic (With Attendance Percentage & Costings added)
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
                bb.beneficiary.attendance_pct = bb.attendance_summary.attendance_percentage if hasattr(bb, 'attendance_summary') and bb.attendance_summary else 0
                
                # --- SURGICAL ADDITION: Inject Costings ---
                cost_record = cost_map.get(bb.id)
                bb.beneficiary.hra = cost_record.ta_da if cost_record else 0
                bb.beneficiary.total_cost = cost_record.total_cost if cost_record else 0
                
                participants.append(bb.beneficiary)
                
    elif training_type == "TRAINER":
        # SURGICAL FIX: Unified Trainer logic utilizing attendance_summary
        bts = batch.trainer_participations.select_related('trainer', 'attendance_summary').filter(
            attendance_summary__is_successful=True, 
            is_active=True
        )
        for bt in bts:
            if bt.trainer:
                bt.trainer.attendance_pct = bt.attendance_summary.attendance_percentage if hasattr(bt, 'attendance_summary') and bt.attendance_summary else 0
                
                cost_record = cost_map.get(bt.id)
                bt.trainer.hra = cost_record.ta_da if cost_record else 0
                bt.trainer.total_cost = cost_record.total_cost if cost_record else 0
                
                participants.append(bt.trainer)
                
    elif training_type == "STAFF":
        # SURGICAL ADDITION: Staff Participant Logic
        # Added 'staff__staff' to select_related to efficiently fetch the underlying StaffProfile
        bss = batch.staff_participations.select_related('staff__staff', 'attendance_summary').filter(
            attendance_summary__is_successful=True, 
            is_active=True
        )
        for bs in bss:
            if bs.staff:
                bs.staff.attendance_pct = bs.attendance_summary.attendance_percentage if hasattr(bs, 'attendance_summary') and bs.attendance_summary else 0
                
                cost_record = cost_map.get(bs.id)
                bs.staff.hra = cost_record.hra if cost_record else 0
                bs.staff.ta_da = cost_record.ta_da if cost_record else 0
                bs.staff.total_cost = cost_record.total_cost if cost_record else 0
                
                # SURGICAL FIX: Map deep nested StaffProfile fields to the TRStaff object for the template
                staff_profile = bs.staff.staff
                bs.staff.employee_id = staff_profile.employee_id if staff_profile and staff_profile.employee_id else "—"
                bs.staff.mobile = staff_profile.mobile if staff_profile and staff_profile.mobile else "—"
                bs.staff.designation = bs.staff.designation or "—"
                
                participants.append(bs.staff)

    master_trainers = batch.master_trainer_participations.select_related('master_trainer').filter(is_active=True)

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
        'block_name': batch.block.block_name_en if batch.block else "—",
        'district_name': batch.district.district_name_en if batch.district else "—",
        'participants': participants,
        'training_type': training_type,
        'master_trainers': [mt.master_trainer for mt in master_trainers if mt.master_trainer],
        'left_logo': left_logo.as_uri(),
        'right_logo': right_logo.as_uri(),
    }

    # 3. Render HTML string
    html_string = render_to_string('tms/pdf/certificate_template.html', context)

    # 4. Generate PDF buffer using WeasyPrint
    pdf_buffer = io.BytesIO()
    HTML(string=html_string).write_pdf(pdf_buffer)
    pdf_buffer.seek(0)
    
    return pdf_buffer