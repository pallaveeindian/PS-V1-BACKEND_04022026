import logging
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count, Q
from TMS.models import TrainingRequest, TRBeneficiary, TRTrainer, TRStaff

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Scans for and safely soft-deletes (is_active=False) active Training Requests that have absolutely no participants or enrolled members.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING('\n[INIT] Commencing nightly scan for empty Training Requests...'))

        # Fetch all currently active Training Requests
        active_trs = TrainingRequest.objects.filter(is_active=True)
        total_active = active_trs.count()
        
        self.stdout.write(f" -> Found {total_active} currently active Training Requests to evaluate.\n")

        deactivated_count = 0
        error_count = 0

        # We process one by one to ensure the participant count logic exactly mirrors 
        # the TrainingRequestListSerializer's get_participant_count/enrolled_count logic.
        for tr in active_trs:
            try:
                participant_count = 0
                enrolled_count = 0

                # 1. Determine exact counts based on training_type
                if tr.training_type == 'BENEFICIARY':
                    base_qs = TRBeneficiary.objects.filter(training=tr, is_active=True)
                    participant_count = base_qs.count()
                    enrolled_count = base_qs.filter(CB_selected=True).count()
                    
                elif tr.training_type == 'TRAINER':
                    base_qs = TRTrainer.objects.filter(training=tr, is_active=True)
                    participant_count = base_qs.count()
                    enrolled_count = base_qs.filter(CB_selected=True).count()
                    
                elif tr.training_type == 'STAFF':
                    base_qs = TRStaff.objects.filter(training=tr, is_active=True)
                    participant_count = base_qs.count()
                    enrolled_count = base_qs.filter(CB_selected=True).count()

                # 2. Deactivation Condition
                if participant_count == 0 and enrolled_count == 0:
                    with transaction.atomic():
                        # We use update() to bypass full model save signals if they are heavy, 
                        # or you can use .save(update_fields=['is_active']) if you prefer.
                        # Using standard soft-delete standard for your mixin:
                        tr.is_active = False
                        tr.save(update_fields=['is_active', 'updated_at'])
                        
                        deactivated_count += 1
                        self.stdout.write(
                            self.style.SUCCESS(f" [DEACTIVATED] TR ID #{tr.id} (Type: {tr.training_type}) - Reason: 0 Participants.")
                        )
                        
            except Exception as e:
                error_count += 1
                logger.error(f"Error processing TR #{tr.id}: {str(e)}")
                self.stdout.write(self.style.ERROR(f" [ERROR] Failed to process TR ID #{tr.id}: {str(e)}"))

        # Summary Output
        self.stdout.write("\n" + "="*50)
        self.stdout.write(self.style.WARNING("               SCAN COMPLETE"))
        self.stdout.write("="*50)
        self.stdout.write(self.style.SUCCESS(f" 🟢 Successfully Deactivated: {deactivated_count}"))
        if error_count > 0:
            self.stdout.write(self.style.ERROR(f" 🔴 Errors Encountered: {error_count}"))
        else:
            self.stdout.write(self.style.SUCCESS(" 🟢 Errors Encountered: 0"))
        self.stdout.write("="*50 + "\n")