import logging

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import MasterUser
from TMS.models import TrainingPlanSequence

logger = logging.getLogger(__name__)


class DeleteTrainingPlanSequenceAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, sequence_id, *args, **kwargs):
        # Only find active rows. An already deleted row returns 404.
        sequence = get_object_or_404(
            TrainingPlanSequence,
            id=sequence_id,
            is_active=True,
        )

        try:
            user = MasterUser.objects.get(username=request.user.username)

            sequence.is_active = False
            sequence.updated_by = user
            sequence.save(update_fields=["is_active", "updated_by"])

            return Response(
                {
                    "message": "Training Plan Sequence successfully deleted.",
                    "data": {
                        "id": sequence.id,
                        "sequence_group_name": sequence.sequence_group_name,
                        "training_plan_id": sequence.training_plan_id,
                        "step_order": sequence.step_order,
                        "is_active": sequence.is_active,
                    },
                },
                status=status.HTTP_200_OK,
            )

        except MasterUser.DoesNotExist:
            return Response(
                {"error": "Authenticated MasterUser not found."},
                status=status.HTTP_403_FORBIDDEN,
            )

        except Exception as e:
            logger.exception(
                "Failed to delete TrainingPlanSequence id=%s: %s",
                sequence_id,
                e,
            )
            return Response(
                {
                    "error": "An unexpected error occurred while deleting the sequence.",
                    "detail": str(e),
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )