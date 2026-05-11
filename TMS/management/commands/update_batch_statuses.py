# pragati_setu/TMS/management/commands/update_batch_statuses.py

import time
import logging
from django.core.management.base import BaseCommand
from django.utils import timezone
from TMS.models import (
    Batch, 
    BatchBeneficiary, 
    BatchTrainer,
    BatchEkycVerification, 
    ParticipantAttendance, 
    BeneficiaryAttendanceSummary,
    BatchMasterTrainer,
    TrainingPartnerAchievement
)

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Continuously updates batch statuses, tracks achievements on closure, and calculates attendance.'
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Memory set for attendance to prevent double-processing within the same uptime
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
        # 2. PROCESS COMPLETED BATCHES (ATTENDANCE & TRAINERS ONLY)
        # ------------------------------------------------------
        completed_batches = Batch.objects.filter(
            status='COMPLETED'
        ).exclude(
            id__in=BeneficiaryAttendanceSummary.objects.values_list('batch_id', flat=True)
        ).exclude(
            id__in=self.processed_completed_batches
        )

        for batch in completed_batches:
            self.processed_completed_batches.add(batch.id)
            
            # --- FLIP MASTER TRAINER STATUS TO AVAILABLE ---
            trainers_updated = BatchMasterTrainer.objects.filter(batch=batch).update(status='AVAILABLE')
            if trainers_updated > 0:
                self.stdout.write(self.style.SUCCESS(f"Flipped {trainers_updated} Master Trainer(s) to AVAILABLE for Batch {batch.code or batch.id}."))

            # --- TRIGGER ATTENDANCE CALCULATION ---
            self.calculate_batch_attendance(batch)


        # ------------------------------------------------------
        # 3. PROCESS CLOSED BATCHES (ACHIEVEMENTS)
        # ------------------------------------------------------
        # Requires: Batch is CLOSED, Report is DMM_SIGNED, and we haven't counted it yet.
        closed_batches = Batch.objects.filter(
            status='CLOSED',
            batch_report__status='DMM_SIGNED', # Follows the reverse relation to BatchReport
            is_achievement_counted=False
        )

        for batch in closed_batches:
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

            # Permanently flag as counted to survive daemon restarts
            batch.is_achievement_counted = True
            batch.save(update_fields=['is_achievement_counted'])


    def calculate_batch_attendance(self, batch):        
        training_plan = batch.request.training_plan if batch.request else None
        
        if not training_plan or not training_plan.no_of_days:
            self.stdout.write(self.style.WARNING(f"Skipping attendance for Batch {batch.id}: No training_plan or no_of_days set."))
            return

        total_days = training_plan.no_of_days
        
        # --- TRAINEES ---
        batch_beneficiaries = BatchBeneficiary.objects.filter(batch=batch).select_related('beneficiary')
        for bb in batch_beneficiaries:
            p_id = str(bb.id)
            is_dropout = False
            
            ekyc = BatchEkycVerification.objects.filter(
                batch=batch, participant_role='trainee', participant_id=p_id
            ).first()

            if ekyc and ekyc.remarks and 'DROP-OUT' in ekyc.remarks.upper():
                is_dropout = True

            present_days = ParticipantAttendance.objects.filter(
                attendance__batch=batch, participant_role='trainee', participant_id=p_id, present=True
            ).count()

            attendance_percentage = min((present_days / total_days) * 100, 100.0)
            is_successful = (attendance_percentage >= 80.0) and not is_dropout

            bb.attended = is_successful
            bb.save(update_fields=['attended'])
            
            bb.beneficiary.attended = is_successful
            bb.beneficiary.save(update_fields=['attended'])

            BeneficiaryAttendanceSummary.objects.update_or_create(
                batch_beneficiary=bb,
                defaults={
                    'batch': batch, 'training_request': batch.request, 'total_training_days': total_days,
                    'days_present': present_days, 'attendance_percentage': attendance_percentage,
                    'is_dropout': is_dropout, 'is_successful': is_successful
                }
            )
            
        # --- TRAINERS (TOT) ---
        batch_trainers = BatchTrainer.objects.filter(batch=batch).select_related('trainer')
        for bt in batch_trainers:
            p_id = str(bt.id)
            is_dropout = False
            
            ekyc = BatchEkycVerification.objects.filter(
                batch=batch, participant_role='trainee', participant_id=p_id
            ).first()

            if ekyc and ekyc.remarks and 'DROP-OUT' in ekyc.remarks.upper():
                is_dropout = True

            present_days = ParticipantAttendance.objects.filter(
                attendance__batch=batch, participant_role='trainee', participant_id=p_id, present=True
            ).count()

            attendance_percentage = min((present_days / total_days) * 100, 100.0)
            is_successful = (attendance_percentage >= 80.0) and not is_dropout

            bt.attended = is_successful
            bt.save(update_fields=['attended'])
            
            bt.trainer.attended = is_successful
            bt.trainer.save(update_fields=['attended'])

            BeneficiaryAttendanceSummary.objects.update_or_create(
                batch_trainer=bt,
                defaults={
                    'batch': batch, 'training_request': batch.request, 'total_training_days': total_days,
                    'days_present': present_days, 'attendance_percentage': attendance_percentage,
                    'is_dropout': is_dropout, 'is_successful': is_successful
                }
            )

        self.stdout.write(self.style.SUCCESS(f"Successfully calculated and populated summary models for Batch {batch.code or batch.id}."))