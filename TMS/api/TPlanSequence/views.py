from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from django.db.models import Sum, Q, Count

from TMS.models import (
    TrainingPlanSequence,
    TrainingRequest,
    TRBeneficiary, TRTrainer, TRStaff,
    BatchBeneficiary, BatchTrainer, BatchStaff,
    BeneficiaryAttendanceSummary,
    TrainingPartnerTargets
)
from .serializers import TrainingPlanSequenceReportSerializer

class SequencePagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100

class TrainingPlanSequenceReportAPIView(APIView):
    """
    Returns paginated modular sequence analytics for training plans,
    tracking Descended, Successful, Dropout, and Lateral entries across steps.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        params = request.query_params
        financial_year = params.get("financial_year")
        theme_id = params.get("theme_id") or params.get("theme")

        # Base Sequence Queryset ordered by group and step
        qs = TrainingPlanSequence.objects.filter(is_active=True).select_related(
            'training_plan', 
            'training_plan__theme',
            'next_training_plan'
        ).order_by('sequence_group_name', 'step_order')

        if theme_id:
            qs = qs.filter(training_plan__theme_id=theme_id)

        paginator = SequencePagination()
        paginated_qs = paginator.paginate_queryset(qs, request)

        report_results = []
        
        # Pre-fetch helper mappings to prevent N+1 queries during iteration
        for idx, seq in enumerate(paginated_qs):
            current_plan = seq.training_plan
            
            # 1. Target calculation
            target_qs = TrainingPartnerTargets.objects.filter(is_active=True, training_plan=current_plan)
            if financial_year:
                target_qs = target_qs.filter(financial_year=financial_year)
            total_target = target_qs.aggregate(total=Sum('target_count'))['total'] or 0

            # 2. Onboarded participants count (via TrainingRequests)
            tr_qs = TrainingRequest.objects.filter(is_active=True, training_plan=current_plan)
            if financial_year:
                tr_qs = tr_qs.filter(financial_year=financial_year)
            tr_ids = list(tr_qs.values_list('id', flat=True))

            ben_count = TRBeneficiary.objects.filter(is_active=True, training_id__in=tr_ids).count()
            trainer_count = TRTrainer.objects.filter(is_active=True, training_id__in=tr_ids).count()
            staff_count = TRStaff.objects.filter(is_active=True, training_id__in=tr_ids).count()
            total_onboarded = ben_count + trainer_count + staff_count

            # 3. Descendants & Lateral analysis (Comparing with previous step in sequence)
            descended_entries = 0
            successful_descendants = 0
            dropout_descendants = 0
            lateral_entries = total_onboarded

            # Find previous sequence step
            prev_seq = TrainingPlanSequence.objects.filter(next_training_plan=current_plan, is_active=True).first()

            if prev_seq and total_onboarded > 0:
                prev_plan = prev_seq.training_plan
                prev_tr_ids = list(TrainingRequest.objects.filter(is_active=True, training_plan=prev_plan).values_list('id', flat=True))

                # Collect unique identifiers (Lokos codes for beneficiaries, mobile for trainers, employee_id for staff)
                current_beneficiaries = set(TRBeneficiary.objects.filter(is_active=True, training_id__in=tr_ids).exclude(lokos_member_code__isnull=True).values_list('lokos_shg_code', 'lokos_member_code'))
                current_trainers = set(TRTrainer.objects.filter(is_active=True, training_id__in=tr_ids).exclude(trainer__mobile_no__isnull=True).values_list('trainer__mobile_no'))
                current_staff = set(TRStaff.objects.filter(is_active=True, training_id__in=tr_ids).exclude(staff__employee_id__isnull=True).values_list('staff__employee_id'))

                # Fetch successful/dropout status from previous step summary
                prev_summaries = BeneficiaryAttendanceSummary.objects.filter(
                    is_active=True,
                    training_request_id__in=prev_tr_ids
                ).select_related(
                    'batch_beneficiary__beneficiary',
                    'batch_trainer__trainer__trainer',
                    'batch_staff__staff__staff'
                )

                prev_history_map = {}
                for summary in prev_summaries:
                    key = None
                    if summary.batch_beneficiary and summary.batch_beneficiary.beneficiary:
                        b = summary.batch_beneficiary.beneficiary
                        key = (b.lokos_shg_code, b.lokos_member_code)
                    elif summary.batch_trainer and summary.batch_trainer.trainer and summary.batch_trainer.trainer.trainer:
                        t = summary.batch_trainer.trainer.trainer
                        key = (t.mobile_no,)
                    elif summary.batch_staff and summary.batch_staff.staff and summary.batch_staff.staff.staff:
                        s = summary.batch_staff.staff.staff
                        key = (s.employee_id,)
                    
                    if key:
                        prev_history_map[key] = summary.is_successful

                # Evaluate current participants against previous step history
                matched_count = 0
                success_count = 0
                dropout_count = 0

                # Evaluate Beneficiaries
                for item in current_beneficiaries:
                    if item in prev_history_map:
                        matched_count += 1
                        if prev_history_map[item]:
                            success_count += 1
                        else:
                            dropout_count += 1

                # Evaluate Trainers
                for item in current_trainers:
                    if item in prev_history_map:
                        matched_count += 1
                        if prev_history_map[item]:
                            success_count += 1
                        else:
                            dropout_count += 1

                # Evaluate Staff
                for item in current_staff:
                    if item in prev_history_map:
                        matched_count += 1
                        if prev_history_map[item]:
                            success_count += 1
                        else:
                            dropout_count += 1

                descended_entries = matched_count
                successful_descendants = success_count
                dropout_descendants = dropout_count
                lateral_entries = max(0, total_onboarded - descended_entries)

            report_results.append({
                "sr_no": (paginator.page.number - 1) * paginator.page_size + idx + 1,
                "training_plan": current_plan,
                "sequence_group_name": seq.sequence_group_name,
                "step_order": seq.step_order,
                "target": total_target,
                "onboarded": total_onboarded,
                "descended_entries": descended_entries,
                "successful_descendants": successful_descendants,
                "dropout_descendants": dropout_descendants,
                "lateral_entries": lateral_entries,
            })

        serializer = TrainingPlanSequenceReportSerializer(report_results, many=True)
        return paginator.get_paginated_response(serializer.data)