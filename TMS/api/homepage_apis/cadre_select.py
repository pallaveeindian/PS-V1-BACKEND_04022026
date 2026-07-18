from django.db.models import Count, F, Sum
from django.db.models.functions import Coalesce
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from rest_framework.views import APIView
from rest_framework.response import Response
from TMS.models import TrainingRequest, TrainingPartnerTargets
from core.models import MasterDistrict 

class PublicCadreSelectionSummaryView(APIView):
    """
    Public API for Homepage Cadre Selection Summary.
    Cached for 5 seconds to ensure SUPERFAST load times.
    Supports detailed row records, zero-filled district-wise aggregations,
    and target vs cadre percentage calculations.
    """
    
    @method_decorator(cache_page(5 * 1))
    def get(self, request, *args, **kwargs):
        # 1. Base Queryset
        queryset = TrainingRequest.objects.filter(is_active=True)

        # 2. Extract Query Parameters
        district_id = request.query_params.get('district_id')
        block_id = request.query_params.get('block_id')
        exact_date = request.query_params.get('date')
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        financial_year = request.query_params.get('financial_year')
        
        # New Stackable Filters
        theme_id = request.query_params.get('theme_id')
        plan_id = request.query_params.get('plan_id')

        # Custom summary parameter flags
        district_wise_cadre_summary = request.query_params.get('district_wise_cadre_summary') == '1'
        dist_trgt_prcnt = request.query_params.get('dist_trgt_prcnt') == '1'
        dist_theme_prcnt = request.query_params.get('dist_theme_prcnt') == '1'
        theme_wise_summary = request.query_params.get('theme_wise_summary') == '1' 

        # Validate Mandatory Parameters for the New Endpoints
        if (dist_trgt_prcnt or dist_theme_prcnt or theme_wise_summary) and not financial_year:
            return Response({
                "status": "error",
                "message": "financial_year is MANDATORY for target vs cadre percentage calculations."
            }, status=400)

        # 3. Apply Filters to Base Queryset
        if district_id:
            queryset = queryset.filter(district_id=district_id)
            
        if block_id:
            queryset = queryset.filter(block_id=block_id)
            
        if exact_date:
            queryset = queryset.filter(created_at__date=exact_date)
            
        if start_date and end_date:
            queryset = queryset.filter(created_at__date__range=[start_date, end_date])
            
        if financial_year:
            queryset = queryset.filter(financial_year=financial_year)

        if theme_id:
            queryset = queryset.filter(training_plan__theme_id=theme_id)

        if plan_id:
            queryset = queryset.filter(training_plan_id=plan_id)

        # 4. Construct response payload base
        response_payload = {
            "status": "success",
            "filters_applied": {
                "financial_year": financial_year,
                "theme_id": theme_id,
                "plan_id": plan_id
            }
        }

        # 5a. Branch: District Wise Cadre Summary (Includes all 0-count districts)
        if district_wise_cadre_summary:
            district_aggregations = queryset.values('district_id').annotate(
                total_beneficiaries=Count('beneficiary_registrations', distinct=True),
                total_trainers=Count('trainer_registrations', distinct=True)
            )

            counts_lookup = {
                item['district_id']: item 
                for item in district_aggregations 
                if item['district_id'] is not None
            }

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

            response_payload["district_wise_cadre_summary"] = sorted(
                summary_data, 
                key=lambda x: (
                    -(x['total_beneficiaries'] + x['total_trainers']), 
                    x['district_name_en'] or ""
                )
            )

        # 5b. Branch: District Target vs Cadre Percentage
        if dist_trgt_prcnt:
            target_qs = TrainingPartnerTargets.objects.filter(
                financial_year=financial_year, 
                district__isnull=False
            )
            # Propagate stackable filters to the target calculation
            if district_id: 
                target_qs = target_qs.filter(district_id=district_id)
            if theme_id: 
                target_qs = target_qs.filter(training_plan__theme_id=theme_id)
            if plan_id: 
                target_qs = target_qs.filter(training_plan_id=plan_id)

            target_dict = {
                item['district_id']: item['total'] or 0
                for item in target_qs.values('district_id').annotate(total=Sum('target_count'))
                if item['district_id'] is not None
            }

            cadre_dict = {
                item['district_id']: item['b_count'] + item['t_count']
                for item in queryset.values('district_id').annotate(
                    b_count=Count('beneficiary_registrations', distinct=True),
                    t_count=Count('trainer_registrations', distinct=True)
                )
                if item['district_id'] is not None
            }

            all_districts = MasterDistrict.objects.values('district_id', 'district_name_en')
            dist_trgt_data = []
            
            for dist in all_districts:
                d_id = dist['district_id']
                
                # If a specific district filter was passed, only return that district
                if district_id and str(d_id) != str(district_id):
                    continue

                t_target = target_dict.get(d_id, 0)
                t_cadre = cadre_dict.get(d_id, 0)
                percentage = round((t_cadre / t_target * 100), 2) if t_target > 0 else 0.0

                dist_trgt_data.append({
                    "district_id": d_id,
                    "district_name_en": dist['district_name_en'] or "-",
                    "total_target": t_target,
                    "total_cadre": t_cadre,
                    "percentage": percentage
                })

            response_payload["district_target_percentage"] = sorted(
                dist_trgt_data,
                key=lambda x: x['total_cadre'],
                reverse=True
            )

        # 5c. Branch: District & Theme Wise Percentage
        if dist_theme_prcnt:
            target_qs = TrainingPartnerTargets.objects.filter(
                financial_year=financial_year,
                district__isnull=False,
            )
            if district_id: 
                target_qs = target_qs.filter(district_id=district_id)
            if theme_id: 
                target_qs = target_qs.filter(training_plan__theme_id=theme_id)
            if plan_id: 
                target_qs = target_qs.filter(training_plan_id=plan_id)

            # Using Coalesce in case theme is attached directly rather than through training_plan
            target_data = target_qs.annotate(
                resolved_theme=Coalesce('training_plan__theme__theme_name', 'theme')
            ).filter(
                resolved_theme__isnull=False
            ).values(
                'district_id', 'district__district_name_en', 'resolved_theme'
            ).annotate(total_target=Sum('target_count'))

            target_map = {}
            for item in target_data:
                key = (item['district_id'], item['resolved_theme'])
                target_map[key] = {
                    "district_name_en": item['district__district_name_en'],
                    "target": item['total_target'] or 0
                }

            cadre_data = queryset.filter(
                district__isnull=False, 
                training_plan__theme__isnull=False
            ).values(
                'district_id', 'district__district_name_en', 'training_plan__theme__theme_name'
            ).annotate(
                b_count=Count('beneficiary_registrations', distinct=True),
                t_count=Count('trainer_registrations', distinct=True)
            )

            cadre_map = {}
            for item in cadre_data:
                key = (item['district_id'], item['training_plan__theme__theme_name'])
                cadre_map[key] = {
                    "district_name_en": item['district__district_name_en'],
                    "cadre": item['b_count'] + item['t_count']
                }

            # Combine unique (district_id, theme_name) tuple keys from both targets and actuals
            all_keys = set(target_map.keys()).union(set(cadre_map.keys()))
            dist_theme_data = []

            for d_id, theme_name in all_keys:
                t_target = target_map.get((d_id, theme_name), {}).get("target", 0)
                t_cadre = cadre_map.get((d_id, theme_name), {}).get("cadre", 0)
                
                d_name = target_map.get((d_id, theme_name), {}).get("district_name_en") or \
                         cadre_map.get((d_id, theme_name), {}).get("district_name_en") or "-"

                percentage = round((t_cadre / t_target * 100), 2) if t_target > 0 else 0.0

                dist_theme_data.append({
                    "district_id": d_id,
                    "district_name_en": d_name,
                    "theme_name": theme_name,
                    "theme_target": t_target,
                    "total_on_boarded": t_cadre,
                    "percentage": percentage
                })

            response_payload["district_theme_percentage"] = sorted(
                dist_theme_data,
                key=lambda x: x['total_on_boarded'],
                reverse=True
            )

        # 5d. Branch: Theme Wise Summary (Aggregated across all districts)
        if theme_wise_summary:
            target_qs = TrainingPartnerTargets.objects.filter(
                financial_year=financial_year
            )
            # Propagate stackable filters
            if district_id:
                target_qs = target_qs.filter(district_id=district_id)
            if theme_id:
                target_qs = target_qs.filter(training_plan__theme_id=theme_id)
            if plan_id:
                target_qs = target_qs.filter(training_plan_id=plan_id)

            # Group targets exclusively by theme
            target_data = target_qs.annotate(
                resolved_theme=Coalesce('training_plan__theme__theme_name', 'theme')
            ).filter(
                resolved_theme__isnull=False
            ).values('resolved_theme').annotate(total_target=Sum('target_count'))

            theme_target_map = {
                item['resolved_theme']: item['total_target'] or 0 
                for item in target_data
            }

            # Group achieved (cadre) exclusively by theme
            cadre_data = queryset.filter(
                training_plan__theme__isnull=False
            ).values('training_plan__theme__theme_name').annotate(
                b_count=Count('beneficiary_registrations', distinct=True),
                t_count=Count('trainer_registrations', distinct=True)
            )

            theme_cadre_map = {
                item['training_plan__theme__theme_name']: item['b_count'] + item['t_count']
                for item in cadre_data
            }

            # Combine unique theme keys from both targets and actuals
            all_themes = set(theme_target_map.keys()).union(set(theme_cadre_map.keys()))
            theme_summary_data = []

            for t_name in all_themes:
                t_target = theme_target_map.get(t_name, 0)
                t_cadre = theme_cadre_map.get(t_name, 0)
                percentage = round((t_cadre / t_target * 100), 2) if t_target > 0 else 0.0

                theme_summary_data.append({
                    "theme_name": t_name,
                    "theme_target": t_target,
                    "total_on_boarded": t_cadre,
                    "percentage": percentage
                })

            response_payload["theme_wise_summary"] = sorted(
                theme_summary_data,
                key=lambda x: x['total_on_boarded'],
                reverse=True
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