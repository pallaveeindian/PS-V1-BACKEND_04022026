# pragati_setu/TMS/management/commands/update_batch_statuses.py

import time
import logging
from django.core.management.base import BaseCommand
from django.utils import timezone
from TMS.models import (
    Batch, 
    BatchBeneficiary, 
    BatchEkycVerification, 
    ParticipantAttendance, 
    BeneficiaryAttendanceSummary,
    TrainingPartnerAchievement
)

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Continuously updates batch statuses, tracks achievements, and calculates 80% attendance upon completion.'
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Memory set to prevent double-processing completed batches
        self.processed_completed_batches = set()

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting continuous batch status monitor for Pragati Setu...'))
        
        while True:
            try:
                self.process_batches()
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Error during processing: {e}"))
                logger.error(f"Batch status loop error: {e}")
            
            # Sleep for 5 seconds to prevent CPU pegging. 
            time.sleep(5)

    def process_batches(self):
        today = timezone.now().date()
        
        # ------------------------------------------------------
        # 1. AUTO-START BATCHES
        # Mark batches as ONGOING if start_date is today or earlier
        # ------------------------------------------------------
        batches_to_start = Batch.objects.filter(
            status='SCHEDULED',
            start_date__lte=today
        )

        for batch in batches_to_start:
            batch.status = 'ONGOING'
            batch.save(update_fields=['status'])
            self.stdout.write(self.style.SUCCESS(f"Marked Batch {batch.code or batch.id} as ONGOING."))

        # ------------------------------------------------------
        # 2. PROCESS COMPLETED BATCHES (LISTENER MODE)
        # Find batches the frontend has marked as COMPLETED.
        # Exclude those already processed (in memory or in DB) to prevent double-counting.
        # ------------------------------------------------------
        completed_batches = Batch.objects.filter(
            status='COMPLETED'
        ).exclude(
            id__in=BeneficiaryAttendanceSummary.objects.values_list('batch_id', flat=True)
        ).exclude(
            id__in=self.processed_completed_batches
        )

        for batch in completed_batches:
            # Immediately mark as processed in memory so we don't process it again in the next 5-second tick
            self.processed_completed_batches.add(batch.id)
            
            # --- AUTO-INCREMENT ACHIEVEMENT ---
            if batch.request and getattr(batch.request, 'partner', None) and batch.request.training_plan:
                achievement = TrainingPartnerAchievement.objects.filter(
                    partner=batch.request.partner,
                    training_plan=batch.request.training_plan
                ).order_by('-id').first()

                if achievement:
                    achievement.batches_completed += 1
                    achievement.date_achieved = today
                    achievement.save(update_fields=['batches_completed', 'date_achieved'])
                    self.stdout.write(self.style.SUCCESS(f"Incremented achievement for Partner {batch.request.partner.name}."))
            
            # --- TRIGGER ATTENDANCE CALCULATION ---
            self.calculate_batch_attendance(batch)

    def calculate_batch_attendance(self, batch):        
        training_plan = batch.request.training_plan if batch.request else None
        
        if not training_plan or not training_plan.no_of_days:
            self.stdout.write(self.style.WARNING(f"Skipping attendance for Batch {batch.id}: No training_plan or no_of_days set."))
            return

        total_days = training_plan.no_of_days
        batch_beneficiaries = BatchBeneficiary.objects.filter(batch=batch).select_related('beneficiary')

        for bb in batch_beneficiaries:
            # --- SURGICAL FIX: Use the BatchBeneficiary ID to match ParticipantAttendance ---
            p_id = str(bb.id)
            # ------------------------------------------------------------------------------
            is_dropout = False
            
            # 1. Check for DROP-OUT in eKYC
            ekyc = BatchEkycVerification.objects.filter(
                batch=batch, 
                participant_role='trainee', 
                participant_id=p_id
            ).first()

            if ekyc and ekyc.remarks and 'DROP-OUT' in ekyc.remarks.upper():
                is_dropout = True

            # 2. Calculate Present Days
            present_days = ParticipantAttendance.objects.filter(
                attendance__batch=batch,
                participant_role='trainee',
                participant_id=p_id,
                present=True
            ).count()

            # 3. Calculate Percentage
            attendance_percentage = (present_days / total_days) * 100
            
            # Ensure percentage doesn't exceed 100 if extra attendance was accidentally marked
            if attendance_percentage > 100.0:
                attendance_percentage = 100.0

            # 4. Determine Success (>= 80% AND not a dropout)
            is_successful = (attendance_percentage >= 80.0) and not is_dropout

            # 5. Update the base TRBeneficiary / BatchBeneficiary logic
            bb.attended = is_successful
            bb.save(update_fields=['attended'])
            
            bb.beneficiary.attended = is_successful
            bb.beneficiary.save(update_fields=['attended'])

            # 6. AUTO-POPULATE THE NEW SUMMARY MODEL
            BeneficiaryAttendanceSummary.objects.update_or_create(
                batch_beneficiary=bb,
                defaults={
                    'batch': batch,
                    'training_request': batch.request,
                    'total_training_days': total_days,
                    'days_present': present_days,
                    'attendance_percentage': attendance_percentage,
                    'is_dropout': is_dropout,
                    'is_successful': is_successful
                }
            )
            
        self.stdout.write(self.style.SUCCESS(f"Successfully calculated and populated summary models for Batch {batch.code or batch.id}."))