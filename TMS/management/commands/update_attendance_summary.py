import logging
from django.core.management.base import BaseCommand
from django.db import transaction
from TMS.models import (
    Batch, 
    BatchBeneficiary, 
    BatchTrainer,
    BatchStaff, 
    BatchEkycVerification, 
    ParticipantAttendance, 
    BeneficiaryAttendanceSummary
)

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Recalculates attendance summaries and success flags for all participants in COMPLETED batches based on the strict Attendance Rules Matrix.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING('Starting attendance recalculation for all COMPLETED batches...'))
        
        completed_batches = Batch.objects.filter(status='COMPLETED').select_related('training_plan')
        
        total_batches = completed_batches.count()
        self.stdout.write(self.style.SUCCESS(f"Found {total_batches} COMPLETED batches to process."))

        count = 0
        for batch in completed_batches:
            try:
                with transaction.atomic():
                    self.calculate_batch_attendance(batch)
                count += 1
                if count % 10 == 0:
                    self.stdout.write(f"Processed {count}/{total_batches} batches...")
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Error processing Batch ID {batch.id}: {str(e)}"))
                logger.error(f"Error recalculating attendance for Batch {batch.id}: {e}")

        self.stdout.write(self.style.SUCCESS('Finished recalculating attendance for all COMPLETED batches.'))

    def calculate_batch_attendance(self, batch):        
        training_plan = batch.training_plan
        
        if not training_plan or not training_plan.no_of_days:
            self.stdout.write(self.style.WARNING(f"  -> Skipping Batch {batch.id}: No training_plan or no_of_days set."))
            return

        total_days = training_plan.no_of_days

        # --- Strict Rules Matrix for Minimum Attendance ---
        MIN_ATTENDANCE_REQ = {
            1: 1,
            2: 2,
            3: 3,
            4: 3,
            5: 4,
            6: 5,
            7: 6,
            8: 7,
            9: 8,
            10: 8,
            11: 9,
            12: 10,
            13: 11,
            14: 12,
            15: 12
        }
        
        # Fallback to pure 80% math if day count > 15
        required_days = MIN_ATTENDANCE_REQ.get(total_days, max(1, int(total_days * 0.8)))
        
        # --- TRAINEES (Beneficiaries) ---
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
            
            is_successful = (present_days >= required_days) and not is_dropout

            bb.attended = is_successful
            bb.save(update_fields=['attended'])
            
            if bb.beneficiary:
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
            
            is_successful = (present_days >= required_days) and not is_dropout

            bt.attended = is_successful
            bt.save(update_fields=['attended'])
            
            if bt.trainer:
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
            
            is_successful = (present_days >= required_days) and not is_dropout

            bs.attended = is_successful
            bs.save(update_fields=['attended'])
            
            if bs.staff:
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