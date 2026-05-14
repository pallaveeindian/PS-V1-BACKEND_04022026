from django.db.models import Count, F
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from rest_framework.views import APIView
from rest_framework.response import Response
from TMS.models import TrainingRequest

class PublicCadreSelectionSummaryView(APIView):
    """
    Public API for Homepage Cadre Selection Summary.
    Cached for 1 minute (60 seconds) to ensure SUPERFAST load times.
    Cache keys are automatically generated based on the URL query parameters.
    """
    
    # Cache the response for 5 minutes. Adjust the timeout as needed.
    @method_decorator(cache_page(60 * 1))
    def get(self, request, *args, **kwargs):
        # 1. Base Queryset (Assuming SoftDeleteMixin uses 'is_deleted' or 'deleted_at')
        # Adjust the filter based on your exact SoftDelete implementation
        queryset = TrainingRequest.objects.filter(
            is_active=True,
        )

        # 2. Extract Query Parameters
        district_id = request.query_params.get('district_id')
        block_id = request.query_params.get('block_id')
        exact_date = request.query_params.get('date')
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')

        # 3. Apply Filters
        if district_id:
            queryset = queryset.filter(district_id=district_id)
            
        if block_id:
            queryset = queryset.filter(block_id=block_id)
            
        if exact_date:
            queryset = queryset.filter(created_at__date=exact_date)
            
        if start_date and end_date:
            queryset = queryset.filter(created_at__date__range=[start_date, end_date])

        # 4. Construct the Optimized Query
        # Using .values() bypasses model instantiation (huge speed boost)
        # Using distinct=True prevents count multiplication from multiple left joins
        data = queryset.select_related(
            'created_by', 
            'district', 
            'block', 
            'training_plan'
        ).values(
            username=F('created_by__username'),
            district_name_en=F('district__district_name_en'),
            block_name_en=F('block__block_name_en'),
            training_name=F('training_plan__training_name'),
            created_date=F('created_at')
        ).annotate(
            beneficiary_count=Count('beneficiary_registrations', distinct=True),
            trainer_count=Count('trainer_registrations', distinct=True)
        ).order_by('-created_at')[:100] # Limiting to 100 for the homepage to maintain speed

        # 5. Return JSON directly (Bypassing DRF Serializer overhead)
        return Response({
            "status": "success",
            "count": len(data),
            "data": list(data)
        })