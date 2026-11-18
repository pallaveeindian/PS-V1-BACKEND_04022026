from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.db.models import Sum

from core.models import MasterUser
from TMS.models import *


class DTPTargetCountAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        financial_year = request.query_params.get("financial_year")
        training_plan_id = request.query_params.get("training_plan_id")
        district_id = request.query_params.get("district_id")
        partner_id = request.query_params.get("partner_id")

        if not financial_year or not training_plan_id:
            return Response(
                {"error": "Missing required query parameters: 'financial_year' and 'training_plan_id'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            training_plan_id = int(training_plan_id)
            if district_id:
                district_id = int(district_id)
            if partner_id:
                partner_id = int(partner_id)
        except (TypeError, ValueError):
            return Response(
                {"error": "'training_plan_id', 'district_id', and 'partner_id' must be valid integers."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            master_user = MasterUser.objects.get(
                username=request.user.username,
                is_active=True,
            )
        except MasterUser.DoesNotExist:
            return Response(
                {"error": "Authenticated active MasterUser not found."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # An active DTP's assigned partner and district remain the query scope.
        dtp = (
            DistrictTP.objects
            .filter(
                master_user=master_user,
                is_active_dtp=True,
                is_active=True,
                partner__is_active=True,
            )
            .select_related("partner", "district")
            .first()
        )

        if dtp:
            partner = dtp.partner
            district = dtp.district

            # If IDs are supplied for a DTP, they must match the assignment.
            if (
                (partner_id is not None and partner.id != partner_id)
                or (district_id is not None and district.district_id != district_id)
            ):
                return Response(
                    {"error": "The supplied partner_id or district_id does not match your DTP assignment."},
                    status=status.HTTP_403_FORBIDDEN,
                )
        else:
            # Non-DTP users must explicitly provide both IDs.
            if district_id is None or partner_id is None:
                return Response(
                    {"error": "Non-DTP users must provide both 'district_id' and 'partner_id'."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            try:
                district = MasterDistrict.objects.get(
                    district_id=district_id,
                )
                partner = TrainingPartner.objects.get(
                    id=partner_id,
                    is_active=True,
                )
            except (MasterDistrict.DoesNotExist, TrainingPartner.DoesNotExist):
                return Response(
                    {"error": "The supplied active district or training partner was not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )

        total_target_count = (
            TrainingPartnerTargets.objects
            .filter(
                partner=partner,
                district=district,
                training_plan_id=training_plan_id,
                financial_year=financial_year,
                is_active=True,
            )
            .aggregate(total_targets=Sum("target_count"))
            .get("total_targets")
            or 0
        )

        common_batch_filters = {
            "is_active": True,
            "batch__is_active": True,
            "batch__partner": partner,
            "batch__district": district,
            "batch__training_plan_id": training_plan_id,
            "batch__financial_year": financial_year,
        }

        enrolled_beneficiaries = BatchBeneficiary.objects.filter(
            beneficiary__is_active=True,
            **common_batch_filters,
        ).count()

        enrolled_trainers = BatchTrainer.objects.filter(
            trainer__is_active=True,
            **common_batch_filters,
        ).count()

        enrolled_staff = BatchStaff.objects.filter(
            staff__is_active=True,
            **common_batch_filters,
        ).count()

        total_achievement_count = (
            enrolled_beneficiaries + enrolled_trainers + enrolled_staff
        )

        return Response(
            {
                "meta": {
                    "partner_id": partner.id,
                    "partner_name": partner.name,
                    "district_id": district.district_id,
                    "district_name": district.district_name_en,
                    "training_plan_id": training_plan_id,
                    "financial_year": financial_year,
                },
                "total_target_count": total_target_count,
                "total_achievement_count": total_achievement_count,
                "remaining_target": max(
                    total_target_count - total_achievement_count,
                    0,
                ),
            },
            status=status.HTTP_200_OK,
        )