from django.http import JsonResponse
from django.db.models import OuterRef, Subquery, Count, Q
from core.models import MasterUser, MasterGeoUserScope, MasterDistrict, MasterPanchayat
from epSakhi.models import CRPEP, CRPEPToPanchayat, MappingCRPTargets
from core.api.upsrlm import BaseUpsrlmView, _as_list  

def get_dmmu_crp_stats(request):
    """
    Returns DMM accounts (role_id = 2) with their district_id, district_name_en, 
    and a count of fully completed CRP accounts created by them.
    """
    # 1. Subquery to get the district_id for the user from MasterGeoUserScope
    district_id_subquery = MasterGeoUserScope.objects.filter(
        user_id=OuterRef('id')
    ).values('district_id')[:1]

    # 2. Subquery to get the district name based on the resolved district_id
    district_name_subquery = MasterDistrict.objects.filter(
        district_id=OuterRef('geo_district_id')
    ).values('district_name_en')[:1]

    # 3. Subquery to get the district target_count based on the resolved district_id
    target_count_subquery = MappingCRPTargets.objects.filter(
        district_id=OuterRef('geo_district_id')
    ).values('target_count')[:1]

    # 4. Main Query: Filter DMM users, annotate geographic data, and count completed CRPs
    # A CRP is completed if it has a MasterUser record, a CRPEP record, and at least 1 CRPEPToPanchayat record.
    dmms = MasterUser.objects.filter(
        role_id=2
    ).annotate(
        geo_district_id=Subquery(district_id_subquery)
    ).annotate(
        geo_district_name=Subquery(district_name_subquery)
    ).annotate(
        district_target_count=Subquery(target_count_subquery)        
    ).annotate(
        created_crp_count=Count(
            'masteruser_created_by_set',  # Related name for MasterUser.created_by
            filter=Q(
                masteruser_created_by_set__crpep_account__isnull=False,  # Has CRPEP row
                masteruser_created_by_set__crpeptopanchayat__isnull=False  # Has CRPEPToPanchayat row
            ),
            distinct=True
        )
    ).order_by('-created_crp_count')

    # 4. Serialize data
    response_data = []
    for dmm in dmms:
        response_data.append({
            "dmmu_user_id": dmm.id,
            "username": dmm.username,
            "district_id": dmm.geo_district_id,
            "district_name_en": dmm.geo_district_name,
            "created_crp_count": dmm.created_crp_count,
            "district_target_count": dmm.district_target_count
        })

    return JsonResponse({
        "status": "success",
        "count": len(response_data),
        "data": response_data
    })


def get_dmmu_crp_detail(request, dmmu_id):
    """
    Returns completed CRP accounts created by a specific DMMU, 
    including their CRPEP details, LokOS CLF Name, and allocated panchayats (with names).
    """
    # 1. Fetch completed CRPs created by the specified dmmu_id
    completed_crps = MasterUser.objects.filter(
        created_by_id=dmmu_id,
        crpep_account__isnull=False,
        crpeptopanchayat__isnull=False
    ).distinct().prefetch_related(
        'crpep_account',          # Prefetch CRPEP data
        'crpeptopanchayat_set'    # Prefetch Panchayat allocation data
    )

    crp_data_list = []
    
    # Initialize the base view to utilize the fetch_from_apisetu tool
    upsrlm_helper = BaseUpsrlmView()

    for crp in completed_crps:
        # Extract CRPEP Data
        crpep_info = []
        for ep in crp.crpep_account.all():
            block_id = ep.block.block_id if ep.block else None
            nodal_clf = ep.nodal_clf
            clf_name = None
            
            # Request CLF block list to resolve 'name' of the nodal_clf
            if block_id and nodal_clf:
                try:
                    cache_key = f"upsrlm:clf-list:{block_id}"
                    raw_clfs = upsrlm_helper.fetch_from_apisetu(
                        cache_key, 
                        "clf/block", 
                        params={"block_id": block_id}
                    )
                    
                    # raw_clfs is a dict/list. Safely extract the array from 'results' or 'data'
                    clfs = []
                    if isinstance(raw_clfs, list):
                        clfs = raw_clfs
                    elif isinstance(raw_clfs, dict):
                        if "results" in raw_clfs and isinstance(raw_clfs["results"], list):
                            clfs = raw_clfs["results"]
                        elif "data" in raw_clfs and isinstance(raw_clfs["data"], list):
                            clfs = raw_clfs["data"]
                        else:
                            clfs = [raw_clfs]
                    
                    for clf in clfs:
                        if str(clf.get("code")) == str(nodal_clf):
                            clf_name = clf.get("name")
                            break
                except Exception:
                    # Ignore API/Gateway errors gracefully and leave clf_name as None
                    pass

            crpep_info.append({
                "crpep_id": ep.id,
                "name": ep.name,
                "district_id": ep.district.district_id if ep.district else None,
                "district_name": ep.district.district_name_en if ep.district else None,
                "block_id": block_id,
                "block_name": ep.block.block_name_en if ep.block else None,
                "panchayat_id": ep.panchayat.panchayat_id if ep.panchayat else None,
                "panchayat_name": ep.panchayat.panchayat_name_en if ep.panchayat else None,
                "lokos_shg_code": ep.lokos_shg_code,
                "nodal_clf": nodal_clf,
                "nodal_clf_name": clf_name,  
                "lokos_member_code": ep.lokos_member_code,
                "category": ep.category,
                "subcategory": ep.subcategory,
                "marks_obtained": ep.marks_obtained,
                "mobile_number": ep.mobile_number,
            })

        # Extract Allocated Panchayats and resolve their English names
        allocated_panchayat_ids = list(
            crp.crpeptopanchayat_set.values_list('allocated_panchayat_id', flat=True)
        )
        
        # Query MasterPanchayat to fetch the actual names
        allocated_panchayats_qs = MasterPanchayat.objects.filter(panchayat_id__in=allocated_panchayat_ids)
        allocated_panchayats_details = [
            {
                "panchayat_id": p.panchayat_id,
                "panchayat_name_en": p.panchayat_name_en
            } 
            for p in allocated_panchayats_qs
        ]

        # Build final dictionary (excluding password and username)
        crp_data_list.append({
            "master_user_id": crp.id,
            "recovery_email": crp.recovery_email,
            "recovery_mobile": crp.recovery_mobile,
            "is_active": crp.is_active,
            "last_active_on": crp.last_active_on,
            "created_at": crp.created_at,
            "crpep_details": crpep_info,
            "allocated_panchayats": allocated_panchayats_details # Detailed array with names included
        })

    return JsonResponse({
        "status": "success",
        "dmmu_id": dmmu_id,
        "completed_crp_count": len(crp_data_list),
        "crp_details": crp_data_list
    })