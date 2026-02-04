# LDMS/api/report_views.py
from rest_framework.viewsets import ViewSet
from django.http import StreamingHttpResponse
from rest_framework.response import Response
from django.db.models import F
from datetime import datetime
import xlsxwriter
import io

from LDMS.models import recorded_benefs
from core.models import MasterBlock, MasterDistrictCategoryMapping


class RecordedBeneficiaryReportViewSet(ViewSet):
    """
    REPORT API for Recorded Beneficiaries
    - JSON response (default)
    - Excel export when ?export=excel
    """

    def list(self, request):
        params = request.query_params
        export_type = params.get("export")

        qs = (
            recorded_benefs.objects
            .select_related(
                "district_id",
                "block_id",
                "panchayat_id",
                "village_id",
                "support_bucket__department",
                "support_bucket__scheme",
                "support_bucket__bucket_type",
            )
            .prefetch_related(
                "support_bucket__trainingsupport_set",
                "support_bucket__bucket_approval_set",
            )
            .filter(
                support_bucket__bucket_approval__approval_status="APPROVED"
            )
        )

        # =====================================================
        # GEOGRAPHY FILTERS
        # =====================================================
        mandal_id = params.get("mandal_id")
        dc_id = params.get("dc_id")
        district_id = params.get("district_id")
        block_id = params.get("block_id")
        panchayat_id = params.get("panchayat_id")

        if mandal_id:
            block_ids = MasterBlock.objects.filter(
                district__mandal_id=mandal_id
            ).values_list("block_id", flat=True)
            qs = qs.filter(block_id__in=block_ids)

        if dc_id:
            district_ids = MasterDistrictCategoryMapping.objects.filter(
                category_id=dc_id
            ).values_list("district_id", flat=True)

            block_ids = MasterBlock.objects.filter(
                district_id__in=district_ids
            ).values_list("block_id", flat=True)

            qs = qs.filter(block_id__in=block_ids)

        if district_id:
            qs = qs.filter(district_id=district_id)

        if block_id:
            qs = qs.filter(block_id=block_id)

        if panchayat_id:
            qs = qs.filter(panchayat_id=panchayat_id)

        # =====================================================
        # DEPARTMENT / SCHEME
        # =====================================================
        if params.get("department_id"):
            qs = qs.filter(support_bucket__department_id=params["department_id"])

        if params.get("scheme_id"):
            qs = qs.filter(support_bucket__scheme_id=params["scheme_id"])

        if params.get("scope"):
            qs = qs.filter(support_bucket__scheme__scope__icontains=params["scope"])

        if params.get("funding"):
            qs = qs.filter(support_bucket__scheme__funding__icontains=params["funding"])

        if params.get("contact_point"):
            qs = qs.filter(
                support_bucket__scheme__contact_point__icontains=params["contact_point"]
            )

        # =====================================================
        # BENEFICIARY FILTERS
        # =====================================================
        for field in [
            "pld_status",
            "designation",
            "gender",
            "religion",
            "marital_status",
            "social_category",
        ]:
            if params.get(field):
                qs = qs.filter(**{field: params[field]})

        # =====================================================
        # FINAL VALUES
        # =====================================================
        values_qs = qs.values(
            "pld_status",
            "member_name",
            "lokos_shg_code",
            "lokos_member_code",
            "designation",
            "mobile",
            "age",
            "gender",
            "religion",
            "marital_status",
            "father_husband_name",
            "social_category",
            "education",
            "address",
            district_name_en=F("district_id__district_name_en"),
            block_name_en=F("block_id__block_name_en"),
            panchayat_name_en=F("panchayat_id__panchayat_name_en"),
            village_name_english=F("village_id__village_name_english"),
            department_name=F("support_bucket__department__name"),
            scheme_name=F("support_bucket__scheme__name"),
            scheme_code=F("support_bucket__scheme__code"),
            bucket_type=F("support_bucket__bucket_type__bucket_type"),
            benefit_name=F("support_bucket__benefit_name"),
            benefit_amount=F("support_bucket__benefit_amount"),
            benefit_description=F("support_bucket__benefit_description"),
            training_theme=F(
                "support_bucket__trainingsupport__training_theme__theme_name"
            ),
            training_plan=F(
                "support_bucket__trainingsupport__training_plan__training_name"
            ),
            approval_date=F("support_bucket__bucket_approval__approval_date"),
            approved_by=F(
                "support_bucket__bucket_approval__approved_by__username"
            ),
        )

        # =====================================================
        # 🟢 EXCEL EXPORT
        # =====================================================
        if export_type == "excel":
            return self._export_excel(values_qs)

        # Default JSON (small data only)
        return Response(list(values_qs[:5000]))  # safety cap

    # =====================================================
    # EXCEL STREAMER
    # =====================================================
    def _export_excel(self, queryset):
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"constant_memory": True})
        worksheet = workbook.add_worksheet("Recorded Beneficiaries")

        header_format = workbook.add_format({
            "bold": True,
            "bg_color": "#C62828",
            "color": "#FFFFFF",
            "border": 1,
        })

        columns = [
            ("pld_status", "Is PLD"),
            ("member_name", "SHG Member Name"),
            ("lokos_shg_code", "SHG Code"),
            ("lokos_member_code", "SHG Member Code"),
            ("designation", "Designation"),
            ("mobile", "Phone No"),
            ("age", "Age"),
            ("gender", "Gender"),
            ("religion", "Religion"),
            ("marital_status", "Marital Status"),
            ("father_husband_name", "Relation Name"),
            ("social_category", "Social Category"),
            ("education", "Education"),
            ("address", "Address"),
            ("district_name_en", "District"),
            ("block_name_en", "Block"),
            ("panchayat_name_en", "Panchayat"),
            ("village_name_english", "Village"),
            ("department_name", "Department"),
            ("scheme_name", "Scheme"),
            ("scheme_code", "Scheme Code"),
            ("bucket_type", "Support Bucket"),
            ("benefit_name", "Benefit"),
            ("benefit_amount", "Amount"),
            ("benefit_description", "Description"),
            ("training_theme", "Training Theme"),
            ("training_plan", "Training Plan"),
            ("approval_date", "Approval Date"),
            ("approved_by", "Approved By"),
        ]

        # Header
        for col, (_, title) in enumerate(columns):
            worksheet.write(0, col, title, header_format)

        row = 1
        for record in queryset.iterator(chunk_size=5000):
            for col, (key, _) in enumerate(columns):
                worksheet.write(row, col, record.get(key) or "")
            row += 1

        workbook.close()
        output.seek(0)

        filename = f"LDMS_Recorded_Beneficiaries_{datetime.now().date()}.xlsx"

        response = StreamingHttpResponse(
            output,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response
