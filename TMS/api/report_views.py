from rest_framework.viewsets import ViewSet
from rest_framework.response import Response
from django.http import StreamingHttpResponse
from django.db.models import F, Q, Count
from datetime import datetime
import xlsxwriter
import io

from TMS.models import (
    Batch, BatchBeneficiary, BatchTrainer,
    BatchAttendance, ParticipantAttendance
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
                "beneficiary_participations__beneficiary",
                "trainer_participations__trainer",
                "attendances__participant_records",
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
            batch_qs = batch_qs.filter(
                request__training_plan__theme_id=params["theme_id"]
            )

        if params.get("training_plan_id"):
            batch_qs = batch_qs.filter(
                request__training_plan_id=params["training_plan_id"]
            )

        if params.get("training_partner_id"):
            batch_qs = batch_qs.filter(
                request__partner_id=params["training_partner_id"]
            )

        if params.get("level"):
            batch_qs = batch_qs.filter(request__level=params["level"])

        if params.get("batch_type"):
            batch_qs = batch_qs.filter(batch_type=params["batch_type"])

        if params.get("batch_status"):
            batch_qs = batch_qs.filter(status=params["batch_status"])

        # =====================================================
        # TRAINING TYPE (MANDATORY)
        # =====================================================
        batch_qs = batch_qs.filter(request__training_type=training_type)

        rows = []

        # =====================================================
        # BENEFICIARY FLOW
        # =====================================================
        if training_type == "BENEFICIARY":
            bb_qs = (
                BatchBeneficiary.objects
                .select_related(
                    "batch",
                    "beneficiary",
                    "beneficiary__district",
                    "beneficiary__block",
                    "beneficiary__panchayat",
                    "beneficiary__village",
                )
                .filter(
                    batch__in=batch_qs,
                    attended=True,
                    is_replaced=False,
                )
            )

            # Participant filters
            for field in [
                "gender",
                "designation",
                "pld_status",
                "social_category",
                "religion",
            ]:
                if params.get(field):
                    bb_qs = bb_qs.filter(**{f"beneficiary__{field}": params[field]})

            rows = self._build_beneficiary_rows(bb_qs)

        # =====================================================
        # TRAINER FLOW
        # =====================================================
        else:
            bt_qs = (
                BatchTrainer.objects
                .select_related(
                    "batch",
                    "trainer",
                    "trainer__district",
                    "trainer__block",
                )
                .filter(
                    batch__in=batch_qs,
                    attended=True,
                    is_replaced=False,
                )
            )

            if params.get("designation"):
                bt_qs = bt_qs.filter(trainer__designation=params["designation"])

            rows = self._build_trainer_rows(bt_qs)

        # =====================================================
        # EXPORT / RESPONSE
        # =====================================================
        if export_type == "excel":
            return self._export_excel(rows, training_type)

        return Response(rows[:5000])  # safety cap

    # =====================================================
    # BENEFICIARY ROW BUILDER
    # =====================================================
    def _build_beneficiary_rows(self, queryset):
        data = []
        sno = 1

        for bb in queryset:
            batch = bb.batch
            plan = batch.request.training_plan
            attendance = self._attendance_string(
                batch, bb.beneficiary.id, "trainee", plan.no_of_days
            )

            data.append({
                "SNo": sno,
                "Batch Code": batch.code,
                "Member Name": bb.beneficiary.member_name,
                "Age": bb.beneficiary.age,
                "Gender": bb.beneficiary.gender,
                "Designation": bb.beneficiary.designation,
                "PLD Status": bb.beneficiary.pld_status,
                "Social Category": bb.beneficiary.social_category,
                "Religion": bb.beneficiary.religion,
                "Mobile": bb.beneficiary.mobile,
                "Email": bb.beneficiary.email,
                "Education": bb.beneficiary.education,
                "Address": bb.beneficiary.address,
                "District": getattr(bb.beneficiary.district, "district_name_en", ""),
                "Block": getattr(bb.beneficiary.block, "block_name_en", ""),
                "Panchayat": getattr(bb.beneficiary.panchayat, "panchayat_name_en", ""),
                "Village": getattr(bb.beneficiary.village, "village_name_english", ""),
                "Registered On": bb.registered_on,
                "Master Trainers": ", ".join(
                    batch.master_trainers.values_list("full_name", flat=True)
                ),
                "Training Theme": plan.theme.theme_name if plan.theme else "",
                "Training Plan": plan.training_name,
                "Type of Training": plan.type_of_training,
                "Level": plan.level_of_training,
                "No of Days": plan.no_of_days,
                "Training Partner": batch.request.partner.name if batch.request.partner else "",
                "Start Date": batch.start_date,
                "End Date": batch.end_date,
                "Batch Status": batch.status,
                "Attendance": attendance,
            })
            sno += 1

        return data

    # =====================================================
    # TRAINER ROW BUILDER
    # =====================================================
    def _build_trainer_rows(self, queryset):
        data = []
        sno = 1

        for bt in queryset:
            batch = bt.batch
            plan = batch.request.training_plan
            attendance = self._attendance_string(
                batch, bt.trainer_id, "trainer", plan.no_of_days
            )

            data.append({
                "SNo": sno,
                "Batch Code": batch.code,
                "Trainer Name": bt.trainer.full_name,
                "Mobile": bt.trainer.mobile_no,
                "Aadhaar": bt.trainer.aadhaar_no,
                "District": getattr(bt.trainer.district, "district_name_en", ""),
                "Block": getattr(bt.trainer.block, "block_name_en", ""),
                "Designation": bt.trainer.designation,
                "Registered On": bt.registered_on,
                "Master Trainers": ", ".join(
                    batch.master_trainers.values_list("full_name", flat=True)
                ),
                "Training Theme": plan.theme.theme_name if plan.theme else "",
                "Training Plan": plan.training_name,
                "Type of Training": plan.type_of_training,
                "Level": plan.level_of_training,
                "No of Days": plan.no_of_days,
                "Training Partner": batch.request.partner.name if batch.request.partner else "",
                "Start Date": batch.start_date,
                "End Date": batch.end_date,
                "Batch Status": batch.status,
                "Attendance": attendance,
            })
            sno += 1

        return data

    # =====================================================
    # ATTENDANCE CALCULATOR
    # =====================================================
    def _attendance_string(self, batch, participant_id, role, total_days):
        present_days = ParticipantAttendance.objects.filter(
            attendance__batch=batch,
            participant_id=str(participant_id),
            participant_role=role,
            present=True,
        ).count()

        return f"{present_days}/{total_days or 0}"

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
