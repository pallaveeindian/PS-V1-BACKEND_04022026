import sys
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Sum

from TMS.models import (
    TrainingPlanSequence,
    TrainingRequest,
    TRBeneficiary,
    TRTrainer,
    TRStaff,
    TrainingPartnerTargets,
)

class Command(BaseCommand):
    help = "Sequentially propagates missing participants forward across steps (M1->M2->M3) for FY 2026-27 with strict duplicate prevention and atomic transaction safety."

    def add_arguments(self, parser):
        parser.add_argument(
            '--fy',
            type=str,
            default='2026-27',
            help='Financial Year to analyze (default: 2026-27)'
        )

    def handle(self, *args, **options):
        fy = options['fy']
        self.stdout.write(self.style.SUCCESS(f"=== STARTING SEQUENCE PARTICIPANT PROPAGATION & ANALYTICS (FY: {fy}) ==="))

        sequences = TrainingPlanSequence.objects.filter(is_active=True).select_related(
            'training_plan',
            'training_plan__theme',
            'next_training_plan'
        ).order_by('sequence_group_name', 'step_order')

        if not sequences.exists():
            self.stdout.write(self.style.WARNING("No active TrainingPlanSequence records found."))
            return

        groups = {}
        for seq in sequences:
            groups.setdefault(seq.sequence_group_name, []).append(seq)

        global_sr_no = 1

        # Helper function to compute & print the report table
        def print_analytics_table(title_prefix=""):
            self.stdout.write("\n" + "-" * 105)
            self.stdout.write(f"{title_prefix} ANALYTICS REPORT FOR GROUP: {group_name} (FY: {fy})")
            self.stdout.write("-" * 105)
            header_format = f"{'Sr No':<6} | {'Plan Name':<40} | {'Theme Name':<15} | {'Target':<8} | {'Onboarded':<10} | {'Descended':<10} | {'Lateral':<10}"
            self.stdout.write(header_format)
            self.stdout.write("-" * 105)

            current_sr = global_sr_no - len(steps)
            for s_idx, seq_item in enumerate(steps):
                c_plan = seq_item.training_plan
                target_val = TrainingPartnerTargets.objects.filter(is_active=True, training_plan=c_plan, financial_year=fy).aggregate(total=Sum('target_count'))['total'] or 0

                tr_qs_local = TrainingRequest.objects.filter(is_active=True, training_plan=c_plan, financial_year=fy)
                tr_ids_local = list(tr_qs_local.values_list('id', flat=True))

                b_c = TRBeneficiary.objects.filter(is_active=True, training_id__in=tr_ids_local).count()
                t_c = TRTrainer.objects.filter(is_active=True, training_id__in=tr_ids_local).count()
                s_c = TRStaff.objects.filter(is_active=True, training_id__in=tr_ids_local).count()
                onboarded_val = b_c + t_c + s_c

                descended_val = 0
                lateral_val = onboarded_val

                if s_idx > 0:
                    prev_plan_obj = steps[s_idx - 1].training_plan
                    prev_tr_ids_local = list(TrainingRequest.objects.filter(is_active=True, training_plan=prev_plan_obj, financial_year=fy).values_list('id', flat=True))

                    curr_bens_l = set(TRBeneficiary.objects.filter(is_active=True, training_id__in=tr_ids_local).exclude(lokos_member_code__isnull=True).values_list('lokos_shg_code', 'lokos_member_code'))
                    curr_trains_l = set(TRTrainer.objects.filter(is_active=True, training_id__in=tr_ids_local).values_list('trainer__mobile_no'))
                    curr_stfs_l = set(TRStaff.objects.filter(is_active=True, training_id__in=tr_ids_local).values_list('staff__employee_id'))

                    prev_bens_l = set(TRBeneficiary.objects.filter(is_active=True, training_id__in=prev_tr_ids_local).exclude(lokos_member_code__isnull=True).values_list('lokos_shg_code', 'lokos_member_code'))
                    prev_trains_l = set(TRTrainer.objects.filter(is_active=True, training_id__in=prev_tr_ids_local).values_list('trainer__mobile_no'))
                    prev_stfs_l = set(TRStaff.objects.filter(is_active=True, training_id__in=prev_tr_ids_local).values_list('staff__employee_id'))

                    matched_l = len((curr_bens_l & prev_bens_l) | (curr_trains_l & prev_trains_l) | (curr_stfs_l & prev_stfs_l))
                    descended_val = matched_l
                    lateral_val = max(0, onboarded_val - descended_val)

                theme_txt = c_plan.theme.theme_name if c_plan.theme else "—"
                self.stdout.write(f"{current_sr + s_idx:<6} | {c_plan.training_name[:40]:<40} | {theme_txt[:15]:<15} | {target_val:<8} | {onboarded_val:<10} | {descended_val:<10} | {lateral_val:<10}")
            self.stdout.write("-" * 105)

        # Wrap everything in a strict top-level atomic block to guarantee absolute rollback safety
        try:
            with transaction.atomic():
                for group_name, steps in groups.items():
                    self.stdout.write("\n" + "=" * 100)
                    self.stdout.write(self.style.NOTICE(f"PROCESSING SEQUENCE GROUP: {group_name} ({len(steps)} Steps)"))
                    self.stdout.write("=" * 100)

                    # Print BEFORE PROPAGATION Analytics
                    print_analytics_table(title_prefix="[BEFORE PROPAGATION]")

                    sid = transaction.savepoint()
                    try:
                        # Evaluate step-by-step transitions sequentially (M1 -> M2 -> M3...)
                        for i in range(len(steps) - 1):
                            current_seq = steps[i]
                            next_seq = steps[i + 1]

                            curr_plan = current_seq.training_plan
                            next_plan = next_seq.training_plan

                            self.stdout.write(f"\n--- Propagating Step {current_seq.step_order} ({curr_plan.training_name}) -> Step {next_seq.step_order} ({next_plan.training_name}) ---")

                            curr_tr_qs = TrainingRequest.objects.filter(is_active=True, training_plan=curr_plan, financial_year=fy)
                            next_tr_qs = TrainingRequest.objects.filter(is_active=True, training_plan=next_plan, financial_year=fy)

                            curr_tr_ids = list(curr_tr_qs.values_list('id', flat=True))
                            next_tr_ids = list(next_tr_qs.values_list('id', flat=True))

                            if not curr_tr_ids:
                                self.stdout.write(f"  -> No Training Requests found for step {current_seq.step_order}. Skipping.")
                                continue

                            sample_tr = curr_tr_qs.first()
                            if not sample_tr:
                                continue
                            t_type = sample_tr.training_type

                            # 1. Collect current step participants
                            curr_bens = {
                                (b.lokos_shg_code, b.lokos_member_code): b 
                                for b in TRBeneficiary.objects.filter(is_active=True, training_id__in=curr_tr_ids).exclude(lokos_member_code__isnull=True)
                            }
                            curr_trains = {
                                (t.trainer.mobile_no if t.trainer else t.mobile_no): t 
                                for t in TRTrainer.objects.filter(is_active=True, training_id__in=curr_tr_ids)
                            }
                            curr_stfs = {
                                (s.staff.employee_id if s.staff else s.full_name): s 
                                for s in TRStaff.objects.filter(is_active=True, training_id__in=curr_tr_ids)
                            }

                            curr_map = {}
                            if t_type == "BENEFICIARY": curr_map = curr_bens
                            elif t_type == "TRAINER": curr_map = curr_trains
                            elif t_type == "STAFF": curr_map = curr_stfs

                            # 2. Collect ALL existing participants across ALL training requests in the NEXT step (to prevent duplication)
                            next_keys = set()
                            if t_type == "BENEFICIARY":
                                next_keys = set(TRBeneficiary.objects.filter(is_active=True, training_id__in=next_tr_ids).exclude(lokos_member_code__isnull=True).values_list('lokos_shg_code', 'lokos_member_code'))
                            elif t_type == "TRAINER":
                                next_keys = set(TRTrainer.objects.filter(is_active=True, training_id__in=next_tr_ids).values_list('trainer__mobile_no'))
                            elif t_type == "STAFF":
                                next_keys = set(TRStaff.objects.filter(is_active=True, training_id__in=next_tr_ids).values_list('staff__employee_id'))

                            # 3. Find participants in current step NOT present in next step
                            missing_participants = [
                                obj for k, obj in curr_map.items() if k not in next_keys
                            ]

                            if missing_participants:
                                self.stdout.write(self.style.WARNING(f"  -> Found {len(missing_participants)} participants in Step {current_seq.step_order} missing in Step {next_seq.step_order}. Moving them forward..."))

                                grouped_missing = {}
                                for p in missing_participants:
                                    parent_tr = p.training
                                    group_key = (parent_tr.partner_id, parent_tr.district_id, parent_tr.block_id)
                                    grouped_missing.setdefault(group_key, []).append(p)

                                for (partner_id, district_id, block_id), parts in grouped_missing.items():
                                    target_tr = next_tr_qs.filter(
                                        partner_id=partner_id,
                                        district_id=district_id,
                                        block_id=block_id
                                    ).first()

                                    if not target_tr:
                                        sample_source_tr = parts[0].training
                                        target_tr = TrainingRequest.objects.create(
                                            financial_year=fy,
                                            training_plan=next_plan,
                                            partner=sample_source_tr.partner,
                                            training_type=t_type,
                                            level=sample_source_tr.level,
                                            status="BATCHING",
                                            district=sample_source_tr.district,
                                            block=sample_source_tr.block,
                                            remarks=f"Auto-propagated from sequence group '{group_name}' (Step {current_seq.step_order} -> {next_seq.step_order})",
                                            created_by=sample_source_tr.created_by
                                        )
                                        # Update local next_tr_ids list so newly created TR is included
                                        next_tr_ids.append(target_tr.id)
                                        self.stdout.write(f"    + Created TrainingRequest ID {target_tr.id} for Plan ID {next_plan.id} in District {district_id}")

                                    # Double check against existing participants in target_tr to ensure absolute zero repetition
                                    existing_in_tr_keys = set()
                                    if t_type == "BENEFICIARY":
                                        existing_in_tr_keys = set(TRBeneficiary.objects.filter(is_active=True, training=target_tr).exclude(lokos_member_code__isnull=True).values_list('lokos_shg_code', 'lokos_member_code'))
                                    elif t_type == "TRAINER":
                                        existing_in_tr_keys = set(TRTrainer.objects.filter(is_active=True, training=target_tr).values_list('trainer__mobile_no'))
                                    elif t_type == "STAFF":
                                        existing_in_tr_keys = set(TRStaff.objects.filter(is_active=True, training=target_tr).values_list('staff__employee_id'))

                                    filtered_parts = []
                                    for bp in parts:
                                        k_val = None
                                        if t_type == "BENEFICIARY": k_val = (bp.lokos_shg_code, bp.lokos_member_code)
                                        elif t_type == "TRAINER": k_val = (bp.trainer.mobile_no if bp.trainer else bp.mobile_no,)
                                        elif t_type == "STAFF": k_val = (bp.staff.employee_id if bp.staff else bp.full_name,)

                                        if k_val not in existing_in_tr_keys:
                                            filtered_parts.append(bp)

                                    if filtered_parts:
                                        if t_type == "BENEFICIARY":
                                            new_objs = [
                                                TRBeneficiary(
                                                    training=target_tr,
                                                    lokos_shg_code=bp.lokos_shg_code,
                                                    lokos_shg_name=bp.lokos_shg_name,
                                                    lokos_member_code=bp.lokos_member_code,
                                                    member_name=bp.member_name,
                                                    relation=bp.relation,
                                                    relation_name=bp.relation_name,
                                                    age=bp.age,
                                                    gender=bp.gender,
                                                    designation=bp.designation,
                                                    pld_status=bp.pld_status,
                                                    social_category=bp.social_category,
                                                    religion=bp.religion,
                                                    mobile=bp.mobile,
                                                    email=bp.email,
                                                    education=bp.education,
                                                    address=bp.address,
                                                    district=bp.district,
                                                    block=bp.block,
                                                    panchayat=bp.panchayat,
                                                    village=bp.village,
                                                    remarks=bp.remarks,
                                                    created_by=bp.created_by
                                                ) for bp in filtered_parts
                                            ]
                                            TRBeneficiary.objects.bulk_create(new_objs)
                                            self.stdout.write(f"      Added {len(new_objs)} unique beneficiaries to TrainingRequest ID {target_tr.id}")

                                        elif t_type == "TRAINER":
                                            new_objs = [
                                                TRTrainer(
                                                    training=target_tr,
                                                    trainer=tp.trainer,
                                                    full_name=tp.full_name,
                                                    mobile_no=tp.mobile_no,
                                                    aadhaar_no=tp.aadhaar_no,
                                                    district=tp.district,
                                                    block=tp.block,
                                                    remarks=tp.remarks,
                                                    created_by=tp.created_by
                                                ) for tp in filtered_parts
                                            ]
                                            TRTrainer.objects.bulk_create(new_objs)
                                            self.stdout.write(f"      Added {len(new_objs)} unique trainers to TrainingRequest ID {target_tr.id}")

                                        elif t_type == "STAFF":
                                            new_objs = [
                                                TRStaff(
                                                    training=target_tr,
                                                    staff=sp.staff,
                                                    full_name=sp.full_name,
                                                    designation=sp.designation,
                                                    theme=sp.theme,
                                                    district=sp.district,
                                                    block=sp.block,
                                                    remarks=sp.remarks,
                                                    created_by=sp.created_by
                                                ) for sp in filtered_parts
                                            ]
                                            TRStaff.objects.bulk_create(new_objs)
                                            self.stdout.write(f"      Added {len(new_objs)} unique staff to TrainingRequest ID {target_tr.id}")
                            else:
                                self.stdout.write(f"  -> All participants from Step {current_seq.step_order} are already present in Step {next_seq.step_order}.")

                    except Exception as e:
                        transaction.savepoint_rollback(sid)
                        self.stdout.write(self.style.ERROR(f"✖ Error processing sequence group '{group_name}': {e}"))
                        raise e

                    # Print AFTER PROPAGATION Analytics
                    print_analytics_table(title_prefix="[AFTER PROPAGATION]")
                    global_sr_no += len(steps)

                    # =====================================================================
                    # INTERACTIVE CHECKPOINT PROMPT
                    # =====================================================================
                    while True:
                        user_input = input(f"\n[ATOMIC CHECKPOINT] Commit changes for sequence group '{group_name}'? [y/N/q (quit script)]: ").strip().lower()
                        if user_input == 'y':
                            transaction.savepoint_commit(sid)
                            self.stdout.write(self.style.SUCCESS(f"✔ Committed changes for sequence group '{group_name}' to Database."))
                            break
                        elif user_input in ['n', '']:
                            transaction.savepoint_rollback(sid)
                            self.stdout.write(self.style.WARNING(f"✘ Rolled back changes for sequence group '{group_name}'."))
                            break
                        elif user_input == 'q':
                            transaction.savepoint_rollback(sid)
                            self.stdout.write(self.style.ERROR("Exiting script per user request. All pending changes rolled back."))
                            sys.exit(0)
                        else:
                            print("Invalid input. Please enter 'y' (yes), 'n' (no/rollback), or 'q' (quit).")

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"✖ Fatal transaction error encountered: {e}. Entire script rolled back."))
            sys.exit(1)

        self.stdout.write(self.style.SUCCESS("\n=== SEQUENCE PROPAGATION & ANALYTICS COMPLETED ==="))