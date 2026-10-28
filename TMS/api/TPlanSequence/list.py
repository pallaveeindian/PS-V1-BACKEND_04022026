# Desktop/BDO_Projects/pragati_setu/TMS/api/TPlanSequence/list.py
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from django.db.models import OuterRef, Subquery

from TMS.models import TrainingPlanSequence
from .serializers import TrainingPlanSequenceListSerializer

class TrainingPlanSequenceListAPIView(generics.ListAPIView):
    """
    Returns a paginated list of all active Training Plan Sequences,
    including the resolved names of the previous, current, and next training plans.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = TrainingPlanSequenceListSerializer
    
    # Assuming you still have SequencePagination defined in your views.py
    # If not, you can swap this for standard PageNumberPagination
    from rest_framework.pagination import PageNumberPagination
    class StandardResultsSetPagination(PageNumberPagination):
        page_size = 20
        page_size_query_param = 'page_size'
        max_page_size = 100
        
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        # Highly efficient Subquery to fetch the name of the previous step's training plan
        prev_plan_subquery = TrainingPlanSequence.objects.filter(
            sequence_group_name=OuterRef('sequence_group_name'),
            step_order=OuterRef('step_order') - 1,
            is_active=True
        ).values('training_plan__training_name')[:1]

        # Base query with select_related for current and next plans to prevent N+1 queries
        return TrainingPlanSequence.objects.filter(is_active=True).select_related(
            'training_plan',
            'training_plan__theme',
            'next_training_plan'
        ).annotate(
            annotated_prev_plan_name=Subquery(prev_plan_subquery)
        ).order_by('sequence_group_name', 'step_order')