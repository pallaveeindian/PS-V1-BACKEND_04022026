from django.core.exceptions import PermissionDenied
from django.db.models import Q
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
        batch_id = request.query_params.get("batch_id")
        training_request_id = request.query_params.get("training_request_id")

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
        tr_filters = {
            "financial_year": financial_year,
            "training_plan_id": training_plan_id,
            "district_id__in": district_ids
        }
        
        if training_request_id:
            tr_filters["id"] = training_request_id

        # OR requests that were previously BATCHING but moved to PENDING because this batch consumed them.
        if batch_id:
            # If batch_id is provided, we must include requests that might be PENDING 
            # because they were fully mapped to this specific batch.
            training_requests = TrainingRequest.objects.filter(**tr_filters).filter(
                Q(status="BATCHING") | Q(status="PENDING")
            )
        else:
            tr_filters["status"] = "BATCHING"
            training_requests = TrainingRequest.objects.filter(**tr_filters)

        if not training_requests.exists():
            return Response(
                {
                    "message": "No valid training requests found matching the selection criteria.",
                    "results": [],
                },
                status=status.HTTP_200_OK,
            )

        # 4. Fetch the targeted participant type data and apply advanced filters
        if participant_type == "beneficiary":
            if batch_id:
                linked_ids = list(BatchBeneficiary.objects.filter(batch_id=batch_id).values_list('beneficiary_id', flat=True))
                trainees = TRBeneficiary.objects.filter(
                    Q(training__in=training_requests) & 
                    (Q(CB_selected=False) | Q(CB_selected=True, id__in=linked_ids))
                )
            else:
                trainees = TRBeneficiary.objects.filter(training__in=training_requests, CB_selected=False)

            # Apply Optional Filters for Beneficiaries
            if block_id:
                trainees = trainees.filter(training__block_id=block_id)
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

            # Search Filter (SHG Code, Member Code, Name, or Training Request ID)
            if search_query:
                # SURGICAL FIX: If it exactly matches a valid Training ID, snap to it to prevent substring false positives
                if search_query.isdigit() and training_requests.filter(id=search_query).exists():
                    search_q = Q(training_id=search_query)
                else:
                    search_q = (
                        Q(lokos_shg_code__icontains=search_query) |
                        Q(lokos_member_code__icontains=search_query) |
                        Q(member_name__icontains=search_query)
                    )
                    if search_query.isdigit():
                        search_q |= Q(training_id=search_query)
                    
                trainees = trainees.filter(search_q)

            serializer = TRBeneficiarySerializer(trainees, many=True)

        else: # TRAINER
            linked_ids = []
            if batch_id:
                # Use the clean ManyToMany reverse relation to avoid naming collisions
                linked_ids = list(TRTrainer.objects.filter(trainers_for_batch__id=batch_id).values_list('id', flat=True))

            # 1. Group all optional filters into a single Q object
            optional_filters = Q()
            
            # SURGICAL FIX: Completely ignore block_id for trainers. 
            # (We purposefully do NOT add block_id to optional_filters here)

            if gender:
                optional_filters &= Q(trainer__gender__iexact=gender)
            if designation:
                optional_filters &= Q(trainer__designation__icontains=designation)
            if social_category:
                optional_filters &= Q(trainer__social_category__iexact=social_category)
            
            # Search Filter (Mobile, Name, Aadhaar, or Training Request ID)
            if search_query:
                # SURGICAL FIX: If it exactly matches a valid Training ID, snap to it to prevent substring false positives
                if search_query.isdigit() and training_requests.filter(id=search_query).exists():
                    search_q = Q(training_id=search_query)
                else:
                    search_q = (
                        Q(full_name__icontains=search_query) |
                        Q(mobile_no__icontains=search_query) |
                        Q(aadhaar_no__icontains=search_query)
                    )
                    if search_query.isdigit():
                        search_q |= Q(training_id=search_query)
                    
                optional_filters &= search_q

            # 2. Apply logic: Include if (Unselected AND matches filters) OR (Already Selected for this batch)
            if batch_id:
                trainees = TRTrainer.objects.filter(
                    Q(training__in=training_requests) & 
                    (
                        (Q(CB_selected=False) & optional_filters) | 
                        Q(CB_selected=True, id__in=linked_ids)
                    )
                )
            else:
                trainees = TRTrainer.objects.filter(
                    Q(training__in=training_requests) & 
                    Q(CB_selected=False) & 
                    optional_filters
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