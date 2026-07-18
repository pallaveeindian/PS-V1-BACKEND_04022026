from django.core.management.base import BaseCommand
from django.db import transaction
from TMS.models import Batch 

class Command(BaseCommand):
    help = 'Retrospectively updates the level field for all existing batches based on their code structure.'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.WARNING("Starting batch level recalculation..."))

        batches_to_update = []
        original_levels = {}

        # 1. Fetch all batches
        # Using select_related is not strictly necessary here since we only read code/type/level, 
        # but it's safe. We filter out batches that don't have a code yet.
        batches = Batch.objects.exclude(code__isnull=True).order_by('id')

        self.stdout.write(self.style.SUCCESS(f"Found {batches.count()} batches with codes to evaluate.\n"))
        
        # Table Header
        self.stdout.write("-" * 95)
        self.stdout.write(f"{'ID':<6} | {'BATCH CODE':<35} | {'PARTICIPANT':<15} | {'OLD LEVEL':<12} | {'NEW LEVEL':<12}")
        self.stdout.write("-" * 95)

        for batch in batches:
            # Store original level for fallback/revert purposes
            original_levels[batch.id] = batch.level

            code = str(batch.code).upper()
            part_type = str(batch.participant_type).upper() if batch.participant_type else "UNKNOWN"
            new_level = None

            # Logic Rules based on your exact requirements:
            if "-UP-" in code:
                # Rule 1: No block given -> DISTRICT
                new_level = "DISTRICT"
            
            elif "-COMB-" in code:
                # Rule 2: Combined batch
                if part_type == "TRAINER":
                    new_level = "DISTRICT"
                else:
                    # If BENEFICIARY (or default fallback), it's a Block-level combined batch
                    new_level = "BLOCK"
            
            else:
                # Rule 3: Specific block name is present in the code -> BLOCK
                new_level = "BLOCK"

            # Add to update list if the level needs to change
            old_level_display = str(batch.level) if batch.level else "None"
            
            if batch.level != new_level:
                self.stdout.write(f"{batch.id:<6} | {code:<35} | {part_type:<15} | {old_level_display:<12} | {new_level:<12}")
                batch.level = new_level
                batches_to_update.append(batch)

        self.stdout.write("-" * 95)

        # 2. Execute the Database Update
        if not batches_to_update:
            self.stdout.write(self.style.SUCCESS("\nAll batches already have the correct level. No changes made."))
            return

        self.stdout.write(self.style.WARNING(f"\nPrepared {len(batches_to_update)} batches for level update."))
        
        try:
            with transaction.atomic():
                # We use bulk_update to write them all at once extremely fast
                # We update ONLY the 'level' field
                Batch.objects.bulk_update(batches_to_update, ['level'], batch_size=1000)
            self.stdout.write(self.style.SUCCESS("Successfully applied new levels to the database!"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Database error during update: {e}"))
            return

        # 3. Fallback / Revert Prompt
        self.stdout.write(self.style.WARNING(
            "\nReview the output table above. If the levels look incorrect, "
            "you can revert the database back to the original states right now."
        ))
        
        revert_choice = input("Do you want to REVERT these changes back to the original levels? (y/N): ")

        if revert_choice.strip().lower() == 'y':
            self.stdout.write(self.style.WARNING("Reverting changes... Please wait."))
            
            revert_list = []
            for batch in batches_to_update:
                batch.level = original_levels[batch.id]
                revert_list.append(batch)
            
            try:
                with transaction.atomic():
                    Batch.objects.bulk_update(revert_list, ['level'], batch_size=1000)
                self.stdout.write(self.style.SUCCESS("Revert successful! All original levels have been restored."))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Critical error during revert: {e}"))
        else:
            self.stdout.write(self.style.SUCCESS("Changes committed permanently! You can exit now."))