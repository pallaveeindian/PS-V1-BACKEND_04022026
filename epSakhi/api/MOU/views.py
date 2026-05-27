from rest_framework.permissions import BasePermission, SAFE_METHODS
from rest_framework.exceptions import PermissionDenied, NotFound
from django.core.exceptions import ObjectDoesNotExist

from django.db.models import Q
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db import transaction
import traceback

from rest_framework.pagination import PageNumberPagination

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
            "field_failures": drf_errors # Shows exactly which field failed (e.g. {"est_monthly_sales": ["..."]})
        }

        # 4. Attach Row Coordinates if this happened in an array
        if row_index is not None:
            response_data["error"]["failed_at_row"] = row_index + 1 # +1 makes it Row 1 instead of Row 0
        if sub_row_index is not None:
            response_data["error"]["failed_at_sub_row"] = sub_row_index + 1

        return Response(response_data, status=status.HTTP_400_BAD_REQUEST)

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        master_user = get_master_user(request)
        if not master_user:
            return self._format_error("AUTH_002", drf_errors={"user": "Not authenticated properly."})

        data = request.data
        
        try:
            # 1. Create Enterprise
            ent_data = data.get('enterprise', {})
            ent_serializer = MOUEnterpriseSerializer(data=ent_data)
            if not ent_serializer.is_valid():
                # Note: You can parse ent_serializer.errors here to pick a more specific ErrorDB code
                # like ENT_002 if 'entrepreneur_contact' is in errors. For simplicity, we use the base code.
                error_code = "ENT_003" if "lokos_shg" in ent_serializer.errors else "ENT_001"
                return self._format_error(error_code, ent_serializer.errors)
            enterprise = ent_serializer.save(created_by=master_user)

            # 2. Create MOUs & Nested Docs
            for i, mou_data in enumerate(data.get('mous', [])):
                mou_data['enterprise'] = enterprise.id
                mou_serializer = MOUSerializer(data=mou_data)
                if not mou_serializer.is_valid():
                    code = "MOU_002" if "mou_date" in mou_serializer.errors else "MOU_001"
                    return self._format_error(code, mou_serializer.errors, row_index=i)
                mou = mou_serializer.save(created_by=master_user)

                # Process MOU Docs
                for j, doc_data in enumerate(mou_data.get('mou_docs', [])):
                    doc_data['mou_id'] = mou.id
                    doc_serializer = MOUDocsSerializer(data=doc_data)
                    if not doc_serializer.is_valid():
                        code = "DOC_002" if "doc_file" in doc_serializer.errors else "DOC_001"
                        return self._format_error(code, doc_serializer.errors, row_index=i, sub_row_index=j)
                    doc_serializer.save(created_by=master_user)

            # 3. Create Buyer Organizations
            for i, org_data in enumerate(data.get('buyer_orgs', [])):
                org_data['enterprise'] = enterprise.id
                org_serializer = MOUOrgSerializer(data=org_data)
                if not org_serializer.is_valid():
                    code = "ORG_002" if "org_contact" in org_serializer.errors else "ORG_001"
                    return self._format_error(code, org_serializer.errors, row_index=i)
                org_serializer.save(created_by=master_user)

            # 4. Create Traders
            for i, trader_data in enumerate(data.get('traders', [])):
                trader_data['enterprise'] = enterprise.id
                trader_serializer = MOUTradersSerializer(data=trader_data)
                if not trader_serializer.is_valid():
                    code = "TRD_002" if "trader_contact" in trader_serializer.errors else "TRD_001"
                    return self._format_error(code, trader_serializer.errors, row_index=i)
                trader_serializer.save(created_by=master_user)

            # 5. Create Products & Nested Categories
            for i, prod_data in enumerate(data.get('products', [])):
                prod_data['enterprise'] = enterprise.id
                prod_serializer = MOUProductsSerializer(data=prod_data)
                if not prod_serializer.is_valid():
                    return self._format_error("PRD_001", prod_serializer.errors, row_index=i)
                product = prod_serializer.save(created_by=master_user)

                # Process Categories
                for j, cat_data in enumerate(prod_data.get('prod_categories', [])):
                    cat_data['MOUProdID'] = product.id
                    cat_serializer = MOUProdCategoriesSerializer(data=cat_data)
                    if not cat_serializer.is_valid():
                        code = "CAT_002" if "parent_category" in cat_serializer.errors else "CAT_001"
                        return self._format_error(code, cat_serializer.errors, row_index=i, sub_row_index=j)
                    cat_serializer.save(created_by=master_user)

            # 6. Create Sales
            for i, sales_data in enumerate(data.get('sales', [])):
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