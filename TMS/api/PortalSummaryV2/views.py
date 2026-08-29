from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.db.models import Count, Sum, Q
from django.utils import timezone

from core.models import MasterDistrict
from TMS.models import (
    Batch, 
    TRBeneficiary, TRTrainer, TRStaff,
    BatchBeneficiary, BatchTrainer, BatchStaff,
    TrainingPartnerTargets
)
from .serializers import PortalSummaryReportQuerySerializer  # Import the serializer you created above

class PortalSummaryReportAPIView(APIView):
    """
    State-wide and District-wide Summary Report API.
    Strictly requires 'financial_year'.
    Excludes all DRAFT batches and mandates is_active=True across all models.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        # 1. Validate Query Params
        serializer = PortalSummaryReportQuerySerializer(data=request.query_params)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        fy = serializer.validated_data['financial_year']

        # ---------------------------------------------------------
        # AGGREGATION ENGINE (Highly Optimized to prevent N+1 queries)
        # ---------------------------------------------------------

        # A. BATCH COUNTS (Grouped by District)
        # Excludes DRAFT and ensures is_active=True
        batch_qs = Batch.objects.filter(is_active=True, financial_year=fy).exclude(status='DRAFT')
        
        b_stats_raw = batch_qs.values('district_id').annotate(
            total=Count('id'),
            scheduled=Count('id', filter=Q(status='SCHEDULED')),
            pending=Count('id', filter=Q(status='PENDING')),
            ongoing=Count('id', filter=Q(status='ONGOING')),
            completed=Count('id', filter=Q(status='COMPLETED')),
            review=Count('id', filter=Q(status='REVIEW')),
            closed=Count('id', filter=Q(status='CLOSED')),
            rejected=Count('id', filter=Q(status='REJECTED')),
        )
        b_stats_map = {item['district_id']: item for item in b_stats_raw}

        # B. PARTICIPANTS ENROLLED IN BATCHES (Grouped by District)
        def get_enrolled_pax_stats(model):
            return model.objects.filter(
                is_active=True, 
                batch__is_active=True, 
                batch__financial_year=fy
            ).exclude(batch__status='DRAFT').values('batch__district_id').annotate(
                total=Count('id'),
                scheduled=Count('id', filter=Q(batch__status='SCHEDULED')),
                pending=Count('id', filter=Q(batch__status='PENDING')),
                ongoing=Count('id', filter=Q(batch__status='ONGOING')),
                completed=Count('id', filter=Q(batch__status='COMPLETED')),
                review=Count('id', filter=Q(batch__status='REVIEW')),
                closed=Count('id', filter=Q(batch__status='CLOSED')),
                rejected=Count('id', filter=Q(batch__status='REJECTED')),
            )

        p_stats_map = {}
        for qs in [get_enrolled_pax_stats(BatchBeneficiary), get_enrolled_pax_stats(BatchTrainer), get_enrolled_pax_stats(BatchStaff)]:
            for item in qs:
                d_id = item['batch__district_id']
                if d_id not in p_stats_map:
                    p_stats_map[d_id] = {k: 0 for k in ['total', 'scheduled', 'pending', 'ongoing', 'completed', 'review', 'closed', 'rejected']}
                for k in p_stats_map[d_id].keys():
                    p_stats_map[d_id][k] += item[k]

        # C. PARTICIPANTS ONBOARDED (Training Requests - Grouped by District)
        def get_onboarded_pax_stats(model):
            return model.objects.filter(
                is_active=True, 
                training__is_active=True, 
                training__financial_year=fy
            ).values('district_id').annotate(total=Count('id'))

        onboarded_map = {}
        for qs in [get_onboarded_pax_stats(TRBeneficiary), get_onboarded_pax_stats(TRTrainer), get_onboarded_pax_stats(TRStaff)]:
            for item in qs:
                d_id = item['district_id']
                onboarded_map[d_id] = onboarded_map.get(d_id, 0) + item['total']

        # D. TARGETS (Grouped by District)
        tgt_qs = TrainingPartnerTargets.objects.filter(
            is_active=True, financial_year=fy
        ).values('district_id').annotate(total_target=Sum('target_count'))
        target_map = {item['district_id']: item['total_target'] for item in tgt_qs}

        # ---------------------------------------------------------
        # COMPUTE STATE-WIDE TOTALS
        # ---------------------------------------------------------
        state_b_stats = {k: sum(d.get(k, 0) for d in b_stats_map.values()) for k in ['total', 'scheduled', 'pending', 'ongoing', 'completed', 'review', 'closed', 'rejected']}
        state_p_stats = {k: sum(d.get(k, 0) for d in p_stats_map.values()) for k in ['total', 'scheduled', 'pending', 'ongoing', 'completed', 'review', 'closed', 'rejected']}
        state_onboarded = sum(onboarded_map.values())
        state_target = sum(target_map.values())

        # Formatting Helper for JSON Structure
        def format_summary_row(b_st, p_st, onb, tgt):
            b_comp = b_st.get('completed', 0)
            b_rev = b_st.get('review', 0)
            b_clo = b_st.get('closed', 0)
            
            p_comp = p_st.get('completed', 0)
            p_rev = p_st.get('review', 0)
            p_clo = p_st.get('closed', 0)

            enrolled = p_st.get('total', 0)
            remaining = max(0, onb - enrolled)
            ach_pct = round((onb / tgt * 100), 2) if tgt and tgt > 0 else 0.0

            return {
                "batch_counts": {
                    "1_total_batches_created": b_st.get('total', 0),
                    "2_scheduled_batches": b_st.get('scheduled', 0),
                    "3_batches_pending_at_dmm": b_st.get('pending', 0),
                    "4_ongoing_batches": b_st.get('ongoing', 0),
                    "5_completed_batches": b_comp,
                    "6_completed_batches_for_verification": b_rev,
                    "7_completed_batch_closed": b_clo,
                    "8_batches_rejected_by_dmm": b_st.get('rejected', 0),
                    "9_total_batches_completed": b_comp + b_rev + b_clo,
                    "10_total_target": tgt or 0,
                    "11_participants_onboarded": onb,
                    "12_participants_enrolled_in_batches": enrolled,
                    "13_remaining_participants_for_enrollment": remaining,
                    "14_achievement_percentage": f"{ach_pct}%"
                },
                "participant_counts": {
                    "1_total_batches_created": p_st.get('total', 0),
                    "2_scheduled_batches": p_st.get('scheduled', 0),
                    "3_batches_pending_at_dmm": p_st.get('pending', 0),
                    "4_ongoing_batches": p_st.get('ongoing', 0),
                    "5_completed_batches": p_comp,
                    "6_completed_batches_for_verification": p_rev,
                    "7_completed_batch_closed": p_clo,
                    "8_batches_rejected_by_dmm": p_st.get('rejected', 0),
                    "9_total_batches_completed": p_comp + p_rev + p_clo,
                    "10_total_target": None,
                    "11_participants_onboarded": None,
                    "12_participants_enrolled_in_batches": None,
                    "13_remaining_participants_for_enrollment": None,
                    "14_achievement_percentage": None
                }
            }

        # ---------------------------------------------------------
        # COMPILE DISTRICT SUMMARIES
        # ---------------------------------------------------------
        all_districts = MasterDistrict.objects.all().values('district_id', 'district_name_en').order_by('district_name_en')
        district_summaries = []

        for dist in all_districts:
            did = dist['district_id']
            b_st = b_stats_map.get(did, {k: 0 for k in state_b_stats.keys()})
            p_st = p_stats_map.get(did, {k: 0 for k in state_p_stats.keys()})
            onb = onboarded_map.get(did, 0)
            tgt = target_map.get(did, 0)

            district_summaries.append({
                "district_id": did,
                "district_name": dist['district_name_en'],
                "summary": format_summary_row(b_st, p_st, onb, tgt)
            })

        # ---------------------------------------------------------
        # FINAL RESPONSE
        # ---------------------------------------------------------
        response_data = {
            "status": "success",
            "report_date": timezone.now().strftime("%d-%m-%y"),
            "financial_year": fy,
            "state_wide_summary": format_summary_row(state_b_stats, state_p_stats, state_onboarded, state_target),
            "district_summaries": district_summaries
        }

        return Response(response_data, status=status.HTTP_200_OK)