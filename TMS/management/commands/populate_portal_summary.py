# pragati_setu/TMS/management/commands/populate_portal_summary.py
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
import time

from django.core.management.base import BaseCommand, CommandError
from django.db import models, transaction
from django.db.models import Count, OuterRef, Q, Subquery, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from core.models import MasterBlock, MasterDistrict
from TMS.models import (
    Batch,
    BatchBeneficiary,
    BatchBlockCoverage,
    BatchStaff,
    BatchTrainer,
    BeneficiaryAttendanceSummary,
    TMSPortalSummary,
    TrainingPartnerTargets,
    TrainingPlan,
    TrainingRequest,
    TRBeneficiary,
    TRStaff,
    TRTrainer,
)


STAT_KEYS = (
    "total",
    "scheduled",
    "pending",
    "ongoing",
    "completed",
    "review",
    "closed",
    "rejected",
)


def empty_stats():
    return {k: 0 for k in STAT_KEYS}


def add_stats(target_dict, source_dict):
    for k in STAT_KEYS:
        target_dict[k] += source_dict.get(k, 0) or 0


def has_any_activity(b_st, p_st, onb, tgt, trn):
    return bool(
        b_st.get("total", 0)
        or p_st.get("total", 0)
        or onb
        or tgt
        or trn
    )


def get_indian_financial_year(ref_date):
    """Returns 'YYYY-YY' for the Indian Financial Year (April 1 - March 31)."""
    if ref_date.month >= 4:
        start_year = ref_date.year
    else:
        start_year = ref_date.year - 1
    end_short = str(start_year + 1)[-2:]
    return f"{start_year}-{end_short}"


class Command(BaseCommand):
    help = (
        "Computes and stores a complete daily snapshot of TMS Portal Summary "
        "(STATE, DISTRICT, and BLOCK levels across ALL TrainingPlans and overall) "
        "into TMSPortalSummary."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--date",
            type=str,
            default=None,
            help=(
                "Snapshot date in YYYY-MM-DD format. Defaults to yesterday "
                "(since the systemd timer runs at 12:00 AM for the day just ended)."
            ),
        )
        parser.add_argument(
            "--fy",
            nargs="+",
            type=str,
            default=None,
            help="One or more financial years to snapshot (e.g., --fy 2025-26 2026-27).",
        )
        parser.add_argument(
            "--all-fys",
            action="store_true",
            help="Snapshot all active financial years found across Batches, TRs, and Targets.",
        )
        parser.add_argument(
            "--include-zero-plan-rows",
            action="store_true",
            help=(
                "Also store zero-activity DISTRICT/BLOCK per-plan rows. "
                "By default, overall rows (all 75 districts & all blocks) and all STATE per-plan rows "
                "are always stored, while DISTRICT/BLOCK per-plan rows are stored when non-zero "
                "to prevent unnecessary table bloat."
            ),
        )

    def _resolve_snapshot_date(self, date_str):
        if not date_str:
            # Running at 00:00 AM captures the completed previous calendar day
            return timezone.localdate() - timedelta(days=1)
        try:
            return datetime.strptime(date_str.strip(), "%Y-%m-%d").date()
        except ValueError:
            raise CommandError(
                f"Invalid --date '{date_str}'. Expected YYYY-MM-DD."
            )

    def _resolve_financial_years(self, fy_arg, all_fys, snapshot_date):
        if fy_arg:
            return sorted(set(fy.strip() for fy in fy_arg if fy.strip()))

        if all_fys:
            fy_set = set()
            for model in (Batch, TrainingRequest, TrainingPartnerTargets):
                values = (
                    model.objects.filter(is_active=True)
                    .exclude(financial_year__isnull=True)
                    .exclude(financial_year="")
                    .values_list("financial_year", flat=True)
                    .distinct()
                )
                fy_set.update(v.strip() for v in values if v and v.strip())
            if fy_set:
                return sorted(fy_set)

        return [get_indian_financial_year(snapshot_date)]

    def _annotate_batch_status_counts(self, qs, prefix=""):
        st_field = f"{prefix}status"
        return qs.annotate(
            total=Count("id"),
            scheduled=Count("id", filter=Q(**{st_field: "SCHEDULED"})),
            pending=Count("id", filter=Q(**{st_field: "PENDING"})),
            ongoing=Count("id", filter=Q(**{st_field: "ONGOING"})),
            completed=Count("id", filter=Q(**{st_field: "COMPLETED"})),
            review=Count("id", filter=Q(**{st_field: "REVIEW"})),
            closed=Count("id", filter=Q(**{st_field: "CLOSED"})),
            rejected=Count("id", filter=Q(**{st_field: "REJECTED"})),
        )

    def _build_snapshot_obj(
        self,
        *,
        snapshot_date,
        fy,
        scope_level,
        district_id,
        district_name,
        block_id,
        block_name,
        block_name_local,
        theme_id,
        theme_name,
        plan_id,
        plan_name,
        b_st,
        p_st,
        onb,
        tgt,
        trained_count,
    ):
        b_comp = b_st.get("completed", 0)
        b_rev = b_st.get("review", 0)
        b_clo = b_st.get("closed", 0)

        p_comp = p_st.get("completed", 0)
        p_rev = p_st.get("review", 0)
        p_clo = p_st.get("closed", 0)

        total_pax_in_completed = p_comp + p_rev + p_clo
        dropout_count = max(0, total_pax_in_completed - trained_count)

        enrolled = p_st.get("total", 0)
        remaining = max(0, onb - enrolled)
        tgt_val = tgt or 0
        ach_pct = (
            Decimal(str(round((onb / tgt_val * 100), 2)))
            if tgt_val > 0
            else Decimal("0.00")
        )

        snapshot_key = (
            f"{snapshot_date.isoformat()}|{fy}|{scope_level}|"
            f"D{district_id or 0}|B{block_id or 0}|P{plan_id or 0}"
        )

        return TMSPortalSummary(
            snapshot_date=snapshot_date,
            financial_year=fy,
            scope_level=scope_level,
            snapshot_key=snapshot_key,
            district_id=district_id,
            district_name=district_name,
            block_id=block_id,
            block_name=block_name,
            block_name_local=block_name_local,
            theme_id=theme_id,
            theme_name=theme_name,
            training_plan_id=plan_id,
            training_plan_name=plan_name,
            # Batch Counts
            total_batches_created=b_st.get("total", 0),
            scheduled_batches=b_st.get("scheduled", 0),
            batches_pending_at_dmm=b_st.get("pending", 0),
            ongoing_batches=b_st.get("ongoing", 0),
            completed_batches=b_comp,
            completed_batches_for_verification=b_rev,
            completed_batch_closed=b_clo,
            batches_rejected_by_dmm=b_st.get("rejected", 0),
            total_batches_completed=b_comp + b_rev + b_clo,
            participants_trained=trained_count,
            participants_dropout=dropout_count,
            total_target=tgt_val,
            participants_onboarded=onb,
            participants_enrolled_in_batches=enrolled,
            remaining_participants_for_enrollment=remaining,
            achievement_percentage=ach_pct,
            # Participant Counts
            pax_total_batches_created=enrolled,
            pax_scheduled_batches=p_st.get("scheduled", 0),
            pax_batches_pending_at_dmm=p_st.get("pending", 0),
            pax_ongoing_batches=p_st.get("ongoing", 0),
            pax_completed_batches=p_comp,
            pax_completed_batches_for_verification=p_rev,
            pax_completed_batch_closed=p_clo,
            pax_batches_rejected_by_dmm=p_st.get("rejected", 0),
            pax_total_batches_completed=total_pax_in_completed,
        )

    def _populate_for_fy(
        self,
        snapshot_date,
        fy,
        all_districts,
        blocks_by_district,
        all_plans,
        include_zero_plan_rows,
    ):
        # -----------------------------------------------------------------
        # 1. Fallback Subqueries (identical to PortalSummaryReportAPIView)
        # -----------------------------------------------------------------
        cov_dist_sq = Subquery(
            BatchBlockCoverage.objects.filter(
                batch_id=OuterRef("pk"),
                is_active=True,
                block__district_id__isnull=False,
            ).values("block__district_id")[:1],
            output_field=models.BigIntegerField(),
        )
        ben_dist_sq = Subquery(
            BatchBeneficiary.objects.filter(
                batch_id=OuterRef("pk"),
                is_active=True,
                training_request__district_id__isnull=False,
            ).values("training_request__district_id")[:1],
            output_field=models.BigIntegerField(),
        )
        cov_block_sq = Subquery(
            BatchBlockCoverage.objects.filter(
                batch_id=OuterRef("pk"),
                is_active=True,
                block_id__isnull=False,
            ).values("block_id")[:1],
            output_field=models.BigIntegerField(),
        )
        ben_block_sq = Subquery(
            BatchBeneficiary.objects.filter(
                batch_id=OuterRef("pk"),
                is_active=True,
                training_request__block_id__isnull=False,
            ).values("training_request__block_id")[:1],
            output_field=models.BigIntegerField(),
        )

        # -----------------------------------------------------------------
        # 2. Single-Pass Aggregations Grouped by (district, block, plan)
        # -----------------------------------------------------------------
        # A. Batches
        b_block_plan = defaultdict(empty_stats)
        b_dist_plan = defaultdict(empty_stats)
        b_block_all = defaultdict(empty_stats)
        b_dist_all = defaultdict(empty_stats)

        batch_rows = self._annotate_batch_status_counts(
            Batch.objects.filter(is_active=True, financial_year=fy)
            .exclude(status="DRAFT")
            .annotate(
                eff_district_id=Coalesce(
                    "district_id",
                    "block__district_id",
                    "centre__district_id",
                    cov_dist_sq,
                    ben_dist_sq,
                    output_field=models.BigIntegerField(),
                ),
                eff_block_id=Coalesce(
                    "block_id",
                    "centre__block_id",
                    cov_block_sq,
                    ben_block_sq,
                    output_field=models.BigIntegerField(),
                ),
            )
            .values("eff_district_id", "eff_block_id", "training_plan_id")
        )

        for row in batch_rows:
            did = row["eff_district_id"]
            bid = row["eff_block_id"]
            pid = row["training_plan_id"]
            if did is None:
                continue
            add_stats(b_dist_all[did], row)
            if pid is not None:
                add_stats(b_dist_plan[(did, pid)], row)
            if bid is not None:
                add_stats(b_block_all[(did, bid)], row)
                if pid is not None:
                    add_stats(b_block_plan[(did, bid, pid)], row)

        # B. Enrolled Participants (BatchBeneficiary + BatchTrainer + BatchStaff)
        p_block_plan = defaultdict(empty_stats)
        p_dist_plan = defaultdict(empty_stats)
        p_block_all = defaultdict(empty_stats)
        p_dist_all = defaultdict(empty_stats)

        for model, p_fk in (
            (BatchBeneficiary, "beneficiary"),
            (BatchTrainer, "trainer"),
            (BatchStaff, "staff"),
        ):
            pax_rows = self._annotate_batch_status_counts(
                model.objects.filter(
                    is_active=True,
                    batch__is_active=True,
                    batch__financial_year=fy,
                )
                .exclude(batch__status="DRAFT")
                .annotate(
                    eff_district_id=Coalesce(
                        "batch__district_id",
                        "batch__block__district_id",
                        "batch__centre__district_id",
                        "training_request__district_id",
                        "training_request__block__district_id",
                        f"{p_fk}__district_id",
                        output_field=models.BigIntegerField(),
                    ),
                    eff_block_id=Coalesce(
                        "batch__block_id",
                        "training_request__block_id",
                        f"{p_fk}__block_id",
                        "batch__centre__block_id",
                        output_field=models.BigIntegerField(),
                    ),
                )
                .values("eff_district_id", "eff_block_id", "batch__training_plan_id"),
                prefix="batch__",
            )
            for row in pax_rows:
                did = row["eff_district_id"]
                bid = row["eff_block_id"]
                pid = row["batch__training_plan_id"]
                if did is None:
                    continue
                add_stats(p_dist_all[did], row)
                if pid is not None:
                    add_stats(p_dist_plan[(did, pid)], row)
                if bid is not None:
                    add_stats(p_block_all[(did, bid)], row)
                    if pid is not None:
                        add_stats(p_block_plan[(did, bid, pid)], row)

        # C. Onboarded Participants (TRBeneficiary + TRTrainer + TRStaff)
        onb_block_plan = defaultdict(int)
        onb_dist_plan = defaultdict(int)
        onb_block_all = defaultdict(int)
        onb_dist_all = defaultdict(int)

        for model in (TRBeneficiary, TRTrainer, TRStaff):
            o_rows = (
                model.objects.filter(
                    is_active=True,
                    training__is_active=True,
                    training__financial_year=fy,
                )
                .annotate(
                    eff_district_id=Coalesce(
                        "training__district_id",
                        "district_id",
                        "training__block__district_id",
                        "block__district_id",
                        output_field=models.BigIntegerField(),
                    ),
                    eff_block_id=Coalesce(
                        "training__block_id",
                        "block_id",
                        output_field=models.BigIntegerField(),
                    ),
                )
                .values("eff_district_id", "eff_block_id", "training__training_plan_id")
                .annotate(total=Count("id"))
            )
            for row in o_rows:
                did = row["eff_district_id"]
                bid = row["eff_block_id"]
                pid = row["training__training_plan_id"]
                cnt = row["total"] or 0
                if did is None:
                    continue
                onb_dist_all[did] += cnt
                if pid is not None:
                    onb_dist_plan[(did, pid)] += cnt
                if bid is not None:
                    onb_block_all[(did, bid)] += cnt
                    if pid is not None:
                        onb_block_plan[(did, bid, pid)] += cnt

        # D. Trained Participants (BeneficiaryAttendanceSummary)
        trn_block_plan = defaultdict(int)
        trn_dist_plan = defaultdict(int)
        trn_block_all = defaultdict(int)
        trn_dist_all = defaultdict(int)

        t_rows = (
            BeneficiaryAttendanceSummary.objects.filter(
                is_active=True,
                is_successful=True,
                batch__is_active=True,
                batch__financial_year=fy,
                batch__status__in=["COMPLETED", "REVIEW", "CLOSED"],
            )
            .annotate(
                eff_district_id=Coalesce(
                    "batch__district_id",
                    "batch__block__district_id",
                    "batch__centre__district_id",
                    "training_request__district_id",
                    "training_request__block__district_id",
                    output_field=models.BigIntegerField(),
                ),
                eff_block_id=Coalesce(
                    "batch__block_id",
                    "training_request__block_id",
                    "batch_beneficiary__beneficiary__block_id",
                    "batch_trainer__trainer__block_id",
                    "batch_staff__staff__block_id",
                    "batch__centre__block_id",
                    output_field=models.BigIntegerField(),
                ),
            )
            .values("eff_district_id", "eff_block_id", "batch__training_plan_id")
            .annotate(total_trained=Count("id"))
        )
        for row in t_rows:
            did = row["eff_district_id"]
            bid = row["eff_block_id"]
            pid = row["batch__training_plan_id"]
            cnt = row["total_trained"] or 0
            if did is None:
                continue
            trn_dist_all[did] += cnt
            if pid is not None:
                trn_dist_plan[(did, pid)] += cnt
            if bid is not None:
                trn_block_all[(did, bid)] += cnt
                if pid is not None:
                    trn_block_plan[(did, bid, pid)] += cnt

        # E. Targets (TrainingPartnerTargets)
        tgt_dist_plan = defaultdict(int)
        tgt_dist_all = defaultdict(int)

        tgt_rows = (
            TrainingPartnerTargets.objects.filter(is_active=True, financial_year=fy)
            .values("district_id", "training_plan_id")
            .annotate(total_target=Sum("target_count"))
        )
        for row in tgt_rows:
            did = row["district_id"]
            pid = row["training_plan_id"]
            cnt = row["total_target"] or 0
            if did is None:
                continue
            tgt_dist_all[did] += cnt
            if pid is not None:
                tgt_dist_plan[(did, pid)] += cnt

        # -----------------------------------------------------------------
        # 3. Assemble Snapshot Objects (STATE, DISTRICT, BLOCK x ALL + PER-PLAN)
        # -----------------------------------------------------------------
        objects_to_create = []

        # 3a. OVERALL ROWS (training_plan=None): All Districts, All Blocks, and State Sum
        state_b_all = empty_stats()
        state_p_all = empty_stats()
        state_onb_all = 0
        state_tgt_all = 0
        state_trn_all = 0

        for dist in all_districts:
            did = dist["district_id"]
            dname = dist["district_name_en"]

            b_st = b_dist_all.get(did, empty_stats())
            p_st = p_dist_all.get(did, empty_stats())
            onb = onb_dist_all.get(did, 0)
            tgt = tgt_dist_all.get(did, 0)
            trn = trn_dist_all.get(did, 0)

            add_stats(state_b_all, b_st)
            add_stats(state_p_all, p_st)
            state_onb_all += onb
            state_tgt_all += tgt
            state_trn_all += trn

            # DISTRICT OVERALL
            objects_to_create.append(
                self._build_snapshot_obj(
                    snapshot_date=snapshot_date,
                    fy=fy,
                    scope_level="DISTRICT",
                    district_id=did,
                    district_name=dname,
                    block_id=None,
                    block_name=None,
                    block_name_local=None,
                    theme_id=None,
                    theme_name=None,
                    plan_id=None,
                    plan_name=None,
                    b_st=b_st,
                    p_st=p_st,
                    onb=onb,
                    tgt=tgt,
                    trained_count=trn,
                )
            )

            # BLOCK OVERALL (for all blocks of this district)
            for blk in blocks_by_district.get(did, []):
                bid = blk["block_id"]
                objects_to_create.append(
                    self._build_snapshot_obj(
                        snapshot_date=snapshot_date,
                        fy=fy,
                        scope_level="BLOCK",
                        district_id=did,
                        district_name=dname,
                        block_id=bid,
                        block_name=blk["block_name_en"],
                        block_name_local=blk["block_name_local"],
                        theme_id=None,
                        theme_name=None,
                        plan_id=None,
                        plan_name=None,
                        b_st=b_block_all.get((did, bid), empty_stats()),
                        p_st=p_block_all.get((did, bid), empty_stats()),
                        onb=onb_block_all.get((did, bid), 0),
                        tgt=0,
                        trained_count=trn_block_all.get((did, bid), 0),
                    )
                )

        # STATE OVERALL (exact sum of all district rows)
        objects_to_create.append(
            self._build_snapshot_obj(
                snapshot_date=snapshot_date,
                fy=fy,
                scope_level="STATE",
                district_id=None,
                district_name=None,
                block_id=None,
                block_name=None,
                block_name_local=None,
                theme_id=None,
                theme_name=None,
                plan_id=None,
                plan_name=None,
                b_st=state_b_all,
                p_st=state_p_all,
                onb=state_onb_all,
                tgt=state_tgt_all,
                trained_count=state_trn_all,
            )
        )

        # 3b. PER-PLAN ROWS (STATE, DISTRICT, BLOCK for every active TrainingPlan)
        for plan in all_plans:
            pid = plan.id
            pname = plan.training_name
            tid = plan.theme_id
            tname = plan.theme.theme_name if plan.theme else None

            state_b_plan = empty_stats()
            state_p_plan = empty_stats()
            state_onb_plan = 0
            state_tgt_plan = 0
            state_trn_plan = 0

            for dist in all_districts:
                did = dist["district_id"]
                dname = dist["district_name_en"]

                b_st = b_dist_plan.get((did, pid), empty_stats())
                p_st = p_dist_plan.get((did, pid), empty_stats())
                onb = onb_dist_plan.get((did, pid), 0)
                tgt = tgt_dist_plan.get((did, pid), 0)
                trn = trn_dist_plan.get((did, pid), 0)

                add_stats(state_b_plan, b_st)
                add_stats(state_p_plan, p_st)
                state_onb_plan += onb
                state_tgt_plan += tgt
                state_trn_plan += trn

                if include_zero_plan_rows or has_any_activity(
                    b_st, p_st, onb, tgt, trn
                ):
                    # DISTRICT PER PLAN
                    objects_to_create.append(
                        self._build_snapshot_obj(
                            snapshot_date=snapshot_date,
                            fy=fy,
                            scope_level="DISTRICT",
                            district_id=did,
                            district_name=dname,
                            block_id=None,
                            block_name=None,
                            block_name_local=None,
                            theme_id=tid,
                            theme_name=tname,
                            plan_id=pid,
                            plan_name=pname,
                            b_st=b_st,
                            p_st=p_st,
                            onb=onb,
                            tgt=tgt,
                            trained_count=trn,
                        )
                    )

                # BLOCK PER PLAN
                for blk in blocks_by_district.get(did, []):
                    bid = blk["block_id"]
                    bb_st = b_block_plan.get((did, bid, pid), empty_stats())
                    bp_st = p_block_plan.get((did, bid, pid), empty_stats())
                    b_onb = onb_block_plan.get((did, bid, pid), 0)
                    b_trn = trn_block_plan.get((did, bid, pid), 0)

                    if include_zero_plan_rows or has_any_activity(
                        bb_st, bp_st, b_onb, 0, b_trn
                    ):
                        objects_to_create.append(
                            self._build_snapshot_obj(
                                snapshot_date=snapshot_date,
                                fy=fy,
                                scope_level="BLOCK",
                                district_id=did,
                                district_name=dname,
                                block_id=bid,
                                block_name=blk["block_name_en"],
                                block_name_local=blk["block_name_local"],
                                theme_id=tid,
                                theme_name=tname,
                                plan_id=pid,
                                plan_name=pname,
                                b_st=bb_st,
                                p_st=bp_st,
                                onb=b_onb,
                                tgt=0,
                                trained_count=b_trn,
                            )
                        )

            # STATE PER PLAN (always stored for every active TrainingPlan)
            objects_to_create.append(
                self._build_snapshot_obj(
                    snapshot_date=snapshot_date,
                    fy=fy,
                    scope_level="STATE",
                    district_id=None,
                    district_name=None,
                    block_id=None,
                    block_name=None,
                    block_name_local=None,
                    theme_id=tid,
                    theme_name=tname,
                    plan_id=pid,
                    plan_name=pname,
                    b_st=state_b_plan,
                    p_st=state_p_plan,
                    onb=state_onb_plan,
                    tgt=state_tgt_plan,
                    trained_count=state_trn_plan,
                )
            )

        # -----------------------------------------------------------------
        # 4. Atomic Idempotent Write for (snapshot_date, financial_year)
        # -----------------------------------------------------------------
        with transaction.atomic():
            deleted_count, _ = TMSPortalSummary.objects.filter(
                snapshot_date=snapshot_date,
                financial_year=fy,
            ).delete()
            TMSPortalSummary.objects.bulk_create(objects_to_create, batch_size=1000)

        return len(objects_to_create), deleted_count

    def handle(self, *args, **options):
        t0 = time.monotonic()
        snapshot_date = self._resolve_snapshot_date(options.get("date"))
        financial_years = self._resolve_financial_years(
            options.get("fy"), options.get("all_fys"), snapshot_date
        )
        include_zero_plan_rows = options.get("include_zero_plan_rows", False)

        self.stdout.write(
            self.style.NOTICE(
                f"Starting TMS Portal Summary snapshot | Date: {snapshot_date} | "
                f"FYs: {', '.join(financial_years)}"
            )
        )

        # Preload reference master data once
        all_districts = list(
            MasterDistrict.objects.all()
            .values("district_id", "district_name_en")
            .order_by("district_name_en")
        )
        blocks_by_district = defaultdict(list)
        for blk in (
            MasterBlock.objects.all()
            .values("block_id", "district_id", "block_name_en", "block_name_local")
            .order_by("block_name_en")
        ):
            blocks_by_district[blk["district_id"]].append(blk)

        all_plans = list(
            TrainingPlan.objects.filter(is_active=True)
            .select_related("theme")
            .order_by("training_name")
        )

        grand_total_created = 0
        for fy in financial_years:
            fy_t0 = time.monotonic()
            created, replaced = self._populate_for_fy(
                snapshot_date=snapshot_date,
                fy=fy,
                all_districts=all_districts,
                blocks_by_district=blocks_by_district,
                all_plans=all_plans,
                include_zero_plan_rows=include_zero_plan_rows,
            )
            grand_total_created += created
            self.stdout.write(
                self.style.SUCCESS(
                    f"  ✔ FY {fy}: Saved {created} snapshot rows "
                    f"(replaced {replaced} existing) in {time.monotonic() - fy_t0:.2f}s"
                )
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Completed TMS Portal Summary snapshot for {snapshot_date}: "
                f"{grand_total_created} total rows saved in {time.monotonic() - t0:.2f}s."
            )
        )