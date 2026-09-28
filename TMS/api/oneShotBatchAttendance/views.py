from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.db import transaction
from django.shortcuts import get_object_or_404
import datetime

from core.models import MasterUser
from TMS.models import Batch, BatchAttendance, ParticipantAttendance
from .serializers import OneShotBatchAttendanceSerializer

class OneShotBatchAttendanceAPIView(APIView):
    """
    Records daily attendance for ALL participants in a single atomic transaction.
    Automatically generates 'Absent' records for any provided missing dates.
    Auto-completes the batch if the processing hits the batch end_date.
    """
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        serializer = OneShotBatchAttendanceSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        batch_id = data['batch_id']
        target_date = data['date']
        missing_dates = data.get('missing_dates', [])
        records = data['participant_records']
        ruser = request.user
        user = MasterUser.objects.get(username=ruser.username)

        # 1. Fetch Batch with lock to prevent race conditions on status updates
        batch = get_object_or_404(Batch.objects.select_for_update(), id=batch_id)

        # 2. Process Missing Dates (Auto-Mark Absent)
        for m_date in missing_dates:
            batt_missing, _ = BatchAttendance.objects.get_or_create(
                batch=batch, 
                date=m_date
            )
            
            # Bulk create/update absent records for everyone
            for rec in records:
                ParticipantAttendance.objects.update_or_create(
                    attendance=batt_missing,
                    participant_id=rec['participant_id'],
                    participant_role=rec['participant_role'],
                    defaults={
                        'participant_name': rec.get('participant_name', ''),
                        'present': False, # Strictly absent for missed days
                        'created_by': user
                    }
                )

        # 3. Process Target Date (Actual Attendance)
        batt_today, _ = BatchAttendance.objects.get_or_create(
            batch=batch, 
            date=target_date
        )
        
        for rec in records:
            ParticipantAttendance.objects.update_or_create(
                attendance=batt_today,
                participant_id=rec['participant_id'],
                participant_role=rec['participant_role'],
                defaults={
                    'participant_name': rec.get('participant_name', ''),
                    'present': rec['present'],
                    'created_by': user
                }
            )

        # 4. Auto-Completion Check
        # If the batch end_date matches today OR was caught up in the missing dates
        dates_processed = [target_date] + missing_dates
        if batch.end_date and batch.end_date in dates_processed:
            if batch.status == 'ONGOING':
                batch.status = 'COMPLETED'
                batch.save(update_fields=['status'])

        return Response({
            "message": "Attendance successfully recorded in one shot.",
            "dates_processed": dates_processed,
            "batch_status": batch.status
        }, status=status.HTTP_201_CREATED)