# epSakhi/api/analytics_views.py
from django.db.models import Q, Count, OuterRef, Subquery, IntegerField
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.generics import ListAPIView
from rest_framework.pagination import PageNumberPagination
from django.db.models.functions import Coalesce

from epSakhi.models import (
    BeneficiaryRecorded,
    ExistingEnterprise,
    NewEnterprise,
    CRPEP,
)

from core.models import (
    MasterDistrict,
    MasterBlock,
    MasterPanchayat,
)

from .serializers import CRPEPAnalyticsSerializer

# -----------------------------
# Pagination (10 per page)
# -----------------------------
class TenPerPagePagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 100

class BeneficiaryEnterpriseAnalyticsView(APIView):
    """
    READ ONLY Analytics API

    Returns count of:
    - Existing Enterprise
    - New Enterprise
    - Not Interested (enterprise_id = 'NO')

    Filters:
    gender, marital_status, category, pld_status,
    enterprise_type, special_category,
    district_id, block_id, panchayat_id, village_id

    Search:
    enterprise_id
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = BeneficiaryRecorded.objects.filter(is_active=True)

        # -------------------------
        # Filters
        # -------------------------
        filter_fields = [
            "gender",
            "marital_status",
            "category",
            "pld_status",
            "enterprise_type",
            "special_category",
            "district_id",
            "block_id",
            "panchayat_id",
            "village_id",
        ]

        for field in filter_fields:
            value = request.query_params.get(field)
            if value:
                qs = qs.filter(**{field: value})

        # -------------------------
        # Search by enterprise_id
        # -------------------------
        search = request.query_params.get("enterprise_id")
        if search:
            qs = qs.filter(enterprise_id__icontains=search)

        # -------------------------
        # Classification
        # -------------------------

        # Get valid TH_urids
        existing_th_urids = ExistingEnterprise.objects.filter(
            is_active=True
        ).values_list("TH_urid", flat=True)

        new_th_urids = NewEnterprise.objects.filter(
            is_active=True
        ).values_list("TH_urid", flat=True)

        existing_count = qs.filter(
            enterprise_id__in=existing_th_urids
        ).count()

        new_count = qs.filter(
            enterprise_id__in=new_th_urids
        ).count()

        not_interested_count = qs.filter(
            Q(enterprise_id="NO") | Q(enterprise_id__isnull=True)
        ).count()

        total = qs.count()

        # -------------------------
        # Default Ordering
        # -------------------------
        ordering = request.query_params.get("ordering", "-created_at")
        qs = qs.order_by(ordering)

        return Response(
            {
                "total_beneficiaries": total,
                "existing_enterprise": existing_count,
                "new_enterprise": new_count,
                "not_interested": not_interested_count,
            }
        )
        
# -----------------------------
# CRPEP Analytics View
# -----------------------------
class CRPBeneficiaryAnalyticsView(ListAPIView):
    """
    READ ONLY Analytics API

    Returns CRP list with:
    - total beneficiaries created by that CRP

    Filters:
    id, master_user, nodal_clf, lokos_shg_code,
    lokos_member_code, category, subcategory,
    district_id, block_id, panchayat_id

    Search:
    name, mobile_number

    Default:
    - All CRPs
    - Paginated (10 per page)
    """

    permission_classes = [IsAuthenticated]
    pagination_class = TenPerPagePagination
    serializer_class = CRPEPAnalyticsSerializer

    def get_queryset(self):
        qs = CRPEP.objects.filter(is_active=True)

        params = self.request.query_params

        # -------------------------
        # Filters
        # -------------------------
        filter_fields = [
            "id",
            "master_user",
            "nodal_clf",
            "lokos_shg_code",
            "lokos_member_code",
            "category",
            "subcategory",
            "district_id",
            "block_id",
            "panchayat_id",
        ]

        for field in filter_fields:
            value = params.get(field)
            if value:
                qs = qs.filter(**{field: value})

        # -------------------------
        # Search
        # -------------------------
        search = params.get("search")
        if search:
            qs = qs.filter(
                Q(name__icontains=search) |
                Q(mobile_number__icontains=search)
            )

        # -------------------------
        # Annotate Beneficiary Count
        # -------------------------
        beneficiary_count_subquery = (
            BeneficiaryRecorded.objects.filter(
                created_by=OuterRef("master_user"),
                is_active=True
            )
            .values("created_by")
            .annotate(c=Count("id"))
            .values("c")[:1]
        )

        # -------------------------
        # District Name Subquery
        # -------------------------
        district_name_subquery = MasterDistrict.objects.filter(
            district_id=OuterRef("district_id")
        ).values("district_name_en")[:1]

        # -------------------------
        # Block Name Subquery
        # -------------------------
        block_name_subquery = MasterBlock.objects.filter(
            block_id=OuterRef("block_id")
        ).values("block_name_en")[:1]

        # -------------------------
        # Panchayat Name Subquery
        # -------------------------
        panchayat_name_subquery = MasterPanchayat.objects.filter(
            panchayat_id=OuterRef("panchayat_id")
        ).values("panchayat_name_en")[:1]

        # -------------------------
        # Final Annotations
        # -------------------------
        qs = qs.annotate(
            total_beneficiaries=Coalesce(
                Subquery(beneficiary_count_subquery, output_field=IntegerField()),
                0
            ),
            district_name=Subquery(district_name_subquery),
            block_name=Subquery(block_name_subquery),
            panchayat_name=Subquery(panchayat_name_subquery),
        )

        # -------------------------
        # Default Ordering
        # -------------------------
        ordering = params.get("ordering", "-created_at")
        qs = qs.order_by(ordering)

        return qs