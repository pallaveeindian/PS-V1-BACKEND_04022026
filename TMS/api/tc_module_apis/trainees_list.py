from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.db import models
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from core.models import MasterUser, MasterGeoUserScope
from TMS.models import *
from TMS.api.serializers import TRBeneficiarySerializer, TRTrainerSerializer

# -------------------------------------------------------------------
# Helper Functions
# -------------------------------------------------------------------
def get_master_user(request):
    django_user = request.user

    if not django_user or not django_user.is_authenticated:
        raise PermissionDenied("Authentication required.")

    try:
        return MasterUser.objects.get(username=django_user.username)
    except MasterUser.DoesNotExist:
        raise PermissionDenied("Master user not found.")


# -------------------------------------------------------------------
# API View
# -------------------------------------------------------------------
class FetchTraineesForTrainingPartnerView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        # 1. Extract Core query parameters
        financial_year = request.query_params.get("financial_year")
        training_plan_id = request.query_params.get("training_plan_id")
        participant_type = request.query_params.get("participant_type")

        # Extract Optional Filter query parameters
        block_id = request.query_params.get("block_id")
        gender = request.query_params.get("gender")
        designation = request.query_params.get("designation")
        pld_status = request.query_params.get("pld_status")
        social_category = request.query_params.get("social_category")
        religion = request.query_params.get("religion")
        panchayat_id = request.query_params.get("panchayat_id")
        village_id = request.query_params.get("village_id")
        search_query = request.query_params.get("search")
        exact_age = request.query_params.get("exact_age")
        from_age = request.query_params.get("from_age")
        to_age = request.query_params.get("to_age")

        # Validate mandatory query params
        if not all([financial_year, training_plan_id, participant_type]):
            return Response(
                {
                    "error": "Missing required parameters: financial_year, training_plan_id, and participant_type are all mandatory."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Normalize participant type for matching criteria
        participant_type = participant_type.strip().lower()
        if participant_type not in ["beneficiary", "trainer"]:
            return Response(
                {
                    "error": "Invalid participant_type. Must be either 'beneficiary' or 'trainer'."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 2. Get User context & Scope mapping
        try:
            master_user = get_master_user(request)
        except PermissionDenied as e:
            return Response({"error": str(e)}, status=status.HTTP_403_FORBIDDEN)

        # Fetch active district mappings assigned to the master user
        geo_scopes = MasterGeoUserScope.objects.filter(
            user_id=master_user.id, is_active=1, district_id__isnull=False
        )

        if not geo_scopes.exists():
            return Response(
                {
                    "error": "No active district geoscope found mapped to this user account."
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # Collect distinct district IDs for target filtering
        district_ids = geo_scopes.values_list("district_id", flat=True)

        # 3. Filter Training Requests matching core constraints and status='BATCHING'
        training_requests = TrainingRequest.objects.filter(
            financial_year=financial_year,
            training_plan_id=training_plan_id,
            district_id__in=district_ids,
            status="BATCHING",
        )

        if not training_requests.exists():
            return Response(
                {
                    "message": "No training requests found matching the selection criteria under 'BATCHING' status.",
                    "results": [],
                },
                status=status.HTTP_200_OK,
            )

        # 4. Fetch the targeted participant type data and apply advanced filters
        if participant_type == "beneficiary":
            trainees = TRBeneficiary.objects.filter(training__in=training_requests, CB_selected=False)

            # Apply Optional Filters for Beneficiaries
            if block_id:
                trainees = trainees.filter(block_id=block_id)
            if panchayat_id:
                trainees = trainees.filter(panchayat_id=panchayat_id)
            if village_id:
                trainees = trainees.filter(village_id=village_id)
            if gender:
                trainees = trainees.filter(gender__iexact=gender)
            if designation:
                trainees = trainees.filter(designation__icontains=designation)
            if pld_status:
                trainees = trainees.filter(pld_status__iexact=pld_status)
            if social_category:
                trainees = trainees.filter(social_category__iexact=social_category)
            if religion:
                trainees = trainees.filter(religion__iexact=religion)
            
            # Age Filters
            if exact_age and exact_age.isdigit():
                trainees = trainees.filter(age=int(exact_age))
            if from_age and from_age.isdigit():
                trainees = trainees.filter(age__gte=int(from_age))
            if to_age and to_age.isdigit():
                trainees = trainees.filter(age__lte=int(to_age))

            # Search Filter (SHG Code, Member Code, or Name)
            if search_query:
                trainees = trainees.filter(
                    Q(lokos_shg_code__icontains=search_query) |
                    Q(lokos_member_code__icontains=search_query) |
                    Q(member_name__icontains=search_query)
                )

            serializer = TRBeneficiarySerializer(trainees, many=True)

        else: # TRAINER
            trainees = TRTrainer.objects.filter(training__in=training_requests, CB_selected=False)

            # Apply Optional Filters mapped to Trainer structure
            if block_id:
                trainees = trainees.filter(block_id=block_id)
            if gender:
                trainees = trainees.filter(trainer__gender__iexact=gender)
            if designation:
                trainees = trainees.filter(trainer__designation__icontains=designation)
            if social_category:
                trainees = trainees.filter(trainer__social_category__iexact=social_category)
            
            # Search Filter (Mobile, Name, or Aadhaar)
            if search_query:
                trainees = trainees.filter(
                    Q(full_name__icontains=search_query) |
                    Q(mobile_no__icontains=search_query) |
                    Q(aadhaar_no__icontains=search_query)
                )

            serializer = TRTrainerSerializer(trainees, many=True)

        return Response(
            {
                "meta": {
                    "financial_year": financial_year,
                    "training_plan_id": training_plan_id,
                    "participant_type": participant_type,
                    "matched_requests_count": training_requests.count(),
                    "returned_participants_count": trainees.count()
                },
                "results": serializer.data,
            },
            status=status.HTTP_200_OK,
        )