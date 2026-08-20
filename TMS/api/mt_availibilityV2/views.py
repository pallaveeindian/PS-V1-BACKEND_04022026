from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from TMS.models import *
from core.models import MasterUser
from .serializers import *

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
        # busy_tr = TRTrainer.objects.filter(
        #     trainer=trainer,
        #     training__status='BATCHING',
        #     is_active=True
        # ).select_related('training', 'training__district', 'training__block').first()

        # if busy_tr:
        #     tr = busy_tr.training
        #     return Response({
        #         "is_available": False,
        #         "busy_type": "TRAINING_REQUEST",
        #         "busy_reason": "Trainer is currently tied to a Training Request in the BATCHING phase.",
        #         "training_request_id": tr.id,
        #         "district_name_en": tr.district.district_name_en if tr.district else None,
        #         "block_name_en": tr.block.block_name_en if tr.block else None,
        #         "busy_context": AvailabilityTrainingRequestSerializer(tr).data
        #     }, status=status.HTTP_200_OK)

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


class ReplaceBatchMasterTrainerAPIView(APIView):
    """
    Replaces the Master Trainer(s) of a Batch with a new, available Master Trainer.
    Strictly enforces constraints on Batch status, prior Ekyc/Attendance, and MT availability.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = ReplaceBatchMasterTrainerSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        batch_id = serializer.validated_data['batch_id']
        new_mt_id = serializer.validated_data['master_trainer_id']

        # ---------------------------------------------------------
        # 1. Fetch Entities & Validate Existence
        # ---------------------------------------------------------
        try:
            batch = Batch.objects.get(id=batch_id, is_active=True)
        except Batch.DoesNotExist:
            return Response({"error": "Batch not found or is inactive."}, status=status.HTTP_404_NOT_FOUND)

        try:
            new_mt = MasterTrainer.objects.get(id=new_mt_id, is_active=True)
        except MasterTrainer.DoesNotExist:
            return Response({"error": "New Master Trainer not found or is inactive."}, status=status.HTTP_404_NOT_FOUND)

        # ---------------------------------------------------------
        # 2. Batch Status Constraints
        # ---------------------------------------------------------
        if batch.status not in ['ONGOING', 'SCHEDULED']:
            return Response({
                "error": f"Replacement failed. Batch status must be ONGOING or SCHEDULED. Current status is '{batch.status}'."
            }, status=status.HTTP_400_BAD_REQUEST)

        # ---------------------------------------------------------
        # 3. No eKYC or Attendance Constraint
        # ---------------------------------------------------------
        if BatchEkycVerification.objects.filter(batch=batch, is_active=True).exists():
            return Response({
                "error": "Replacement blocked: eKYC verification records already exist for this batch."
            }, status=status.HTTP_400_BAD_REQUEST)

        if BatchAttendance.objects.filter(batch=batch, is_active=True).exists():
            return Response({
                "error": "Replacement blocked: Attendance records have already been generated for this batch."
            }, status=status.HTTP_400_BAD_REQUEST)

        # ---------------------------------------------------------
        # 4. New Master Trainer Availability Constraint
        # ---------------------------------------------------------
        # Check A: Tied to a TR in BATCHING phase
        is_in_batching_tr = TRTrainer.objects.filter(
            trainer=new_mt,
            training__status='BATCHING',
            is_active=True,
            training__is_active=True
        ).exists()

        if is_in_batching_tr:
            return Response({
                "error": "The selected Master Trainer is currently locked to a Training Request in the 'BATCHING' phase."
            }, status=status.HTTP_400_BAD_REQUEST)

        # Check B: Overlapping active batch
        if batch.start_date and batch.end_date:
            overlapping_batches = BatchMasterTrainer.objects.filter(
                master_trainer=new_mt,
                is_active=True,
                batch__is_active=True,
                batch__status__in=['DRAFT', 'PENDING', 'ONGOING', 'SCHEDULED', 'REJECTED'],
                batch__start_date__lte=batch.end_date,
                batch__end_date__gte=batch.start_date
            ).exclude(batch=batch)

            if overlapping_batches.exists():
                return Response({
                    "error": "The selected Master Trainer is busy in another overlapping batch during these dates."
                }, status=status.HTTP_400_BAD_REQUEST)

        # ---------------------------------------------------------
        # 5. Execution (Atomic Swap)
        # ---------------------------------------------------------
        try:
            with transaction.atomic():
                # Attempt to retrieve Auth User for tracking
                try:
                    auth_user = MasterUser.objects.get(username=request.user.username)
                except MasterUser.DoesNotExist:
                    auth_user = None

                # Soft delete any existing Master Trainers from this batch
                existing_bmts = BatchMasterTrainer.objects.filter(batch=batch, is_active=True)
                for bmt in existing_bmts:
                    bmt.is_active = False
                    bmt.deleted_at = timezone.now()
                    bmt.deleted_by = auth_user
                    bmt.remarks = (
                        f"{bmt.remarks or ''} [Replaced by {auth_user}]"
                    ).strip()
                    bmt.save()

                # Insert the new Master Trainer
                new_bmt = BatchMasterTrainer.objects.create(
                    batch=batch,
                    master_trainer=new_mt,
                    status='AVAILABLE',
                    participated=False,
                    remarks="Assigned via Replacement API.",
                    created_by=auth_user
                )

                # ============================================================
                # SURGICAL ADDITION: EXPLICITLY LOG TRAINER REPLACEMENT IN HISTORY
                # ============================================================
                # Create a list of names for the old trainers being removed to include in the log
                old_trainer_names = ", ".join([
                    (bmt.master_trainer.full_name if bmt.master_trainer else "Unknown") 
                    for bmt in existing_bmts
                ])
                
                BatchHistory.objects.create(
                    batch=batch,
                    status=batch.status, # Status remains the same during MT replacement
                    remarks=f"Master Trainer replaced by {auth_user.username}. Replaced: {old_trainer_names} with {new_mt.full_name}.",
                    created_by=auth_user
                )
                # ============================================================

            return Response({
                "status": "success",
                "message": "Master Trainer has been successfully replaced in the batch.",
                "new_batch_master_trainer_id": new_bmt.id
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)