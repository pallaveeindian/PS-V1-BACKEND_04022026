from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.db.models import Count, Sum, Q, F, Value
from django.db.models.functions import Coalesce

from core.models import MasterUser, MasterGeoUserScope, MasterDistrict, MasterBlock
from TMS.models import (
    Batch, TrainingRequest, TRBeneficiary, TRTrainer, TRStaff,
    BatchBeneficiary, BatchTrainer, BatchStaff,
    TrainingPartnerTargets, TrainingTheme
)

class AdminDashboardMetricsAPIView(APIView):
    """
    Unified Dashboard API for BMMU, DMMU, and SMMU.
    Automatically restricts geographic and thematic scope based on User Role.
    Requires 'financial_year'. DRAFT batches are completely ignored.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        financial_year = request.query_params.get('financial_year')
        if not financial_year:
            return Response(
                {"error": "financial_year query parameter is strictly required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            user = MasterUser.objects.get(username=request.user.username)
        except MasterUser.DoesNotExist:
            return Response({"error": "User profile not found."}, status=status.HTTP_404_NOT_FOUND)

        role_id = getattr(user, 'role_id', None)
        
        # Base Q Objects (is_active=True and EXCLUDE DRAFT BATCHES)
        batch_q = Q(financial_year=financial_year, is_active=True) & ~Q(status='DRAFT')
        tr_q = Q(financial_year=financial_year, is_active=True)
        target_q = Q(financial_year=financial_year, is_active=True)

        # Extraction Params (Common Filters)
        plan_id = request.query_params.get('plan_id')
        if plan_id:
            batch_q &= Q(training_plan_id=plan_id)
            tr_q &= Q(training_plan_id=plan_id)
            target_q &= Q(training_plan_id=plan_id)

        # -------------------------------------------------------------
        # ROLE BASED SCOPING
        # -------------------------------------------------------------
        scope_district_id = None

        if role_id == 1: # BMMU
            geo = MasterGeoUserScope.objects.filter(user_id=user.id, is_active=1).first()
            if not geo or not geo.block_id:
                return Response({"error": "No Block mapped to BMMU user."}, status=status.HTTP_403_FORBIDDEN)
            
            batch_q &= Q(block_id=geo.block_id)
            tr_q &= Q(block_id=geo.block_id)
            target_q &= Q(district_id=geo.district_id) # Targets are typically district-wise
            scope_district_id = geo.district_id

        elif role_id == 2: # DMMU
            geo = MasterGeoUserScope.objects.filter(user_id=user.id, is_active=1).first()
            if not geo or not geo.district_id:
                return Response({"error": "No District mapped to DMMU user."}, status=status.HTTP_403_FORBIDDEN)
            
            scope_district_id = geo.district_id
            batch_q &= Q(district_id=scope_district_id)
            tr_q &= Q(district_id=scope_district_id)
            target_q &= Q(district_id=scope_district_id)

            req_block_id = request.query_params.get('block_id')
            if req_block_id:
                batch_q &= Q(block_id=req_block_id)
                tr_q &= Q(block_id=req_block_id)

        elif role_id == 3: # SMMU
            theme = TrainingTheme.objects.filter(expert=user, is_active=True).first()
            if not theme:
                return Response({"error": "No Training Theme mapped to SMMU user."}, status=status.HTTP_403_FORBIDDEN)
            
            batch_q &= Q(training_plan__theme_id=theme.id)
            tr_q &= Q(training_plan__theme_id=theme.id)
            target_q &= Q(training_plan__theme_id=theme.id)

            req_district_id = request.query_params.get('district_id')
            req_block_id = request.query_params.get('block_id')
            if req_district_id:
                batch_q &= Q(district_id=req_district_id)
                tr_q &= Q(district_id=req_district_id)
                target_q &= Q(district_id=req_district_id)
            if req_block_id:
                batch_q &= Q(block_id=req_block_id)
                tr_q &= Q(block_id=req_block_id)

        else:
            return Response({"error": "Role not authorized for this dashboard."}, status=status.HTTP_403_FORBIDDEN)

        # -------------------------------------------------------------
        # 1. KPI CARDS (BATCH STATUS COUNTS)
        # -------------------------------------------------------------
        batch_stats = Batch.objects.filter(batch_q).aggregate(
            total=Count('id'),
            draft=Count('id', filter=Q(status='DRAFT')), # Handled by Q logic above, strictly 0
            pending=Count('id', filter=Q(status='PENDING')),
            ongoing=Count('id', filter=Q(status='ONGOING')),
            scheduled=Count('id', filter=Q(status='SCHEDULED')),
            completed=Count('id', filter=Q(status='COMPLETED')),
            review=Count('id', filter=Q(status='REVIEW')),
            closed=Count('id', filter=Q(status='CLOSED')),
            rejected=Count('id', filter=Q(status='REJECTED')),
        )

        # -------------------------------------------------------------
        # 2. PARTICIPANTS ALLOTTED VS TRAINED & STATUS PAX COUNTS
        # -------------------------------------------------------------
        tr_qs = TrainingRequest.objects.filter(tr_q)
        total_allotted_beneficiaries = TRBeneficiary.objects.filter(training__in=tr_qs, is_active=True).count()
        total_allotted_trainers = TRTrainer.objects.filter(training__in=tr_qs, is_active=True).count()
        total_allotted_staff = TRStaff.objects.filter(training__in=tr_qs, is_active=True).count()

        valid_batches = Batch.objects.filter(batch_q)
        
        # Base querysets for ALL enrolled participants in active valid batches
        bb_all = BatchBeneficiary.objects.filter(batch__in=valid_batches, is_active=True, beneficiary__isnull=False)
        bt_all = BatchTrainer.objects.filter(batch__in=valid_batches, is_active=True, trainer__trainer__isnull=False)
        bs_all = BatchStaff.objects.filter(batch__in=valid_batches, is_active=True, staff__isnull=False)

        # Helper function to get pax count for a specific batch status
        def get_pax_by_status(status_val):
            if status_val == 'DRAFT': 
                return 0
            return (
                bb_all.filter(batch__status=status_val).count() +
                bt_all.filter(batch__status=status_val).count() +
                bs_all.filter(batch__status=status_val).count()
            )

        # Base querysets for strictly CLOSED batches (used for Trained Participants & Demographics)
        closed_batches = valid_batches.filter(status='CLOSED')
        bb_qs = bb_all.filter(batch__in=closed_batches)
        bt_qs = bt_all.filter(batch__in=closed_batches)
        bs_qs = bs_all.filter(batch__in=closed_batches)

        total_trained_beneficiaries = bb_qs.count()
        total_trained_trainers = bt_qs.count()
        total_trained_staff = bs_qs.count()

        kpi_data = {
            "total_batches_created": batch_stats['total'] or 0,
            "total_pax_count": bb_all.count() + bt_all.count() + bs_all.count(),

            "draft_batches": 0, 
            "draft_pax_count": 0,

            "pending_batches": batch_stats['pending'] or 0,
            "pending_pax_count": get_pax_by_status('PENDING'),

            "ongoing_batches": batch_stats['ongoing'] or 0,
            "ongoing_pax_count": get_pax_by_status('ONGOING'),

            "scheduled_batches": batch_stats['scheduled'] or 0,
            "scheduled_pax_count": get_pax_by_status('SCHEDULED'),

            "completed_batches": batch_stats['completed'] or 0,
            "completed_pax_count": get_pax_by_status('COMPLETED'),

            "review_batches": batch_stats['review'] or 0,
            "review_pax_count": get_pax_by_status('REVIEW'),

            "closed_batches": batch_stats['closed'] or 0,
            "closed_pax_count": get_pax_by_status('CLOSED'),

            "rejected_batches": batch_stats['rejected'] or 0,
            "rejected_pax_count": get_pax_by_status('REJECTED'),

            "total_participants_allotted": total_allotted_beneficiaries + total_allotted_trainers + total_allotted_staff,
            "total_participants_trained": total_trained_beneficiaries + total_trained_trainers + total_trained_staff
        }

        # -------------------------------------------------------------
        # 3. PARTICIPANT BIFURCATIONS
        # -------------------------------------------------------------
        def format_bifurcation(qs, field):
            data = qs.annotate(label=Coalesce(F(field), Value('Unknown'))).values('label').annotate(count=Count('id')).order_by('-count')
            return {item['label'] if item['label'] else 'Unknown': item['count'] for item in data}

        beneficiary_bifurcation = {
            "by_social_category": format_bifurcation(bb_qs, 'beneficiary__social_category'),
            "by_religion": format_bifurcation(bb_qs, 'beneficiary__religion'),
            "by_pld_status": format_bifurcation(bb_qs, 'beneficiary__pld_status'),
        }

        trainer_bifurcation = {
            "by_designation": format_bifurcation(bt_qs, 'trainer__trainer__designation'),
        }

        staff_bifurcation = {
            "by_designation": format_bifurcation(bs_qs, 'staff__designation'),
        }

        # -------------------------------------------------------------
        # 4. THEME WISE TARGETS VS ACHIEVEMENTS (PARTICIPANTS)
        # -------------------------------------------------------------
        # Target aggregations
        target_aggs = TrainingPartnerTargets.objects.filter(target_q).annotate(
            resolved_theme=Coalesce('training_plan__theme__theme_name', 'theme')
        ).filter(resolved_theme__isnull=False).values('resolved_theme').annotate(total=Sum('target_count'))
        
        target_map = {t['resolved_theme']: t['total'] for t in target_aggs}

        # Onboarded Aggregations (TR Participants)
        def get_theme_onboarded(model):
            return model.objects.filter(
                is_active=True, 
                training__is_active=True,
                training__in=tr_qs
            ).values('training__training_plan__theme__theme_name').annotate(total=Count('id'))

        onboarded_map = {}
        for qs in [get_theme_onboarded(TRBeneficiary), get_theme_onboarded(TRTrainer), get_theme_onboarded(TRStaff)]:
            for item in qs:
                th_name = item['training__training_plan__theme__theme_name']
                if th_name:
                    onboarded_map[th_name] = onboarded_map.get(th_name, 0) + item['total']

        # Enrolled Aggregations (Batch Participants in ALL non-draft batches)
        def get_theme_enrolled(model, participant_field):
            return model.objects.filter(
                **{f"{participant_field}__isnull": False},
                is_active=True,
                batch__in=valid_batches
            ).values('batch__training_plan__theme__theme_name').annotate(total=Count('id'))

        enrolled_map = {}
        for qs in [
            get_theme_enrolled(BatchBeneficiary, 'beneficiary'), 
            get_theme_enrolled(BatchTrainer, 'trainer'), 
            get_theme_enrolled(BatchStaff, 'staff')
        ]:
            for item in qs:
                th_name = item['batch__training_plan__theme__theme_name']
                if th_name:
                    enrolled_map[th_name] = enrolled_map.get(th_name, 0) + item['total']

        # Achieved/Trained Aggregations (Batch Participants in CLOSED batches ONLY)
        def get_theme_achieved(model, participant_field):
            return model.objects.filter(
                **{f"{participant_field}__isnull": False},
                is_active=True,
                batch__in=closed_batches # Strictly CLOSED batches
            ).values('batch__training_plan__theme__theme_name').annotate(total=Count('id'))

        achieved_map = {}
        for qs in [
            get_theme_achieved(BatchBeneficiary, 'beneficiary'), 
            get_theme_achieved(BatchTrainer, 'trainer'), 
            get_theme_achieved(BatchStaff, 'staff')
        ]:
            for item in qs:
                th_name = item['batch__training_plan__theme__theme_name']
                if th_name:
                    achieved_map[th_name] = achieved_map.get(th_name, 0) + item['total']

        # Compile Final Theme Metrics
        all_themes = set(target_map.keys()).union(set(onboarded_map.keys())).union(set(enrolled_map.keys()))
        theme_wise_performance = []

        for th in all_themes:
            tgt = target_map.get(th, 0)
            onb = onboarded_map.get(th, 0)
            enr = enrolled_map.get(th, 0)
            ach = achieved_map.get(th, 0)
            
            theme_wise_performance.append({
                "theme_name": th,
                "target": tgt,
                "onboarded": onb,
                "enrolled": enr,
                "achieved": ach, # Strictly trained participants from CLOSED batches
                "percentage": round((onb / tgt * 100), 2) if tgt > 0 else 0.0
            })
        
        # Sort by most achieved participants
        theme_wise_performance.sort(key=lambda x: x['achieved'], reverse=True)

        # -------------------------------------------------------------
        # 5. DMMU & SMMU BLOCK-WISE STATS
        # -------------------------------------------------------------
        block_wise_stats = []
        # Target district is scope_district_id for DMMU, or the passed district_id for SMMU
        target_district_for_blocks = scope_district_id if role_id == 2 else request.query_params.get('district_id') if role_id == 3 else None

        if target_district_for_blocks:
            blocks = MasterBlock.objects.filter(district_id=target_district_for_blocks)
            b_map = {b.block_id: {"block_name": b.block_name_en, "total_batches": 0, "onboarded": 0, "enrolled": 0, "achieved": 0} for b in blocks}

            # Total Batches per block (Kept at the Batch level)
            batch_counts = valid_batches.filter(block__isnull=False).values('block_id').annotate(total=Count('id'))
            for item in batch_counts:
                if item['block_id'] in b_map:
                    b_map[item['block_id']]['total_batches'] += item['total']

            # EXACT FIX: Onboarded per block (Grouped by the Training Request's Block)
            for Model in [TRBeneficiary, TRTrainer, TRStaff]:
                qs = Model.objects.filter(
                    is_active=True, training__in=tr_qs, training__block__isnull=False
                ).values('training__block_id').annotate(total=Count('id'))
                for item in qs:
                    blk_id = item['training__block_id']
                    if blk_id in b_map:
                        b_map[blk_id]['onboarded'] += item['total']

            # EXACT FIX: Enrolled per block (Grouped by the Training Request's Block)
            for Model, field in [(BatchBeneficiary, 'beneficiary'), (BatchTrainer, 'trainer'), (BatchStaff, 'staff')]:
                qs = Model.objects.filter(
                    **{f"{field}__isnull": False}, is_active=True, batch__in=valid_batches, training_request__block__isnull=False
                ).values('training_request__block_id').annotate(total=Count('id'))
                for item in qs:
                    blk_id = item['training_request__block_id']
                    if blk_id in b_map:
                        b_map[blk_id]['enrolled'] += item['total']

            # EXACT FIX: Achieved per block (CLOSED ONLY, Grouped by the Training Request's Block)
            for Model, field in [(BatchBeneficiary, 'beneficiary'), (BatchTrainer, 'trainer'), (BatchStaff, 'staff')]:
                qs = Model.objects.filter(
                    **{f"{field}__isnull": False}, is_active=True, batch__in=closed_batches, training_request__block__isnull=False
                ).values('training_request__block_id').annotate(total=Count('id'))
                for item in qs:
                    blk_id = item['training_request__block_id']
                    if blk_id in b_map:
                        b_map[blk_id]['achieved'] += item['total']

            block_wise_stats = [{"block_id": k, **v} for k, v in b_map.items()]
            block_wise_stats.sort(key=lambda x: x['block_name'] or "")

        # -------------------------------------------------------------
        # 6. SMMU DISTRICT-WISE STATS (Role 3)
        # -------------------------------------------------------------
        district_wise_stats = []
        if role_id == 3:
            districts = MasterDistrict.objects.all()
            d_map = {d.district_id: {"district_name": d.district_name_en, "target": 0, "onboarded": 0, "enrolled": 0, "achieved": 0} for d in districts}

            # Targets per district
            tgt_qs = TrainingPartnerTargets.objects.filter(
                target_q, district__isnull=False
            ).values('district_id').annotate(total=Sum('target_count'))
            for item in tgt_qs:
                if item['district_id'] in d_map:
                    d_map[item['district_id']]['target'] += (item['total'] or 0)

            # Onboarded per district
            for Model in [TRBeneficiary, TRTrainer, TRStaff]:
                qs = Model.objects.filter(
                    is_active=True, training__in=tr_qs, district__isnull=False
                ).values('district_id').annotate(total=Count('id'))
                for item in qs:
                    if item['district_id'] in d_map:
                        d_map[item['district_id']]['onboarded'] += item['total']

            # Enrolled per district
            for Model, field in [(BatchBeneficiary, 'beneficiary'), (BatchTrainer, 'trainer'), (BatchStaff, 'staff')]:
                qs = Model.objects.filter(
                    **{f"{field}__isnull": False}, is_active=True, batch__in=valid_batches, batch__district__isnull=False
                ).values('batch__district_id').annotate(total=Count('id'))
                for item in qs:
                    if item['batch__district_id'] in d_map:
                        d_map[item['batch__district_id']]['enrolled'] += item['total']

            # Achieved per district (CLOSED ONLY)
            for Model, field in [(BatchBeneficiary, 'beneficiary'), (BatchTrainer, 'trainer'), (BatchStaff, 'staff')]:
                qs = Model.objects.filter(
                    **{f"{field}__isnull": False}, is_active=True, batch__in=closed_batches, batch__district__isnull=False
                ).values('batch__district_id').annotate(total=Count('id'))
                for item in qs:
                    if item['batch__district_id'] in d_map:
                        d_map[item['batch__district_id']]['achieved'] += item['total']

            district_wise_stats = [{"district_id": k, **v} for k, v in d_map.items()]
            district_wise_stats.sort(key=lambda x: x['district_name'] or "")

        # -------------------------------------------------------------
        # FINAL PAYLOAD
        # -------------------------------------------------------------
        response_payload = {
            "status": "success",
            "filters_applied": {
                "financial_year": financial_year,
                "plan_id": plan_id,
                "district_id": request.query_params.get('district_id') if role_id == 3 else scope_district_id,
                "block_id": request.query_params.get('block_id')
            },
            "kpi_cards": kpi_data,
            "participant_bifurcation": {
                "total_trained_beneficiaries": total_trained_beneficiaries,
                "beneficiary_breakdown": beneficiary_bifurcation,
                "total_trained_trainers": total_trained_trainers,
                "trainer_breakdown": trainer_bifurcation,
                "total_trained_staff": total_trained_staff,
                "staff_breakdown": staff_bifurcation,
            },
            "theme_wise_performance": theme_wise_performance,
        }

        # Inject Role-Specific Additions
        if role_id == 2:
            response_payload["block_wise_stats"] = block_wise_stats
        elif role_id == 3:
            response_payload["district_wise_stats"] = district_wise_stats
            if request.query_params.get('district_id'):
                response_payload["block_wise_stats"] = block_wise_stats

        return Response(response_payload, status=status.HTTP_200_OK)