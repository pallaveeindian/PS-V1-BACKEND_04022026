from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.db.models import Q

from TMS.models import MasterTrainer, TRTrainer, BatchTrainer, BatchMasterTrainer
from .serializers import AvailabilityTrainingRequestSerializer, AvailabilityBatchSerializer

class CheckTrainerAvailabilityView(APIView):
    """
    Checks if a MasterTrainer is available for assignment.
    A trainer is considered BUSY and UNAVAILABLE if:
    1. They are in a TRTrainer where TrainingRequest status == 'BATCHING'.
    2. They are in an active Batch (DRAFT, PENDING, ONGOING, SCHEDULED, REJECTED) AND the 
       requested assignment dates overlap based on the batch's current status.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, trainer_id, *args, **kwargs):
        trainer = get_object_or_404(MasterTrainer, id=trainer_id)
        
        # Intercept the requested assignment's start_date and end_date from query params
        req_start_date = request.query_params.get('start_date')
        req_end_date = request.query_params.get('end_date')

        # ---------------------------------------------------------
        # CONDITION 1: Check TRTrainer (Training Request Phase)
        # ---------------------------------------------------------
        busy_tr = TRTrainer.objects.filter(
            trainer=trainer,
            training__status='BATCHING',
            is_active=True
        ).select_related('training', 'training__district', 'training__block').first()

        if busy_tr:
            tr = busy_tr.training
            return Response({
                "is_available": False,
                "busy_type": "TRAINING_REQUEST",
                "busy_reason": "Trainer is currently tied to a Training Request in the BATCHING phase.",
                "training_request_id": tr.id,
                "district_name_en": tr.district.district_name_en if tr.district else None,
                "block_name_en": tr.block.block_name_en if tr.block else None,
                "busy_context": AvailabilityTrainingRequestSerializer(tr).data
            }, status=status.HTTP_200_OK)

        # ---------------------------------------------------------
        # CONDITION 2: Check Active Batches (Trainee or Lead Trainer)
        # ---------------------------------------------------------
        # If batch is COMPLETED, REVIEW, CLOSED -> Trainer is FREE.
        # Otherwise (ONGOING, SCHEDULED) -> Check dates for overlap.
        active_batch_statuses = ['ONGOING', 'SCHEDULED']
        
        # Base query: Are they in an active batch status?
        batch_busy_q = Q(batch__status__in=active_batch_statuses)

        # Date Overlap Evaluation Logic
        date_overlap_q = Q()

        # RULE A: For SCHEDULED (and other pre-execution phases)
        # Trainer is strictly busy if there is ANY date overlap: (batch_start <= req_end AND batch_end >= req_start)
        if req_start_date and req_end_date:
            date_overlap_q |= Q(batch__status__in=['SCHEDULED']) & \
                              ((Q(batch__start_date__lte=req_end_date) & Q(batch__end_date__gte=req_start_date)) | \
                               Q(batch__start_date__isnull=True) | Q(batch__end_date__isnull=True))
        elif req_end_date:
            date_overlap_q |= Q(batch__status__in=['SCHEDULED']) & \
                              (Q(batch__start_date__lte=req_end_date) | Q(batch__start_date__isnull=True))
        elif req_start_date:
            date_overlap_q |= Q(batch__status__in=['SCHEDULED']) & \
                              (Q(batch__end_date__gte=req_start_date) | Q(batch__end_date__isnull=True))
        else:
            date_overlap_q |= Q(batch__status__in=['SCHEDULED'])

        # RULE B: For ONGOING phase
        # Trainer is FREE if the requested start_date is AFTER the batch's end_date
        # Therefore, they are BUSY if the batch ends ON or AFTER the req_start_date
        if req_start_date:
            date_overlap_q |= Q(batch__status='ONGOING') & \
                              (Q(batch__end_date__gte=req_start_date) | Q(batch__end_date__isnull=True))
        else:
            date_overlap_q |= Q(batch__status='ONGOING')

        # Combine the base active status query with the targeted date overlap logic
        batch_busy_q &= date_overlap_q

        # Check BatchTrainer (Trainee role)
        busy_bt = BatchTrainer.objects.filter(
            batch_busy_q,
            trainer__trainer=trainer,
            is_active=True
        ).select_related('batch').first()

        if busy_bt:
            return Response({
                "is_available": False,
                "busy_type": "BATCH",
                "busy_reason": f"Trainer is assigned as a participant in a Batch currently in {busy_bt.batch.status} phase with overlapping dates.",
                "busy_context": AvailabilityBatchSerializer(busy_bt.batch).data
            }, status=status.HTTP_200_OK)

        # Check BatchMasterTrainer (Lead Trainer role)
        busy_bmt = BatchMasterTrainer.objects.filter(
            batch_busy_q,
            master_trainer=trainer,
            is_active=True
        ).select_related('batch').first()

        if busy_bmt:
            return Response({
                "is_available": False,
                "busy_type": "BATCH",
                "busy_reason": f"Trainer is leading a Batch currently in {busy_bmt.batch.status} phase with overlapping dates.",
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