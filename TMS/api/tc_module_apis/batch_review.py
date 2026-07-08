from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from core.models import MasterUser
from TMS.models import Batch

class ApproveRejectBatchAPIView(APIView):
    """
    Dedicated API for DMMU/Approval Authorities to Approve or Reject a Batch.
    Simply updating the status here will automatically trigger the BatchHistory signal.
    """
    permission_classes = [IsAuthenticated]

    def patch(self, request, batch_id, *args, **kwargs):
        try:
            user = MasterUser.objects.get(username=request.user.username)
        except MasterUser.DoesNotExist:
            return Response(
                {"error": "Authenticated MasterUser not found."}, 
                status=status.HTTP_403_FORBIDDEN
            )

        # Fetch the batch
        batch = get_object_or_404(Batch, id=batch_id)
        
        new_status = request.data.get("status")
        rejection_reason = request.data.get("rejection_reason", "").strip()

        # Validation
        if not new_status:
            return Response({"error": "The 'status' field is required."}, status=status.HTTP_400_BAD_REQUEST)

        valid_statuses = [choice[0] for choice in Batch.STATUS]
        if new_status.upper() not in valid_statuses:
            return Response(
                {"error": f"Invalid status. Must be one of {valid_statuses}."}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        if new_status.upper() == "REJECTED" and not rejection_reason:
            return Response(
                {"error": "A 'rejection_reason' is strictly required when rejecting a batch."}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        # Apply Updates
        batch.status = new_status.upper()
        
        if batch.status == "REJECTED":
            batch.rejection_reason = rejection_reason
        else:
            # Optional: Clear rejection reason if it's moving forward to SCHEDULED
            batch.rejection_reason = None 

        batch.updated_by = user
        
        # THIS SAVE AUTOMATICALLY TRIGGERS THE BatchHistory SIGNAL!
        batch.save() 

        return Response({
            "message": f"Batch successfully updated to {batch.status}.",
            "batch_id": batch.id,
            "batch_code": batch.code,
            "status": batch.status
        }, status=status.HTTP_200_OK)