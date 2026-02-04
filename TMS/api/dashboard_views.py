# TMS/api/dashboard_views.py

from datetime import date, datetime

from django.db.models import Count, Q
from django.shortcuts import get_object_or_404

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from drf_yasg.utils import swagger_auto_schema

from core.models import MasterUser, MasterDistrict, MasterBlock
from core.api.lookups import parse_csv_param

from TMS import models as tms_models
from TMS.api.serializers import (
    TrainingPlanSerializer,
    TrainingRequestSerializer,
    BatchSerializer,
    TrainingPartnerSerializer,
)


# -------------------------------------------------------------------
# Helper – role name
# -------------------------------------------------------------------

def _user_role(user: MasterUser) -> str:
    try:
        role = getattr(user, "role", None)
        if role and getattr(role, "name", None):
            return role.name.lower()
    except Exception:
        pass
    return ""


# -------------------------------------------------------------------
# 2. BMMU – Dashboard & Trainings list
# -------------------------------------------------------------------

class BmmuDashboardAPIView(APIView):
    """
    BMMU dashboard – summary of requests & upcoming batches in user's block.
    """
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="BMMU Dashboard",
        tags=["TMS – BMMU"],
        manual_parameters=[],
        responses={200: "Dashboard payload"},
    )
    def get(self, request):
        role = _user_role(request.user)
        if role != "bmmu":
            return Response(
                {"ok": False, "error": "Not authorized for BMMU dashboard."},
                status=403,
            )

        # Scope by block via BmmuBlockAssignment
        block_id = None
        try:
            assign = (
                tms_models.BmmuBlockAssignment.objects.filter(user_id=request.user.id)
                .select_related("block")
                .first()
            )
            if assign and assign.block_id:
                block_id = assign.block_id
        except Exception:
            block_id = None

        # Training requests for this block
        tr_qs = tms_models.TrainingRequest.objects.all().select_related("training_plan")
        if block_id:
            tr_qs = tr_qs.filter(block_id=block_id)

        status_param = request.query_params.get("status")
        if status_param:
            tr_qs = tr_qs.filter(status__iexact=status_param)

        kpi = {
            "total_requests": tr_qs.count(),
            "pending": tr_qs.filter(status__iexact="PENDING").count(),
            "ongoing": tr_qs.filter(status__iexact="ONGOING").count(),
            "completed": tr_qs.filter(status__iexact="COMPLETED").count(),
        }

        # Batches in this block (via block_id on TrainingRequest)
        batch_qs = tms_models.Batch.objects.filter(request__in=tr_qs).select_related(
            "training_plan", "centre"
        )

        today = date.today()
        upcoming = batch_qs.filter(start_date__gte=today).order_by("start_date")[:20]

        return Response(
            {
                "ok": True,
                "scope": {"block_id": block_id},
                "kpi": kpi,
                "training_requests": TrainingRequestSerializer(tr_qs, many=True).data,
                "upcoming_batches": BatchSerializer(upcoming, many=True).data,
            }
        )


class BmmuTrainingsListAPIView(APIView):
    """
    List of batches visible to BMMU user (by block).
    """
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="BMMU – Trainings list",
        tags=["TMS – BMMU"],
        manual_parameters=[],
        responses={200: "List of Batch"},
    )
    def get(self, request):
        role = _user_role(request.user)
        if role != "bmmu":
            return Response(
                {"ok": False, "error": "Not authorized for BMMU trainings list."},
                status=403,
            )

        block_id = None
        try:
            assign = (
                tms_models.BmmuBlockAssignment.objects.filter(user_id=request.user.id)
                .select_related("block")
                .first()
            )
            if assign and assign.block_id:
                block_id = assign.block_id
        except Exception:
            block_id = None

        qs = tms_models.Batch.objects.all().select_related(
            "training_plan", "request", "centre"
        )
        if block_id:
            qs = qs.filter(request__block_id=block_id)

        status_param = request.query_params.get("status")
        if status_param:
            qs = qs.filter(status__iexact=status_param)

        return Response({"ok": True, "results": BatchSerializer(qs, many=True).data})


class BmmuRequestDetailAPIView(APIView):
    """
    BMMU view – TrainingRequest + its batches.
    """
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="BMMU – TrainingRequest detail",
        tags=["TMS – BMMU"],
        responses={200: "Request + batches"},
    )
    def get(self, request, request_id):
        role = _user_role(request.user)
        if role != "bmmu":
            return Response(
                {"ok": False, "error": "Not authorized for BMMU request detail."},
                status=403,
            )

        tr = get_object_or_404(
            tms_models.TrainingRequest.objects.select_related("training_plan"),
            pk=request_id,
        )

        batches = tms_models.Batch.objects.filter(request=tr)

        return Response(
            {
                "ok": True,
                "request": TrainingRequestSerializer(tr).data,
                "batches": BatchSerializer(batches, many=True).data,
            }
        )


class BmmuBatchViewAPIView(APIView):
    """
    BMMU view – Batch + basic participant info.
    """
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="BMMU – Batch detail",
        tags=["TMS – BMMU"],
        responses={200: "Batch + participants"},
    )
    def get(self, request, batch_id):
        role = _user_role(request.user)
        if role != "bmmu":
            return Response(
                {"ok": False, "error": "Not authorized for BMMU batch view."},
                status=403,
            )

        batch = get_object_or_404(
            tms_models.Batch.objects.select_related(
                "training_plan", "centre", "request"
            ),
            pk=batch_id,
        )

        ben_qs = tms_models.BatchBeneficiary.objects.filter(batch=batch).select_related(
            "beneficiary"
        )
        beneficiaries = [
            {
                "id": bb.id,
                "member_code": getattr(bb.beneficiary, "lokos_member_code", None),
                "member_name": getattr(bb.beneficiary, "member_name", None),
            }
            for bb in ben_qs
        ]

        return Response(
            {
                "ok": True,
                "batch": BatchSerializer(batch).data,
                "beneficiaries": beneficiaries,
            }
        )


class BmmuBatchAttendanceDateAPIView(APIView):
    """
    BMMU view – attendance of a batch on a specific date.
    """
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="BMMU – Batch attendance by date",
        tags=["TMS – BMMU"],
        manual_parameters=[],
        responses={200: "Attendance records"},
    )
    def get(self, request, batch_id):
        role = _user_role(request.user)
        if role != "bmmu":
            return Response(
                {"ok": False, "error": "Not authorized for BMMU attendance view."},
                status=403,
            )

        batch = get_object_or_404(tms_models.Batch, pk=batch_id)
        date_str = request.query_params.get("date")

        if not date_str:
            return Response(
                {"ok": False, "error": "date query param is required."}, status=400
            )

        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return Response({"ok": False, "error": "Invalid date format."}, status=400)

        attendance = tms_models.BatchAttendance.objects.filter(
            batch=batch, date=dt
        ).first()
        if not attendance:
            return Response({"ok": True, "records": []})

        records = [
            {
                "participant_id": r.participant_id,
                "participant_name": r.participant_name,
                "participant_role": r.participant_role,
                "present": r.present,
            }
            for r in attendance.participant_records.all()
        ]

        return Response(
            {
                "ok": True,
                "date": dt,
                "records": records,
            }
        )


# -------------------------------------------------------------------
# 6. SMMU – Analytics, Filters, Targets & Requests
# -------------------------------------------------------------------

class SmmuDashboardAPIView(APIView):
    """
    SMMU dashboard:
    - TrainingPlans where user is theme_expert.
    - Batches for those plans.
    - Simple status-wise chart.
    """
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="SMMU Dashboard",
        tags=["TMS – SMMU"],
        responses={200: "Dashboard payload"},
    )
    def get(self, request):
        role = _user_role(request.user)
        if role != "smmu":
            return Response(
                {"ok": False, "error": "Not authorized for SMMU dashboard."},
                status=403,
            )

        plans = tms_models.TrainingPlan.objects.filter(theme__expert=request.user)
        plan_ids = list(plans.values_list("id", flat=True))
        batches = tms_models.Batch.objects.filter(request__training_plan_id__in=plan_ids)

        status_counts = (
            batches.values("status")
            .annotate(count=Count("id"))
            .order_by("status")
        )
        chart_labels = [row["status"] or "UNKNOWN" for row in status_counts]
        chart_values = [row["count"] for row in status_counts]

        return Response(
            {
                "ok": True,
                "plans": TrainingPlanSerializer(plans, many=True).data,
                "batches": BatchSerializer(batches, many=True).data,
                "chart": {
                    "labels": chart_labels,
                    "values": chart_values,
                },
            }
        )


class SmmuTrainingRequestsAPIView(APIView):
    """
    SMMU view – batches mapped to modules where user is theme expert.
    """
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="SMMU – Requests (via batches)",
        tags=["TMS – SMMU"],
        responses={200: "List of batches"},
    )
    def get(self, request):
        role = _user_role(request.user)
        if role != "smmu":
            return Response(
                {"ok": False, "error": "Not authorized for SMMU requests."},
                status=403,
            )

        plans = tms_models.TrainingPlan.objects.filter(theme__expert=request.user)
        plan_ids = list(plans.values_list("id", flat=True))

        qs = tms_models.Batch.objects.filter(request__training_plan_id__in=plan_ids)
        status_param = request.query_params.get("status")

        if status_param:
            qs = qs.filter(status__iexact=status_param)
        else:
            qs = qs.filter(status__in=["PENDING", "PROPOSED", "DRAFT", "ONGOING"])

        return Response(
            {"ok": True, "results": BatchSerializer(qs.order_by("-start_date"), many=True).data}
        )


class SmmuRequestDetailAPIView(APIView):
    """
    SMMU view – Batch + partner + centre submissions + beneficiaries.
    """
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="SMMU – Request detail (batch view)",
        tags=["TMS – SMMU"],
        responses={200: "Batch + partner + submissions + beneficiaries"},
    )
    def get(self, request, batch_id):
        role = _user_role(request.user)
        if role != "smmu":
            return Response(
                {"ok": False, "error": "Not authorized for SMMU request detail."},
                status=403,
            )

        batch = get_object_or_404(
            tms_models.Batch.objects.select_related(
                "request", "request__training_plan", "partner", "centre"
            ),
            pk=batch_id,
        )

        submissions = []
        partner = getattr(batch, "partner", None)
        if partner:
            submissions = tms_models.TrainingPartnerSubmission.objects.filter(
                partner=partner
            ).order_by("-id")[:12]

        beneficiaries = tms_models.BatchBeneficiary.objects.filter(
            batch=batch
        ).select_related("beneficiary")

        bene_list = [
            {
                "member_code": getattr(b.beneficiary, "lokos_member_code", None),
                "member_name": getattr(b.beneficiary, "member_name", None),
            }
            for b in beneficiaries
        ]

        return Response(
            {
                "ok": True,
                "batch": BatchSerializer(batch).data,
                "partner": TrainingPartnerSerializer(partner).data if partner else None,
                "submissions": [
                    {
                        "id": s.id,
                        "category": s.category,
                        "file": s.file.url if s.file else None,
                        "notes": s.notes,
                    }
                    for s in submissions
                ],
                "beneficiaries": bene_list,
            }
        )

    @swagger_auto_schema(
        operation_summary="SMMU – approve / reject / revert batch",
        tags=["TMS – SMMU"],
        request_body=None,
        responses={200: "New status"},
    )
    def post(self, request, batch_id):
        """
        POST actions:
          { "action": "approve" }
          { "action": "reject" }
          { "action": "revert", "status": "PENDING" }
        """
        role = _user_role(request.user)
        if role != "smmu":
            return Response(
                {"ok": False, "error": "Not authorized for SMMU request detail."},
                status=403,
            )

        batch = get_object_or_404(tms_models.Batch, pk=batch_id)
        action = request.data.get("action")

        VALID = [c[0] for c in getattr(tms_models.Batch, "STATUS", [])]

        if action == "approve":
            new_status = "ONGOING" if "ONGOING" in VALID else "PENDING"
        elif action == "reject":
            new_status = "REJECTED" if "REJECTED" in VALID else "PENDING"
        elif action == "revert":
            new_status = request.data.get("status") or "PENDING"
            if new_status not in VALID:
                return Response(
                    {"ok": False, "error": f"Invalid status '{new_status}'"}, status=400
                )
        else:
            return Response({"ok": False, "error": "Unknown action."}, status=400)

        batch.status = new_status
        batch.save(update_fields=["status"])

        return Response({"ok": True, "status": batch.status})


class SmmuCreatePartnerTargetAPIView(APIView):
    """
    SMMU – create/update TrainingPartnerTargets.
    """
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="SMMU – create/update partner targets",
        tags=["TMS – SMMU"],
        responses={200: "Target created/updated"},
    )
    def post(self, request):
        role = _user_role(request.user)
        if role != "smmu":
            return Response(
                {"ok": False, "error": "Not authorized for SMMU partner targets."},
                status=403,
            )

        data = request.data
        partner_id = data.get("partner_id")
        target_type = data.get("target_type")
        training_plan_id = data.get("training_plan_id")
        district_id = data.get("district_id")
        theme = data.get("theme")
        target_count = data.get("target_count")
        financial_year = data.get("financial_year")
        notes = data.get("notes") or ""

        if not (partner_id and target_type and target_count and financial_year):
            return Response(
                {
                    "ok": False,
                    "error": "partner_id, target_type, target_count, financial_year are required.",
                },
                status=400,
            )

        partner = get_object_or_404(tms_models.TrainingPartner, pk=partner_id)

        training_plan = None
        district = None
        if target_type == "MODULE":
            training_plan = get_object_or_404(tms_models.TrainingPlan, pk=training_plan_id)
            district = get_object_or_404(MasterDistrict, pk=district_id)
        elif target_type == "DISTRICT":
            district = get_object_or_404(MasterDistrict, pk=district_id)
        elif target_type == "THEME":
            if not theme:
                tp = tms_models.TrainingPlan.objects.filter(theme__expert=request.user).first()
                theme = tp.theme.theme_name if tp and tp.theme else None
            if not theme:
                return Response(
                    {"ok": False, "error": "theme is required for THEME targets."},
                    status=400,
                )

        lookup = {
            "partner": partner,
            "target_type": target_type,
            "financial_year": financial_year,
        }
        defaults = {
            "target_count": target_count,
            "notes": notes,
        }

        if target_type == "MODULE":
            lookup.update({"training_plan": training_plan, "district": district})
        elif target_type == "DISTRICT":
            lookup.update({"district": district})
        else:  # THEME
            lookup.update({"theme": theme})

        obj, created = tms_models.TrainingPartnerTargets.objects.update_or_create(
            defaults=defaults, **lookup
        )

        return Response(
            {
                "ok": True,
                "created": created,
                "target_id": obj.id,
            }
        )


# -------------------------------------------------------------------
# 7. DMMU – Dashboard, Requests & Attendance
# -------------------------------------------------------------------

class DmmuDashboardAPIView(APIView):
    """
    DMMU dashboard – district-scope batch stats.
    """
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="DMMU Dashboard",
        tags=["TMS – DMMU"],
        responses={200: "Dashboard payload"},
    )
    def get(self, request):
        role = _user_role(request.user)
        if role != "dmmu":
            return Response(
                {"ok": False, "error": "Not authorized for DMMU dashboard."},
                status=403,
            )

        district = None
        try:
            assign = (
                tms_models.DmmuDistrictAssignment.objects.filter(user_id=request.user.id)
                .select_related("district")
                .first()
            )
            if assign:
                district = assign.district
        except Exception:
            district = None

        tr_qs = tms_models.TrainingRequest.objects.all()
        if district:
            tr_qs = tr_qs.filter(district=district)

        batches = tms_models.Batch.objects.filter(request__in=tr_qs)

        kpi = {
            "total_batches": batches.count(),
            "pending": batches.filter(status__iexact="PENDING").count(),
            "ongoing": batches.filter(status__iexact="ONGOING").count(),
            "completed": batches.filter(status__iexact="COMPLETED").count(),
        }

        return Response(
            {
                "ok": True,
                "district_id": getattr(district, "district_id", None) if district else None,
                "kpi": kpi,
                "batches": BatchSerializer(batches[:100], many=True).data,
            }
        )


class DmmuTrainingRequestsAPIView(APIView):
    """
    DMMU – training requests in user's district.
    """
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="DMMU – TrainingRequests list",
        tags=["TMS – DMMU"],
        responses={200: "List of TrainingRequest"},
    )
    def get(self, request):
        role = _user_role(request.user)
        if role != "dmmu":
            return Response(
                {"ok": False, "error": "Not authorized for DMMU requests."},
                status=403,
            )

        district = None
        try:
            assign = (
                tms_models.DmmuDistrictAssignment.objects.filter(user_id=request.user.id)
                .select_related("district")
                .first()
            )
            if assign:
                district = assign.district
        except Exception:
            district = None

        qs_block = tms_models.TrainingRequest.objects.none()
        qs_other = tms_models.TrainingRequest.objects.none()

        if district:
            try:
                block_assigns = tms_models.BmmuBlockAssignment.objects.filter(
                    block__district=district
                ).values_list("user_id", flat=True)
                user_ids = list(block_assigns)
                if user_ids:
                    qs_block = tms_models.TrainingRequest.objects.filter(
                        level__iexact="BLOCK", created_by_id__in=user_ids
                    )
            except Exception:
                qs_block = tms_models.TrainingRequest.objects.none()

            try:
                qs_other = tms_models.TrainingRequest.objects.filter(district=district)
            except Exception:
                qs_other = tms_models.TrainingRequest.objects.none()

        qs = (qs_block | qs_other).distinct().order_by("-created_at")

        status_param = (request.query_params.get("status") or "").strip().upper()
        valid_statuses = [
            c[0].upper() for c in getattr(tms_models.TrainingRequest, "STATUS_CHOICES", [])
        ]
        if status_param:
            if status_param in valid_statuses:
                qs = qs.filter(status__iexact=status_param)
            else:
                qs = tms_models.TrainingRequest.objects.none()

        return Response(
            {"ok": True, "results": TrainingRequestSerializer(qs, many=True).data}
        )


class DmmuRequestDetailAPIView(APIView):
    """
    DMMU – TrainingRequest detail + batches.
    """
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="DMMU – TrainingRequest detail",
        tags=["TMS – DMMU"],
        responses={200: "Request + batches"},
    )
    def get(self, request, request_id):
        role = _user_role(request.user)
        if role != "dmmu":
            return Response(
                {"ok": False, "error": "Not authorized for DMMU request detail."},
                status=403,
            )

        tr = get_object_or_404(
            tms_models.TrainingRequest.objects.select_related("training_plan"),
            pk=request_id,
        )
        batches = tms_models.Batch.objects.filter(request=tr)

        return Response(
            {
                "ok": True,
                "request": TrainingRequestSerializer(tr).data,
                "batches": BatchSerializer(batches, many=True).data,
            }
        )


class DmmuBatchDetailAPIView(APIView):
    """
    DMMU – Batch detail with beneficiaries.
    """
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="DMMU – Batch detail",
        tags=["TMS – DMMU"],
        responses={200: "Batch + beneficiaries"},
    )
    def get(self, request, batch_id):
        role = _user_role(request.user)
        if role != "dmmu":
            return Response(
                {"ok": False, "error": "Not authorized for DMMU batch detail."},
                status=403,
            )

        batch = get_object_or_404(
            tms_models.Batch.objects.select_related(
                "request", "request__training_plan", "partner", "centre"
            ),
            pk=batch_id,
        )
        ben_qs = tms_models.BatchBeneficiary.objects.filter(batch=batch).select_related(
            "beneficiary"
        )

        beneficiaries = [
            {
                "member_code": getattr(b.beneficiary, "lokos_member_code", None),
                "member_name": getattr(b.beneficiary, "member_name", None),
            }
            for b in ben_qs
        ]

        return Response(
            {
                "ok": True,
                "batch": BatchSerializer(batch).data,
                "beneficiaries": beneficiaries,
            }
        )


class DmmuBatchAttendanceDateAPIView(APIView):
    """
    DMMU – attendance of batch by date.
    """
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="DMMU – Batch attendance by date",
        tags=["TMS – DMMU"],
        responses={200: "Attendance records"},
    )
    def get(self, request, batch_id):
        role = _user_role(request.user)
        if role != "dmmu":
            return Response(
                {"ok": False, "error": "Not authorized for DMMU attendance view."},
                status=403,
            )

        batch = get_object_or_404(tms_models.Batch, pk=batch_id)
        date_str = request.query_params.get("date")

        if not date_str:
            return Response(
                {"ok": False, "error": "date query param is required."}, status=400
            )

        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return Response({"ok": False, "error": "Invalid date format."}, status=400)

        attendance = tms_models.BatchAttendance.objects.filter(
            batch=batch, date=dt
        ).first()
        if not attendance:
            return Response({"ok": True, "records": []})

        records = [
            {
                "participant_id": r.participant_id,
                "participant_name": r.participant_name,
                "participant_role": r.participant_role,
                "present": r.present,
            }
            for r in attendance.participant_records.all()
        ]

        return Response(
            {
                "ok": True,
                "date": dt,
                "records": records,
            }
        )
