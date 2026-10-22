from django.core.management.base import BaseCommand
from django.db import transaction
from TMS.models import TrainingPlan, TrainingPlanSequence

class Command(BaseCommand):
    help = "Populates sequential training plan relationships (Recurring Sequences) based on predefined module progressions."

    def handle(self, *args, **options):
        # Define the exact mapping sequences requested
        sequences_data = [
            {
                "group_name": "Samuh Sakhi Training",
                "plan_ids": [99, 100, 101, 103] # M1 -> M2 -> M3 -> M4
            },
            {
                "group_name": "VO EC Member Training",
                "plan_ids": [97, 98] # M1 -> M2
            },
            {
                "group_name": "VO BK Training",
                "plan_ids": [95, 96] # M1 -> M2
            },
            {
                "group_name": "SHG BK Training",
                "plan_ids": [153, 154] # M1 -> M2
            },
            {
                "group_name": "Swasthy Sakhi Training",
                "plan_ids": [32, 33, 35] # M1(S1-S3) -> M1(S4-S5) -> M2
            },
            {
                "group_name": "MCLF Visioning",
                "plan_ids": [66, 67, 68] # 1 -> 2 -> 3
            },
            {
                "group_name": "MCLF AAP",
                "plan_ids": [69, 70] # 1 -> 2
            },
            {
                "group_name": "MCLF Pre-Visioning",
                "plan_ids": [116, 117, 118] # 1 -> 2 -> 3
            },
        ]

        with transaction.atomic():
            # Clear out old active mappings to prevent duplication conflicts during re-runs
            TrainingPlanSequence.objects.all().soft_delete() if hasattr(TrainingPlanSequence, 'soft_delete') else TrainingPlanSequence.objects.all().delete()
            
            created_count = 0

            for seq in sequences_data:
                group_name = seq["group_name"]
                plan_ids = seq["plan_ids"]
                
                for index, plan_id in enumerate(plan_ids):
                    try:
                        plan_obj = TrainingPlan.objects.get(pk=plan_id)
                    except TrainingPlan.DoesNotExist:
                        self.stdout.write(self.style.WARNING(f"⚠️ TrainingPlan ID {plan_id} not found in database. Skipping..."))
                        continue

                    step_order = index + 1
                    
                    # Resolve next plan pointer if it exists in the sequence
                    next_plan_obj = None
                    if index + 1 < len(plan_ids):
                        next_plan_id = plan_ids[index + 1]
                        try:
                            next_plan_obj = TrainingPlan.objects.get(pk=next_plan_id)
                        except TrainingPlan.DoesNotExist:
                            pass

                    # Create sequence record
                    TrainingPlanSequence.objects.create(
                        sequence_group_name=group_name,
                        training_plan=plan_obj,
                        step_order=step_order,
                        next_training_plan=next_plan_obj,
                        is_active=True
                    )
                    created_count += 1
                    self.stdout.write(f"✔ Mapped '{group_name}' Step {step_order} -> Plan ID: {plan_id}")

            self.stdout.write(self.style.SUCCESS(f"Successfully populated {created_count} training plan sequence steps."))