from django.db.models import Count, F
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from rest_framework.views import APIView
from rest_framework.response import Response
from TMS.models import TrainingRequest
from core.models import MasterDistrict 

class PublicCadreSelectionSummaryView(APIView):
    """
    Public API for Homepage Cadre Selection Summary.
    Cached for 1 minute (60 seconds) to ensure SUPERFAST load times.
    Supports detailed row records and zero-filled district-wise aggregations.
    """
    
    @method_decorator(cache_page(60 * 1))
    def get(self, request, *args, **kwargs):
        # 1. Base Queryset
        queryset = TrainingRequest.objects.filter(is_active=True)

        # 2. Extract Query Parameters
        district_id = request.query_params.get('district_id')
        block_id = request.query_params.get('block_id')
        exact_date = request.query_params.get('date')
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        financial_year = request.query_params.get('financial_year') # <-- NEW PARAMETER
        
        # Custom summary parameter flag
        district_wise_cadre_summary = request.query_params.get('district_wise_cadre_summary') == '1'

        # 3. Apply Filters
        if district_id:
            queryset = queryset.filter(district_id=district_id)
            
        if block_id:
            queryset = queryset.filter(block_id=block_id)
            
        if exact_date:
            queryset = queryset.filter(created_at__date=exact_date)
            
        if start_date and end_date:
            queryset = queryset.filter(created_at__date__range=[start_date, end_date])
            
        # Apply Financial Year Filter
        if financial_year:
            queryset = queryset.filter(financial_year=financial_year)

        # 4. Construct response payload base
        response_payload = {
            "status": "success",
            "filters_applied": {
                "financial_year": financial_year
            }
        }

        # 5. Optional Branch: District Wise Cadre Summary (Includes all 0-count districts)
        if district_wise_cadre_summary:
            # Aggregate counts by grouping directly on district_id across the filtered queryset
            district_aggregations = queryset.values('district_id').annotate(
                total_beneficiaries=Count('beneficiary_registrations', distinct=True),
                total_trainers=Count('trainer_registrations', distinct=True)
            )

            # Build a hash map for ultra-fast lookup
            counts_lookup = {
                item['district_id']: item 
                for item in district_aggregations 
                if item['district_id'] is not None
            }

            # Fetch ALL districts from Master Table to ensure 0 counts are accurately represented
            all_districts = MasterDistrict.objects.values('district_id', 'district_name_en')

            summary_data = []
            for dist in all_districts:
                d_id = dist['district_id']
                has_data = d_id in counts_lookup

                summary_data.append({
                    "district_id": d_id,
                    "district_name_en": dist['district_name_en'] or "-",
                    "financial_year": financial_year or "All", 
                    "total_beneficiaries": counts_lookup[d_id]['total_beneficiaries'] if has_data else 0,
                    "total_trainers": counts_lookup[d_id]['total_trainers'] if has_data else 0,
                })

            # Sort largest to smallest by total selections, then alphabetically by district name
            response_payload["district_wise_cadre_summary"] = sorted(
                summary_data, 
                key=lambda x: (
                    -(x['total_beneficiaries'] + x['total_trainers']), 
                    x['district_name_en'] or ""
                )
            )

        # 6. Default Branch: Fetch Detailed Records 
        # (Executed regardless or can be wrapped in an else clause depending on your design)
        detailed_data = queryset.select_related(
            'created_by', 'district', 'block', 'training_plan'
        ).values(
            'financial_year', 
            username=F('created_by__username'),
            district_name_en=F('district__district_name_en'),
            block_name_en=F('block__block_name_en'),
            training_name=F('training_plan__training_name'),
            created_date=F('created_at')
        ).annotate(
            beneficiary_count=Count('beneficiary_registrations', distinct=True),
            trainer_count=Count('trainer_registrations', distinct=True)
        ).order_by('-created_at')

        response_payload["count"] = len(detailed_data)
        response_payload["data"] = list(detailed_data)

        return Response(response_payload)