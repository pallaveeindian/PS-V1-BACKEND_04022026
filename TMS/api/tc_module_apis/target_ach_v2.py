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

        # 2. Authenticate and resolve MasterUser (Enforcing is_active=True)
        try:
            master_user = MasterUser.objects.get(username=request.user.username, is_active=True)
        except MasterUser.DoesNotExist:
            return Response(
                {"error": "Authenticated active MasterUser not found."}, 
                status=status.HTTP_403_FORBIDDEN
            )

        # 3. Identify the DistrictTP mapped to this user (Enforcing is_active=True on relationships)
        dtp = DistrictTP.objects.filter(
            master_user=master_user, 
            is_active_dtp=True, 
            is_active=True,
            partner__is_active=True
        ).select_related('partner', 'district').first()

        if not dtp:
            return Response(
                {"error": "Access Denied. The logged-in user is not assigned to an active District TP."}, 
                status=status.HTTP_403_FORBIDDEN
            )

        # 4. Aggregate Target Count (Enforcing is_active=True)
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


        # 5. Aggregate Achievement Count (Count of successful participants in CLOSED batches)
        total_achievement_count = BeneficiaryAttendanceSummary.objects.filter(
            is_active=True,
            is_successful=True,
            batch__is_active=True,
            batch__status='CLOSED',
            batch__partner=dtp.partner,
            batch__district=dtp.district,
            batch__training_plan_id=training_plan_id,
            batch__financial_year=financial_year
        ).count()


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