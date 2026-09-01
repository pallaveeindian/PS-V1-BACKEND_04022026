# pragati_setu/TMS/management/commands/update_batch_statuses.py

import time
import logging
from django.core.management.base import BaseCommand
from django.utils import timezone
from TMS.models import (
    Batch, 
    BatchBeneficiary, 
    BatchTrainer,
    BatchStaff, 
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
            if batch.partner and batch.training_plan:
                
                # Extract financial year directly from the batch
                fy = batch.financial_year
                
                # Build filter query for the exact partner and plan
                qs = TrainingPartnerAchievement.objects.filter(
                    partner=batch.partner,
                    training_plan=batch.training_plan
                )
                
                # Enforce the strict Financial Year boundary
                if fy:
                    qs = qs.filter(financial_year=fy)
                    
                achievement = qs.order_by('-id').first()

                if achievement:
                    achievement.batches_completed += 1
                    achievement.date_achieved = today
                    achievement.save(update_fields=['batches_completed', 'date_achieved'])
                    self.stdout.write(self.style.SUCCESS(f"Incremented achievement for Partner {batch.partner.name} (FY: {achievement.financial_year})."))
                else:
                    self.stdout.write(self.style.WARNING(f"No achievement record found for Partner {batch.partner.name} under FY {fy}."))

            # Permanently flag as counted to survive daemon restarts
            batch.is_achievement_counted = True
            batch.save(update_fields=['is_achievement_counted'])


    def calculate_batch_attendance(self, batch):        
        training_plan = batch.training_plan
        
        if not training_plan or not training_plan.no_of_days:
            self.stdout.write(self.style.WARNING(f"Skipping attendance for Batch {batch.id}: No training_plan or no_of_days set."))
            return

        total_days = training_plan.no_of_days

        # --- SURGICAL ADDITION: Strict Rules Matrix for Minimum Attendance ---
        MIN_ATTENDANCE_REQ = {
            1: 1,
            2: 2,
            3: 3,
            4: 3,
            5: 4,
            6: 5,
            7: 6,
            8: 7,
            9: 7,
            10: 8,
            11: 9,
            12: 10,
            13: 11,
            14: 12,
            15: 12
        }
        
        # Fallback to pure 80% math if day count > 15
        required_days = MIN_ATTENDANCE_REQ.get(total_days, max(1, int(total_days * 0.8)))
        
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

            attendance_percentage = min((present_days / total_days) * 100, 100.0) if total_days > 0 else 0.0
            
            # --- SURGICAL FIX: Applied Rules Matrix Check ---
            is_successful = (present_days >= required_days) and not is_dropout

            bb.attended = is_successful
            bb.save(update_fields=['attended'])
            
            bb.beneficiary.attended = is_successful
            bb.beneficiary.save(update_fields=['attended'])

            BeneficiaryAttendanceSummary.objects.update_or_create(
                batch_beneficiary=bb,
                defaults={
                    'batch': batch, 'training_request': bb.training_request, 'total_training_days': total_days,
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

            attendance_percentage = min((present_days / total_days) * 100, 100.0) if total_days > 0 else 0.0
            
            # --- SURGICAL FIX: Applied Rules Matrix Check ---
            is_successful = (present_days >= required_days) and not is_dropout

            bt.attended = is_successful
            bt.save(update_fields=['attended'])
            
            bt.trainer.attended = is_successful
            bt.trainer.save(update_fields=['attended'])

            BeneficiaryAttendanceSummary.objects.update_or_create(
                batch_trainer=bt,
                defaults={
                    'batch': batch, 'training_request': bt.training_request, 'total_training_days': total_days,
                    'days_present': present_days, 'attendance_percentage': attendance_percentage,
                    'is_dropout': is_dropout, 'is_successful': is_successful
                }
            )

        # --- STAFF ---
        batch_staff = BatchStaff.objects.filter(batch=batch).select_related('staff')
        for bs in batch_staff:
            p_id = str(bs.id)
            is_dropout = False
            
            ekyc = BatchEkycVerification.objects.filter(
                batch=batch, participant_role='trainee', participant_id=p_id
            ).first()

            if ekyc and ekyc.remarks and 'DROP-OUT' in ekyc.remarks.upper():
                is_dropout = True

            present_days = ParticipantAttendance.objects.filter(
                attendance__batch=batch, participant_role='trainee', participant_id=p_id, present=True
            ).count()

            attendance_percentage = min((present_days / total_days) * 100, 100.0) if total_days > 0 else 0.0
            
            # --- SURGICAL FIX: Applied Rules Matrix Check ---
            is_successful = (present_days >= required_days) and not is_dropout

            bs.attended = is_successful
            bs.save(update_fields=['attended'])
            
            bs.staff.attended = is_successful
            bs.staff.save(update_fields=['attended'])

            BeneficiaryAttendanceSummary.objects.update_or_create(
                batch_staff=bs,
                defaults={
                    'batch': batch, 'training_request': bs.training_request, 'total_training_days': total_days,
                    'days_present': present_days, 'attendance_percentage': attendance_percentage,
                    'is_dropout': is_dropout, 'is_successful': is_successful
                }
            )

        self.stdout.write(self.style.SUCCESS(f"Successfully calculated and populated summary models for Batch {batch.code or batch.id}."))