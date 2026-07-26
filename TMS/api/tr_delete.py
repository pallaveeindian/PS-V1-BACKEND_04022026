from django.db import transaction
from django.core.exceptions import PermissionDenied
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import NotFound
from core import models as core_models  
from TMS import models as tms_models

class TrainingRequestCustomDeleteView(APIView):
    """
    Dedicated custom endpoint for execution of oneshot soft-deletions on Training Requests.
    Enforces DMMU group boundaries or system role_id == 2 constraints explicitly.
    """

    def _verify_dmmu_access(self, request):
        auth_user = request.user
        if not auth_user or auth_user.is_anonymous:
            raise PermissionDenied("Authentication credentials were not provided.")

        master_user = core_models.MasterUser.objects.filter(
            username=auth_user.username
        ).first()

        if not master_user:
            raise PermissionDenied("Invalid profile mapping.")

        role_id = getattr(master_user, 'role_id', None)
        role_name = getattr(getattr(master_user, 'role', None), 'name', '').upper()
        
        is_dmmu_role = (role_id == 2) or ("DMMU" in role_name) or (role_id == 3) or ("SMMU" in role_name)

        if not is_dmmu_role:
            raise PermissionDenied("Access Denied: Only SMMU/DMMU operators can execute this deletion.")

        return master_user

    def delete(self, request, request_id):
        """
        Handles explicit HTTP DELETE calls bound to the transaction ID string wrapper.
        """
        # 1. Enforce access limits
        self._verify_dmmu_access(request)

        # 2. Extract targeted active entity reference and validate status
        training_request = tms_models.TrainingRequest.objects.filter(id=request_id, is_active=True).first()
        if not training_request:
            raise NotFound(f"Training Request with ID {request_id} does not exist or has been removed.")
            
        if training_request.status != 'BATCHING':
            return Response(
                {
                    "status": "error",
                    "detail": f"Deletion rejected: Only requests in the 'BATCHING' phase can be deleted. Current status is '{training_request.status}'."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # 3. Handle cascade sequentially inside atomic boundary block
            with transaction.atomic():
                # Purge active dependent joint registration sets cleanly
                tms_models.TRBeneficiary.objects.filter(training=training_request, is_active=True).update(is_active=False)
                tms_models.TRTrainer.objects.filter(training=training_request, is_active=True).update(is_active=False)

                # Finalize master parent object context flag switch
                training_request.delete()  # Falls back safely to SoftDeleteMixin context execution

            return Response(
                {
                    "status": "success",
                    "detail": f"Training Request #{request_id} and downstream child components soft-deleted successfully."
                },
                status=status.HTTP_200_OK
            )

        except Exception as e:
            return Response(
                {
                    "status": "error",
                    "detail": "Failed to safely execute transactional pipeline.",
                    "error": str(e)
                },
                status=status.HTTP_400_BAD_REQUEST
            )