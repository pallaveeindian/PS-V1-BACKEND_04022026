# TMS/api/TPHomepageV2/views.py
import re
from django.db.models import Count, Sum, Q
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

from TMS import models as tms_models
from core import models as core_models
from .serializers import TPDashboardResponseSerializer

class TrainingPartnerDashboardView(APIView):
    """
    Central API Engine for the Training Partner Executive Dashboard.
    Enforces financial year constraint and aggregates targets, closures, 
    centres, and district team tracking metrics.
    Supports 'batches' param ('closed' or 'created') to toggle achievement logic.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        # 1. Validate Financial Year Parameter Constraint
        financial_year = request.query_params.get('financial_year')
        if not financial_year:
            return Response(
                {"detail": "The 'financial_year' query parameter is mandatory."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not re.match(r'^\d{4}-\d{2}$', financial_year):
            return Response(
                {"detail": "Invalid financial_year format. Expected format like '2026-27'."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # SURGICAL ADDITION: Extract 'batches' toggle (Defaults to 'closed')
        batches_toggle = request.query_params.get('batches', 'closed').strip().lower()

        # Build dynamic Q filters based on the batches_toggle
        if batches_toggle == 'created':
            # Include ALL active batches EXCEPT rejected ones
            rel_batch_status_q = ~Q(batch__status='REJECTED')
            batch_status_q = ~Q(status='REJECTED')
            strict_closed_q = ~Q(status='REJECTED')
        else:
            # Default behavior: strictly closed or completed
            rel_batch_status_q = Q(batch__status='CLOSED')
            batch_status_q = Q(status__in=['COMPLETED', 'CLOSED'])
            strict_closed_q = Q(status='CLOSED')

        # 2. Resolve Active Training Partner Scope from Context User
        auth_user = request.user
        master_user = core_models.MasterUser.objects.filter(username=auth_user.username).first()
        if not master_user:
            return Response({"detail": "User contextual profile not found."}, status=status.HTTP_403_FORBIDDEN)

        partner = tms_models.TrainingPartner.objects.filter(master_user=master_user, is_active=True).first()
        if not partner:
            return Response({"detail": "No active Training Partner profile linked to this user account."}, status=status.HTTP_403_FORBIDDEN)

        # 3. Retrieve All Master Districts (Ensuring all 75 options exist in output arrays)
        all_districts = core_models.MasterDistrict.objects.values('district_id', 'district_name_en').order_by('district_name_en')

        # ------------------------------------------------------------
        # METRIC A: KPI CARD PROCESSING ENGINE
        # ------------------------------------------------------------
        batch_stats = tms_models.Batch.objects.filter(
            partner=partner, financial_year=financial_year, is_active=True
        ).aggregate(
            total=Count('id'),
            ongoing=Count('id', filter=Q(status='ONGOING')),
            pending=Count('id', filter=Q(status='PENDING')),
            closed=Count('id', filter=Q(status='CLOSED'))
        )

        total_allotted_beneficiaries = tms_models.TRBeneficiary.objects.filter(
            training__partner=partner, training__financial_year=financial_year, is_active=True
        ).count()
        total_allotted_trainers = tms_models.TRTrainer.objects.filter(
            training__partner=partner, training__financial_year=financial_year, is_active=True
        ).count()

        total_trained_beneficiaries = tms_models.BatchBeneficiary.objects.filter(
            rel_batch_status_q,
            batch__partner=partner, batch__financial_year=financial_year, is_active=True
        ).count()
        total_trained_trainers = tms_models.BatchTrainer.objects.filter(
            rel_batch_status_q,
            batch__partner=partner, batch__financial_year=financial_year, is_active=True
        ).count()

        kpi_data = {
            "total_batches_created": batch_stats['total'] or 0,
            "ongoing_batches": batch_stats['ongoing'] or 0,
            "pending_batches": batch_stats['pending'] or 0,
            "closed_batches": batch_stats['closed'] or 0,
            "total_participants_allotted": total_allotted_beneficiaries + total_allotted_trainers,
            "total_participants_trained": total_trained_beneficiaries + total_trained_trainers
        }

        # ------------------------------------------------------------
        # METRIC B: DISTRICT WISE TARGETS VS ACHIEVEMENTS (ZERO-FILLED FOR 75)
        # ------------------------------------------------------------
        target_aggregations = tms_models.TrainingPartnerTargets.objects.filter(
            partner=partner, financial_year=financial_year, is_active=True, district__isnull=False
        ).values('district_id').annotate(total_target=Sum('target_count'))
        target_lookup = {item['district_id']: item['total_target'] or 0 for item in target_aggregations}

        achievement_aggregations = tms_models.Batch.objects.filter(
            batch_status_q,
            partner=partner, financial_year=financial_year, is_active=True, district__isnull=False
        ).values('district_id').annotate(total_achieved=Count('id'))
        achievement_lookup = {item['district_id']: item['total_achieved'] or 0 for item in achievement_aggregations}

        district_wise_data = []
        for dist in all_districts:
            d_id = dist['district_id']
            district_wise_data.append({
                "district_id": d_id,
                "district_name_en": dist['district_name_en'] or "-",
                "assigned_targets": target_lookup.get(d_id, 0),
                "achieved_batches": achievement_lookup.get(d_id, 0)
            })

        # ------------------------------------------------------------
        # METRIC C: THEME WISE TARGETS VS ACHIEVEMENTS
        # ------------------------------------------------------------
        theme_targets = tms_models.TrainingPartnerTargets.objects.filter(
            partner=partner, financial_year=financial_year, is_active=True, theme__isnull=False
        ).values('theme').annotate(total_target=Sum('target_count'))
        theme_target_lookup = {item['theme']: item['total_target'] or 0 for item in theme_targets}

        theme_achievements = tms_models.Batch.objects.filter(
            batch_status_q,
            partner=partner, financial_year=financial_year, is_active=True, training_plan__theme__isnull=False
        ).values('training_plan__theme__theme_name').annotate(total_achieved=Count('id'))
        theme_achievement_lookup = {item['training_plan__theme__theme_name']: item['total_achieved'] or 0 for item in theme_achievements}

        all_themes_set = set(theme_target_lookup.keys()).union(set(theme_achievement_lookup.keys()))
        theme_wise_data = []
        for theme_name in all_themes_set:
            if theme_name:
                theme_wise_data.append({
                    "theme_name": theme_name,
                    "assigned_targets": theme_target_lookup.get(theme_name, 0),
                    "achieved_batches": theme_achievement_lookup.get(theme_name, 0)
                })

        # ------------------------------------------------------------
        # METRIC D: REGISTERED TRAINING CENTRES DISTRICT WISE
        # ------------------------------------------------------------
        centre_aggregations = tms_models.TrainingPartnerCentre.objects.filter(
            partner=partner, is_active=True, district__isnull=False
        ).values('district_id').annotate(total_centres=Count('id'))
        centre_lookup = {item['district_id']: item['total_centres'] or 0 for item in centre_aggregations}

        district_centres_data = []
        for dist in all_districts:
            d_id = dist['district_id']
            district_centres_data.append({
                "district_id": d_id,
                "district_name_en": dist['district_name_en'] or "-",
                "registered_centres_count": centre_lookup.get(d_id, 0)
            })

        # ------------------------------------------------------------
        # METRIC E: DISTRICT TP TEAM TRACKING ENGINE
        # ------------------------------------------------------------
        dtp_profiles = tms_models.DistrictTP.objects.filter(
            partner=partner, is_active=True
        ).select_related('master_user')
        dtp_lookup = {profile.district_id: profile.master_user.username for profile in dtp_profiles}

        dtp_created_batches = tms_models.Batch.objects.filter(
            partner=partner, financial_year=financial_year, is_active=True, district__isnull=False
        ).values('district_id').annotate(total_created=Count('id'))
        dtp_created_lookup = {item['district_id']: item['total_created'] or 0 for item in dtp_created_batches}

        dtp_closed_batches = tms_models.Batch.objects.filter(
            strict_closed_q,
            partner=partner, financial_year=financial_year, is_active=True, district__isnull=False
        ).values('district_id').annotate(total_closed=Count('id'))
        dtp_closed_lookup = {item['district_id']: item['total_closed'] or 0 for item in dtp_closed_batches}

        district_tp_performance = []
        for dist in all_districts:
            d_id = dist['district_id']
            district_tp_performance.append({
                "district_id": d_id,
                "district_name_en": dist['district_name_en'] or "-",
                "district_tp_username": dtp_lookup.get(d_id, None),
                "batches_created": dtp_created_lookup.get(d_id, 0),
                "batches_closed": dtp_closed_lookup.get(d_id, 0),
                "performance_rank": 0 # Evaluated below after dynamic sorting pass
            })

        # Rank metrics logically based on productivity parameters (Created desc, Closed desc)
        district_tp_performance.sort(key=lambda x: (x['batches_created'], x['batches_closed']), reverse=True)
        for rank_idx, record in enumerate(district_tp_performance, start=1):
            record["performance_rank"] = rank_idx

        # 4. Serialize Output and Return Unified Response
        final_payload = {
            "financial_year": financial_year,
            "training_partner_name": partner.name,
            "kpi_card_info": kpi_data,
            "theme_wise_metrics": theme_wise_data,
            "district_wise_metrics": district_wise_data,
            "district_wise_centres": district_centres_data,
            "district_tp_performance": district_tp_performance
        }

        serializer = TPDashboardResponseSerializer(final_payload)
        return Response(serializer.data, status=status.HTTP_200_OK)