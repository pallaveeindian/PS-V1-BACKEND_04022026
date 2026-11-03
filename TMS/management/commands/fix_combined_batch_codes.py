import sys
import uuid
from collections import defaultdict
from django.core.management.base import BaseCommand
from django.db import transaction

from TMS.models import (
    Batch,
    BatchBlockCoverage,
    BatchBeneficiary,
    BatchTrainer,
    BatchStaff,
    DistrictTP,
    TrainingPartner,
)


class Command(BaseCommand):
    help = (
        "Analyzes all active COMBINED batches, resolves missing district/partner relations, "
        "and assigns properly sequenced '{FY}-{DIST}-COMB-{TP}-{PLAN}-{SEQ}' batch codes atomically."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--fy",
            type=str,
            default=None,
            help="Optional: Filter COMBINED batches by a specific Financial Year (e.g., '2026-27').",
        )

    def resolve_district(self, batch):
        """Attempts to resolve missing district on a COMBINED batch using safe fallbacks."""
        if batch.district:
            return batch.district, "Batch.district"

        if batch.block and getattr(batch.block, "district", None):
            return batch.block.district, "Batch.block.district"

        if batch.centre and getattr(batch.centre, "district", None):
            return batch.centre.district, "Batch.centre.district"

        # Check BatchBlockCoverage
        cov = (
            BatchBlockCoverage.objects.filter(
                batch=batch, is_active=True, block__district__isnull=False
            )
            .select_related("block__district")
            .first()
        )
        if cov and cov.block and cov.block.district:
            return cov.block.district, "BatchBlockCoverage"

        # Check participant TrainingRequests / Beneficiaries
        bb = (
            BatchBeneficiary.objects.filter(batch=batch, is_active=True)
            .select_related("training_request__district", "beneficiary__district")
            .first()
        )
        if bb:
            if bb.training_request and bb.training_request.district:
                return bb.training_request.district, "BatchBeneficiary.training_request"
            if bb.beneficiary and bb.beneficiary.district:
                return bb.beneficiary.district, "BatchBeneficiary.beneficiary"

        bt = (
            BatchTrainer.objects.filter(batch=batch, is_active=True)
            .select_related("training_request__district", "trainer__district")
            .first()
        )
        if bt:
            if bt.training_request and bt.training_request.district:
                return bt.training_request.district, "BatchTrainer.training_request"
            if bt.trainer and bt.trainer.district:
                return bt.trainer.district, "BatchTrainer.trainer"

        bs = (
            BatchStaff.objects.filter(batch=batch, is_active=True)
            .select_related("training_request__district", "staff__district")
            .first()
        )
        if bs:
            if bs.training_request and bs.training_request.district:
                return bs.training_request.district, "BatchStaff.training_request"
            if bs.staff and bs.staff.district:
                return bs.staff.district, "BatchStaff.staff"

        # Check Creator's DistrictTP
        if batch.created_by_id:
            dtp = (
                DistrictTP.objects.filter(
                    master_user_id=batch.created_by_id,
                    is_active=True,
                    district__isnull=False,
                )
                .select_related("district")
                .first()
            )
            if dtp and dtp.district:
                return dtp.district, "Creator DistrictTP"

        return None, None

    def resolve_partner(self, batch):
        """Attempts to resolve missing partner on a COMBINED batch using safe fallbacks."""
        if batch.partner:
            return batch.partner, "Batch.partner"

        if batch.centre and getattr(batch.centre, "partner", None):
            return batch.centre.partner, "Batch.centre.partner"

        if batch.created_by_id:
            dtp = (
                DistrictTP.objects.filter(
                    master_user_id=batch.created_by_id,
                    is_active=True,
                    partner__isnull=False,
                )
                .select_related("partner")
                .first()
            )
            if dtp and dtp.partner:
                return dtp.partner, "Creator DistrictTP"

            tp = TrainingPartner.objects.filter(
                master_user_id=batch.created_by_id, is_active=True
            ).first()
            if tp:
                return tp, "Creator TrainingPartner"

        return None, None

    def handle(self, *args, **options):
        fy_filter = options.get("fy")
        self.stdout.write(
            self.style.SUCCESS(
                f"=== STARTING COMBINED BATCH CODE ANALYSIS & REPAIR (FY: {fy_filter or 'ALL'}) ==="
            )
        )

        qs = (
            Batch.objects.filter(batch_type__iexact="COMBINED", is_active=True)
            .select_related(
                "district",
                "block",
                "block__district",
                "partner",
                "centre",
                "centre__district",
                "centre__partner",
                "training_plan",
                "created_by",
            )
            .order_by("id")
        )

        if fy_filter:
            qs = qs.filter(financial_year=fy_filter)

        combined_batches = list(qs)

        if not combined_batches:
            self.stdout.write(
                self.style.WARNING("No active COMBINED batches found matching criteria.")
            )
            return

        self.stdout.write(
            f"Found {len(combined_batches)} active COMBINED batch(es). Analyzing metadata and prefixes...\n"
        )

        prefix_groups = defaultdict(list)
        unresolved_batches = []

        # 1. Analyze each batch and group by target prefix
        for batch in combined_batches:
            district_obj, dist_source = self.resolve_district(batch)
            partner_obj, part_source = self.resolve_partner(batch)
            fy_str = (batch.financial_year or "").strip()
            plan_id = batch.training_plan_id

            missing_reasons = []
            if len(fy_str) < 4:
                missing_reasons.append(f"Invalid financial_year ('{fy_str}')")
            if not district_obj:
                missing_reasons.append("Missing district (could not resolve from fallbacks)")
            if not partner_obj:
                missing_reasons.append("Missing partner (could not resolve from fallbacks)")
            if not plan_id:
                missing_reasons.append("Missing training_plan_id")

            if missing_reasons:
                unresolved_batches.append((batch, ", ".join(missing_reasons)))
                continue

            fy_code = fy_str[2:4]
            dist_short = (
                getattr(district_obj, "district_short_name_en", None) or "XXX"
            ).strip()
            tp_short = (
                getattr(partner_obj, "tp_short_name", None) or "XXX"
            ).strip()

            target_prefix = f"{fy_code}-{dist_short}-COMB-{tp_short}-{plan_id}"

            prefix_groups[target_prefix].append(
                {
                    "batch": batch,
                    "resolved_district": district_obj,
                    "dist_source": dist_source,
                    "resolved_partner": partner_obj,
                    "part_source": part_source,
                    "target_prefix": target_prefix,
                }
            )

        # 2. Compute sequential codes per prefix group (ordered by batch.id)
        planned_updates = []
        already_correct_count = 0

        for prefix, items in sorted(prefix_groups.items(), key=lambda x: x[0]):
            prefix_with_sep = f"{prefix}-"
            active_batch_ids_in_group = {item["batch"].id for item in items}

            # Check if any soft-deleted or non-grouped batch in DB already holds a code with this prefix
            occupied_codes = set(
                Batch.objects.filter(code__startswith=prefix_with_sep)
                .exclude(id__in=active_batch_ids_in_group)
                .values_list("code", flat=True)
            )

            seq_counter = 1
            for item in items:
                batch = item["batch"]

                # Find next available sequence number not occupied by inactive rows
                while True:
                    candidate_code = f"{prefix_with_sep}{str(seq_counter).zfill(4)}"
                    if candidate_code not in occupied_codes:
                        break
                    seq_counter += 1

                seq_counter += 1

                old_code = batch.code or "None"
                needs_district_fix = batch.district_id != item["resolved_district"].district_id
                needs_partner_fix = batch.partner_id != item["resolved_partner"].id
                needs_code_fix = old_code != candidate_code

                if not (needs_district_fix or needs_partner_fix or needs_code_fix):
                    already_correct_count += 1

                planned_updates.append(
                    {
                        "batch": batch,
                        "old_code": old_code,
                        "new_code": candidate_code,
                        "resolved_district": item["resolved_district"],
                        "dist_source": item["dist_source"],
                        "resolved_partner": item["resolved_partner"],
                        "part_source": item["part_source"],
                        "needs_district_fix": needs_district_fix,
                        "needs_partner_fix": needs_partner_fix,
                        "needs_code_fix": needs_code_fix,
                        "will_update": needs_district_fix or needs_partner_fix or needs_code_fix,
                    }
                )

        # 3. Print Verbose Analysis Table
        self.stdout.write("=" * 145)
        self.stdout.write(
            f"{'Sr':<4} | {'Batch ID':<8} | {'FY':<7} | {'District (Source)':<26} | {'Old Code':<32} | {'New Code':<32} | {'Action':<18}"
        )
        self.stdout.write("=" * 145)

        for idx, row in enumerate(planned_updates, start=1):
            b = row["batch"]
            dist_code = getattr(row["resolved_district"], "district_short_name_en", "XXX")
            dist_label = f"{dist_code} ({row['dist_source']})"

            if not row["will_update"]:
                action_str = "OK (No Change)"
            else:
                flags = []
                if row["needs_code_fix"]:
                    flags.append("RECODE")
                if row["needs_district_fix"]:
                    flags.append("+DIST")
                if row["needs_partner_fix"]:
                    flags.append("+PARTNER")
                action_str = ", ".join(flags)

            line = (
                f"{idx:<4} | {b.id:<8} | {(b.financial_year or 'N/A'):<7} | "
                f"{dist_label[:26]:<26} | {row['old_code'][:32]:<32} | "
                f"{row['new_code'][:32]:<32} | {action_str:<18}"
            )
            if row["will_update"]:
                self.stdout.write(self.style.WARNING(line))
            else:
                self.stdout.write(line)

        self.stdout.write("=" * 145)

        if unresolved_batches:
            self.stdout.write(
                self.style.ERROR(
                    f"\n[!] {len(unresolved_batches)} COMBINED Batch(es) could NOT be resolved and will be skipped:"
                )
            )
            for b, reason in unresolved_batches:
                self.stdout.write(
                    self.style.ERROR(f"  - Batch ID {b.id} (Current Code: {b.code}): {reason}")
                )

        rows_to_modify = [r for r in planned_updates if r["will_update"]]

        self.stdout.write(
            f"\nSUMMARY:"
            f"\n  Total Active COMBINED Batches Analyzed : {len(combined_batches)}"
            f"\n  Already Correct (No Changes Needed)    : {already_correct_count}"
            f"\n  Batches Scheduled for Update           : {len(rows_to_modify)}"
            f"\n  Unresolvable / Skipped Batches         : {len(unresolved_batches)}"
        )

        if not rows_to_modify:
            self.stdout.write(
                self.style.SUCCESS("\nAll resolvable COMBINED batches already have valid codes. Nothing to update!")
            )
            return

        # 4. Atomic Execution with Interactive Commit Prompt
        try:
            with transaction.atomic():
                sid = transaction.savepoint()

                # PASS 1: Assign temporary unique codes to avoid unique constraint collisions during re-indexing
                for r in rows_to_modify:
                    if r["needs_code_fix"]:
                        temp_code = f"TMP-COMB-{r['batch'].id}-{uuid.uuid4().hex[:6].upper()}"
                        Batch.objects.filter(id=r["batch"].id).update(code=temp_code)

                # PASS 2: Assign final sequential codes and repaired foreign keys
                for r in rows_to_modify:
                    update_fields = {"code": r["new_code"]}
                    if r["needs_district_fix"]:
                        update_fields["district_id"] = r["resolved_district"].id
                    if r["needs_partner_fix"]:
                        update_fields["partner_id"] = r["resolved_partner"].id

                    Batch.objects.filter(id=r["batch"].id).update(**update_fields)

                while True:
                    user_input = (
                        input(
                            f"\n[ATOMIC CHECKPOINT] Commit {len(rows_to_modify)} COMBINED batch update(s) to Database? [y/N]: "
                        )
                        .strip()
                        .lower()
                    )
                    if user_input == "y":
                        transaction.savepoint_commit(sid)
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"\n✔ Successfully committed {len(rows_to_modify)} COMBINED batch code update(s) to Database."
                            )
                        )
                        break
                    elif user_input in ["n", "", "q"]:
                        transaction.savepoint_rollback(sid)
                        self.stdout.write(
                            self.style.WARNING(
                                "\n✘ Rolled back all changes. Zero records were modified in the Database."
                            )
                        )
                        break
                    else:
                        print("Invalid input. Please enter 'y' to commit or 'n' to rollback.")

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(
                    f"\n✖ Fatal error during batch code update: {e}. Transaction rolled back completely."
                )
            )
            sys.exit(1)