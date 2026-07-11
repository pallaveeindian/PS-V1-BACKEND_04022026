import time
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import OuterRef, Subquery, Q
from TMS.models import TRBeneficiary, TrainingRequest

class Command(BaseCommand):
    help = 'Atomically populates empty district_id and block_id in TRBeneficiary from their parent TrainingRequest.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING("Starting geographic data sync for TRBeneficiaries..."))
        start_time = time.time()

        # 1. Identify records needing an update (missing either district or block)
        target_beneficiaries = TRBeneficiary.objects.filter(
            Q(district__isnull=True) | Q(block__isnull=True)
        )

        initial_count = target_beneficiaries.count()
        if initial_count == 0:
            self.stdout.write(self.style.SUCCESS("All TRBeneficiaries already have geography data. Exiting."))
            return

        self.stdout.write(f"Found {initial_count} beneficiaries missing geography data.")
        self.stdout.write("Executing database-level atomic update...")

        # 2. Prepare Subqueries to fetch parent TR geography
        # OuterRef('training_id') links the subquery to the beneficiary's training_id
        parent_district_sq = TrainingRequest.objects.filter(
            id=OuterRef('training_id')
        ).values('district_id')[:1]

        parent_block_sq = TrainingRequest.objects.filter(
            id=OuterRef('training_id')
        ).values('block_id')[:1]

        # 3. Execute the update inside a strictly atomic transaction
        try:
            with transaction.atomic():
                # This single query updates all 24,000+ rows instantly at the database layer
                updated_count = target_beneficiaries.update(
                    district_id=Subquery(parent_district_sq),
                    block_id=Subquery(parent_block_sq)
                )
                
            execution_time = round(time.time() - start_time, 2)
            
            self.stdout.write(
                self.style.SUCCESS(
                    f"SUCCESS: {updated_count} TRBeneficiary records synchronized in {execution_time} seconds."
                )
            )
            
            # Post-check to see if any are still missing (e.g., if the parent TR itself had nulls)
            remaining_nulls = TRBeneficiary.objects.filter(
                Q(district__isnull=True) | Q(block__isnull=True)
            ).count()
            
            if remaining_nulls > 0:
                self.stdout.write(
                    self.style.WARNING(
                        f"NOTE: {remaining_nulls} beneficiaries still lack geography because their parent TrainingRequest is also missing it."
                    )
                )

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"CRITICAL FAILURE: Transaction rolled back. Error: {str(e)}")
            )