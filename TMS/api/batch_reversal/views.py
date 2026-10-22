# TMS\api\batch_reversal\views.py
import logging

from django.db import transaction
from django.utils import timezone

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated

from core.models import MasterUser

from TMS.models import (
    Batch,
    BatchMasterTrainer,
    BatchEkycVerification,
    BatchAttendance,
    ParticipantAttendance,
    BatchHistory,
)

from .serializers import BatchReversalSerializer


logger = logging.getLogger(__name__)


def get_master_user_from_request(request):
    try:
        return MasterUser.objects.get(
            username=request.user.username
        )
    except MasterUser.DoesNotExist:
        return None


class BatchReversalAPIView(APIView):

    permission_classes = [IsAuthenticated]

    ALLOWED_STATUSES = {"ONGOING", "SCHEDULED"}

    def post(self, request, *args, **kwargs):

        # ==========================================
        # STEP 1: VALIDATE BATCH IDS
        # ==========================================

        serializer = BatchReversalSerializer(
            data=request.data
        )

        serializer.is_valid(raise_exception=True)








        batch_ids = serializer.validated_data["batch_ids"]
        target_status = serializer.validated_data["target_status"]

        # ==========================================
        # GET MASTER USER
        # ==========================================

        master_user = get_master_user_from_request(request)

        if not master_user:
            return Response(
                {
                    "success": False,
                    "message": "Master User not found."
                },
                status=status.HTTP_403_FORBIDDEN
            )
        # Only SMMU users can perform Batch Reversal
        if getattr(master_user, "role_id", None) != 3:
            return Response(
                {
                    "success": False,
                    "message": "Only SMMU users can reverse batches."
                },
                status=status.HTTP_403_FORBIDDEN
            )

        username = master_user.username

        reversal_remark = (
            f"Batch reversal initiated by {username}"
        )

        try:

            # ======================================
            # ATOMIC TRANSACTION
            # ======================================

            with transaction.atomic():

                # ==================================
                # STEP 2: FETCH AND LOCK BATCHES
                # ==================================

                batches = list(
                    Batch.objects
                    .select_for_update()
                    .filter(id__in=batch_ids)
                    .order_by("id")
                )

                found_ids = {
                    batch.id for batch in batches
                }

                missing_ids = [
                    batch_id
                    for batch_id in batch_ids
                    if batch_id not in found_ids
                ]

                inactive_ids = [
                    batch.id
                    for batch in batches
                    if not batch.is_active
                ]

                if missing_ids or inactive_ids:

                    return Response(
                        {
                            "success": False,
                            "message": (
                                "Some batches are missing "
                                "or deleted."
                            ),
                            "missing_batch_ids": missing_ids,
                            "inactive_batch_ids": inactive_ids
                        },
                        status=status.HTTP_400_BAD_REQUEST
                    )

                # ==================================
                # STEP 3: CHECK BATCH STATUS
                # ==================================

                invalid_batches = [
                    {
                        "batch_id": batch.id,
                        "status": batch.status
                    }
                    for batch in batches
                    if batch.status not in self.ALLOWED_STATUSES
                ]

                if invalid_batches:

                    return Response(
                        {
                            "success": False,
                            "message": (
                                "Only ONGOING or SCHEDULED "
                                "batches can be reversed."
                            ),
                            "invalid_batches": invalid_batches
                        },
                        status=status.HTTP_400_BAD_REQUEST
                    )

                now = timezone.now()

                soft_delete_data = {
                    "is_active": False,
                    "deleted_at": now,
                    "deleted_by_id": master_user.id,
                    "updated_at": now,
                    "updated_by_id": master_user.id,
                }

                # ==================================
                # STEP 4: SOFT DELETE BATCH
                # MASTER TRAINER ASSIGNMENTS
                # ==================================

                master_trainer_count = (
                    BatchMasterTrainer.objects
                    .filter(
                        batch_id__in=batch_ids,
                        is_active=True
                    )
                    .update(**soft_delete_data)
                )

                # ==================================
                # STEP 5: SOFT DELETE BATCH eKYC
                # ==================================

                ekyc_count = (
                    BatchEkycVerification.objects
                    .filter(
                        batch_id__in=batch_ids,
                        is_active=True
                    )
                    .update(**soft_delete_data)
                )

                # ==================================
                # STEP 6: FETCH BATCH ATTENDANCE
                # ==================================

                attendance_ids = list(
                    BatchAttendance.objects
                    .filter(batch_id__in=batch_ids)
                    .values_list("id", flat=True)
                )

                # ==================================
                # STEP 7: SOFT DELETE ALL
                # PARTICIPANT ATTENDANCE
                # ==================================

                participant_attendance_count = (
                    ParticipantAttendance.objects
                    .filter(
                        attendance_id__in=attendance_ids,
                        is_active=True
                    )
                    .update(**soft_delete_data)
                )

                # ==================================
                # STEP 8: SOFT DELETE
                # BATCH ATTENDANCE
                # ==================================

                batch_attendance_count = (
                    BatchAttendance.objects
                    .filter(
                        id__in=attendance_ids,
                        is_active=True
                    )
                    .update(**soft_delete_data)
                )

                # ==================================
                # STEP 9: UPDATE BATCH STATUS
                # ==================================

                batch_updated_count = (
                    Batch.objects
                    .filter(
                        id__in=batch_ids,
                        is_active=True
                    )
                    .update(
                        status=target_status,
                        updated_by_id=master_user.id,
                        updated_at=now
                    )
                )

                if batch_updated_count != len(batch_ids):
                    raise RuntimeError(
                        "Failed to update all selected batches."
                    )

                # ==================================
                # STEP 10: SAVE REVERSAL REMARKS
                # ==================================

                history_records = [
                    BatchHistory(
                        batch=batch,
                        status=target_status,
                        remarks=reversal_remark,
                        created_by=master_user,
                        updated_by=master_user
                    )
                    for batch in batches
                ]

                BatchHistory.objects.bulk_create(
                    history_records
                )

                # ==================================
                # SUCCESS RESPONSE
                # ==================================

                result = {
                    "success": True,
                    "message": (
                        f"{batch_updated_count} batch(es) "
                        f"reversed successfully."
                    ),
                    "updated_batch_ids": batch_ids,
                    "new_status": target_status,
                    "remarks": reversal_remark,
                    "performed_by": username,
                    "soft_deleted_records": {
                        "batch_master_trainers": master_trainer_count,
                        "batch_ekyc": ekyc_count,
                        "participant_attendance": participant_attendance_count,
                        "batch_attendance": batch_attendance_count
                    }
                }

            return Response(
                result,
                status=status.HTTP_200_OK
            )

        except Exception:

            logger.exception(
                "Batch reversal failed for batch_ids=%s",
                batch_ids
            )

            return Response(
                {
                    "success": False,
                    "message": (
                        "Batch reversal failed. "
                        "All changes have been rolled back."
                    )
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
