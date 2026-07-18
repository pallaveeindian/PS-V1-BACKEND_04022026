from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404

from TMS.models import MasterTrainer, TRTrainer, BatchTrainer, BatchMasterTrainer
from .serializers import AvailabilityTrainingRequestSerializer, AvailabilityBatchSerializer

class CheckTrainerAvailabilityView(APIView):
    """
    Checks if a MasterTrainer is available for assignment.
    A trainer is considered BUSY and UNAVAILABLE if:
    1. They are in a TRTrainer where TrainingRequest status == 'BATCHING'.
       - EXCEPT: If they are already mapped to a BatchTrainer, their status depends purely on that Batch's status.
    2. They are in a BatchTrainer where Batch status is DRAFT, PENDING, or ONGOING.
    3. They are in a BatchMasterTrainer where Batch status is DRAFT, PENDING, or ONGOING.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, trainer_id, *args, **kwargs):
        trainer = get_object_or_404(MasterTrainer, id=trainer_id)

        # Defines statuses that mean the batch is active and occupying the trainer
        busy_batch_statuses = ['DRAFT', 'PENDING', 'ONGOING']

        # ---------------------------------------------------------
        # CONDITION 1: Check TRTrainer (Training Request Phase)
        # ---------------------------------------------------------
        tr_trainers_batching = TRTrainer.objects.filter(
            trainer=trainer,
            training__status='BATCHING',
            is_active=True
        ).select_related('training')

        for tr_t in tr_trainers_batching:
            # Check if this TRTrainer has already been assigned to a BatchTrainer
            linked_batches = BatchTrainer.objects.filter(trainer=tr_t, is_active=True).select_related('batch')
            
            if linked_batches.exists():
                # If they are already in a batch, apply the batch status condition again
                busy_bt = linked_batches.filter(batch__status__in=busy_batch_statuses).first()
                if busy_bt:
                    return Response({
                        "is_available": False,
                        "busy_type": "BATCH",
                        "busy_reason": f"Trainer is assigned as a participant in a Batch currently in {busy_bt.batch.status} phase.",
                        "busy_context": AvailabilityBatchSerializer(busy_bt.batch).data
                    }, status=status.HTTP_200_OK)
                # If all linked batches are in a 'free' status (COMPLETED, CLOSED, REJECTED, SCHEDULED),
                # the trainer is considered FREE regarding this mapping. We pass and continue.
            else:
                # If they are NOT linked to any batch yet, they are actively waiting in the BATCHING queue
                return Response({
                    "is_available": False,
                    "busy_type": "TRAINING_REQUEST",
                    "busy_reason": "Trainer is currently tied to a Training Request in the BATCHING phase.",
                    "busy_context": AvailabilityTrainingRequestSerializer(tr_t.training).data
                }, status=status.HTTP_200_OK)

        # ---------------------------------------------------------
        # CONDITION 2: Check BatchTrainer (Trainee inside a Batch)
        # Note: BatchTrainer points to TRTrainer, which points to MasterTrainer
        # ---------------------------------------------------------
        busy_bt = BatchTrainer.objects.filter(
            trainer__trainer=trainer,
            batch__status__in=busy_batch_statuses,
            is_active=True
        ).select_related('batch').first()

        if busy_bt:
            return Response({
                "is_available": False,
                "busy_type": "BATCH",
                "busy_reason": f"Trainer is assigned as a participant in a Batch currently in {busy_bt.batch.status} phase.",
                "busy_context": AvailabilityBatchSerializer(busy_bt.batch).data
            }, status=status.HTTP_200_OK)

        # ---------------------------------------------------------
        # CONDITION 3: Check BatchMasterTrainer (Lead Trainer of a Batch)
        # ---------------------------------------------------------
        busy_bmt = BatchMasterTrainer.objects.filter(
            master_trainer=trainer,
            batch__status__in=busy_batch_statuses,
            is_active=True
        ).select_related('batch').first()

        if busy_bmt:
            return Response({
                "is_available": False,
                "busy_type": "BATCH",
                "busy_reason": f"Trainer is leading a Batch currently in {busy_bmt.batch.status} phase.",
                "busy_context": AvailabilityBatchSerializer(busy_bmt.batch).data
            }, status=status.HTTP_200_OK)

        # ---------------------------------------------------------
        # ALL CLEAR: Trainer is fully available
        # ---------------------------------------------------------
        return Response({
            "is_available": True,
            "busy_type": None,
            "busy_reason": None,
            "busy_context": None,
            "message": "Trainer is completely available for assignment."
        }, status=status.HTTP_200_OK)