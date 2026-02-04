# core/api/lookups.py
"""
Enhanced lookups with:
- multi-filter support
- search (comma-separated tokens)
- group_by (single or comma-separated)
- ordering (supports 'age' computed from dob)
- pagination: page, page_size (PageNumberPagination)
- DB optimizations: select_related, prefetch_related, only
- caching decorator preserved

IMPORTANT FIXES:
- When using select_related('fk') we always include the corresponding fk_id
  column in .only(...) to avoid Django FieldError about "deferred and traversed".
- Detail endpoints now serialize the main model object with a ModelSerializer
  and then attach related lists (addresses/banks/phones) as plain lists.
"""

from rest_framework import permissions, generics, pagination, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django.db.models import Q, Count
from django.db.models.functions import ExtractYear, Now
from django.conf import settings
from django.shortcuts import get_object_or_404

from core.models import *
from core.api.serializers import * 

CACHE_TTL = getattr(settings, 'CACHE_TTL', 300)


class FlexiblePagination(pagination.PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100


# --------------------------
# Helper utilities
# --------------------------
def parse_csv_param(val):
    if not val:
        return []
    return [p.strip() for p in val.split(',') if p.strip()]


def apply_filters(qs, request, allowed_filters):
    # allowed_filters: { 'query_param_name' : 'model_field_name' }
    for qp, model_field in (allowed_filters or {}).items():
        v = request.GET.get(qp)
        if v is None:
            continue
        # allow comma-separated multi values -> IN filter
        vals = parse_csv_param(v)
        if len(vals) == 1:
            qs = qs.filter(**{model_field: vals[0]})
        elif len(vals) > 1:
            qs = qs.filter(**{f"{model_field}__in": vals})
    return qs


def apply_search(qs, request, search_fields):
    search_q = request.GET.get('search')
    if not search_q or not search_fields:
        return qs
    tokens = parse_csv_param(search_q)
    # AND across tokens; OR across fields for each token
    for token in tokens:
        token_q = Q()
        for f in search_fields:
            token_q |= Q(**{f"{f}__icontains": token})
        qs = qs.filter(token_q)
    return qs


def apply_ordering(qs, request, allowed_ordering):
    order_param = request.GET.get('ordering')
    if not order_param:
        return qs
    orderings = parse_csv_param(order_param)
    cleaned = []
    for o in orderings:
        desc = o.startswith('-')
        field = o[1:] if desc else o
        # special computed fields
        if field == 'age':
            # compute age = YEAR(NOW()) - YEAR(dob) (approx)
            qs = qs.annotate(age=ExtractYear(Now()) - ExtractYear('dob'))
            cleaned.append(f"-age" if desc else "age")
            continue
        if field not in allowed_ordering:
            continue
        cleaned.append(o)
    if cleaned:
        qs = qs.order_by(*cleaned)
    return qs


def apply_group_by(qs, request, allowed_group_by, id_field='id'):
    group_by = request.GET.get('group_by')
    if not group_by:
        return None
    groups = parse_csv_param(group_by)
    # allow grouping by one or multiple allowed fields
    chosen = [g for g in groups if g in allowed_group_by]
    if not chosen:
        return None
    # produce aggregated dict { group_key: count, ... }
    agg = qs.values(*chosen).annotate(count=Count(id_field)).order_by(*chosen)
    return list(agg)

# ----------------------------
# Mandals (list)
# ----------------------------
@method_decorator(cache_page(CACHE_TTL), name='get')
class MasterMandalView(generics.ListAPIView):
    permission_classes = (permissions.AllowAny,)
    serializer_class = MasterMandalSerializer
    pagination_class = FlexiblePagination

    SEARCH_FIELDS = ['name', 'th_urid']
    ALLOWED_FILTERS = {'created_by': 'created_by'}
    ALLOWED_ORDERING = {'id', 'name', 'created_at'}
    ALLOWED_GROUP_BY = {'created_by'}

    def get_queryset(self):
        qs = MasterMandal.objects.all().select_related('created_by').order_by('name').only('id', 'name', 'th_urid', 'created_at', 'updated_at', 'created_by_id', 'updated_by_id')
        qs = apply_filters(qs, self.request, self.ALLOWED_FILTERS)
        qs = apply_search(qs, self.request, self.SEARCH_FIELDS)
        qs = apply_ordering(qs, self.request, self.ALLOWED_ORDERING)
        return qs

# ----------------------------
# District Categories (list)
# ----------------------------
@method_decorator(cache_page(CACHE_TTL), name='get')
class DistrictCategoryView(generics.ListAPIView):
    permission_classes = (permissions.AllowAny,)
    serializer_class = MasterDistrictCategorySerializer
    pagination_class = FlexiblePagination

    SEARCH_FIELDS = ['name']
    ALLOWED_FILTERS = {'id': 'id'}
    ALLOWED_ORDERING = {'id', 'name', 'created_at'}
    ALLOWED_GROUP_BY = {'updated_at'}

    def get_queryset(self):
        qs = MasterDistrictCategory.objects.all().order_by('name').only('id', 'name', 'created_at', 'updated_at')
        qs = apply_filters(qs, self.request, self.ALLOWED_FILTERS)
        qs = apply_search(qs, self.request, self.SEARCH_FIELDS)
        qs = apply_ordering(qs, self.request, self.ALLOWED_ORDERING)
        return qs

# ----------------------------
# District Category Mapping (list)
# ----------------------------
@method_decorator(cache_page(CACHE_TTL), name='get')
class DistrictCategoryMappingView(generics.ListAPIView):
    permission_classes = (permissions.AllowAny,)
    serializer_class = MasterDistrictCategoryMappingSerializer
    pagination_class = FlexiblePagination

    SEARCH_FIELDS = ['district__district_name_en', 'category__name']
    ALLOWED_FILTERS = {'district_id': 'district_id', 'category_id': 'category_id'}
    ALLOWED_ORDERING = {'id', 'district_id', 'category_id', 'created_at'}
    ALLOWED_GROUP_BY = {'district_id', 'category_id'}

    def get_queryset(self):
        qs = MasterDistrictCategoryMapping.objects.all() \
            .select_related('district', 'category') \
            .order_by('district_id') \
            .only('id', 'district__district_name_en', 'category__name', 'created_at', 'updated_at')

        qs = apply_filters(qs, self.request, self.ALLOWED_FILTERS)
        qs = apply_search(qs, self.request, self.SEARCH_FIELDS)
        qs = apply_ordering(qs, self.request, self.ALLOWED_ORDERING)

        return qs

# ----------------------------
# Districts (list + detail)
# ----------------------------
@method_decorator(cache_page(CACHE_TTL), name='get')
class DistrictListView(generics.ListAPIView):
    permission_classes = (permissions.AllowAny,)
    serializer_class = MasterDistrictListSerializer
    pagination_class = FlexiblePagination

    SEARCH_FIELDS = ['district_id', 'district_name_en', 'district_name_local', 'district_short_name_en']
    ALLOWED_FILTERS = {'state_id': 'state_id', 'is_active': 'is_active', 'mandal_id': 'mandal_id'}
    ALLOWED_ORDERING = {'district_id', 'district_name_en', 'created_at'}

    def get_queryset(self):
        # We include state_id and mandal_id because code may select_related those in detail views.
        qs = MasterDistrict.objects.all().order_by('district_name_en').only(
            'district_id', 'district_name_en', 'district_short_name_en', 'district_name_local',
            'district_code', 'lgd_code', 'language_id', 'created_at', 'updated_at',
            'state_id', 'mandal_id'
        )
        qs = apply_filters(qs, self.request, self.ALLOWED_FILTERS)
        qs = apply_search(qs, self.request, self.SEARCH_FIELDS)
        qs = apply_ordering(qs, self.request, self.ALLOWED_ORDERING)
        return qs


@method_decorator(cache_page(CACHE_TTL), name='get')
class DistrictDetailView(APIView):
    permission_classes = (permissions.AllowAny,)

    def get(self, request, district_id=None):
        if not district_id:
            return Response({'detail': 'district_id required'}, status=status.HTTP_400_BAD_REQUEST)

        district = get_object_or_404(
            MasterDistrict.objects.select_related('state', 'mandal'),
            district_id=district_id
        )

        # ---------------------------------------------
        #  SURGICAL ADDITION: fields= support for detail
        # ---------------------------------------------
        fields = request.GET.get("fields")
        if fields:
            allowed = parse_csv_param(fields)
            serializer = MasterDistrictDetailSerializer(district)
            data = serializer.data

            # return only selected fields
            filtered = {k: v for k, v in data.items() if k in allowed}
            return Response(filtered)

        # default behaviour (unchanged)
        serializer = MasterDistrictDetailSerializer(district)
        return Response(serializer.data)


# ----------------------------
# Blocks (list + detail)
# ----------------------------
@method_decorator(cache_page(CACHE_TTL), name='get')
class BlockListView(generics.ListAPIView):
    permission_classes = (permissions.AllowAny,)
    serializer_class = MasterBlockListSerializer
    pagination_class = FlexiblePagination

    SEARCH_FIELDS = ['block_id', 'block_name_en', 'block_name_local', 'block_code']
    ALLOWED_FILTERS = {'district_id': 'district_id', 'state_id': 'state_id', 'is_aspirational': 'is_aspirational'}
    ALLOWED_ORDERING = {'block_id', 'block_name_en', 'created_at'}
    ALLOWED_GROUP_BY = {'district_id', 'is_aspirational'}

    def get_queryset(self):
        # path param compatibility: /blocks/<district_id>/
        path_district = self.kwargs.get('district_id')
        # include state_id and district_id because select_related('state','district') may traverse them
        qs = MasterBlock.objects.all().select_related('state', 'district').order_by('block_name_en').only(
            'block_id', 'block_name_en', 'block_name_local', 'block_code', 'rural_urban_area',
            'is_aspirational', 'created_at', 'updated_at', 'state_id', 'district_id'
        )
        if path_district:
            qs = qs.filter(district_id=path_district)
        qs = apply_filters(qs, self.request, self.ALLOWED_FILTERS)
        qs = apply_search(qs, self.request, self.SEARCH_FIELDS)
        qs = apply_ordering(qs, self.request, self.ALLOWED_ORDERING)
        return qs


@method_decorator(cache_page(CACHE_TTL), name='get')
class BlockDetailView(APIView):
    permission_classes = (permissions.AllowAny,)

    def get(self, request, block_id=None):
        if not block_id:
            return Response({'detail': 'block_id required'}, status=status.HTTP_400_BAD_REQUEST)

        block = get_object_or_404(
            MasterBlock.objects.select_related('state', 'district'),
            block_id=block_id
        )

        # ---------------------------------------------
        #   SURGICAL ADDITION: fields= support
        # ---------------------------------------------
        fields = request.GET.get("fields")
        if fields:
            allowed = parse_csv_param(fields)
            serializer = MasterBlockDetailSerializer(block)
            data = serializer.data

            # return ONLY requested fields
            filtered = {k: v for k, v in data.items() if k in allowed}
            return Response(filtered)

        # default full-detail response
        serializer = MasterBlockDetailSerializer(block)
        return Response(serializer.data)


# ----------------------------
# Panchayats (list + detail)
# ----------------------------
@method_decorator(cache_page(CACHE_TTL), name='get')
class PanchayatListView(generics.ListAPIView):
    permission_classes = (permissions.AllowAny,)
    serializer_class = MasterPanchayatListSerializer
    pagination_class = FlexiblePagination

    SEARCH_FIELDS = ['panchayat_name_en', 'panchayat_name_local', 'panchayat_code']
    ALLOWED_FILTERS = {'block_id': 'block_id', 'district_id': 'district_id', 'state_id': 'state_id'}
    ALLOWED_ORDERING = {'panchayat_id', 'panchayat_name_en', 'created_at'}
    ALLOWED_GROUP_BY = {'block_id', 'district_id'}

    def get_queryset(self):
        path_block = self.kwargs.get('block_id')
        # include fk id fields for safe select_related traversal
        qs = MasterPanchayat.objects.all().select_related('state', 'district', 'block').order_by('panchayat_name_en').only(
            'panchayat_id', 'panchayat_name_en', 'panchayat_name_local', 'panchayat_code',
            'rural_urban_area', 'created_at', 'updated_at', 'state_id', 'district_id', 'block_id'
        )
        if path_block:
            qs = qs.filter(block_id=path_block)
        qs = apply_filters(qs, self.request, self.ALLOWED_FILTERS)
        qs = apply_search(qs, self.request, self.SEARCH_FIELDS)
        qs = apply_ordering(qs, self.request, self.ALLOWED_ORDERING)
        return qs


@method_decorator(cache_page(CACHE_TTL), name='get')
class PanchayatDetailView(APIView):
    permission_classes = (permissions.AllowAny,)

    def get(self, request, panchayat_id=None):
        if not panchayat_id:
            return Response({'detail': 'panchayat_id required'}, status=status.HTTP_400_BAD_REQUEST)

        p = get_object_or_404(
            MasterPanchayat.objects.select_related('state', 'district', 'block'),
            panchayat_id=panchayat_id
        )

        # ---------------------------------------------
        #   SURGICAL ADDITION: fields= support
        # ---------------------------------------------
        fields = request.GET.get("fields")
        if fields:
            allowed = parse_csv_param(fields)
            serializer = MasterPanchayatDetailSerializer(p)
            data = serializer.data

            # return only allowed keys
            filtered = {k: v for k, v in data.items() if k in allowed}
            return Response(filtered)

        # default (full) response
        serializer = MasterPanchayatDetailSerializer(p)
        return Response(serializer.data)


# ----------------------------
# Villages (list + detail)
# ----------------------------
@method_decorator(cache_page(CACHE_TTL), name='get')
class VillageListView(generics.ListAPIView):
    permission_classes = (permissions.AllowAny,)
    serializer_class = MasterVillageListSerializer
    pagination_class = FlexiblePagination

    SEARCH_FIELDS = ['village_name_english', 'village_name_local', 'village_code']
    ALLOWED_FILTERS = {'panchayat_id': 'panchayat_id', 'block_id': 'block_id', 'district_id': 'district_id', 'state_id': 'state_id', 'is_active': 'is_active'}
    ALLOWED_ORDERING = {'village_id', 'village_name_english', 'created_at'}
    ALLOWED_GROUP_BY = {'panchayat_id', 'block_id', 'district_id', 'is_active'}

    def get_queryset(self):
        path_panchayat = self.kwargs.get('panchayat_id')
        # include all fk id fields used by select_related
        qs = MasterVillage.objects.all().select_related('state', 'district', 'block', 'panchayat').order_by('village_name_english').only(
            'village_id', 'village_name_english', 'village_name_local', 'village_code', 'is_active',
            'created_at', 'updated_at', 'state_id', 'district_id', 'block_id', 'panchayat_id'
        )
        if path_panchayat:
            qs = qs.filter(panchayat_id=path_panchayat)
        qs = apply_filters(qs, self.request, self.ALLOWED_FILTERS)
        qs = apply_search(qs, self.request, self.SEARCH_FIELDS)
        qs = apply_ordering(qs, self.request, self.ALLOWED_ORDERING)
        return qs


@method_decorator(cache_page(CACHE_TTL), name='get')
class VillageDetailView(APIView):
    permission_classes = (permissions.AllowAny,)

    def get(self, request, village_id=None):
        if not village_id:
            return Response({'detail': 'village_id required'}, status=status.HTTP_400_BAD_REQUEST)

        v = get_object_or_404(
            MasterVillage.objects.select_related('state', 'district', 'block', 'panchayat'),
            village_id=village_id
        )

        # ---------------------------------------------
        #   SURGICAL ADDITION: fields= support
        # ---------------------------------------------
        fields = request.GET.get("fields")
        if fields:
            allowed = parse_csv_param(fields)
            serializer = MasterVillageDetailSerializer(v)
            data = serializer.data

            # return only requested fields
            filtered = {k: v for k, v in data.items() if k in allowed}
            return Response(filtered)

        # default full serializer response
        serializer = MasterVillageDetailSerializer(v)
        return Response(serializer.data)


# ----------------------------
# SHG canonical list & detail
# ----------------------------
@method_decorator(cache_page(CACHE_TTL), name='get')
class ShgListByBlockView(generics.ListAPIView):
    """
    Canonical SHG list endpoint: supports block_id,district_id,panchayat_id,village_id,state_id filters,
    search, group_by (village_id,panchayat_id etc), ordering, and fields= (sparse projection).
    Backwards-compatible path-based endpoints are supported.
    """
    permission_classes = (permissions.AllowAny,)
    serializer_class = MasterShgListSerializer
    pagination_class = FlexiblePagination

    SEARCH_FIELDS = ['name', 'shg_code', 'nic_code']
    ALLOWED_FILTERS = {
        'block_id': 'block_id',
        'district_id': 'district_id',
        'village_id': 'village_id',
        'panchayat_id': 'panchayat_id',
        'state_id': 'state_id',
        'is_active': 'is_active',
        'pfms_verified': 'pfms_verified',
        'is_complete': 'is_complete'
    }
    ALLOWED_ORDERING = {'id', 'name', 'formation_date', 'is_active'}
    ALLOWED_GROUP_BY = {'block_id', 'district_id', 'village_id', 'panchayat_id', 'is_active'}

    def get_queryset(self):
        # IMPORTANT: include state_id and all fk_id fields because we use select_related on them
        qs = MasterShgList.objects.all().select_related('state', 'district', 'block', 'panchayat', 'village').order_by('name').only(
            'id', 'shg_code', 'name', 'formation_date', 'is_active',
            'block_id', 'district_id', 'panchayat_id', 'village_id', 'state_id'
        )
        path_block = self.kwargs.get('block_id')
        if path_block:
            qs = qs.filter(block_id=path_block)
        qs = apply_filters(qs, self.request, self.ALLOWED_FILTERS)
        qs = apply_search(qs, self.request, self.SEARCH_FIELDS)
        qs = apply_ordering(qs, self.request, self.ALLOWED_ORDERING)
        return qs

    def list(self, request, *args, **kwargs):
        qs = self.get_queryset()
        grouped = apply_group_by(qs, request, self.ALLOWED_GROUP_BY, id_field='id')
        if grouped:
            return Response(grouped)

        fields = request.GET.get('fields')
        if fields:
            qs = qs.values(*parse_csv_param(fields))
            page = self.paginate_queryset(qs)
            return self.get_paginated_response(list(page) if page is not None else list(qs))
        return super().list(request, *args, **kwargs)


@method_decorator(cache_page(CACHE_TTL), name='get')
class ShgDetailView(APIView):
    permission_classes = (permissions.AllowAny,)

    def get(self, request, shg_code=None):
        if not shg_code:
            return Response({'detail': 'shg_code required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            shg = MasterShgList.objects.select_related('state', 'district', 'block', 'panchayat', 'village').get(shg_code=shg_code)
        except MasterShgList.DoesNotExist:
            return Response({'detail': 'SHG not found'}, status=status.HTTP_404_NOT_FOUND)

        # serialize main shg model fully (nested state/district/block/panchayat/village come from serializer)
        shg_data = MasterShgDetailSerializer(shg).data

        # attach related lists (simple dicts)
        addresses = MasterShgAddresses.objects.filter(shg_code=shg_code).only(
            'address_line1', 'address_line2', 'city_town', 'pincode', 'state_name', 'block_id', 'district_id', 'village', 'panchayat'
        )
        shg_data['addresses'] = [
            {
                'address_line1': a.address_line1,
                'address_line2': a.address_line2,
                'city_town': a.city_town,
                'pincode': a.pincode,
                'state_name': a.state_name,
                'block_id': getattr(a, 'block_id', None),
                'district_id': getattr(a, 'district_id', None),
                'panchayat': getattr(a, 'panchayat', None),
                'village': getattr(a, 'village', None)
            } for a in addresses
        ]

        banks = MasterShgBanks.objects.filter(shg_code=shg_code).only('account_no', 'bank_name', 'ifsc_code', 'is_default')
        shg_data['banks'] = [
            {'account_no': b.account_no, 'bank_name': b.bank_name, 'ifsc_code': b.ifsc_code, 'is_default': b.is_default} for b in banks
        ]

        phones = MasterShgPhone.objects.filter(shg_code=shg_code).only('phone_no', 'is_default')
        shg_data['phones'] = [{'phone_no': p.phone_no, 'is_default': p.is_default} for p in phones]

        return Response(shg_data)


# ----------------------------
# Beneficiaries - canonical list & detail
# ----------------------------
@method_decorator(cache_page(CACHE_TTL), name='get')
class BeneficiaryListByShgView(generics.ListAPIView):
    """
    Unified beneficiaries endpoint:
     - Query params: member_code, shg_code, block_id, district_id, village_id, panchayat_id,
       marital_status, religion, social_category, search, ordering (including age), group_by, page,page_size,fields
     - If 'member_code' present -> return full detail (beneficiary-detail compatible).
    """
    permission_classes = (permissions.AllowAny,)
    serializer_class = MasterBeneficiaryListSerializer
    pagination_class = FlexiblePagination

    SEARCH_FIELDS = ['member_name', 'member_code', 'nic_member_code', 'father_husband']
    ALLOWED_FILTERS = {
        'shg_code': 'shg_code',
        'block_id': 'block_id',
        'district_id': 'district_id',
        'panchayat_id': 'panchayat_id',
        'village_id': 'village_id',
        'state_id': 'state_id',
        'marital_status': 'marital_status',
        'religion': 'religion',
        'social_category': 'social_category',
        'is_active': 'is_active'
    }
    ALLOWED_ORDERING = {'member_code', 'member_name', 'dob', 'joining_date'}
    ALLOWED_GROUP_BY = {'shg_code', 'block_id', 'district_id', 'village_id', 'panchayat_id', 'marital_status', 'religion', 'social_category'}

    def get_queryset(self):
        # include fk id fields used by select_related('state','district',...)
        qs = MasterBeneficiary.objects.all().select_related('state', 'district', 'block', 'panchayat', 'village').order_by('member_name').only(
            'member_code', 'member_name', 'dob', 'gender', 'joining_date', 'shg_code',
            'state_id', 'district_id', 'block_id', 'panchayat_id', 'village_id',
            'marital_status', 'religion', 'social_category'
        )
        # path param compatibility: shg_code path
        path_shg = self.kwargs.get('shg_code')
        if path_shg:
            qs = qs.filter(shg_code=path_shg)
        qs = apply_filters(qs, self.request, self.ALLOWED_FILTERS)
        qs = apply_search(qs, self.request, self.SEARCH_FIELDS)
        qs = apply_ordering(qs, self.request, self.ALLOWED_ORDERING)
        return qs

    def list(self, request, *args, **kwargs):
        # if member_code query param present, return detailed combined view for single beneficiary
        member_code = request.GET.get('member_code') or self.kwargs.get('member_code')
        if member_code:
            return BeneficiaryDetailView().get(request, member_code=member_code)
        qs = self.get_queryset()
        grouped = apply_group_by(qs, request, self.ALLOWED_GROUP_BY, id_field='member_code')
        if grouped:
            return Response(grouped)

        fields = request.GET.get('fields')
        if fields:
            qs = qs.values(*parse_csv_param(fields))
            page = self.paginate_queryset(qs)
            return self.get_paginated_response(list(page) if page is not None else list(qs))
        return super().list(request, *args, **kwargs)


@method_decorator(cache_page(CACHE_TTL), name='get')
class BeneficiaryDetailView(APIView):
    permission_classes = (permissions.AllowAny,)

    def get(self, request, member_code=None):
        if not member_code:
            return Response({'detail': 'member_code required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            mb = MasterBeneficiary.objects.select_related('state', 'district', 'block', 'panchayat', 'village').get(member_code=member_code)
        except MasterBeneficiary.DoesNotExist:
            return Response({'detail': 'Beneficiary not found'}, status=status.HTTP_404_NOT_FOUND)

        data = MasterBeneficiaryDetailSerializer(mb).data

        addresses = MasterBeneficiaryAddress.objects.filter(member_code=member_code).only(
            'address_line1', 'address_line2', 'address_type', 'city_town', 'postal_code', 'state_id', 'district_id', 'block_id', 'panchayat_id', 'village'
        )
        data['addresses'] = [
            {
                'address_line1': a.address_line1,
                'address_line2': a.address_line2,
                'address_type': a.address_type,
                'city_town': a.city_town,
                'postal_code': a.postal_code
            } for a in addresses
        ]

        banks = MasterBeneficiaryBank.objects.filter(member_code=member_code).only('account_no', 'ifsc_code', 'bank_name', 'is_default')
        data['banks'] = [{'account_no': b.account_no, 'ifsc_code': b.ifsc_code, 'bank_name': b.bank_name, 'is_default': b.is_default} for b in banks]

        designations = MasterBeneficiaryDesignation.objects.filter(member_code=member_code).only('designation', 'is_signatory', 'member_name')
        data['designations'] = [{'designation': d.designation, 'is_signatory': d.is_signatory, 'member_name': d.member_name} for d in designations]

        phones = MasterBeneficiaryPhone.objects.filter(member_code=member_code).only('phone_no', 'is_default')
        data['phones'] = [{'phone_no': p.phone_no, 'is_default': p.is_default} for p in phones]

        return Response(data)


# ----------------------------
# CLF list + detail + sublists
# ----------------------------
@method_decorator(cache_page(CACHE_TTL), name='get')
class ClfListView(generics.ListAPIView):
    permission_classes = (permissions.AllowAny,)
    serializer_class = MasterClfListSerializer
    pagination_class = FlexiblePagination

    SEARCH_FIELDS = ['name', 'clf_code', 'nic_code']
    ALLOWED_FILTERS = {
        'state_id': 'state_id',
        'district_id': 'district_id',
        'block_id': 'block_id',
        'pfms_verified': 'pfms_verified',
        'is_complete': 'is_complete'
    }
    ALLOWED_ORDERING = {'id', 'name', 'formation_date', 'created_date'}
    ALLOWED_GROUP_BY = {'district_id', 'block_id', 'pfms_verified', 'is_complete'}

    def get_queryset(self):
        # include id fields used by select_related
        qs = MasterClfList.objects.all().select_related('state', 'district', 'block').order_by('name').only(
            'id', 'clf_code', 'name', 'nic_code', 'formation_date', 'is_complete', 'pfms_verified', 'state_id', 'district_id', 'block_id'
        )
        qs = apply_filters(qs, self.request, self.ALLOWED_FILTERS)
        qs = apply_search(qs, self.request, self.SEARCH_FIELDS)
        qs = apply_ordering(qs, self.request, self.ALLOWED_ORDERING)
        return qs


@method_decorator(cache_page(CACHE_TTL), name='get')
class ClfDetailView(APIView):
    permission_classes = (permissions.AllowAny,)

    def get(self, request, clf_code=None):
        if not clf_code:
            return Response({'detail': 'clf_code required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            clf = MasterClfList.objects.select_related('state', 'district', 'block').get(clf_code=clf_code)
        except MasterClfList.DoesNotExist:
            return Response({'detail': 'CLF not found'}, status=status.HTTP_404_NOT_FOUND)

        clf_data = MasterClfListSerializer(clf).data

        addresses = MasterClfAddresses.objects.filter(clf_code=clf_code)
        clf_data['addresses'] = [
            {
                'address_line1': a.address_line1,
                'address_line2': a.address_line2,
                'city_town': a.city_town,
                'landmark': a.landmark,
                'postal_code': a.postal_code,
                'state_id': getattr(a, 'state_id', None),
                'district_id': getattr(a, 'district_id', None),
                'block_id': getattr(a, 'block_id', None)
            } for a in addresses
        ]

        banks = MasterClfBanks.objects.filter(clf_code=clf_code)
        clf_data['banks'] = [{'account_no': b.account_no, 'bank_name': b.bank_name, 'ifsc_code': b.ifsc_code, 'is_default': b.is_default} for b in banks]

        phones = MasterClfPhones.objects.filter(clf_code=clf_code)
        clf_data['phones'] = [{'phone_no': p.phone_no, 'is_default': p.is_default} for p in phones]

        vo_details = MasterClfVoDetails.objects.filter(clf_code=clf_code)
        clf_data['vo_details'] = [{'vo_code': v.vo_code, 'vo_name': v.vo_name, 'vo_formation_date': v.vo_formation_date} for v in vo_details]

        return Response(clf_data)


@method_decorator(cache_page(CACHE_TTL), name='get')
class MembersUnderClfView(generics.ListAPIView):
    permission_classes = (permissions.AllowAny,)
    serializer_class = MasterMembersUnderClfListSerializer
    pagination_class = FlexiblePagination

    SEARCH_FIELDS = ['member_name', 'member_code']
    ALLOWED_FILTERS = {'clf_code': 'clf_code', 'is_signatory': 'is_signatory'}
    ALLOWED_ORDERING = {'id', 'member_name'}
    ALLOWED_GROUP_BY = {'designation', 'is_signatory'}

    def get_queryset(self):
        clf_code = self.kwargs.get('clf_code') or self.request.GET.get('clf_code')
        qs = MasterMembersUnderClf.objects.all().only('id', 'clf_code_id', 'member_code', 'member_name', 'designation', 'is_signatory')
        if clf_code:
            # allow either passing code string or internal id
            qs = qs.filter(clf_code__clf_code=clf_code) if isinstance(clf_code, str) else qs.filter(clf_code=clf_code)
        qs = apply_filters(qs, self.request, self.ALLOWED_FILTERS)
        qs = apply_search(qs, self.request, self.SEARCH_FIELDS)
        qs = apply_ordering(qs, self.request, self.ALLOWED_ORDERING)
        return qs


@method_decorator(cache_page(CACHE_TTL), name='get')
class PanchayatsUnderClfView(generics.ListAPIView):
    permission_classes = (permissions.AllowAny,)
    serializer_class = MasterPanchayatsUnderClfListSerializer
    pagination_class = FlexiblePagination

    SEARCH_FIELDS = ['panchayat_name']
    ALLOWED_FILTERS = {'clf_code': 'clf_code'}
    ALLOWED_ORDERING = {'id', 'panchayat_name'}
    ALLOWED_GROUP_BY = {'panchayat_code'}

    def get_queryset(self):
        clf_code = self.kwargs.get('clf_code') or self.request.GET.get('clf_code')
        qs = MasterPanchayatsUnderClf.objects.all().only('id', 'clf_code_id', 'panchayat', 'panchayat_code', 'panchayat_name', 'lgd_gp')
        if clf_code:
            qs = qs.filter(clf_code__clf_code=clf_code) if isinstance(clf_code, str) else qs.filter(clf_code=clf_code)
        qs = apply_filters(qs, self.request, self.ALLOWED_FILTERS)
        qs = apply_search(qs, self.request, self.SEARCH_FIELDS)
        qs = apply_ordering(qs, self.request, self.ALLOWED_ORDERING)
        return qs


@method_decorator(cache_page(CACHE_TTL), name='get')
class VillagesUnderClfView(generics.ListAPIView):
    permission_classes = (permissions.AllowAny,)
    serializer_class = MasterVillagesUnderClfListSerializer
    pagination_class = FlexiblePagination

    SEARCH_FIELDS = ['village_name']
    ALLOWED_FILTERS = {'clf_code': 'clf_code'}
    ALLOWED_ORDERING = {'id', 'village_name'}
    ALLOWED_GROUP_BY = {'village_code'}

    def get_queryset(self):
        clf_code = self.kwargs.get('clf_code') or self.request.GET.get('clf_code')
        qs = MasterVillagesUnderClf.objects.all().only('id', 'clf_code_id', 'panchayat', 'village', 'village_code', 'village_name', 'lgd_village')
        if clf_code:
            qs = qs.filter(clf_code__clf_code=clf_code) if isinstance(clf_code, str) else qs.filter(clf_code=clf_code)
        qs = apply_filters(qs, self.request, self.ALLOWED_FILTERS)
        qs = apply_search(qs, self.request, self.SEARCH_FIELDS)
        qs = apply_ordering(qs, self.request, self.ALLOWED_ORDERING)
        return qs


# ----------------------------
# Roles / Users / State / Mandal
# ----------------------------
@method_decorator(cache_page(CACHE_TTL), name='get')
class MasterRolesView(generics.ListAPIView):
    permission_classes = (permissions.AllowAny,)
    serializer_class = MasterRolesSerializer
    pagination_class = FlexiblePagination

    SEARCH_FIELDS = ['name']
    ALLOWED_FILTERS = {'role_type': 'role_type'}
    ALLOWED_ORDERING = {'id', 'name', 'created_at'}
    ALLOWED_GROUP_BY = {'role_type'}

    def get_queryset(self):
        qs = MasterRoles.objects.all().order_by('name').only('id', 'name', 'role_type', 'created_at', 'updated_at')
        qs = apply_filters(qs, self.request, self.ALLOWED_FILTERS)
        qs = apply_search(qs, self.request, self.SEARCH_FIELDS)
        qs = apply_ordering(qs, self.request, self.ALLOWED_ORDERING)
        return qs

# Master User List View
@method_decorator(cache_page(CACHE_TTL), name='get')
class MasterUserListView(generics.ListAPIView):
    permission_classes = (permissions.AllowAny,)
    serializer_class = MasterUserSerializer
    pagination_class = FlexiblePagination

    SEARCH_FIELDS = ['username', 'recovery_email', 'recovery_mobile', 'id']
    ALLOWED_FILTERS = {'role_id': 'role_id', 'is_active': 'is_active'}
    ALLOWED_ORDERING = {'id', 'username', 'created_at'}
    ALLOWED_GROUP_BY = {'role_id', 'is_active'}

    def get_queryset(self):
        qs = MasterUser.objects.all().select_related('role').order_by('username').only(
            'id', 'username', 'recovery_email', 'recovery_mobile',
            'role_id', 'is_active', 'created_at', 'updated_at'
        )
        qs = apply_filters(qs, self.request, self.ALLOWED_FILTERS)
        qs = apply_search(qs, self.request, self.SEARCH_FIELDS)
        qs = apply_ordering(qs, self.request, self.ALLOWED_ORDERING)
        return qs

    # -------------------------------
    #  SURGICAL FIELD EXTRACTION ADDITION
    # -------------------------------
    def list(self, request, *args, **kwargs):
        qs = self.get_queryset()

        # group_by support
        grouped = apply_group_by(qs, request, self.ALLOWED_GROUP_BY, id_field='id')
        if grouped:
            return Response(grouped)

        # fields= support (like Beneficiary API)
        fields = request.GET.get('fields')
        if fields:
            qs = qs.values(*parse_csv_param(fields))
            page = self.paginate_queryset(qs)
            return self.get_paginated_response(
                list(page) if page is not None else list(qs)
            )

        return super().list(request, *args, **kwargs)

# CRUD for Master User 
class MasterUserCreateView(generics.CreateAPIView):
    permission_classes = (permissions.AllowAny,)
    serializer_class = MasterUserSerializer
    queryset = MasterUser.objects.all()    
    
class MasterUserDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = (permissions.AllowAny,)
    serializer_class = MasterUserSerializer
    queryset = MasterUser.objects.select_related('role')

    lookup_url_kwarg = 'user_id'

    def delete(self, request, *args, **kwargs):
        instance = self.get_object()

        instance.deleted_at = timezone.now()
        if request.user and hasattr(request.user, 'id'):
            instance.deleted_by_id = request.user.id

        instance.save(update_fields=['deleted_at', 'deleted_by'])

        return Response(
            {"detail": "User deleted successfully"},
            status=status.HTTP_204_NO_CONTENT
        )   
    
@method_decorator(cache_page(CACHE_TTL), name='get')
class MasterStateView(generics.ListAPIView):
    permission_classes = (permissions.AllowAny,)
    serializer_class = MasterStateSerializer
    pagination_class = FlexiblePagination

    SEARCH_FIELDS = ['state_name_en', 'state_name_local', 'state_short_name_en']
    ALLOWED_FILTERS = {'category': 'category', 'is_active': 'is_active'}
    ALLOWED_ORDERING = {'state_id', 'state_name_en', 'created_at'}
    ALLOWED_GROUP_BY = {'category', 'is_active'}

    def get_queryset(self):
        qs = MasterState.objects.all().order_by('state_name_en').only('state_id', 'state_name_en', 'state_short_name_en', 'category', 'is_active', 'created_at', 'updated_at')
        qs = apply_filters(qs, self.request, self.ALLOWED_FILTERS)
        qs = apply_search(qs, self.request, self.SEARCH_FIELDS)
        qs = apply_ordering(qs, self.request, self.ALLOWED_ORDERING)
        return qs

# ----------------------------
# User GeoScope view
# ----------------------------
@method_decorator(cache_page(CACHE_TTL), name='get')
class UserGeoScopeView(APIView):
    permission_classes = (permissions.AllowAny,)

    def get(self, request, user_id=None):
        if user_id is None:
            return Response({'detail': 'user_id required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            mu = MasterUser.objects.select_related('role').only('id', 'username', 'role_id').get(id=user_id)
            role_name = mu.get_role_name() or ''
        except MasterUser.DoesNotExist:
            return Response({'detail': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

        scopes = MasterGeoUserScope.objects.filter(user_id=user_id, is_active=1).only('block_id', 'district_id')
        blocks = set()
        districts = set()
        for s in scopes:
            if s.block_id:
                blocks.add(int(s.block_id))
            if s.district_id:
                districts.add(int(s.district_id))

        role_name_lower = (role_name or '').lower()
        response = {'user_id': user_id, 'username': mu.username, 'role': role_name, 'blocks': [], 'districts': []}
        if role_name_lower.startswith('bmmu') or role_name_lower == 'bmmu':
            response['blocks'] = sorted(list(blocks))
        elif role_name_lower.startswith('dmmu') or role_name_lower in ('dmmu', 'dc', 'dcnrlm'):
            response['districts'] = sorted(list(districts))
        else:
            response['blocks'] = sorted(list(blocks))
            response['districts'] = sorted(list(districts))
        return Response(response)

class UserGeoScopeLookupView(APIView):
    permission_classes = (permissions.AllowAny,)

    def get(self, request):
        block_id = request.GET.get("block_id")
        district_id = request.GET.get("district_id")

        if block_id is None and district_id is None:
            return Response(
                {'detail': 'Provide block_id or district_id'},
                status=status.HTTP_400_BAD_REQUEST
            )

        qs = MasterGeoUserScope.objects.filter(is_active=1)

        # ------------------------
        # BLOCK FILTER (supports "null")
        # ------------------------
        if block_id is not None:
            if block_id.lower() == "null":
                qs = qs.filter(block_id__isnull=True)
            elif block_id != "":
                qs = qs.filter(block_id=block_id)

        # ------------------------
        # DISTRICT FILTER (supports "null")
        # ------------------------
        if district_id is not None:
            if district_id.lower() == "null":
                qs = qs.filter(district_id__isnull=True)
            elif district_id != "":
                qs = qs.filter(district_id=district_id)

        # Extract unique list of user_ids
        user_ids = list(qs.values_list("user_id", flat=True).distinct())

        return Response({
            "block_id": block_id,
            "district_id": district_id,
            "users_exist": bool(user_ids),
            "user_ids": user_ids
        })
        
class IsBlockAspirationalView(APIView):
    permission_classes = (permissions.AllowAny,)

    def get(self, request, block_id=None):
        if not block_id:
            return Response({'detail': 'block_id required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            block = MasterBlock.objects.only('is_aspirational').get(block_id=block_id)
        except MasterBlock.DoesNotExist:
            return Response({'detail': 'Block not found'}, status=status.HTTP_404_NOT_FOUND)

        return Response({'block_id': block_id, 'is_aspirational': block.is_aspirational})        
