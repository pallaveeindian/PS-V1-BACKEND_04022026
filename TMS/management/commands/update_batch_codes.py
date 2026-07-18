from django.core.management.base import BaseCommand
from django.db import transaction
from collections import defaultdict
from TMS.models import Batch 

class Command(BaseCommand):
    help = 'Retrospectively updates all existing batch codes to the new format with verbose logging and rollback.'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.WARNING("Starting batch code recalculation..."))

        # Dictionary to track the sequence counter for each unique prefix
        prefix_counters = defaultdict(int)
        batches_to_update = []
        original_codes = {}

        # 1. Fetch all batches ordered by ID to ensure chronological sequencing
        # Using select_related to prevent N+1 query problems
        batches = Batch.objects.select_related(
            'district', 'block', 'partner', 'training_plan'
        ).order_by('id')

        self.stdout.write(self.style.SUCCESS(f"Found {batches.count()} total batches to process.\n"))
        self.stdout.write("-" * 85)
        self.stdout.write(f"{'ID':<6} | {'OLD CODE':<35} | {'NEW CODE'}")
        self.stdout.write("-" * 85)

        for batch in batches:
            # Store original code for fallback/revert purposes
            original_codes[batch.id] = batch.code

            # Step A: Extract Financial Year Short Code (e.g., '2026-27' -> '26')
            fy_code = "XX"
            if batch.financial_year and len(batch.financial_year) >= 4:
                fy_code = batch.financial_year[2:4]

            # Step B: Extract District Short Name
            district = "XXX"
            if batch.district:
                district = batch.district.district_short_name_en or "XXX"

            # Step C: Extract Training Partner Short Name
            tp = "XXX"
            if batch.partner:
                tp = batch.partner.tp_short_name or "XXX"

            # Step D: Extract Plan ID
            plan_id = batch.training_plan.id if batch.training_plan else 0

            # Step E: Determine Prefix Logic Path (FIXED ORDER)
            if batch.batch_type == 'COMBINED':
                # Path 1: Combined batch (Catches combined batches even if they lack a block)
                prefix = f"{fy_code}-{district}-COMB-{tp}-{plan_id}"
            
            elif not batch.block:
                # Path 2: Separate Batch but NO block given
                prefix = f"{fy_code}-UP-{district}-{tp}-{plan_id}"
            
            else:
                # Path 3: Separate batch WITH block
                block_name = batch.block.block_name_local or "XXX"
                prefix = f"{fy_code}-{district}-{block_name}-{tp}-{plan_id}"

            # Step F: Generate new sequential number for this specific prefix
            prefix_counters[prefix] += 1
            new_seq = str(prefix_counters[prefix]).zfill(4)

            # Assign new code
            new_code = f"{prefix}-{new_seq}"
            
            # Add to update list if it changed
            if str(batch.code) != str(new_code):
                self.stdout.write(f"{batch.id:<6} | {str(batch.code):<35} | {new_code}")
                batch.code = new_code
                batches_to_update.append(batch)

        self.stdout.write("-" * 85)

        # 2. Execute the Database Update
        if not batches_to_update:
            self.stdout.write(self.style.SUCCESS("\nAll batches are already up to date. No changes made."))
            return

        self.stdout.write(self.style.WARNING(f"\nPrepared {len(batches_to_update)} batches for update."))
        
        try:
            with transaction.atomic():
                # We use bulk_update to write them all at once extremely fast
                Batch.objects.bulk_update(batches_to_update, ['code'], batch_size=1000)
            self.stdout.write(self.style.SUCCESS("Successfully applied new codes to the database!"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Database error during update: {e}"))
            return

        # 3. Fallback / Revert Prompt
        self.stdout.write(self.style.WARNING(
            "\nReview the output table above. If there are any formatting errors or logic issues, "
            "you can revert the database back to the original codes right now."
        ))
        
        revert_choice = input("Do you want to REVERT these changes back to the original codes? (y/N): ")

        if revert_choice.strip().lower() == 'y':
            self.stdout.write(self.style.WARNING("Reverting changes... Please wait."))
            
            revert_list = []
            for batch in batches_to_update:
                batch.code = original_codes[batch.id]
                revert_list.append(batch)
            
            try:
                with transaction.atomic():
                    Batch.objects.bulk_update(revert_list, ['code'], batch_size=1000)
                self.stdout.write(self.style.SUCCESS("Revert successful! All original codes have been restored."))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Critical error during revert: {e}"))
        else:
            self.stdout.write(self.style.SUCCESS("Changes committed permanently! You can exit now."))