from django.db.models import Count, Q, F, Subquery
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from rest_framework.views import APIView
from rest_framework.response import Response
from TMS.models import TMSFirstLoginTracker, TrainingPartner
from core.models import MasterGeoUserScope, MasterDistrict, MasterBlock

class PublicFirstLoginSummaryView(APIView):
    """
    Public API for Homepage First Login Summary.
    Cached for 1 minute (60 seconds).
    Supports detached GeoScope filtering and hash-mapping for performance.
    """
    
    @method_decorator(cache_page(60 * 1))
    def get(self, request, *args, **kwargs):
        # 1. Base Queryset: Only active users
        queryset = TMSFirstLoginTracker.objects.filter(
            master_user__is_active=1
        )

        # 2. Extract Query Parameters
        district_id = request.query_params.get('district_id')
        block_id = request.query_params.get('block_id')
        exact_date = request.query_params.get('date')
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        role_filter = request.query_params.get('role_name') 
        role_id_filter = request.query_params.get('role_id') 

        # 3. Apply Filters 
        if exact_date:
            # Covers the entire 24-hour period of the exact date
            queryset = queryset.filter(
                first_login_at__gte=f"{exact_date} 00:00:00",
                first_login_at__lte=f"{exact_date} 23:59:59"
            )
            
        elif start_date and end_date:
            # Explicitly sets end_date time to 23:59:59 to prevent midnight cutoff
            queryset = queryset.filter(
                first_login_at__gte=f"{start_date} 00:00:00",
                first_login_at__lte=f"{end_date} 23:59:59"
            )
            
        if role_filter:
            queryset = queryset.filter(master_user__role__name__iexact=role_filter)
            
        if role_id_filter:
            queryset = queryset.filter(master_user__role_id=role_id_filter)

        # Handling Detached GeoScope Filtering via Subquery
        if district_id or block_id:
            geo_filters = {}
            if district_id: geo_filters['district_id'] = district_id
            if block_id: geo_filters['block_id'] = block_id
            
            valid_users = MasterGeoUserScope.objects.filter(**geo_filters).values('user_id')
            queryset = queryset.filter(master_user_id__in=Subquery(valid_users))

        # 4. AGGREGATION: Top-level metrics
        stats = queryset.aggregate(
            total_first_logins=Count('id'),
            passwords_changed=Count('id', filter=Q(must_change_password=False)),
            passwords_pending=Count('id', filter=Q(must_change_password=True)),
            smmu_count=Count('id', filter=Q(master_user__role__name__icontains='smmu')),
            dmmu_count=Count('id', filter=Q(master_user__role__name__icontains='dmmu')),
            bmmu_count=Count('id', filter=Q(master_user__role__name__icontains='bmmu')),
            tp_count=Count('id', filter=Q(master_user__role__name__icontains='training_partner')),
        )

        # 5. AGGREGATION: Distinct Districts & Blocks
        filtered_user_ids = queryset.values('master_user_id')
        geo_scopes = MasterGeoUserScope.objects.filter(user_id__in=Subquery(filtered_user_ids))
        
        distinct_districts = geo_scopes.exclude(district_id__isnull=True).values('district_id').distinct().count()
        distinct_blocks = geo_scopes.exclude(block_id__isnull=True).values('block_id').distinct().count()

        # 6. FETCH ALL RECORDS 
        list_data = list(queryset.values(
            'master_user_id',
            'first_login_at',
            'must_change_password',
            username=F('master_user__username'),
            role_name=F('master_user__role__name'),
            tp_name=F('master_user__tp_account__name') 
        ))

        # 7. PYTHON Hash Mapping for Geo Names (To bypass slow detached DB Joins)
        if list_data:
            fetched_uids = [item['master_user_id'] for item in list_data]
            
            geo_mapping = {
                g['user_id']: g 
                for g in MasterGeoUserScope.objects.filter(user_id__in=fetched_uids).values('user_id', 'district_id', 'block_id')
            }
            
            dist_ids = {g['district_id'] for g in geo_mapping.values() if g['district_id']}
            block_ids = {g['block_id'] for g in geo_mapping.values() if g['block_id']}
            
            dist_names = {
                d['district_id']: d['district_name_en'] 
                for d in MasterDistrict.objects.filter(district_id__in=dist_ids).values('district_id', 'district_name_en')
            }
            block_names = {
                b['block_id']: b['block_name_en'] 
                for b in MasterBlock.objects.filter(block_id__in=block_ids).values('block_id', 'block_name_en')
            }
            
            for item in list_data:
                uid = item['master_user_id']
                item['district_name_en'] = None
                item['block_name_en'] = None
                
                if uid in geo_mapping:
                    d_id = geo_mapping[uid]['district_id']
                    b_id = geo_mapping[uid]['block_id']
                    if d_id in dist_names: item['district_name_en'] = dist_names[d_id]
                    if b_id in block_names: item['block_name_en'] = block_names[b_id]
                    
                del item['master_user_id']

        # 8. Return Payload
        return Response({
            "status": "success",
            "metrics": {
                "total_first_logins": stats['total_first_logins'],
                "passwords_changed": stats['passwords_changed'],
                "passwords_pending": stats['passwords_pending'],
                "unique_districts_logged_in": distinct_districts,
                "unique_blocks_logged_in": distinct_blocks,
                "cadre_distribution": {
                    "SMMU": stats['smmu_count'],
                    "DMMU": stats['dmmu_count'],
                    "BMMU": stats['bmmu_count'],
                    "Training_Partner": stats['tp_count']
                }
            },
            "total_records": len(list_data),
            "all_records": list_data
        })