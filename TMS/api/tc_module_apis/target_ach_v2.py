from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.db.models import Sum

from core.models import MasterUser
from TMS.models import *

class DTPTargetCountAPIView(APIView):
    """
    Returns the aggregated target_count for the logged-in DTP user.
    Automatically filters by the DTP's mapped TrainingPartner and MasterDistrict.
    Requires 'financial_year' and 'training_plan_id' as query parameters.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        # 1. Extract Query Parameters
        financial_year = request.query_params.get("financial_year")
        training_plan_id = request.query_params.get("training_plan_id")

        if not financial_year or not training_plan_id:
            return Response(
                {"error": "Missing required query parameters: 'financial_year' and 'training_plan_id'."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 2. Authenticate and resolve MasterUser
        try:
            master_user = MasterUser.objects.get(username=request.user.username)
        except MasterUser.DoesNotExist:
            return Response(
                {"error": "Authenticated MasterUser not found."}, 
                status=status.HTTP_403_FORBIDDEN
            )

        # 3. Identify the DistrictTP mapped to this user
        dtp = DistrictTP.objects.filter(
            master_user=master_user, 
            is_active_dtp=True, 
            is_active=True
        ).select_related('partner', 'district').first()

        if not dtp:
            return Response(
                {"error": "Access Denied. The logged-in user is not assigned to an active District TP."}, 
                status=status.HTTP_403_FORBIDDEN
            )

        # 4. Aggregate Target Count
        target_aggregation = TrainingPartnerTargets.objects.filter(
            partner=dtp.partner,
            district=dtp.district,
            training_plan_id=training_plan_id,
            financial_year=financial_year,
            is_active=True
        ).aggregate(
            total_targets=Sum("target_count")
        )

        total_target_count = target_aggregation.get("total_targets") or 0


        # 5. Aggregate Achievement Count
        achievement_aggregation = TrainingPartnerAchievement.objects.filter(
            partner=dtp.partner,
            district=dtp.district,
            training_plan_id=training_plan_id,
            financial_year=financial_year,
            is_active=True
        ).aggregate(
            total_achievement=Sum("batches_completed")
        )

        total_achievement_count = (
            achievement_aggregation.get("total_achievement") or 0
        )


        # 6. Return Response
        return Response(
            {
                "meta": {
                    "partner_id": dtp.partner.id,
                    "partner_name": dtp.partner.name,
                    "district_id": dtp.district.district_id,
                    "district_name": dtp.district.district_name_en,
                    "training_plan_id": int(training_plan_id),
                    "financial_year": financial_year,
                },
                "total_target_count": total_target_count,
                "total_achievement_count": total_achievement_count,
                "remaining_target": max(
                    total_target_count - total_achievement_count,
                    0
                ),
            },
            status=status.HTTP_200_OK,
        )