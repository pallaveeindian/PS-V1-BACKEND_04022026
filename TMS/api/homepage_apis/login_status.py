from django.db.models import Count, Q, F, Subquery
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from rest_framework.views import APIView
from rest_framework.response import Response
from TMS.models import TMSFirstLoginTracker, TrainingPartner
from core.models import MasterGeoUserScope, MasterDistrict, MasterBlock, MasterUser

class PublicFirstLoginSummaryView(APIView):
    """
    Public API for Homepage First Login / Not Logged In Summary.
    Cached for 1 minute (30 seconds).
    Supports detached GeoScope filtering and hash-mapping for performance.
    """
    
    @method_decorator(cache_page(30 * 1))
    def get(self, request, *args, **kwargs):
        # 1. Extract Query Parameters
        district_id = request.query_params.get('district_id')
        block_id = request.query_params.get('block_id')
        exact_date = request.query_params.get('date')
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        role_filter = request.query_params.get('role_name') 
        role_id_filter = request.query_params.get('role_id') 
        passwd_status = request.query_params.get('passwd_status')
        
        # Custom Flags
        not_logged_in = request.query_params.get('not_logged_in') == '1'
        district_wise_summary = request.query_params.get('district_wise_summary') == '1'

        # 2. Base Queryset Dynamic Construction
        if not_logged_in:
            # Users who HAVE NOT logged in (No TMSFirstLoginTracker entry)
            queryset = MasterUser.objects.filter(
                is_active=1
            ).exclude(
                id__in=TMSFirstLoginTracker.objects.values('master_user_id')
            )
            role_prefix = ""
        else:
            # Users who HAVE logged in
            queryset = TMSFirstLoginTracker.objects.filter(
                master_user__is_active=1
            )
            role_prefix = "master_user__"

        # 3. Apply Filters 
        if not not_logged_in:
            if exact_date:
                queryset = queryset.filter(
                    first_login_at__gte=f"{exact_date} 00:00:00",
                    first_login_at__lte=f"{exact_date} 23:59:59"
                )
            elif start_date and end_date:
                queryset = queryset.filter(
                    first_login_at__gte=f"{start_date} 00:00:00",
                    first_login_at__lte=f"{end_date} 23:59:59"
                )

        if passwd_status == 'Pending Change':
                queryset = queryset.filter(must_change_password=True)
        elif passwd_status == 'Changed':
            queryset = queryset.filter(must_change_password=False)

        if role_filter:
            queryset = queryset.filter(**{f"{role_prefix}role__name__iexact": role_filter})
            
        if role_id_filter:
            queryset = queryset.filter(**{f"{role_prefix}role_id": role_id_filter})

        # Handling Detached GeoScope Filtering via Subquery
        if district_id or block_id:
            geo_filters = {}
            if district_id: geo_filters['district_id'] = district_id
            if block_id: geo_filters['block_id'] = block_id
            
            valid_users = MasterGeoUserScope.objects.filter(**geo_filters).values('user_id')
            
            if not_logged_in:
                queryset = queryset.filter(id__in=Subquery(valid_users))
            else:
                queryset = queryset.filter(master_user_id__in=Subquery(valid_users))

        # 4. AGGREGATION: Top-level metrics
        if not_logged_in:
            stats = queryset.aggregate(
                total_records=Count('id'),
                smmu_count=Count('id', filter=Q(role__name__icontains='smmu')),
                dmmu_count=Count('id', filter=Q(role__name__icontains='dmmu')),
                bmmu_count=Count('id', filter=Q(role__name__icontains='bmmu')),
                tp_count=Count('id', filter=Q(role__name__icontains='training_partner')),
            )
            total_first_logins = 0
            passwords_changed = 0
            passwords_pending = 0
            total_not_logged_in = stats['total_records']
        else:
            stats = queryset.aggregate(
                total_first_logins=Count('id'),
                passwords_changed=Count('id', filter=Q(must_change_password=False)),
                passwords_pending=Count('id', filter=Q(must_change_password=True)),
                smmu_count=Count('id', filter=Q(master_user__role__name__icontains='smmu')),
                dmmu_count=Count('id', filter=Q(master_user__role__name__icontains='dmmu')),
                bmmu_count=Count('id', filter=Q(master_user__role__name__icontains='bmmu')),
                tp_count=Count('id', filter=Q(master_user__role__name__icontains='training_partner')),
            )
            total_first_logins = stats['total_first_logins']
            passwords_changed = stats['passwords_changed']
            passwords_pending = stats['passwords_pending']
            total_not_logged_in = 0

        # 5. AGGREGATION: Distinct Districts & Blocks
        if not_logged_in:
            filtered_user_ids = queryset.values('id')
        else:
            filtered_user_ids = queryset.values('master_user_id')
            
        geo_scopes = MasterGeoUserScope.objects.filter(user_id__in=Subquery(filtered_user_ids))
        
        distinct_districts = geo_scopes.exclude(district_id__isnull=True).values('district_id').distinct().count()
        distinct_blocks = geo_scopes.exclude(block_id__isnull=True).values('block_id').distinct().count()

        # 6. FETCH ALL RECORDS 
        if not_logged_in:
            list_data = list(queryset.values(
                master_user_id=F('id'),
                username_val=F('username'),
                role_name=F('role__name'),
                tp_name=F('tp_account__name') 
            ))
            for item in list_data:
                item['first_login_at'] = None
                item['must_change_password'] = None
                item['username'] = item.pop('username_val')
        else:
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
                item['district_id'] = None
                item['district_name_en'] = None
                item['block_id'] = None
                item['block_name_en'] = None
                
                if uid in geo_mapping:
                    d_id = geo_mapping[uid]['district_id']
                    b_id = geo_mapping[uid]['block_id']
                    if d_id in dist_names: 
                        item['district_id'] = d_id
                        item['district_name_en'] = dist_names[d_id]
                    if b_id in block_names: 
                        item['block_id'] = b_id
                        item['block_name_en'] = block_names[b_id]
                    
                del item['master_user_id']
                
        # 8. District & Block Wise Summary Mapping
        summary_data = []
        if district_wise_summary and list_data:
            summary_dict = {}
            for item in list_data:
                d_id = item['district_id']
                if not d_id:
                    continue
                
                d_name = item['district_name_en']
                b_id = item['block_id']
                b_name = item['block_name_en']
                
                if d_id not in summary_dict:
                    summary_dict[d_id] = {
                        "district_id": d_id,
                        "district_name_en": d_name,
                        "total_users": 0,
                        "blocks": {}
                    }
                    
                summary_dict[d_id]["total_users"] += 1
                
                if b_id:
                    if b_id not in summary_dict[d_id]["blocks"]:
                        summary_dict[d_id]["blocks"][b_id] = {
                            "block_id": b_id,
                            "block_name_en": b_name,
                            "user_count": 0
                        }
                    summary_dict[d_id]["blocks"][b_id]["user_count"] += 1
            
            # Format cleanly to list format
            for d_id, d_data in summary_dict.items():
                summary_data.append({
                    "district_id": d_data["district_id"],
                    "district_name_en": d_data["district_name_en"],
                    "district_user_count": d_data["total_users"],
                    "blocks": list(d_data["blocks"].values())
                })
                
            # Optional: sort alphabetically by district name
            summary_data = sorted(summary_data, key=lambda x: (x['district_name_en'] or ""))

        # 9. Return Payload
        response_payload = {
            "status": "success",
            "metrics": {
                "total_first_logins": total_first_logins,
                "total_not_logged_in": total_not_logged_in,
                "passwords_changed": passwords_changed,
                "passwords_pending": passwords_pending,
                "unique_districts_represented": distinct_districts,
                "unique_blocks_represented": distinct_blocks,
                "cadre_distribution": {
                    "SMMU": stats['smmu_count'],
                    "DMMU": stats['dmmu_count'],
                    "BMMU": stats['bmmu_count'],
                    "Training_Partner": stats['tp_count']
                }
            }
        }
        
        if district_wise_summary:
            response_payload["district_wise_summary"] = summary_data
            
        response_payload["total_records"] = len(list_data)
        response_payload["all_records"] = list_data

        return Response(response_payload)