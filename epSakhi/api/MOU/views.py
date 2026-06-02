from rest_framework.permissions import BasePermission, SAFE_METHODS
from rest_framework.exceptions import PermissionDenied, NotFound
from rest_framework.generics import RetrieveAPIView
from django.core.exceptions import ObjectDoesNotExist

from django.db.models import Q
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db.models import F
from datetime import date
from django.db import transaction
import traceback

from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated

from core.models import MasterGeoUserScope, MasterBlock, MasterDistrict
from epSakhi.models import *
from .serializers import *

# Pagination
class MOUEnterprisePagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 100

# Role Helper Function
def _role_name(user) -> str:
    try:
        role = getattr(user, "role", None)
        if role and getattr(role, "name", None):
            return role.name.lower()
    except Exception:
        pass
    return ""

def get_master_user(request):
    if not request.user or not request.user.is_authenticated:
        return None
    try:
        # Replace `core_models` with your actual module path
        return MasterUser.objects.get(username=request.user.username)
    except ObjectDoesNotExist:
        return None

class IsBMMUOrDMMUOrReadOnly(BasePermission):
    """
    Allows read-only access for all authenticated users.
    Write access is restricted to BMMU (role_id=1) and DMMU (role_id=2).
    """
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
            
        # Read permissions are allowed to any authenticated user
        if request.method in SAFE_METHODS:
            return True

        master_user = get_master_user(request)
        if not master_user:
            return False

        role_name = _role_name(master_user)
        role_id = getattr(master_user.role, 'id', None)

        # Write permissions (POST, PUT, PATCH, DELETE)
        if role_name in ['bmmu', 'dmmu'] or role_id in [1, 2]:
            return True
            
        return False

# One-Shot Creation API
class MOUOneShotCreateView(APIView):
    permission_classes = [IsBMMUOrDMMUOrReadOnly]

    def _format_error(self, base_error_code, drf_errors=None, row_index=None, sub_row_index=None):
        """
        Explicitly pulls the error definition from ErrorDB and packages it 
        with the DRF serializer field-level errors for exact diagnosis.
        """
        # 1. Fetch exact error from DB
        error_record = ErrorDB.objects.filter(error_code=base_error_code).first()
        
        # 2. Setup fallbacks in case DB isn't seeded yet
        db_message = error_record.error_message if error_record else "Validation Error"
        db_info = error_record.additional_info if error_record else "Check submitted data."

        # 3. Construct the strict JSON response payload
        response_data = {
            "success": False,
            "error": {
                "code": base_error_code,
                "message": db_message,
                "guidance": db_info,
            },
            "field_failures": drf_errors 
        }

        # 4. Attach Row Coordinates if this happened in an array
        if row_index is not None:
            response_data["error"]["failed_at_row"] = row_index + 1 
        if sub_row_index is not None:
            response_data["error"]["failed_at_sub_row"] = sub_row_index + 1

        return Response(response_data, status=status.HTTP_400_BAD_REQUEST)

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        master_user = get_master_user(request)
        if not master_user:
            return self._format_error("AUTH_002", drf_errors={"user": "Not authenticated properly."})

        # --- SURGICAL FIX: Extract JSON from FormData ---
        if 'payload' in request.data:
            import json
            data = json.loads(request.data.get('payload', '{}'))
        else:
            data = request.data.copy()
        
        try:
            # =================================================================
            # 1. PARSE & CREATE ENTERPRISE 
            # =================================================================
            basic_info = data.get('basic_info', {})
            ent_prod_sel = data.get('selection_ent_prod', 'enterprise')
            
            ent_data = data.get('enterprise') or {}
            prod_data = data.get('product') or {}

            # Build flat payload for the Enterprise Serializer
            ent_payload = {
                'enterprise_name': ent_data.get('enterprise_name', '') if ent_prod_sel == 'enterprise' else prod_data.get('product_name', ''),
                'entrepreneur_name': ent_data.get('entrepreneur_name', ''),
                'entrepreneur_contact': ent_data.get('entrepreneur_contact', ''),
                
                # React has already perfectly formatted enterprise_type as a stringified dict
                'enterprise_type': ent_data.get('enterprise_type', None), 
                
                # --- SURGICAL FIX: Map file from request.FILES and correct DB spelling (entrepeneur) ---
                'entrepeneur_picture': request.FILES.get('entrepreneur_picture', None),
                
                # --- SURGICAL FIX: Map SHG & CBO missing fields ---
                'lokos_shg_name': basic_info.get('shg_name', ''),
                'lokos_shg_code': basic_info.get('shg_code', ''),
                'lokos_clf_name': basic_info.get('clf_name', ''),
                'lokos_clf_code': basic_info.get('clf_code', ''),
                'lokos_vo_name': basic_info.get('vo_name', ''),
                'lokos_vo_code': basic_info.get('vo_code', ''),
                
                # --- SURGICAL FIX: Django expects exact field names for Foreign Keys (without _id postfix) ---
                'district': basic_info.get('district_id') or None,
                'block': basic_info.get('block_id') or None,
                'panchayat': basic_info.get('panchayat_id') or None,
                'village': basic_info.get('village_id') or None,  # Village is now correctly captured
            }

            ent_serializer = MOUEnterpriseSerializer(data=ent_payload)
            if not ent_serializer.is_valid():
                error_code = "ENT_003" if any("lokos" in key for key in ent_serializer.errors) else "ENT_001"
                return self._format_error(error_code, ent_serializer.errors)
            
            enterprise = ent_serializer.save(created_by=master_user)

            # =================================================================
            # 1b. CREATE PRODUCTS & NESTED CATEGORIES IF CHOSEN
            # =================================================================
            if ent_prod_sel == 'product' and prod_data.get('product_name'):
                prod_serializer = MOUProductsSerializer(data={
                    'enterprise': enterprise.id,
                    'product_name': prod_data.get('product_name')
                })
                if not prod_serializer.is_valid():
                    return self._format_error("PRD_001", prod_serializer.errors)
                product_instance = prod_serializer.save(created_by=master_user)

                # Map child product categories into MOUProdCategories table
                for j, cat_item in enumerate(prod_data.get('prod_categories', [])):
                    cat_serializer = MOUProdCategoriesSerializer(data={
                        'MOUProdID': product_instance.id,
                        'parent_category': cat_item.get('parent_category', ''),
                        'child_category': cat_item.get('child_category', '')
                    })
                    if not cat_serializer.is_valid():
                        return self._format_error("CAT_001", cat_serializer.errors, sub_row_index=j)
                    cat_serializer.save(created_by=master_user)


            # =================================================================
            # 2. CREATE BUYER ORG OR TRADER (Handling Objects directly)
            # =================================================================
            org_trader_sel = data.get('selection_org_trader', 'buyer_org')
            
            if org_trader_sel == 'buyer_org':
                buyer_org_data = data.get('buyer_org') or {}
                if buyer_org_data.get('buyer_org_name'): 
                    buyer_org_data['enterprise'] = enterprise.id
                    
                    org_serializer = MOUOrgSerializer(data=buyer_org_data)
                    if not org_serializer.is_valid():
                        code = "ORG_002" if "org_contact" in org_serializer.errors else "ORG_001"
                        return self._format_error(code, org_serializer.errors)
                    org_serializer.save(created_by=master_user)

            elif org_trader_sel == 'trader':
                trader_data = data.get('trader') or {}
                if trader_data.get('trader_name'):
                    trader_data['enterprise'] = enterprise.id
                    
                    trader_serializer = MOUTradersSerializer(data=trader_data)
                    if not trader_serializer.is_valid():
                        code = "TRD_002" if "trader_contact" in trader_serializer.errors else "TRD_001"
                        return self._format_error(code, trader_serializer.errors)
                    trader_serializer.save(created_by=master_user)


            # =================================================================
            # 3. CREATE MOUs & NESTED DOCS
            # =================================================================
            for i, mou_data in enumerate(data.get('mous', [])):
                if not mou_data.get('mou_status') and not mou_data.get('mou_date'):
                    continue
                    
                mou_data['enterprise'] = enterprise.id
                mou_serializer = MOUSerializer(data=mou_data)
                if not mou_serializer.is_valid():
                    code = "MOU_002" if "mou_date" in mou_serializer.errors else "MOU_001"
                    return self._format_error(code, mou_serializer.errors, row_index=i)
                mou = mou_serializer.save(created_by=master_user)

                # Process MOU Docs
                for j, doc_data in enumerate(mou_data.get('mou_docs', [])):
                    if not doc_data.get('doc_name') and not request.FILES.get(f'mou_doc_{j}'):
                        continue 
                        
                    doc_data['mou_id'] = mou.id
                    doc_data['doc_file'] = request.FILES.get(f'mou_doc_{j}', None)
                    
                    doc_serializer = MOUDocsSerializer(data=doc_data)
                    if not doc_serializer.is_valid():
                        code = "DOC_002" if "doc_file" in doc_serializer.errors else "DOC_001"
                        return self._format_error(code, doc_serializer.errors, row_index=i, sub_row_index=j)
                    doc_serializer.save(created_by=master_user)


            # =================================================================
            # 4. CREATE SALES PROJECTIONS
            # =================================================================
            for i, sales_data in enumerate(data.get('sales', [])):
                if not any(sales_data.values()):
                    continue 
                    
                sales_data['enterprise'] = enterprise.id
                sales_serializer = MOUSalesSerializer(data=sales_data)
                
                if not sales_serializer.is_valid():
                    code = "SAL_001"
                    if "est_annual_sales" in sales_serializer.errors and "cannot be less than monthly" in str(sales_serializer.errors):
                        code = "SAL_003"
                    elif "negative" in str(sales_serializer.errors):
                        code = "SAL_002"
                    return self._format_error(code, sales_serializer.errors, row_index=i)
                sales_serializer.save(created_by=master_user)


            # =================================================================
            # 5. UPDATE DISTRICT TARGETS (DMMU / BMMU tracking)
            # =================================================================
            role_name = _role_name(master_user)
            if role_name in ['dmmu', 'bmmu']:
                user_scope = MasterGeoUserScope.objects.filter(
                    user_id=master_user.id, 
                    is_active=1
                ).first()

                if user_scope and user_scope.district_id:
                    today = date.today()
                    if today.month >= 4:
                        current_fy = f"{today.year}-{str(today.year + 1)[-2:]}"
                    else:
                        current_fy = f"{today.year - 1}-{str(today.year)[-2:]}"

                    target_record = DistMOUTarget.objects.select_for_update().filter(
                        district_id=user_scope.district_id,
                        financial_year=current_fy,
                        is_active=True
                    ).first()

                    if target_record:
                        if target_record.achieved_mou is None:
                            target_record.achieved_mou = 1
                        else:
                            target_record.achieved_mou += 1
                        
                        target_record.save(update_fields=['achieved_mou', 'updated_at'])


            return Response({
                "success": True,
                "message": "Enterprise survey data successfully saved.",
                "enterprise_id": enterprise.id
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            traceback.print_exc() 
            return self._format_error(
                "SYS_001", 
                drf_errors={"exception": str(e)}
            )

# Listing API
class MOUEnterpriseListingAPI(APIView):

    def get(self, request):

        queryset = MOUEnterprise.objects.filter(
            is_active=True,
            deleted_at__isnull=True
        ).select_related(
            "district",
            "block",
            "panchayat"
        ).order_by("-id")

        # -----------------------------
        # FILTERS
        # -----------------------------

        district_id = request.GET.get("district")
        block_id = request.GET.get("block")
        panchayat_id = request.GET.get("panchayat")
        lokos_shg_code = request.GET.get("lokos_shg_code")
        lokos_clf_code = request.GET.get("lokos_clf_code")
        lokos_vo_code = request.GET.get("lokos_vo_code")
        search = request.GET.get("search")

        if district_id:
            queryset = queryset.filter(district_id=district_id)

        if block_id:
            queryset = queryset.filter(block_id=block_id)

        if panchayat_id:
            queryset = queryset.filter(panchayat_id=panchayat_id)

        if lokos_shg_code:
            queryset = queryset.filter(
                lokos_shg_code__icontains=lokos_shg_code
            )

        if lokos_clf_code:
            queryset = queryset.filter(
                lokos_clf_code__icontains=lokos_clf_code
            )

        if lokos_vo_code:
            queryset = queryset.filter(
                lokos_vo_code__icontains=lokos_vo_code
            )

        # -----------------------------
        # SEARCH
        # -----------------------------

        if search:
            queryset = queryset.filter(
                Q(enterprise_name__icontains=search) |
                Q(entrepreneur_name__icontains=search) |
                Q(entrepreneur_contact__icontains=search)
            )

        # -----------------------------
        # PAGINATION
        # -----------------------------

        paginator = MOUEnterprisePagination()
        paginated_queryset = paginator.paginate_queryset(
            queryset,
            request
        )

        serializer = MOUEnterpriseListSerializer(
            paginated_queryset,
            many=True
        )

        return paginator.get_paginated_response({
            "success": True,
            "message": "Enterprise listing fetched successfully.",
            "data": serializer.data
        }) 

# Detail API with nested serializers for all related MOU data
class MOUEnterpriseDetailView(RetrieveAPIView):
    """
    Retrieves a single MOU Enterprise and ALL its related nested survey data.
    """
    queryset = MOUEnterprise.objects.all()
    serializer_class = MOUEnterpriseDetailSerializer
    permission_classes = [IsBMMUOrDMMUOrReadOnly] 
    lookup_field = 'id'        

# Deletion API (Soft Delete)
class MOUEnterpriseDeleteView(APIView):
    """
    Atomically soft-deletes an MOU Enterprise and all of its related nested records.
    Iterates through instances to ensure SoftDeleteMixin.delete() is called, 
    preventing Django's default queryset hard-delete behavior.
    """
    permission_classes = [IsBMMUOrDMMUOrReadOnly]

    def _format_error(self, base_error_code, drf_errors=None, status_code=status.HTTP_400_BAD_REQUEST):
        """Helper to format exact error diagnoses from ErrorDB."""
        error_record = ErrorDB.objects.filter(error_code=base_error_code).first()
        
        db_message = error_record.error_message if error_record else "Validation Error"
        db_info = error_record.additional_info if error_record else "Check submitted data."

        response_data = {
            "success": False,
            "error": {
                "code": base_error_code,
                "message": db_message,
                "guidance": db_info,
            }
        }
        if drf_errors:
            response_data["field_failures"] = drf_errors

        return Response(response_data, status=status_code)

    @transaction.atomic
    def delete(self, request, id, *args, **kwargs):
        master_user = get_master_user(request)
        if not master_user:
            return self._format_error("AUTH_002", drf_errors={"user": "Not authenticated properly."}, status_code=status.HTTP_403_FORBIDDEN)

        try:
            # 1. Fetch the Target Enterprise
            enterprise = MOUEnterprise.objects.get(id=id)

            # 2. Explicitly Soft-Delete Grandchildren individually
            for mou in enterprise.mous.all():
                for doc in mou.mou_docs.all():
                    doc.delete(by_user=master_user)
            
            for product in enterprise.products.all():
                for category in product.prod_categories.all():
                    category.delete(by_user=master_user)

            # 3. Explicitly Soft-Delete Children individually
            for mou in enterprise.mous.all():
                mou.delete(by_user=master_user)
                
            for org in enterprise.buyer_orgs.all():
                org.delete(by_user=master_user)
                
            for trader in enterprise.traders.all():
                trader.delete(by_user=master_user)
                
            for product in enterprise.products.all():
                product.delete(by_user=master_user)
                
            for sale in enterprise.sales.all():
                sale.delete(by_user=master_user)

            # 4. Delete the Parent Enterprise
            enterprise.delete(by_user=master_user)

            # 5. Decrement District MOU Target for DMMU/BMMU
            role_name = _role_name(master_user)
            if role_name in ['dmmu', 'bmmu']:
                # 5a. Get User's District Assignment
                user_scope = MasterGeoUserScope.objects.filter(
                    user_id=master_user.id, 
                    is_active=1
                ).first()

                if user_scope and user_scope.district_id:
                    # 5b. Determine Current Financial Year (e.g., "2024-25")
                    today = date.today()
                    if today.month >= 4:
                        current_fy = f"{today.year}-{str(today.year + 1)[-2:]}"
                    else:
                        current_fy = f"{today.year - 1}-{str(today.year)[-2:]}"

                    # 5c. Fetch Target Record using select_for_update
                    target_record = DistMOUTarget.objects.select_for_update().filter(
                        district_id=user_scope.district_id,
                        financial_year=current_fy,
                        is_active=True
                    ).first()

                    if target_record:
                        # 5d. Safely decrement (prevent going below 0)
                        if target_record.achieved_mou is not None and target_record.achieved_mou > 0:
                            target_record.achieved_mou -= 1
                            target_record.save(update_fields=['achieved_mou', 'updated_at'])

            # If no exception was raised, transaction commits automatically
            return Response({
                "success": True,
                "message": f"MOU Enterprise with ID {id} and all related data successfully soft-deleted.",
                "deleted_id": id
            }, status=status.HTTP_200_OK)

        except MOUEnterprise.DoesNotExist:
            return self._format_error("ENT_404", status_code=status.HTTP_404_NOT_FOUND)

        except Exception as e:
            traceback.print_exc()
            return self._format_error(
                "SYS_001", 
                drf_errors={"exception": str(e)}, 
                status_code=status.HTTP_400_BAD_REQUEST
            )

# District wise Target vs Achievement API for DMMU/BMMU dashboards (can be filtered by financial year)
class MOUTargetListView(APIView):
    """
    API to fetch MOU Targets with advanced sorting, filtering, 
    and a custom district-wise summary driven by MasterGeoUserScope.
    """
    permission_classes = [IsAuthenticated] # Or use IsBMMUOrDMMUOrReadOnly if preferred

    def get(self, request, *args, **kwargs):
        # 1. Extract Query Parameters
        district_id = request.query_params.get('district_id')
        financial_year = request.query_params.get('financial_year')
        sort_by = request.query_params.get('sort_by')
        district_wise_summary = request.query_params.get('district_wise_summary') == '1'

        # 2. Determine Default Financial Year if none provided
        if not financial_year:
            today = date.today()
            if today.month >= 4:
                financial_year = f"{today.year}-{str(today.year + 1)[-2:]}"
            else:
                financial_year = f"{today.year - 1}-{str(today.year)[-2:]}"

        # 3. Base Queryset
        queryset = DistMOUTarget.objects.filter(
            is_active=True,
            financial_year=financial_year
        ).select_related('district')

        # 4. Apply Filters
        if district_id:
            queryset = queryset.filter(district_id=district_id)

        # 5. Apply Sorting
        if sort_by == 'achieved_desc':
            queryset = queryset.order_by(F('achieved_mou').desc(nulls_last=True))
        elif sort_by == 'achieved_asc':
            queryset = queryset.order_by(F('achieved_mou').asc(nulls_last=True))
        elif sort_by == 'target_desc':
            queryset = queryset.order_by(F('mou_target').desc(nulls_last=True))
        elif sort_by == 'target_asc':
            queryset = queryset.order_by(F('mou_target').asc(nulls_last=True))
        else:
            queryset = queryset.order_by('district__district_name_en') # Default

        # 6. Branch Logic: Detailed Summary vs Standard List
        if district_wise_summary:
            return self._get_district_wise_summary(queryset, financial_year)
        
        # Standard List Response
        target_list = []
        for target in queryset:
            target_list.append({
                "id": target.id,
                "district_id": target.district_id,
                "district_name": target.district.district_name_en if target.district else None,
                "mou_target": target.mou_target or 0,
                "achieved_mou": target.achieved_mou or 0,
                "financial_year": target.financial_year
            })

        return Response({
            "success": True,
            "financial_year": financial_year,
            "total_records": len(target_list),
            "data": target_list
        }, status=status.HTTP_200_OK)

    def _get_district_wise_summary(self, target_queryset, financial_year):
        """
        Helper method to map MOUEnterprise forms to MasterGeoUserScope blocks.
        """
        # A. Get Target District IDs
        dist_ids = list(target_queryset.values_list('district_id', flat=True))

        # B. Fetch all active MOUEnterprise records for these districts
        # Filtering by the same year logic can be added if MOUEnterprise tracks FY natively.
        # Here we just grab active forms in the district.
        forms = MOUEnterprise.objects.filter(
            district_id__in=dist_ids, 
            is_active=True
        ).values('district_id', 'created_by')

        # C. Map created_by users to their Block Scope
        user_ids = {f['created_by'] for f in forms if f['created_by']}
        
        scopes = MasterGeoUserScope.objects.filter(
            user_id__in=user_ids, 
            is_active=1
        ).values('user_id', 'block_id')
        
        block_ids = {s['block_id'] for s in scopes if s['block_id']}
        
        blocks = MasterBlock.objects.filter(
            block_id__in=block_ids
        ).values('block_id', 'block_name_en')

        # D. Build Lookup Dictionaries
        block_name_map = {b['block_id']: b['block_name_en'] for b in blocks}
        user_to_block_name = {}
        for s in scopes:
            b_id = s.get('block_id')
            if b_id and b_id in block_name_map:
                user_to_block_name[s['user_id']] = block_name_map[b_id]

        # E. Construct the Final Output Dictionary as requested
        summary_data = []
        for target in target_queryset:
            d_id = target.district_id
            d_name = target.district.district_name_en if target.district else "Unknown"
            
            # Filter forms for this specific district
            dist_forms = [f for f in forms if f['district_id'] == d_id]
            
            # Count by block
            block_counts = {}
            for form in dist_forms:
                uid = form['created_by']
                b_name = user_to_block_name.get(uid, "Unknown/SMMU/DMMU")
                block_counts[b_name] = block_counts.get(b_name, 0) + 1

            # Build dict structure exactly as requested
            district_dict = {
                "district": d_id,
                "district_name": d_name,
                "blocks": len(block_counts),
                "total_achieved_mou": target.achieved_mou or 0,
            }
            
            # Unpack block counts directly into the dictionary
            for b_name, count in block_counts.items():
                district_dict[b_name] = count
                
            summary_data.append(district_dict)

        return Response({
            "success": True,
            "financial_year": financial_year,
            "total_districts": len(summary_data),
            "data": summary_data
        }, status=status.HTTP_200_OK)