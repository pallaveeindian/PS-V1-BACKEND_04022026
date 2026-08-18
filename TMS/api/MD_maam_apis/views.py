from rest_framework.views import APIView
from rest_framework.response import Response
from django.db.models import F, Sum, Count, Q, Case, When, IntegerField, Min
from TMS.models import *
from TMS.api.tms_views import BatchListPagination
from epSakhi.models import BeneficiaryRecorded, MOUEnterprise
from LDMS.models import recorded_benefs
from .serializers import *

class MasterProgressReportView(APIView):
    """
    Returns aggregated matrix of targets, onboarded users, batches, and trained participants.
    
    Query Params:
    - report_type: 'theme' (default) or 'plan'
    - district_id: Filter by specific district
    - theme_id: Filter by specific theme
    - plan_id: Filter by specific training plan
    """
    
    def get(self, request):
        report_type = request.query_params.get('report_type', 'theme')
        dist_filter = request.query_params.get('district_id')
        theme_filter = request.query_params.get('theme_id')
        plan_filter = request.query_params.get('plan_id')
        financial_year_filter = request.query_params.get('financial_year')

        data_dict = {}

        # -----------------------------
        # Helper 1: Grouping Key Builder
        # -----------------------------
        def get_key(row):
            dist_id = row.get('dist_id')
            dist_name = row.get('dist_name')
            
            # Read from the safe alias names we define below
            grp_id = row.get('group_id')
            grp_name = row.get('group_name')

            if not dist_id or not grp_id:
                return None
            return (dist_id, dist_name, grp_id, grp_name)

        def init_row(key):
            if key not in data_dict:
                data_dict[key] = {
                    'district_id': key[0],
                    'district_name': key[1],
                    'group_id': key[2],
                    'group_name': key[3],
                    'target': 0,
                    'total_onboarded': 0,
                    'total_batches': 0,
                    'dmmu_approved_batches': 0,
                    'ongoing_batches': 0,
                    'completed_batches': 0,
                    'total_participants_trained': 0
                }

        # -----------------------------
        # Helper 2: Base Filter Applier
        # -----------------------------
        def apply_filters(qs, prefix):
            if dist_filter:
                qs = qs.filter(**{f"{prefix}district_id": dist_filter})
            if theme_filter:
                qs = qs.filter(**{f"{prefix}training_plan__theme_id": theme_filter})
            if plan_filter:
                qs = qs.filter(**{f"{prefix}training_plan_id": plan_filter})
            if financial_year_filter:
                qs = qs.filter(**{
                    f"{prefix}financial_year": financial_year_filter
                })
            return qs


        def get_group_kwargs(prefix):
            if report_type == 'plan':
                return {
                    'dist_id': F(f"{prefix}district_id"),
                    'dist_name': F(f"{prefix}district__district_name_en"),
                    'group_id': F(f"{prefix}training_plan_id"),
                    'group_name': F(f"{prefix}training_plan__training_name")
                }
            else:
                return {
                    'dist_id': F(f"{prefix}district_id"),
                    'dist_name': F(f"{prefix}district__district_name_en"),
                    'group_id': F(f"{prefix}training_plan__theme_id"),
                    'group_name': F(f"{prefix}training_plan__theme__theme_name")
                }

        # -----------------------------
        # Query A: Targets
        # -----------------------------
        qs_targets = TrainingPartnerTargets.objects.filter(is_active=True, training_plan__isnull=False)
        qs_targets = apply_filters(qs_targets, prefix="")
        targets_data = qs_targets.values(**get_group_kwargs("")).annotate(val=Sum('target_count'))
        
        for row in targets_data:
            key = get_key(row)
            if key:
                init_row(key)
                data_dict[key]['target'] += row['val'] or 0

        # -----------------------------
        # Query B: Total Onboarded (TR Participants)
        # -----------------------------
        for TRModel in [TRBeneficiary, TRTrainer, TRStaff]:
            qs_tr = TRModel.objects.filter(is_active=True, training__is_active=True)
            qs_tr = apply_filters(qs_tr, prefix="training__")
            tr_data = qs_tr.values(**get_group_kwargs("training__")).annotate(val=Count('id'))
            
            for row in tr_data:
                key = get_key(row)
                if key:
                    init_row(key)
                    data_dict[key]['total_onboarded'] += row['val'] or 0

        # -----------------------------
        # Query C: Batches & Status Breakdown
        # -----------------------------
        qs_batch = Batch.objects.filter(is_active=True)
        qs_batch = apply_filters(qs_batch, prefix="")
        
        dmmu_statuses = ['PENDING', 'ONGOING', 'SCHEDULED', 'COMPLETED', 'REVIEW', 'CLOSED']
        
        batch_data = qs_batch.values(**get_group_kwargs("")).annotate(
            total_b=Count('id'),
            dmmu_b=Count(Case(When(status__in=dmmu_statuses, then=1), output_field=IntegerField())),
            ongoing_b=Count(Case(When(status='ONGOING', then=1), output_field=IntegerField())),
            completed_b=Count(Case(When(status='COMPLETED', then=1), output_field=IntegerField())),
        )
        
        for row in batch_data:
            key = get_key(row)
            if key:
                init_row(key)
                data_dict[key]['total_batches'] += row['total_b'] or 0
                data_dict[key]['dmmu_approved_batches'] += row['dmmu_b'] or 0
                data_dict[key]['ongoing_batches'] += row['ongoing_b'] or 0
                data_dict[key]['completed_batches'] += row['completed_b'] or 0

        # -----------------------------
        # Query D: Total Participants Trained (Closed Batches Only)
        # -----------------------------
        for BPModel in [BatchBeneficiary, BatchTrainer, BatchStaff]:
            qs_bp = BPModel.objects.filter(is_active=True, batch__is_active=True, batch__status='CLOSED')
            qs_bp = apply_filters(qs_bp, prefix="batch__")
            bp_data = qs_bp.values(**get_group_kwargs("batch__")).annotate(val=Count('id'))
            
            for row in bp_data:
                key = get_key(row)
                if key:
                    init_row(key)
                    data_dict[key]['total_participants_trained'] += row['val'] or 0

        # -----------------------------
        # Assemble Final Data & Totals Row
        # -----------------------------
        result_list = []
        totals = {
            'district_id': None,
            'district_name': 'TOTAL AGGREGATE',
            'group_id': None,
            'group_name': 'ALL RECORDS',
            'target': 0,
            'total_onboarded': 0,
            'total_batches': 0,
            'dmmu_approved_batches': 0,
            'ongoing_batches': 0,
            'completed_batches': 0,
            'total_participants_trained': 0,
            'percentage': 0.0
        }

        for val in data_dict.values():
            # Local Percentages
            onboarded = val['total_onboarded']
            trained = val['total_participants_trained']
            val['percentage'] = round((trained / onboarded * 100), 2) if onboarded > 0 else 0.0

            # Accumulate Totals
            totals['target'] += val['target']
            totals['total_onboarded'] += onboarded
            totals['total_batches'] += val['total_batches']
            totals['dmmu_approved_batches'] += val['dmmu_approved_batches']
            totals['ongoing_batches'] += val['ongoing_batches']
            totals['completed_batches'] += val['completed_batches']
            totals['total_participants_trained'] += trained

            result_list.append(val)

        # Global Percentage
        if totals['total_onboarded'] > 0:
            totals['percentage'] = round((totals['total_participants_trained'] / totals['total_onboarded'] * 100), 2)
        else:
            totals['percentage'] = 0.0

        # Sort the actual rows by District Name, then Group Name
        result_list.sort(key=lambda x: (x['district_name'] or '', x['group_name'] or ''))

        # Inject Total at the top
        final_data = [totals] + result_list

        serializer = MasterProgressReportSerializer(final_data, many=True)
        return Response({"status": "success", "data": serializer.data})

class TrainingCentreSummaryView(APIView):
    """
    Returns aggregated stats for Training Centres.
    Filters: district_id, partner_id
    """
    def get(self, request):
        district_id = request.query_params.get('district_id')
        partner_id = request.query_params.get('partner_id')
        fy = request.query_params.get('financial_year')

        # 1. Base Queryset with Annotations
        qs = TrainingPartnerCentre.objects.filter(is_active=True).select_related('partner', 'district')

        # Apply Filters
        if district_id:
            qs = qs.filter(district_id=district_id)
        if partner_id:
            qs = qs.filter(partner_id=partner_id)

        # 2. Annotate counts directly in the DB
        qs = qs.annotate(
            # Count active TPCPs associated with this centre
            tpcp_count=Count(
                'tpcptocentre', 
                filter=Q(tpcptocentre__is_active=True), 
                distinct=True
            ),
            # Count active Batches (excluding REJECTED)
            batch_count=Count(
                'batch', 
                filter=Q(batch__is_active=True) & ~Q(batch__status='REJECTED'), 
                distinct=True
            ),
            # Count active uploaded assets
            asset_count=Count(
                'submissions', 
                filter=Q(submissions__is_active=True), 
                distinct=True
            )
        ).order_by('-created_at')

        # 3. Pagination
        paginator = BatchListPagination()
        page = paginator.paginate_queryset(qs, request)

        # 4. Map Allocated Targets (District + Partner combo) safely
        combo_keys = set()
        for centre in page:
            if centre.partner_id and centre.district_id:
                combo_keys.add((centre.partner_id, centre.district_id))

        targets_dict = {}
        if combo_keys:
            partner_ids = [k[0] for k in combo_keys]
            district_ids = [k[1] for k in combo_keys]
            
            targets_qs = TrainingPartnerTargets.objects.filter(
                is_active=True,
                partner_id__in=partner_ids,
                district_id__in=district_ids,
            ).values('partner_id', 'district_id').annotate(total_tgt=Sum('target_count'))

            if fy:
                targets_qs = targets_qs.filter(financial_year=fy)

            for t in targets_qs:
                targets_dict[(t['partner_id'], t['district_id'])] = t['total_tgt']

        # Inject the allocated targets into the paginated objects
        for centre in page:
            key = (centre.partner_id, centre.district_id)
            centre.allocated_target = targets_dict.get(key, 0)

        # 5. Serialize & Return
        serializer = CentreSummarySerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class CentreSubmissionListView(APIView):
    """
    Returns all uploaded assets (TrainingPartnerSubmission) for a specific centre_id.
    """
    def get(self, request, centre_id):
        submissions = TrainingPartnerSubmission.objects.filter(
            centre_id=centre_id, 
            is_active=True
        ).order_by('-created_at')
        
        serializer = CentreSubmissionSerializer(submissions, many=True)
        return Response({
            "status": "success",
            "data": serializer.data
        })


class DmmuCertificatePendencyView(APIView):
    """
    Returns a list of districts that have CLOSED batches but have 
    pending/missing certificate uploads (BatchReport status != 'DMM_SIGNED').
    
    Query Params:
    - financial_year: Filter by FY (e.g. '2026-27')
    """
    def get(self, request):
        fy = request.query_params.get('financial_year')

        # Condition defining an "Uncertified" batch
        # A batch is uncertified if it lacks a related BatchReport with 'DMM_SIGNED' status
        uncertified_condition = ~Q(batch_report__status='DMM_SIGNED')

        # Base Query: Only look at Active & CLOSED batches mapped to a district
        qs = Batch.objects.filter(
            is_active=True,
            status='CLOSED',
            district__isnull=False
        )

        # Apply Financial Year Filter if provided
        if fy:
            qs = qs.filter(financial_year=fy)

        # Aggregate the data grouped by District
        data = qs.values(
            'district__district_id',
            'district__district_name_en'
        ).annotate(
            # Total Closed Batches in the district
            total_closed_batches=Count('id', distinct=True),
            
            # Batches where Certificates are uploaded (BatchReport status is DMM_SIGNED)
            certificates_uploaded=Count(
                'id', 
                filter=Q(batch_report__status='DMM_SIGNED'), 
                distinct=True
            ),
            
            # Pending Backlog (Batches without a DMM_SIGNED report)
            pending_backlog=Count(
                'id', 
                filter=uncertified_condition, 
                distinct=True
            ),
            
            # Oldest date an uncertified batch transitioned to 'CLOSED'
            oldest_uncertified_date=Min(
                'status_history__created_at',
                filter=Q(status_history__status='CLOSED') & uncertified_condition
            )
        ).filter(
            # ONLY return districts that actually have a pending backlog
            pending_backlog__gt=0
        ).order_by('-pending_backlog') # Order by highest backlog first

        serializer = CertificatePendencySerializer(data, many=True)
        
        return Response({
            "status": "success",
            "data": serializer.data
        })   


class BeneficiaryEligibilityAnalyticsView(APIView):
    """
    Returns aggregated matrix of participant eligibility and attendance ratio.
    Filters: financial_year, district_id, block_id
    """
    def get(self, request):
        fy = request.query_params.get('financial_year')
        district_id = request.query_params.get('district_id')
        block_id = request.query_params.get('block_id')

        # Base Query: Active batches tied to a geography
        qs = Batch.objects.filter(is_active=True, district__isnull=False, block__isnull=False)

        # Apply Filters
        if fy:
            qs = qs.filter(financial_year=fy)
        if district_id:
            qs = qs.filter(district_id=district_id)
        if block_id:
            qs = qs.filter(block_id=block_id)

        # Aggregate safely using DISTINCT to avoid Cartesian product explosion
        data = qs.values(
            'district__district_id',
            'district__district_name_en',
            'block__block_id',
            'block__block_name_en'
        ).annotate(
            total_ben=Count('beneficiary_participations', filter=Q(beneficiary_participations__is_active=True), distinct=True),
            total_trn=Count('trainer_participations', filter=Q(trainer_participations__is_active=True), distinct=True),
            total_stf=Count('staff_participations', filter=Q(staff_participations__is_active=True), distinct=True),
            
            # Count successful participants directly from the attendance summary table.
            # We explicitly exclude Master Trainers to align with the prompt's scope.
            successful_pax=Count(
                'beneficiary_summaries', 
                filter=Q(
                    beneficiary_summaries__is_active=True, 
                    beneficiary_summaries__is_successful=True,
                    beneficiary_summaries__batch_master_trainer__isnull=True 
                ), 
                distinct=True
            )
        ).order_by('district__district_name_en', 'block__block_name_en')

        # Process logical equations in Python
        result_list = []
        for row in data:
            total_participants = row['total_ben'] + row['total_trn'] + row['total_stf']
            successful = row['successful_pax']
            
            # Safety clamp in case of orphaned data anomalies
            if successful > total_participants:
                successful = total_participants

            unsuccessful = total_participants - successful
            
            # Net Attendance Ratio (%)
            ratio = round((successful / total_participants * 100), 2) if total_participants > 0 else 0.0

            # Only append if there are actually participants allocated to this block
            if total_participants > 0:
                result_list.append({
                    'district__district_id': row['district__district_id'],
                    'district__district_name_en': row['district__district_name_en'],
                    'block__block_id': row['block__block_id'],
                    'block__block_name_en': row['block__block_name_en'],
                    'total_participants': total_participants,
                    'successful_participants': successful,
                    'unsuccessful_participants': unsuccessful,
                    'attendance_ratio': ratio
                })

        serializer = BeneficiaryEligibilitySerializer(result_list, many=True)
        return Response({"status": "success", "data": serializer.data})        


class HomeDashboardGlobalStatsView(APIView):
    """
    Aggregates high-level statistical counts across TMS, EPSMS, LDMS, and SHG-MOU 
    for the primary State Master Dashboard.
    """
    def get(self, request):
        
        # ==========================================
        # 1. TMS (Training Management System)
        # ==========================================
        tms_stats = Batch.objects.filter(is_active=True).aggregate(
            total=Count('id', filter=~Q(status__in=['DRAFT', 'REJECTED'])),
            completed=Count('id', filter=Q(status__in=['COMPLETED', 'CLOSED', 'REVIEW'])),
            pending=Count('id', filter=Q(status__in=['BATCHING', 'PENDING', 'SCHEDULED'])),
            ongoing=Count('id', filter=Q(status='ONGOING'))
        )

        # ==========================================
        # 2. EPSMS (Enterprise Management System)
        # ==========================================
        epsms_stats = BeneficiaryRecorded.objects.filter(is_active=True).aggregate(
            total=Count('id'),
            existing=Count('id', filter=Q(enterprise_type__iexact='exep')),
            new_ep=Count('id', filter=Q(enterprise_type__iexact='newep')),
            non_ep=Count('id', filter=Q(enterprise_type__iexact='noep'))
        )

        # ==========================================
        # 3. LDMS (Lakhpati Didi Management System)
        # ==========================================
        ldms_stats = recorded_benefs.objects.filter(is_active=True).aggregate(
            total=Count('id'),
            # Handles different string representations of True
            pld=Count('id', filter=Q(pld_status__iexact='TRUE') | Q(pld_status__iexact='YES') | Q(pld_status='1'))
        )
        ldms_total = ldms_stats['total'] or 0
        ldms_pld = ldms_stats['pld'] or 0
        ldms_non_pld = ldms_total - ldms_pld

        # ==========================================
        # 4. SHG-MOU (MOU Management System)
        # ==========================================
        # ALIAS NAMES CHANGED HERE: Added 'count_' prefix to avoid field name collisions
        mou_stats = MOUEnterprise.objects.filter(is_active=True).aggregate(
            count_shg=Count('id', filter=Q(lokos_shg_code__isnull=False) | Q(lokos_shg_name__isnull=False)),
            count_vo=Count('id', filter=Q(lokos_shg_code__isnull=True, lokos_vo_code__isnull=False)),
            count_clf=Count('id', filter=Q(lokos_shg_code__isnull=True, lokos_vo_code__isnull=True, lokos_clf_code__isnull=False)),
            count_block=Count('id', filter=Q(lokos_clf_code__isnull=True, block__isnull=False)),
            count_district=Count('id', filter=Q(block__isnull=True, district__isnull=False)),
            count_state=Count('id', filter=Q(district__isnull=True))
        )

        # ==========================================
        # 5. Assemble Payload
        # ==========================================
        payload = {
            # TMS
            "tms_total_batches": tms_stats['total'] or 0,
            "tms_completed": tms_stats['completed'] or 0,
            "tms_pending": tms_stats['pending'] or 0,
            "tms_ongoing": tms_stats['ongoing'] or 0,

            # EPSMS
            "epsms_total_forms": epsms_stats['total'] or 0,
            "epsms_existing": epsms_stats['existing'] or 0,
            "epsms_new": epsms_stats['new_ep'] or 0,
            "epsms_non_ep": epsms_stats['non_ep'] or 0,

            # LDMS
            "ldms_total_support": ldms_total,
            "ldms_pld": ldms_pld,
            "ldms_non_pld": ldms_non_pld,

            # MOU (Mapped to the new non-conflicting aliases)
            "mou_state": mou_stats['count_state'] or 0,
            "mou_district": mou_stats['count_district'] or 0,
            "mou_block": mou_stats['count_block'] or 0,
            "mou_clf": mou_stats['count_clf'] or 0,
            "mou_vo": mou_stats['count_vo'] or 0,
            "mou_shg": mou_stats['count_shg'] or 0,
        }

        serializer = HomeDashboardStatsSerializer(data=payload)
        serializer.is_valid(raise_exception=True)

        return Response({
            "status": "success",
            "data": serializer.validated_data
        })