from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.db.models import Count, Sum, Q, OuterRef, Subquery
from django.db.models.functions import Coalesce
from django.utils import timezone

from core.models import MasterDistrict, MasterBlock
from TMS.models import (
    TrainingPlan,
    Batch,
    BatchBlockCoverage,
    TRBeneficiary,
    TRTrainer,
    TRStaff,
    BatchBeneficiary,
    BatchTrainer,
    BatchStaff,
    TrainingPartnerTargets,
    BeneficiaryAttendanceSummary,
)
from .serializers import PortalSummaryReportQuerySerializer

class PortalSummaryReportAPIView(APIView):
    """
    State-wide, District-wide, Plan-wise (per District), and Block-wise (per District) Summary Report API.
    - Strictly requires 'financial_year'.
    - Excludes all DRAFT batches and mandates is_active=True across all models.
    - Supports optional 'theme', 'training_plan', 'district_id', and 'block_wise' filtering.
    - 'block_wise=true' is strictly allowed ONLY when 'district_id' is provided.
    """
    permission_classes = [IsAuthenticated]

    STAT_KEYS = [
        "total",
        "scheduled",
        "pending",
        "ongoing",
        "completed",
        "review",
        "closed",
        "rejected",
    ]

    def _empty_stats(self):
        return {k: 0 for k in self.STAT_KEYS}

    def _format_summary_row(self, b_st, p_st, onb, tgt, trained_count):
        b_comp = b_st.get("completed", 0)
        b_rev = b_st.get("review", 0)
        b_clo = b_st.get("closed", 0)

        p_comp = p_st.get("completed", 0)
        p_rev = p_st.get("review", 0)
        p_clo = p_st.get("closed", 0)

        total_pax_in_completed_batches = p_comp + p_rev + p_clo
        dropout_count = max(0, total_pax_in_completed_batches - trained_count)

        enrolled = p_st.get("total", 0)
        remaining = max(0, onb - enrolled)
        ach_pct = round((onb / tgt * 100), 2) if tgt and tgt > 0 else 0.0

        return {
            "batch_counts": {
                "1_total_batches_created": b_st.get("total", 0),
                "2_scheduled_batches": b_st.get("scheduled", 0),
                "3_batches_pending_at_dmm": b_st.get("pending", 0),
                "4_ongoing_batches": b_st.get("ongoing", 0),
                "5_completed_batches": b_comp,
                "6_completed_batches_for_verification": b_rev,
                "7_completed_batch_closed": b_clo,
                "8_batches_rejected_by_dmm": b_st.get("rejected", 0),
                "9_total_batches_completed": b_comp + b_rev + b_clo,
                "9a_participants_trained": trained_count,
                "9b_participants_dropout": dropout_count,
                "10_total_target": tgt or 0,
                "11_participants_onboarded": onb,
                "12_participants_enrolled_in_batches": enrolled,
                "13_remaining_participants_for_enrollment": remaining,
                "14_achievement_percentage": f"{ach_pct}%",
            },
            "participant_counts": {
                "1_total_batches_created": p_st.get("total", 0),
                "2_scheduled_batches": p_st.get("scheduled", 0),
                "3_batches_pending_at_dmm": p_st.get("pending", 0),
                "4_ongoing_batches": p_st.get("ongoing", 0),
                "5_completed_batches": p_comp,
                "6_completed_batches_for_verification": p_rev,
                "7_completed_batch_closed": p_clo,
                "8_batches_rejected_by_dmm": p_st.get("rejected", 0),
                "9_total_batches_completed": total_pax_in_completed_batches,
                "9a_participants_trained": trained_count,
                "9b_participants_dropout": dropout_count,
                "10_total_target": None,
                "11_participants_onboarded": None,
                "12_participants_enrolled_in_batches": None,
                "13_remaining_participants_for_enrollment": None,
                "14_achievement_percentage": None,
            },
        }

    def get(self, request, *args, **kwargs):
        # 1. Validate Core Query Params
        serializer = PortalSummaryReportQuerySerializer(data=request.query_params)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        fy = serializer.validated_data["financial_year"]

        # 2. Extract Optional Filters & Scope Parameters
        theme_id = request.query_params.get("theme")
        plan_id = request.query_params.get("training_plan")
        district_id_raw = request.query_params.get("district_id")
        block_wise_raw = str(request.query_params.get("block_wise", "")).strip().lower()
        block_wise = block_wise_raw in ["true", "1", "yes"]

        if block_wise and not district_id_raw:
            return Response(
                {
                    "error": "Invalid parameters: 'block_wise=true' can only be used in combination with 'district_id'."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        district_obj = None
        district_id = None
        if district_id_raw:
            if not str(district_id_raw).strip().isdigit():
                return Response(
                    {"error": "Invalid 'district_id'. Must be a numeric ID."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            district_id = int(district_id_raw)
            district_obj = (
                MasterDistrict.objects.filter(district_id=district_id)
                .values("district_id", "district_name_en")
                .first()
            )
            if not district_obj:
                return Response(
                    {"error": f"District with ID {district_id} not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )

        # 3. Dynamic Theme & Plan Filter Dictionaries
        batch_kwargs = {}
        pax_batch_kwargs = {}
        onb_kwargs = {}
        tgt_kwargs = {}

        if plan_id:
            batch_kwargs["training_plan_id"] = plan_id
            pax_batch_kwargs["batch__training_plan_id"] = plan_id
            onb_kwargs["training__training_plan_id"] = plan_id
            tgt_kwargs["training_plan_id"] = plan_id

        if theme_id:
            batch_kwargs["training_plan__theme_id"] = theme_id
            pax_batch_kwargs["batch__training_plan__theme_id"] = theme_id
            onb_kwargs["training__training_plan__theme_id"] = theme_id
            tgt_kwargs["training_plan__theme_id"] = theme_id

        # 4. Fallback Subqueries to Recover Missing District/Block on Batches
        cov_dist_sq = Subquery(
            BatchBlockCoverage.objects.filter(
                batch_id=OuterRef("pk"),
                is_active=True,
                block__district_id__isnull=False,
            ).values("block__district_id")[:1]
        )
        ben_dist_sq = Subquery(
            BatchBeneficiary.objects.filter(
                batch_id=OuterRef("pk"),
                is_active=True,
                training_request__district_id__isnull=False,
            ).values("training_request__district_id")[:1]
        )

        cov_block_sq = Subquery(
            BatchBlockCoverage.objects.filter(
                batch_id=OuterRef("pk"),
                is_active=True,
                block_id__isnull=False,
            ).values("block_id")[:1]
        )
        ben_block_sq = Subquery(
            BatchBeneficiary.objects.filter(
                batch_id=OuterRef("pk"),
                is_active=True,
                training_request__block_id__isnull=False,
            ).values("training_request__block_id")[:1]
        )

        # Base Querysets with Resolved Effective District
        base_batch_qs = (
            Batch.objects.filter(is_active=True, financial_year=fy, **batch_kwargs)
            .exclude(status="DRAFT")
            .annotate(
                eff_district_id=Coalesce(
                    "district_id",
                    "block__district_id",
                    "centre__district_id",
                    cov_dist_sq,
                    ben_dist_sq,
                )
            )
        )

        def get_base_enrolled_qs(model, participant_fk):
            return (
                model.objects.filter(
                    is_active=True,
                    batch__is_active=True,
                    batch__financial_year=fy,
                    **pax_batch_kwargs,
                )
                .exclude(batch__status="DRAFT")
                .annotate(
                    eff_district_id=Coalesce(
                        "batch__district_id",
                        "batch__block__district_id",
                        "batch__centre__district_id",
                        "training_request__district_id",
                        "training_request__block__district_id",
                        f"{participant_fk}__district_id",
                    )
                )
            )

        def get_base_onboarded_qs(model):
            return model.objects.filter(
                is_active=True,
                training__is_active=True,
                training__financial_year=fy,
                **onb_kwargs,
            ).annotate(
                eff_district_id=Coalesce(
                    "training__district_id",
                    "district_id",
                    "training__block__district_id",
                    "block__district_id",
                )
            )

        base_trained_qs = BeneficiaryAttendanceSummary.objects.filter(
            is_active=True,
            is_successful=True,
            batch__is_active=True,
            batch__financial_year=fy,
            batch__status__in=["COMPLETED", "REVIEW", "CLOSED"],
            **pax_batch_kwargs,
        ).annotate(
            eff_district_id=Coalesce(
                "batch__district_id",
                "batch__block__district_id",
                "batch__centre__district_id",
                "training_request__district_id",
                "training_request__block__district_id",
            )
        )

        base_tgt_qs = TrainingPartnerTargets.objects.filter(
            is_active=True, financial_year=fy, **tgt_kwargs
        )

        # Helper to annotate batch status counts on any grouped queryset
        def annotate_batch_status_counts(qs, prefix=""):
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

        # =====================================================================
        # MODE 1: DISTRICT + BLOCK-WISE BREAKDOWN (district_id + block_wise=true)
        # =====================================================================
        if district_id and block_wise:
            b_qs = base_batch_qs.filter(eff_district_id=district_id).annotate(
                eff_block_id=Coalesce(
                    "block_id", "centre__block_id", cov_block_sq, ben_block_sq
                )
            )
            b_stats_raw = annotate_batch_status_counts(b_qs.values("eff_block_id"))
            b_stats_map = {item["eff_block_id"]: item for item in b_stats_raw}

            p_stats_map = {}
            for model, p_fk in [
                (BatchBeneficiary, "beneficiary"),
                (BatchTrainer, "trainer"),
                (BatchStaff, "staff"),
            ]:
                p_qs = (
                    get_base_enrolled_qs(model, p_fk)
                    .filter(eff_district_id=district_id)
                    .annotate(
                        eff_block_id=Coalesce(
                            "batch__block_id",
                            "training_request__block_id",
                            f"{p_fk}__block_id",
                            "batch__centre__block_id",
                        )
                    )
                )
                for item in annotate_batch_status_counts(
                    p_qs.values("eff_block_id"), prefix="batch__"
                ):
                    blk_id = item["eff_block_id"]
                    if blk_id not in p_stats_map:
                        p_stats_map[blk_id] = self._empty_stats()
                    for k in self.STAT_KEYS:
                        p_stats_map[blk_id][k] += item[k]

            onboarded_map = {}
            for model in [TRBeneficiary, TRTrainer, TRStaff]:
                o_qs = (
                    get_base_onboarded_qs(model)
                    .filter(eff_district_id=district_id)
                    .annotate(eff_block_id=Coalesce("training__block_id", "block_id"))
                    .values("eff_block_id")
                    .annotate(total=Count("id"))
                )
                for item in o_qs:
                    blk_id = item["eff_block_id"]
                    onboarded_map[blk_id] = onboarded_map.get(blk_id, 0) + item["total"]

            t_qs = (
                base_trained_qs.filter(eff_district_id=district_id)
                .annotate(
                    eff_block_id=Coalesce(
                        "batch__block_id",
                        "training_request__block_id",
                        "batch_beneficiary__beneficiary__block_id",
                        "batch_trainer__trainer__block_id",
                        "batch_staff__staff__block_id",
                        "batch__centre__block_id",
                    )
                )
                .values("eff_block_id")
                .annotate(total_trained=Count("id"))
            )
            trained_map = {item["eff_block_id"]: item["total_trained"] for item in t_qs}

            district_target = (
                base_tgt_qs.filter(district_id=district_id).aggregate(
                    total_target=Sum("target_count")
                )["total_target"]
                or 0
            )

            all_blocks = (
                MasterBlock.objects.filter(district_id=district_id)
                .values("block_id", "block_name_en", "block_name_local")
                .order_by("block_name_en")
            )

            block_summaries = []
            tot_b_stats = self._empty_stats()
            tot_p_stats = self._empty_stats()
            tot_onboarded = 0
            tot_trained = 0

            for blk in all_blocks:
                bid = blk["block_id"]
                b_st = b_stats_map.get(bid, self._empty_stats())
                p_st = p_stats_map.get(bid, self._empty_stats())
                onb = onboarded_map.get(bid, 0)
                trn = trained_map.get(bid, 0)

                for k in self.STAT_KEYS:
                    tot_b_stats[k] += b_st.get(k, 0)
                    tot_p_stats[k] += p_st.get(k, 0)
                tot_onboarded += onb
                tot_trained += trn

                block_summaries.append(
                    {
                        "block_id": bid,
                        "block_name": blk["block_name_en"],
                        "block_name_local": blk["block_name_local"],
                        "district_id": district_id,
                        "district_name": district_obj["district_name_en"],
                        "summary": self._format_summary_row(b_st, p_st, onb, 0, trn),
                    }
                )

            # Include any district-level/unmapped-block records in the district total if present
            if None in b_stats_map or None in p_stats_map or None in onboarded_map or None in trained_map:
                unmapped_b = b_stats_map.get(None, self._empty_stats())
                unmapped_p = p_stats_map.get(None, self._empty_stats())
                unmapped_onb = onboarded_map.get(None, 0)
                unmapped_trn = trained_map.get(None, 0)
                for k in self.STAT_KEYS:
                    tot_b_stats[k] += unmapped_b.get(k, 0)
                    tot_p_stats[k] += unmapped_p.get(k, 0)
                tot_onboarded += unmapped_onb
                tot_trained += unmapped_trn

            district_total_summary = self._format_summary_row(
                tot_b_stats, tot_p_stats, tot_onboarded, district_target, tot_trained
            )

            return Response(
                {
                    "status": "success",
                    "report_date": timezone.now().strftime("%d-%m-%y"),
                    "financial_year": fy,
                    "district_id": district_id,
                    "district_name": district_obj["district_name_en"],
                    "block_wise": True,
                    "state_wide_summary": district_total_summary,
                    "district_summaries": [
                        {
                            "district_id": district_id,
                            "district_name": district_obj["district_name_en"],
                            "summary": district_total_summary,
                        }
                    ],
                    "block_summaries": block_summaries,
                },
                status=status.HTTP_200_OK,
            )

        # =====================================================================
        # MODE 2: DISTRICT PLAN-WISE BREAKDOWN (district_id without block_wise)
        # =====================================================================
        if district_id and not block_wise:
            b_qs = base_batch_qs.filter(eff_district_id=district_id)
            b_stats_raw = annotate_batch_status_counts(b_qs.values("training_plan_id"))
            b_stats_map = {item["training_plan_id"]: item for item in b_stats_raw}

            p_stats_map = {}
            for model, p_fk in [
                (BatchBeneficiary, "beneficiary"),
                (BatchTrainer, "trainer"),
                (BatchStaff, "staff"),
            ]:
                p_qs = get_base_enrolled_qs(model, p_fk).filter(eff_district_id=district_id)
                for item in annotate_batch_status_counts(
                    p_qs.values("batch__training_plan_id"), prefix="batch__"
                ):
                    pid = item["batch__training_plan_id"]
                    if pid not in p_stats_map:
                        p_stats_map[pid] = self._empty_stats()
                    for k in self.STAT_KEYS:
                        p_stats_map[pid][k] += item[k]

            onboarded_map = {}
            for model in [TRBeneficiary, TRTrainer, TRStaff]:
                o_qs = (
                    get_base_onboarded_qs(model)
                    .filter(eff_district_id=district_id)
                    .values("training__training_plan_id")
                    .annotate(total=Count("id"))
                )
                for item in o_qs:
                    pid = item["training__training_plan_id"]
                    onboarded_map[pid] = onboarded_map.get(pid, 0) + item["total"]

            t_qs = (
                base_trained_qs.filter(eff_district_id=district_id)
                .values("batch__training_plan_id")
                .annotate(total_trained=Count("id"))
            )
            trained_map = {
                item["batch__training_plan_id"]: item["total_trained"] for item in t_qs
            }

            tgt_qs = (
                base_tgt_qs.filter(district_id=district_id)
                .values("training_plan_id")
                .annotate(total_target=Sum("target_count"))
            )
            target_map = {
                item["training_plan_id"]: item["total_target"] for item in tgt_qs
            }

            plans_qs = TrainingPlan.objects.filter(is_active=True).select_related("theme").order_by("training_name")
            if theme_id:
                plans_qs = plans_qs.filter(theme_id=theme_id)
            if plan_id:
                plans_qs = plans_qs.filter(id=plan_id)

            training_plan_summaries = []
            tot_b_stats = self._empty_stats()
            tot_p_stats = self._empty_stats()
            tot_onboarded = 0
            tot_target = 0
            tot_trained = 0

            for plan in plans_qs:
                pid = plan.id
                b_st = b_stats_map.get(pid, self._empty_stats())
                p_st = p_stats_map.get(pid, self._empty_stats())
                onb = onboarded_map.get(pid, 0)
                tgt = target_map.get(pid, 0) or 0
                trn = trained_map.get(pid, 0)

                for k in self.STAT_KEYS:
                    tot_b_stats[k] += b_st.get(k, 0)
                    tot_p_stats[k] += p_st.get(k, 0)
                tot_onboarded += onb
                tot_target += tgt
                tot_trained += trn

                training_plan_summaries.append(
                    {
                        "training_plan_id": pid,
                        "training_plan_name": plan.training_name,
                        "theme_id": plan.theme_id,
                        "theme_name": plan.theme.theme_name if plan.theme else None,
                        "district_id": district_id,
                        "district_name": district_obj["district_name_en"],
                        "summary": self._format_summary_row(b_st, p_st, onb, tgt, trn),
                    }
                )

            district_total_summary = self._format_summary_row(
                tot_b_stats, tot_p_stats, tot_onboarded, tot_target, tot_trained
            )

            return Response(
                {
                    "status": "success",
                    "report_date": timezone.now().strftime("%d-%m-%y"),
                    "financial_year": fy,
                    "district_id": district_id,
                    "district_name": district_obj["district_name_en"],
                    "block_wise": False,
                    "state_wide_summary": district_total_summary,
                    "district_summaries": [
                        {
                            "district_id": district_id,
                            "district_name": district_obj["district_name_en"],
                            "summary": district_total_summary,
                        }
                    ],
                    "training_plan_summaries": training_plan_summaries,
                },
                status=status.HTTP_200_OK,
            )

        # =====================================================================
        # MODE 3: DEFAULT STATE-WIDE & ALL-DISTRICTS SUMMARY
        # =====================================================================
        b_stats_raw = annotate_batch_status_counts(base_batch_qs.values("eff_district_id"))
        b_stats_map = {item["eff_district_id"]: item for item in b_stats_raw}

        p_stats_map = {}
        for model, p_fk in [
            (BatchBeneficiary, "beneficiary"),
            (BatchTrainer, "trainer"),
            (BatchStaff, "staff"),
        ]:
            p_qs = get_base_enrolled_qs(model, p_fk)
            for item in annotate_batch_status_counts(
                p_qs.values("eff_district_id"), prefix="batch__"
            ):
                d_id = item["eff_district_id"]
                if d_id not in p_stats_map:
                    p_stats_map[d_id] = self._empty_stats()
                for k in self.STAT_KEYS:
                    p_stats_map[d_id][k] += item[k]

        onboarded_map = {}
        for model in [TRBeneficiary, TRTrainer, TRStaff]:
            o_qs = (
                get_base_onboarded_qs(model)
                .values("eff_district_id")
                .annotate(total=Count("id"))
            )
            for item in o_qs:
                d_id = item["eff_district_id"]
                onboarded_map[d_id] = onboarded_map.get(d_id, 0) + item["total"]

        tgt_qs = base_tgt_qs.values("district_id").annotate(
            total_target=Sum("target_count")
        )
        target_map = {item["district_id"]: item["total_target"] for item in tgt_qs}

        trained_qs = base_trained_qs.values("eff_district_id").annotate(
            total_trained=Count("id")
        )
        trained_map = {
            item["eff_district_id"]: item["total_trained"] for item in trained_qs
        }

        # Compile District Rows AND Accumulate State Row Directly From District Rows
        all_districts = (
            MasterDistrict.objects.all()
            .values("district_id", "district_name_en")
            .order_by("district_name_en")
        )
        district_summaries = []

        state_b_stats = self._empty_stats()
        state_p_stats = self._empty_stats()
        state_onboarded = 0
        state_target = 0
        state_trained = 0

        for dist in all_districts:
            did = dist["district_id"]
            b_st = b_stats_map.get(did, self._empty_stats())
            p_st = p_stats_map.get(did, self._empty_stats())
            onb = onboarded_map.get(did, 0)
            tgt = target_map.get(did, 0) or 0
            trn = trained_map.get(did, 0)

            for k in self.STAT_KEYS:
                state_b_stats[k] += b_st.get(k, 0)
                state_p_stats[k] += p_st.get(k, 0)
            state_onboarded += onb
            state_target += tgt
            state_trained += trn

            district_summaries.append(
                {
                    "district_id": did,
                    "district_name": dist["district_name_en"],
                    "summary": self._format_summary_row(b_st, p_st, onb, tgt, trn),
                }
            )

        response_data = {
            "status": "success",
            "report_date": timezone.now().strftime("%d-%m-%y"),
            "financial_year": fy,
            "state_wide_summary": self._format_summary_row(
                state_b_stats,
                state_p_stats,
                state_onboarded,
                state_target,
                state_trained,
            ),
            "district_summaries": district_summaries,
        }

        return Response(response_data, status=status.HTTP_200_OK)