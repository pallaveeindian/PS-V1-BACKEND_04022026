# Desktop/BDO_Projects/pragati_setu/TMS/api/TPlanSequence/create.py
import logging
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.shortcuts import get_object_or_404

from core.models import MasterUser
from TMS.models import TrainingPlanSequence
from .serializers import TrainingPlanSequenceCreateSerializer

logger = logging.getLogger(__name__)

class CreateTrainingPlanSequenceAPIView(APIView):
    """
    Registers or Updates a training plan into a sequence group.
    - Pass 'id' in the payload or '?edit=<id>' in the URL to edit an existing row.
    - step_order: 1 indicates the first step.
    - next_training_plan: Can be null/empty if it is the last step in the sequence.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        # Determine if this is an edit operation
        sequence_id = request.data.get("id") or request.query_params.get("edit")
        
        if sequence_id:
            # EDIT MODE
            instance = get_object_or_404(TrainingPlanSequence, id=sequence_id)
            serializer = TrainingPlanSequenceCreateSerializer(instance, data=request.data, partial=True)
            success_message = "Training Plan Sequence successfully updated."
            status_code = status.HTTP_200_OK
        else:
            # CREATE MODE
            serializer = TrainingPlanSequenceCreateSerializer(data=request.data)
            success_message = "Training Plan Sequence successfully registered."
            status_code = status.HTTP_201_CREATED
        
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            request_user = request.user if getattr(request.user, "is_authenticated", False) else None
            
            try:
                user = MasterUser.objects.get(username=request.user.username)
            except MasterUser.DoesNotExist:
                return Response({"error": "Authenticated MasterUser not found."}, status=status.HTTP_403_FORBIDDEN)


            # Save the sequence row and automatically assign the creator/updater
            if sequence_id:
                sequence_instance = serializer.save(updated_by=user)
            else:
                sequence_instance = serializer.save(created_by=user)
            
            return Response(
                {
                    "message": success_message,
                    "data": {
                        "id": sequence_instance.id,
                        "sequence_group_name": sequence_instance.sequence_group_name,
                        "training_plan_id": sequence_instance.training_plan_id,
                        "step_order": sequence_instance.step_order,
                        "next_training_plan_id": sequence_instance.next_training_plan_id,
                    }
                },
                status=status_code
            )
            
        except Exception as e:
            logger.exception(f"Failed to process TrainingPlanSequence: {e}")
            return Response(
                {
                    "error": "An unexpected error occurred while processing the sequence.",
                    "detail": str(e),
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )