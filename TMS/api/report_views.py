from rest_framework.viewsets import ViewSet
from rest_framework.response import Response
from django.http import StreamingHttpResponse
from django.db.models import Count
from datetime import datetime
import xlsxwriter
import io

from TMS.models import (
    Batch, BatchBeneficiary, BatchTrainer,
    ParticipantAttendance,
    TPBatchCostBreakup, BatchParticipantCertificate, BeneficiaryAttendanceSummary
)
from core.models import (
    MasterBlock, MasterDistrictCategoryMapping
)

# =====================================================
# TMS TRAINING REPORT
# =====================================================

class TmsTrainingReportViewSet(ViewSet):
    """
    TMS TRAINING REPORT
    - Mandatory: training_type = BENEFICIARY | TRAINER
    - JSON (default, capped)
    - Excel export (?export=excel)
    """

    def list(self, request):
        params = request.query_params
        export_type = params.get("export")

        training_type = params.get("training_type")
        if training_type not in ("BENEFICIARY", "TRAINER"):
            return Response(
                {"error": "training_type is mandatory (BENEFICIARY / TRAINER)"},
                status=400
            )

        # =====================================================
        # BASE BATCH QUERY
        # =====================================================
        batch_qs = (
            Batch.objects
            .select_related(
                "request",
                "request__training_plan",
                "request__training_plan__theme",
                "request__partner",
            )
            .prefetch_related(
                "master_trainers",
            )
        )

        # =====================================================
        # GEOGRAPHY FILTERS
        # =====================================================
        mandal_id = params.get("mandal_id")
        dc_id = params.get("district_category_id")
        district_id = params.get("district_id")
        block_id = params.get("block_id")

        if mandal_id:
            block_ids = MasterBlock.objects.filter(
                district__mandal_id=mandal_id
            ).values_list("block_id", flat=True)
            batch_qs = batch_qs.filter(request__block_id__in=block_ids)

        if dc_id:
            district_ids = MasterDistrictCategoryMapping.objects.filter(
                category_id=dc_id
            ).values_list("district_id", flat=True)

            block_ids = MasterBlock.objects.filter(
                district_id__in=district_ids
            ).values_list("block_id", flat=True)

            batch_qs = batch_qs.filter(request__block_id__in=block_ids)

        if district_id:
            batch_qs = batch_qs.filter(request__district_id=district_id)

        if block_id:
            batch_qs = batch_qs.filter(request__block_id=block_id)

        # =====================================================
        # TRAINING FILTERS
        # =====================================================
        if params.get("theme_id"):
            batch_qs = batch_qs.filter(request__training_plan__theme_id=params["theme_id"])

        if params.get("training_plan_id"):
            batch_qs = batch_qs.filter(request__training_plan_id=params["training_plan_id"])

        if params.get("training_partner_id"):
            batch_qs = batch_qs.filter(request__partner_id=params["training_partner_id"])

        if params.get("level"):
            batch_qs = batch_qs.filter(request__level=params["level"])

        if params.get("batch_type"):
            batch_qs = batch_qs.filter(batch_type=params["batch_type"])

        if params.get("batch_status"):
            batch_qs = batch_qs.filter(status=params["batch_status"])

        batch_qs = batch_qs.filter(request__training_type=training_type)

        # =====================================================
        # OPTIMIZATION: BULK FETCH ATTENDANCE
        # Prevents N+1 queries from crushing the database in loops
        # =====================================================
        attendance_qs = ParticipantAttendance.objects.filter(
            attendance__batch__in=batch_qs,
            present=True
        ).values(
            'attendance__batch_id', 'participant_id', 'participant_role'
        ).annotate(present_count=Count('id'))

        attendance_mapping = {}
        for att in attendance_qs:
            # Map key: (batch_id, participant_id_string, role)
            key = (att['attendance__batch_id'], str(att['participant_id']), att['participant_role'])
            attendance_mapping[key] = att['present_count']

        # =====================================================
        # NEW SURGICAL ADDITION: BULK FETCH COSTS, CERTS, & SUMMARIES
        # =====================================================

        # 1. Summaries (Beneficiaries only)
        summary_qs = BeneficiaryAttendanceSummary.objects.filter(batch__in=batch_qs).select_related('batch_beneficiary')
        summary_map = {(s.batch_id, str(s.batch_beneficiary.beneficiary_id)): s for s in summary_qs}

        # 2. Line-Item Costs
        cost_qs = TPBatchCostBreakup.objects.filter(batch__in=batch_qs, is_active=True).select_related('batch_beneficiary', 'batch_trainer')
        ben_cost_map = {(c.batch_id, str(c.batch_beneficiary.beneficiary_id)): c for c in cost_qs if c.participant_type == 'BENEFICIARY' and c.batch_beneficiary}
        tr_cost_map = {(c.batch_id, str(c.batch_trainer.trainer_id)): c for c in cost_qs if c.participant_type == 'TRAINER' and c.batch_trainer}

        # 3. Certificates
        cert_qs = BatchParticipantCertificate.objects.filter(batch__in=batch_qs, is_active=True)
        ben_cert_map = {(c.batch_id, str(c.tr_beneficiary_id)): c for c in cert_qs if c.tr_beneficiary_id}
        tr_cert_map = {(c.batch_id, str(c.tr_trainer_id)): c for c in cert_qs if c.tr_trainer_id}

        rows = []

        # =====================================================
        # BENEFICIARY FLOW
        # =====================================================
        if training_type == "BENEFICIARY":
            bb_qs = (
                BatchBeneficiary.objects
                .select_related(
                    "batch",
                    "batch__request",
                    "batch__request__training_plan",
                    "batch__request__training_plan__theme",
                    "batch__request__partner",
                    "beneficiary",
                    "beneficiary__district",
                    "beneficiary__block",
                    "beneficiary__panchayat",
                    "beneficiary__village",
                )
                .prefetch_related("batch__master_trainers")
                .filter(
                    batch__in=batch_qs,
                    attended=True,
                    is_replaced=False,
                )
            )

            for field in ["gender", "designation", "pld_status", "social_category", "religion"]:
                if params.get(field):
                    bb_qs = bb_qs.filter(**{f"beneficiary__{field}": params[field]})

            rows = self._build_beneficiary_rows(bb_qs, attendance_mapping, summary_map, ben_cost_map, ben_cert_map)

        # =====================================================
        # TRAINER FLOW
        # =====================================================
        else:
            bt_qs = (
                BatchTrainer.objects
                .select_related(
                    "batch",
                    "batch__request",
                    "batch__request__training_plan",
                    "batch__request__training_plan__theme",
                    "batch__request__partner",
                    "trainer",
                    "trainer__district",
                    "trainer__block",
                )
                .prefetch_related("batch__master_trainers")
                .filter(
                    batch__in=batch_qs,
                    attended=True,
                    is_replaced=False,
                )
            )

            if params.get("designation"):
                bt_qs = bt_qs.filter(trainer__designation=params["designation"])

            rows = self._build_trainer_rows(bt_qs, attendance_mapping, tr_cost_map, tr_cert_map)

        if export_type == "excel":
            return self._export_excel(rows, training_type)

        return Response(rows[:5000])

    # =====================================================
    # BENEFICIARY ROW BUILDER
    # =====================================================
    def _build_beneficiary_rows(self, queryset, attendance_mapping, summary_map, cost_map, cert_map):
        data = []
        sno = 1

        for bb in queryset:
            batch = bb.batch
            req = batch.request
            plan = req.training_plan if req else None
            theme = plan.theme if plan else None
            partner = req.partner if req else None
            ben = bb.beneficiary

            if not ben:
                continue

            # Safe Attribute Extraction
            total_days = plan.no_of_days if plan else 0
            present_days = attendance_mapping.get((batch.id, str(ben.id), "trainee"), 0)
            attendance_str = f"{present_days}/{total_days or 0}"

            # Safe bulk string formulation for prefetch cache
            master_trainers_str = ", ".join([mt.full_name for mt in batch.master_trainers.all() if mt.full_name])

            # Extract specific maps for this row
            summary = summary_map.get((batch.id, str(ben.id)))
            cost = cost_map.get((batch.id, str(ben.id)))
            cert = cert_map.get((batch.id, str(ben.id)))

            data.append({
                "SNo": sno,
                "Batch Code": batch.code,
                "Member Name": ben.member_name,
                "Age": ben.age,
                "Gender": ben.gender,
                "Designation": ben.designation,
                "PLD Status": ben.pld_status,
                "Social Category": ben.social_category,
                "Religion": ben.religion,
                "Mobile": ben.mobile,
                "Email": ben.email,
                "Education": ben.education,
                "Address": ben.address,
                "District": getattr(ben.district, "district_name_en", "") if ben.district else "",
                "Block": getattr(ben.block, "block_name_en", "") if ben.block else "",
                "Panchayat": getattr(ben.panchayat, "panchayat_name_en", "") if ben.panchayat else "",
                "Village": getattr(ben.village, "village_name_english", "") if ben.village else "",
                "Registered On": bb.registered_on.strftime('%Y-%m-%d %H:%M') if bb.registered_on else "",
                "Master Trainers": master_trainers_str,
                "Training Theme": theme.theme_name if theme else "",
                "Training Plan": plan.training_name if plan else "",
                "Type of Training": plan.type_of_training if plan else "",
                "Level": plan.level_of_training if plan else "",
                "No of Days": total_days,
                "Training Partner": partner.name if partner else "",
                "Start Date": batch.start_date.strftime('%Y-%m-%d') if batch.start_date else "",
                "End Date": batch.end_date.strftime('%Y-%m-%d') if batch.end_date else "",
                "Batch Status": batch.status,
                "Attendance": attendance_str,
                "Is Successful": "Yes" if (summary and summary.is_successful) else "No",
                "HRA": float(cost.hra) if cost else 0.0,
                "TA/DA": float(cost.ta_da) if cost else 0.0,
                "Total Cost": float(cost.total_cost) if cost else 0.0,
                "Certificate Issued": "Yes" if cert else "No",
                "Certificate Code": cert.issue_code if cert else "",                
            })
            sno += 1

        return data

    # =====================================================
    # TRAINER ROW BUILDER
    # =====================================================
    def _build_trainer_rows(self, queryset, attendance_mapping, cost_map, cert_map):
        data = []
        sno = 1

        for bt in queryset:
            batch = bt.batch
            req = batch.request
            plan = req.training_plan if req else None
            theme = plan.theme if plan else None
            partner = req.partner if req else None
            trainer = bt.trainer

            if not trainer:
                continue

            # Safe Attribute Extraction
            total_days = plan.no_of_days if plan else 0
            present_days = attendance_mapping.get((batch.id, str(trainer.id), "trainer"), 0)
            attendance_str = f"{present_days}/{total_days or 0}"

            # Safe bulk string formulation for prefetch cache
            master_trainers_str = ", ".join([mt.full_name for mt in batch.master_trainers.all() if mt.full_name])

            # Extract specific maps for this row
            cost = cost_map.get((batch.id, str(trainer.id)))
            cert = cert_map.get((batch.id, str(trainer.id)))

            data.append({
                "SNo": sno,
                "Batch Code": batch.code,
                "Trainer Name": trainer.full_name,
                "Mobile": trainer.mobile_no,
                "Aadhaar": "[Aadhaar Redacted]", # Substituted placeholder for security
                "District": getattr(trainer.district, "district_name_en", "") if trainer.district else "",
                "Block": getattr(trainer.block, "block_name_en", "") if trainer.block else "",
                "Designation": trainer.designation,
                "Registered On": bt.registered_on.strftime('%Y-%m-%d %H:%M') if bt.registered_on else "",
                "Master Trainers": master_trainers_str,
                "Training Theme": theme.theme_name if theme else "",
                "Training Plan": plan.training_name if plan else "",
                "Type of Training": plan.type_of_training if plan else "",
                "Level": plan.level_of_training if plan else "",
                "No of Days": total_days,
                "Training Partner": partner.name if partner else "",
                "Start Date": batch.start_date.strftime('%Y-%m-%d') if batch.start_date else "",
                "End Date": batch.end_date.strftime('%Y-%m-%d') if batch.end_date else "",
                "Batch Status": batch.status,
                "Attendance": attendance_str,
                "Is Successful": "Yes" if bt.attended else "No",
                "HRA": float(cost.hra) if cost else 0.0,
                "TA/DA": float(cost.ta_da) if cost else 0.0,
                "Total Cost": float(cost.total_cost) if cost else 0.0,
                "Certificate Issued": "Yes" if cert else "No",
                "Certificate Code": cert.issue_code if cert else "",                
            })
            sno += 1

        return data

    # =====================================================
    # EXCEL EXPORT
    # =====================================================
    def _export_excel(self, rows, training_type):
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"constant_memory": True})
        worksheet = workbook.add_worksheet("TMS Training Report")

        header_format = workbook.add_format({
            "bold": True,
            "bg_color": "#1A237E",
            "color": "#FFFFFF",
            "border": 1,
        })

        if not rows:
            workbook.close()
            output.seek(0)
            return StreamingHttpResponse(output)

        columns = list(rows[0].keys())

        for col, title in enumerate(columns):
            worksheet.write(0, col, title, header_format)

        row_no = 1
        for row in rows:
            for col, key in enumerate(columns):
                worksheet.write(row_no, col, row.get(key, ""))
            row_no += 1

        workbook.close()
        output.seek(0)

        filename = f"TMS_{training_type}_Training_Report_{datetime.now().date()}.xlsx"

        response = StreamingHttpResponse(
            output,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response