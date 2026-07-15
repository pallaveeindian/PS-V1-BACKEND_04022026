# epSakhi/api/views.py

import json
import csv
from io import StringIO
from collections import defaultdict

import requests
import certifi
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from django.conf import settings
from django.core.cache import cache
from django.db import transaction, models
from django.db.models import Q
from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page

from rest_framework.pagination import PageNumberPagination
from rest_framework import viewsets, status, filters, generics
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import PermissionDenied
from rest_framework.generics import ListAPIView

from core.models import (
    MasterUser,
    MasterPanchayat,
    MasterBlock,
    MasterDistrict,
    MasterGeoUserScope,
)
from epSakhi.models import *

from .serializers import *
# from core.upsrlm_sync import sync_shg_list, sync_shg_detail


# Backward-compat alias: keep old name used everywhere in code,
# but actually point to the new model.
EnterpriseSupportDetail = EnterpriseSubsidyDetail

# -------------------------------------------------------------------
# Common helpers
# -------------------------------------------------------------------

CACHE_TTL = getattr(settings, 'CACHE_TTL', 300)
SHG_CACHE_TTL = getattr(settings, 'SHG_CACHE_TTL', 300)

def _parse_csv_param(value: str):
    if not value:
        return []
    return [p.strip() for p in value.split(',') if p.strip()]


def _paginate_plain_list(request, data):
    """
    Simple manual paginator for list-of-dicts responses.
    Supports page & page_size query params; defaults page_size=10.
    """
    try:
        page = int(request.GET.get('page', '1'))
        page_size = int(request.GET.get('page_size', '10'))
    except ValueError:
        page, page_size = 1, 10
    if page < 1:
        page = 1
    if page_size < 1:
        page_size = 10

    total = len(data)
    start = (page - 1) * page_size
    end = start + page_size
    items = data[start:end]
    return {
        'meta': {
            'page': page,
            'page_size': page_size,
            'total': total,
        },
        'data': items,
    }


def _apply_list_filters(rows, filter_map, params):
    """
    rows: list[dict]
    filter_map: { query_param_name: key_in_row }
    """
    for qparam, field in filter_map.items():
        if qparam in params:
            value = params.get(qparam)
            rows = [r for r in rows if str(r.get(field)) == str(value)]
    return rows


def _apply_list_search(rows, search_term, search_fields):
    if not search_term:
        return rows
    ql = search_term.lower()
    out = []
    for r in rows:
        for f in search_fields:
            v = r.get(f)
            if v is not None and ql in str(v).lower():
                out.append(r)
                break
    return out


def _apply_list_ordering(rows, ordering_param, allowed_fields):
    if not ordering_param:
        return rows
    reverse = ordering_param.startswith('-')
    key = ordering_param.lstrip('-')
    if key not in allowed_fields:
        return rows
    return sorted(rows, key=lambda r: r.get(key) or '', reverse=reverse)


def _apply_list_group_by(rows, group_by_param):
    if not group_by_param:
        return None
    keys = [k.strip() for k in group_by_param.split(',') if k.strip()]
    if not keys:
        return None
    agg = defaultdict(int)
    for r in rows:
        gk = tuple(r.get(k) for k in keys)
        agg[gk] += 1
    out = [{'group': dict(zip(keys, k)), 'count': v} for k, v in agg.items()]
    return out


def _apply_fields_projection_list(rows, fields_param):
    if not fields_param:
        return rows
    cols = [c.strip() for c in fields_param.split(',') if c.strip()]
    return [{c: r.get(c) for c in cols} for r in rows]


# -------------------------------------------------------------------
# SHG (UPSRLM via APISetu) – simple endpoints used by epSakhi
# -------------------------------------------------------------------

def _get_apisetu_headers():
    client_id = settings.APISETU_CLIENT_ID
    api_key = settings.APISETU_API_KEY
    if not client_id or not api_key:
        raise RuntimeError("APISETU_CLIENT_ID / APISETU_API_KEY must be set in settings")
    return {
        "X-APISETU-CLIENTID": client_id,
        "X-APISETU-APIKEY": api_key,
        "accept": "application/json",
        "scope": "members",
    }


def _call_apisetu_shg_list(block_id: int):
    template = "https://apisetu.gov.in/mord/lokos/srv/v1/up/shg/block?block_id={block_id}"
    
    if not template:
        raise RuntimeError("APISETU_SHG_LIST_URL_TEMPLATE is not configured")

    url = template.format(block_id=block_id)

    # -------------------------------
    # NEW (SURGICAL): retries + backoff
    # -------------------------------
    session = requests.Session()

    retry = Retry(
        total=3,
        backoff_factor=1,               # 1s, 2s, 4s
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        raise_on_status=False
    )

    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    # -------------------------------

    resp = session.get(
        url,
        headers=_get_apisetu_headers(),
        timeout=(5, 60),   # connect timeout, read timeout
        verify=False
    )

    if resp.status_code != 200:
        raise RuntimeError(
            f"APISetu SHG list error {resp.status_code}: {resp.text[:200]}"
        )

    data = resp.json()

    # # NEW: import into master_* tables on first fetch (view will cache separately)
    # try:
    #     sync_shg_list(block_id, data)
    # except Exception:
    #     # don't break API view if import fails
    #     logger.exception("Failed to sync SHG list for block_id=%s", block_id)

    return data


def _call_apisetu_shg_detail(shg_code: str):
    template = "https://apisetu.gov.in/mord/lokos/srv/v1/up/shg?shg_code={shg_code}"
    url = template.format(shg_code=shg_code)

    # -------------------------------
    # NEW (SURGICAL): retries + backoff
    # -------------------------------
    session = requests.Session()

    retry = Retry(
        total=3,
        backoff_factor=1,               # 1s, 2s, 4s
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        raise_on_status=False
    )

    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    # -------------------------------

    resp = session.get(
        url,
        headers=_get_apisetu_headers(),
        timeout=(5, 60),   # connect timeout, read timeout
        verify=False
    )

    if resp.status_code != 200:
        raise RuntimeError(
            f"APISetu SHG detail error {resp.status_code}: {resp.text[:200]}"
        )

    data = resp.json()

    # # NEW: import into master_* tables
    # try:
    #     sync_shg_detail(data)
    # except Exception:
    #     logger.exception("Failed to sync SHG detail for shg_code=%s", shg_code)

    return data


class UpsrlmShgListView(APIView):
    """
    GET /api/v1/epsakhi/upsrlm-shg-list/<block_id>/
    Wrapper around APISetu SHG list for a given block.
    """
    permission_classes = (IsAuthenticated,)

    def get(self, request, block_id):
        cache_key = f"upsrlm_shg_list:{block_id}"
        j = cache.get(cache_key)
        if j is None:
            try:
                j = _call_apisetu_shg_list(block_id)
            except Exception as e:
                return Response({'detail': f'Error fetching SHG list: {str(e)}'}, status=502)
            cache.set(cache_key, j, SHG_CACHE_TTL)

        # APISetu sometimes returns a top-level LIST, sometimes a DICT
        if isinstance(j, list):
            rows = j
        elif isinstance(j, dict):
            rows = j.get('data') or j.get('shg_list') or j.get('shgList') or []
        else:
            rows = []

        # optional search, ordering, fields, pagination
        rows = _apply_list_search(
            rows,
            request.GET.get('search'),
            ['name', 'code', 'nicCode', 'uuid' , 'panchayatId' , 'villageId'],
        )
        rows = _apply_list_ordering(
            rows,
            request.GET.get('ordering'),
            allowed_fields={'name', 'code'},
        )
        grouped = _apply_list_group_by(rows, request.GET.get('group_by'))
        if grouped is not None:
            grouped = _apply_fields_projection_list(grouped, request.GET.get('fields'))
            return Response(grouped)

        rows = _apply_fields_projection_list(rows, request.GET.get('fields'))
        result = _paginate_plain_list(request, rows)
        return Response(result)



class UpsrlmShgMembersView(APIView):
    """
    GET /api/v1/epsakhi/upsrlm-shg-members/<shg_code>/
    Uses SHG detail endpoint and returns members with filters/search/ordering/pagination.
    """
    permission_classes = (IsAuthenticated,)

    def get(self, request, shg_code):
        cache_key = f"upsrlm_shg_detail:{shg_code}"
        j = cache.get(cache_key)
        if j is None:
            try:
                j = _call_apisetu_shg_detail(shg_code)
            except Exception as e:
                return Response({'detail': f'Error fetching shg-members: {str(e)}'}, status=502)
            cache.set(cache_key, j, SHG_CACHE_TTL)

        members = j.get('shg_members', []) or []

        # Simple filters
        if request.GET.get('aadhar_verified') is not None:
            av = request.GET.get('aadhar_verified')
            if av.lower() in ('1', 'true', 'yes'):
                members = [m for m in members if m.get('aadhar_verified')]
            else:
                members = [m for m in members if not m.get('aadhar_verified')]
        
        if request.GET.get('pld_status') is not None:
            av = request.GET.get('pld_status')
            if av.lower() in ('1', 'true', 'yes'):
                members = [m for m in members if m.get('pld_status')]
            else:
                members = [m for m in members if not m.get('pld_status')]

        for f in ('gender', 'religion', 'social_category'):
            if request.GET.get(f):
                members = [m for m in members if m.get(f) == request.GET.get(f)]

        # search
        q = request.GET.get('search')
        if q:
            ql = q.lower()

            def mmatch(m):
                if ql in (m.get('member_name') or '').lower():
                    return True
                if ql in (str(m.get('member_code')) or '').lower():
                    return True
                if ql in (m.get('nic_member_code') or '').lower():
                    return True
                if ql in (m.get('member_guid') or '').lower():
                    return True
                for ph in m.get('member_phones', []):
                    if ql in str(ph.get('phone_no') or ''):
                        return True
                return False

            members = [m for m in members if mmatch(m)]

        # ordering
        ordering = request.GET.get('ordering')
        if ordering:
            reverse = ordering.startswith('-')
            key = ordering.lstrip('-')
            members = sorted(members, key=lambda m: m.get(key) or '', reverse=reverse)

        # group_by
        group_by = request.GET.get('group_by')
        if group_by:
            keys = [k.strip() for k in group_by.split(',') if k.strip()]
            agg = {}
            for it in members:
                group_key = tuple(str(it.get(k)) for k in keys)
                agg[group_key] = agg.get(group_key, 0) + 1
            out = [{'group': dict(zip(keys, k)), 'count': v} for k, v in agg.items()]
            return Response(out)

        # fields projection
        fields = request.GET.get('fields')
        if fields:
            cols = [c.strip() for c in fields.split(',') if c.strip()]
            members = [{c: m.get(c) for c in cols} for m in members]

        # pagination
        result = _paginate_plain_list(request, members)
        return Response(result)


class UpsrlmShgDetailView(APIView):
    """
    GET /api/v1/epsakhi/upsrlm-shg-detail/<shg_code>/
    Returns SHG detail (without members, unless requested).
    """
    permission_classes = (IsAuthenticated,)

    def get(self, request, shg_code):
        cache_key = f"upsrlm_shg_detail:{shg_code}"
        j = cache.get(cache_key)
        if j is None:
            try:
                j = _call_apisetu_shg_detail(shg_code)
            except Exception as e:
                return Response({'detail': f'Error fetching shg-detail: {str(e)}'}, status=502)
            cache.set(cache_key, j, SHG_CACHE_TTL)

        data = {k: v for k, v in j.items() if k != 'shg_members'}
        fields = request.GET.get('fields')
        if fields:
            cols = [c.strip() for c in fields.split(',') if c.strip()]
            data = {c: data.get(c) for c in cols}
        return Response(data)


# -------------------------------------------------------------------
# BaseProjectionMixin (used by some viewsets)
# -------------------------------------------------------------------

class BaseProjectionMixin:
    """
    Adds support for:
      - fields=<comma>
      - group_by=<comma>
      - ordering=<field or -field>
    """

    filter_backends = [filters.SearchFilter, filters.OrderingFilter]

    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset())

        group_by = request.GET.get('group_by')
        if group_by:
            keys = [k.strip() for k in group_by.split(',') if k.strip()]
            vals = qs.values(*keys).order_by().annotate(count=models.Count('id'))
            return Response(list(vals))

        fields = request.GET.get('fields')
        if fields:
            cols = [c.strip() for c in fields.split(',') if c.strip()]
            qs = qs.values(*cols)
            page = self.paginate_queryset(qs)
            return self.get_paginated_response(list(page) if page is not None else list(qs))
        return super().list(request, *args, **kwargs)


# -------------------------------------------------------------------
# CRPEP + mapping viewsets
# -------------------------------------------------------------------

class CRPEPViewSet(viewsets.ModelViewSet, BaseProjectionMixin):
    queryset = CRPEP.objects.all().order_by('-created_at')
    serializer_class = CRPEPSerializer
    permission_classes = [IsAuthenticated]
    search_fields = ['name', 'mobile_number', 'lokos_member_code', 'lokos_shg_code']
    ordering_fields = ['created_at', 'marks_obtained', 'id']

    # 🔐 Only specific users can create CRP accounts
    def perform_create(self, serializer):

        auth_user = self.request.user

        try:
            master_user = MasterUser.objects.get(
                username=auth_user.username
            )
        except MasterUser.DoesNotExist:
            raise PermissionDenied("Invalid user")

        allowed_ids = {2, 12}

        if master_user.role_id not in allowed_ids:
            raise PermissionDenied(
                "Not authorized to create CRP accounts."
            )

        serializer.save(
            created_by=master_user
        )

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.GET
        if params.get('district_id'):
            qs = qs.filter(district_id=int(params['district_id']))
        if params.get('block_id'):
            qs = qs.filter(block_id=int(params['block_id']))
        if params.get('panchayat_id'):
            qs = qs.filter(panchayat_id=int(params['panchayat_id']))
        if params.get('lokos_member_code'):
            qs = qs.filter(lokos_shg_code=params['lokos_member_code'])            
        if params.get('lokos_shg_code'):
            qs = qs.filter(lokos_shg_code=params['lokos_shg_code'])
        if params.get('nodal_clf'):
            qs = qs.filter(nodal_clf=params['nodal_clf'])
        return qs

    @action(detail=False, methods=['get'])
    def export(self, request):
        """
        Export CRPEP list to CSV with basic fields.
        """
        qs = self.get_queryset().only(
            'id',
            'name',
            'district_id',
            'block_id',
            'panchayat_id',
            'lokos_shg_code',
            'mobile_number',
            'category',
            'marks_obtained',
        )

        buffer = StringIO()
        writer = csv.writer(buffer)
        writer.writerow(
            ['id', 'name', 'district_id', 'block_id', 'panchayat_id', 'shg_code', 'mobile_number', 'category', 'marks_obtained']
        )

        for r in qs.iterator():
            writer.writerow(
                [
                    r.id,
                    r.name,
                    r.district_id,
                    r.block_id,
                    r.panchayat_id,
                    getattr(r, 'lokos_shg_code', ''),
                    r.mobile_number,
                    r.category,
                    r.marks_obtained,
                ]
            )

        buffer.seek(0)
        response = HttpResponse(buffer.getvalue(), content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="crpep_export.csv"'
        return response


class CRPPanchayatMappingViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    @action(detail=True, methods=['post'])
    def link(self, request, pk=None):
        crp_id = pk
        panchayat_ids = request.data.get('panchayat_ids', [])
        if not isinstance(panchayat_ids, list):
            return Response({'detail': 'panchayat_ids must be list'}, status=status.HTTP_400_BAD_REQUEST)
        created = []
        with transaction.atomic():
            for pid in panchayat_ids:
                obj, _ = CRPEPToPanchayat.objects.get_or_create(crp_id=crp_id, allocated_panchayat_id=pid)
                created.append(obj.id)
        return Response({'created_ids': created})


# -------------------------------------------------------------------
# BeneficiaryRecorded ViewSet
# -------------------------------------------------------------------

class SurgicalCustomPagination(PageNumberPagination):
    page_query_param = 'page'
    page_size_query_param = 'limit'  # Maps frontend 'limit' to DRF page size
    max_page_size = 100

class BeneficiaryRecordedViewSet(viewsets.ModelViewSet, BaseProjectionMixin):
    # Set the custom pagination class here
    pagination_class = SurgicalCustomPagination

    serializer_class = BeneficiaryRecordedSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['applicant_name', 'lokos_member_code', 'mobile', 'email', 'enterprise_id']
    ordering_fields = ['age', 'created_at']

    def list(self, request, *args, **kwargs):
        # Default to returning ALL unless '?paginate=true' is passed
        if request.GET.get('paginate') != 'true':
            self.pagination_class = None

        qs = self.filter_queryset(self.get_queryset())

        # Handle 'group_by'
        group_by = request.GET.get('group_by')
        if group_by:
            keys = [k.strip() for k in group_by.split(',') if k.strip()]
            vals = qs.values(*keys).order_by().annotate(count=models.Count('id'))
            page = self.paginate_queryset(vals)
            if page is not None:
                return self.get_paginated_response(list(page))
            return Response(list(vals))

        # Handle 'fields'
        fields = request.GET.get('fields')
        if fields:
            cols = [c.strip() for c in fields.split(',') if c.strip()]
            qs = qs.values(*cols)
            page = self.paginate_queryset(qs)
            if page is not None:
                return self.get_paginated_response(list(page))
            return Response(list(qs))

        # Fallback to standard serialized response (Paginated or ALL)
        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)

    def get_queryset(self):
        qs = (
            BeneficiaryRecorded.objects
            .select_related('district_id', 'block_id', 'panchayat_id', 'village_id')
            .order_by('-created_at')
        )

        if self.action == "list":
            qs = qs.filter(is_active=True)

        params = self.request.GET
        if params.get('created_by'):
            qs = qs.filter(created_by_id=int(params['created_by']))
        if params.get('district_id'):
            qs = qs.filter(district_id=int(params['district_id']))
        if params.get('block_id'):
            qs = qs.filter(block_id=int(params['block_id']))
        if params.get('panchayat_id'):
            qs = qs.filter(panchayat_id=int(params['panchayat_id']))
        if params.get('village_id'):
            qs = qs.filter(village_id=int(params['village_id']))
        if params.get('lokos_shg_code'):
            qs = qs.filter(lokos_shg_code=params['lokos_shg_code'])
        if params.get('gender'):
            qs = qs.filter(gender=params['gender'])
        if params.get('marital_status'):
            qs = qs.filter(marital_status=params['marital_status'])
        if params.get('category'):
            qs = qs.filter(category=params['category'])
        if params.get('pld_status'):
            qs = qs.filter(pld_status=params['pld_status'])
        return qs

# -------------------------------------------------------------------
# Enterprise main viewsets
# -------------------------------------------------------------------

class ExistingEnterpriseViewSet(viewsets.ModelViewSet):
    """
    /api/v1/epsakhi/existing-enterprise/
    """
    queryset = ExistingEnterprise.objects.all().order_by('-created_at')
    serializer_class = ExistingEnterpriseSerializer
    permission_classes = [IsAuthenticated]


class NewEnterpriseViewSet(viewsets.ModelViewSet):
    """
    /api/v1/epsakhi/new-enterprise/
    """
    queryset = NewEnterprise.objects.all().order_by('-created_at')
    serializer_class = NewEnterpriseSerializer
    permission_classes = [IsAuthenticated]


# -------------------------------------------------------------------
# Child tables – loan/support(subsidy)/training/media
# (updated with search, ordering, simple filtering)
# -------------------------------------------------------------------
class EnterpriseLicensesViewSet(viewsets.ModelViewSet):
    """
    /api/v1/epsakhi/enterprise-licenses/

    Query params:
      - enterprise_id=<id> (optional filter)
    """    
    queryset = EnterpriseLicenses.objects.all().order_by('-created_at')
    serializer_class = EnterpriseLicensesSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['enterprise_id__id', 'license_category', 'license_no', 'license_name']
    ordering_fields = ['created_at']

    def get_queryset(self):
        qs = super().get_queryset()
        enterprise_id = self.request.query_params.get('enterprise_id')
        if enterprise_id:
            qs = qs.filter(enterprise_id__id=enterprise_id)
        return qs

class EnterpriseLoanDetailViewSet(viewsets.ModelViewSet):
    """
    /api/v1/epsakhi/enterprise-loan-details/

    Query params:
      - enterprise_id=<id> (optional filter)
    """
    queryset = EnterpriseLoanDetail.objects.all().order_by('-created_at')
    serializer_class = EnterpriseLoanDetailSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['enterprise_id__id', 'institution_name']
    ordering_fields = ['created_at', 'loan_amount', 'date_taken']

    def get_queryset(self):
        qs = super().get_queryset()
        enterprise_id = self.request.query_params.get('enterprise_id')
        if enterprise_id:
            qs = qs.filter(enterprise_id__id=enterprise_id)
        form_type = self.request.query_params.get('form_type')
        if form_type:
            qs = qs.filter(form_type=form_type)
        return qs

class EnterpriseSubsidyDetailViewSet(viewsets.ModelViewSet):
    """
    /api/v1/epsakhi/enterprise-support-details/

    NOTE:
    - One enterprise can have MANY subsidy rows (epSakhi_exEpSubsidy).
    """
    queryset = EnterpriseSubsidyDetail.objects.all().order_by('-created_at')
    serializer_class = EnterpriseSubsidyDetailSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['enterprise_id__id', 'subsidy_type', 'subsidy_name']
    ordering_fields = ['created_at']

    def get_queryset(self):
        qs = super().get_queryset()
        enterprise_id = self.request.query_params.get('enterprise_id')
        if enterprise_id:
            qs = qs.filter(enterprise_id__id=enterprise_id)
        return qs

class EnterpriseShopViewSet(viewsets.ModelViewSet):
    """
    /api/v1/epsakhi/enterprise-shop/

    Query params:
      - enterprise_id=<id> (optional filter)
    """    
    queryset = EnterpriseShop.objects.all().order_by('-created_at')
    serializer_class = EnterpriseShopSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['enterprise_id__id', 'shop_category', 'shop_type']
    ordering_fields = ['created_at']

    def get_queryset(self):
        qs = super().get_queryset()
        enterprise_id = self.request.query_params.get('enterprise_id')
        if enterprise_id:
            qs = qs.filter(enterprise_id__id=enterprise_id)
        return qs

class ShopMediaViewSet(viewsets.ModelViewSet):
    """
    /api/v1/epsakhi/shop-media/

    Query params:
      - product_id=<id> (optional filter)
    """    
    queryset = ShopMedia.objects.all().order_by('-created_at')
    serializer_class = ShopMediaSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['product_id__id']
    ordering_fields = ['created_at']

    def get_queryset(self):
        qs = super().get_queryset()
        product_id = self.request.query_params.get('product_id')
        if product_id:
            qs = qs.filter(product_id=product_id)
        return qs

class EnterpriseProductViewSet(viewsets.ModelViewSet):
    """
    /api/v1/epsakhi/enterprise-products/

    Query params:
      - enterprise_id=<id> (optional filter)
    """    
    queryset = EnterpriseProduct.objects.all().order_by('-created_at')
    serializer_class = EnterpriseProductSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['enterprise_id__id', 'activity_or_product_type']
    ordering_fields = ['created_at']

    def get_queryset(self):
        qs = super().get_queryset()
        enterprise_id = self.request.query_params.get('enterprise_id')
        if enterprise_id:
            qs = qs.filter(enterprise_id__id=enterprise_id)
        return qs
    
class ProductMediaViewSet(viewsets.ModelViewSet):
    """
    /api/v1/epsakhi/product-media/

    Query params:
      - product_id=<id> (optional filter)
    """    
    queryset = ProductMedia.objects.all().order_by('-created_at')
    serializer_class = ProductMediaSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['product_id__id']
    ordering_fields = ['created_at']

    def get_queryset(self):
        qs = super().get_queryset()
        product_id = self.request.query_params.get('product_id')
        if product_id:
            qs = qs.filter(product_id=product_id)
        return qs    

class EnterpriseMediaViewSet(viewsets.ModelViewSet):
    """
    /api/v1/epsakhi/enterprise-media/
    """
    queryset = EnterpriseMedia.objects.all().order_by('-created_at')
    serializer_class = EnterpriseMediaSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['enterprise_id__id']
    ordering_fields = ['created_at']

    def get_queryset(self):
        qs = super().get_queryset()
        enterprise_id = self.request.query_params.get('enterprise_id')
        if enterprise_id:
            qs = qs.filter(enterprise_id__id=enterprise_id)
        return qs

# Shared Classes
class EnterpriseTypeCategoryViewSet(viewsets.ModelViewSet):
    """
    /api/v1/epsakhi/enterprise-types/
    """
    queryset = EnterpriseTypeCategory.objects.all().order_by('-created_at')
    serializer_class = EnterpriseTypeCategorySerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['enterprise_id', 'parent_category', 'sub_category', 'form_type']
    ordering_fields = ['created_at']

    def get_queryset(self):
        qs = super().get_queryset()
        enterprise_id = self.request.query_params.get('enterprise_id')
        if enterprise_id:
            qs = qs.filter(enterprise_id=enterprise_id)
        form_type = self.request.query_params.get('form_type')
        if form_type:
            qs = qs.filter(form_type=form_type)
        return qs
    
class EnterpriseSupportViewSet(viewsets.ModelViewSet):
    """
    /api/v1/epsakhi/enterprise-support/
    """
    queryset = EnterpriseSupport.objects.all().order_by('-created_at')
    serializer_class = EnterpriseSupportSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['enterprise_id', 'support_category', 'support_sub_category', 'form_type']
    ordering_fields = ['created_at']

    def get_queryset(self):
        qs = super().get_queryset()
        enterprise_id = self.request.query_params.get('enterprise_id')
        if enterprise_id:
            qs = qs.filter(enterprise_id=enterprise_id)
        form_type = self.request.query_params.get('form_type')
        if form_type:
            qs = qs.filter(form_type=form_type)
        return qs    

class EnterpriseMandatoryFundViewSet(viewsets.ModelViewSet):
    """
    /api/v1/epsakhi/mandatory-fund/
    """
    queryset = EnterpriseMandatoryFund.objects.all().order_by('-created_at')
    serializer_class = EnterpriseMandatoryFundSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['enterprise_id', 'fund_type', 'repayment_status', 'form_type']
    ordering_fields = ['created_at']

    def get_queryset(self):
        qs = super().get_queryset()
        enterprise_id = self.request.query_params.get('enterprise_id')
        if enterprise_id:
            qs = qs.filter(enterprise_id=enterprise_id)
        form_type = self.request.query_params.get('form_type')
        if form_type:
            qs = qs.filter(form_type=form_type)
        return qs    

class EnterpriseTrainingReqViewSet(viewsets.ModelViewSet):
    """
    /api/v1/epsakhi/enterprise-training-reqs/
    """
    queryset = EnterpriseTrainingReq.objects.all().order_by('-created_at')
    serializer_class = EnterpriseTrainingReqSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['enterprise_id', 'sector', 'department']
    ordering_fields = ['created_at', 'expected_income']

    def get_queryset(self):
        qs = super().get_queryset()
        enterprise_id = self.request.query_params.get('enterprise_id')
        if enterprise_id:
            qs = qs.filter(enterprise_id=enterprise_id)
        form_type = self.request.query_params.get('form_type')
        if form_type:
            qs = qs.filter(form_type=form_type)
        return qs

class TrainingCertificatesViewSet(viewsets.ModelViewSet):
    """
    /api/v1/epsakhi/training-certif/

    Query params:
      - enterprise_id=<TH_urid> (optional filter)
      - training_id=<TH_urid> (optional filter)
    """    
    queryset = TrainingCertificates.objects.all().order_by('-created_at')
    serializer_class = TrainingCertificatesSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['enterprise_id', 'training_id']
    ordering_fields = ['created_at']

    def get_queryset(self):
        qs = super().get_queryset()
        enterprise_id = self.request.query_params.get('enterprise_id')
        if enterprise_id:
            qs = qs.filter(enterprise_id=enterprise_id)
        training_id = self.request.query_params.get('training_id')
        if training_id:
            qs = qs.filter(training_id_id=training_id)    
        return qs  

class NoEnterpriseFormViewSet(viewsets.ModelViewSet):
    """
    /api/v1/epsakhi/no-enterprise-forms/
    """
    queryset = NoEnterpriseForm.objects.all().order_by('-created_at')
    serializer_class = NoEnterpriseFormSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['recorded_benef_id']
    ordering_fields = ['created_at']

    def get_queryset(self):
        qs = super().get_queryset()
        recorded_benef_id = self.request.query_params.get('recorded_benef_id')
        if recorded_benef_id:
            qs = qs.filter(recorded_benef_id=recorded_benef_id)
        return qs


class NoEnterpriseWageViewSet(viewsets.ModelViewSet):
    """
    /api/v1/epsakhi/no-enterprise-wages/
    """
    queryset = NoEnterpriseWage.objects.all().order_by('-created_at')
    serializer_class = NoEnterpriseWageSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['enterprise_id', 'placement_sector', 'type_of_emp', 'location_scope', 'location']
    ordering_fields = ['created_at', 'exp_salary']

    def get_queryset(self):
        qs = super().get_queryset()
        enterprise_id = self.request.query_params.get('enterprise_id')
        if enterprise_id:
            qs = qs.filter(enterprise_id=enterprise_id)
        return qs


# -------------------------------------------------------------------
# CRP helper APIs: CLF → CRP list, CRP detail, Panchayats under CRP, etc.
# (Logic kept same; only imports updated to new models)
# -------------------------------------------------------------------


class CRPListByClfView(APIView):
    """
    GET /api/v1/epsakhi/crp-list/<clf_code>/
    Returns a list of CRPs whose nodal_clf == clf_code.
    """
    permission_classes = (IsAuthenticated,)

    def get(self, request, clf_code):
        qs = CRPEP.objects.filter(nodal_clf=clf_code).order_by('name')
        rows = list(
            qs.values(
                'id',
                'name',
                'mobile_number',
                'lokos_shg_code',
                'category',
                'marks_obtained',
                'TH_urid',
            )
        )

        rows = _apply_list_search(rows, request.GET.get('search'), ['name', 'mobile_number', 'lokos_shg_code'])
        rows = _apply_list_ordering(rows, request.GET.get('ordering'), {'name', 'id', 'marks_obtained'})

        grouped = _apply_list_group_by(rows, request.GET.get('group_by'))
        if grouped is not None:
            grouped = _apply_fields_projection_list(grouped, request.GET.get('fields'))
            return Response(grouped)

        rows = _apply_fields_projection_list(rows, request.GET.get('fields'))
        result = _paginate_plain_list(request, rows)
        return Response(result)

class CRPListAPIView(ListAPIView):
    serializer_class = CRPListSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = (
            CRPEP.objects.select_related(
                "district",
                "block",
                "panchayat"
            )
            .filter(is_active=True)
        )

        district = self.request.query_params.get("district", "").strip()
        block = self.request.query_params.get("block", "").strip()
        panchayat = self.request.query_params.get("panchayat", "").strip()
        search = self.request.query_params.get("search", "").strip()

        if district and district.lower() not in ("null", "undefined"):
            queryset = queryset.filter(district_id=int(district))

        if block and block.lower() not in ("null", "undefined"):
            queryset = queryset.filter(block_id=int(block))

        if panchayat and panchayat.lower() not in ("null", "undefined"):
            queryset = queryset.filter(panchayat_id=int(panchayat))

        if search:
            queryset = queryset.filter(
                Q(name__icontains=search)
                | Q(lokos_shg_code__icontains=search)
                | Q(lokos_member_code__icontains=search)
            )

        return queryset.order_by("id")

class CRPDetailView(APIView):
    """
    GET /api/v1/epsakhi/crp-detail/<member_code>/
    member_code = lokos_member_code of CRP.
    """
    permission_classes = (IsAuthenticated,)

    def get(self, request, member_code):
        try:
            crp = CRPEP.objects.select_related("master_user").get(
                lokos_member_code=member_code
            )
        except CRPEP.DoesNotExist:
            return Response(
                {'detail': 'CRP not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        data = CRPEPSerializer(crp).data

        fields_param = request.GET.get('fields')
        if fields_param:
            allowed = _parse_csv_param(fields_param)
            data = {k: v for k, v in data.items() if k in allowed}

        return Response(data)



class CRPDetailbyUserID(APIView):
    """
    GET /api/v1/epsakhi/crp-detail/id/<id>/
    id = master_user.id
    """
    permission_classes = (IsAuthenticated,)

    def get(self, request, id):
        try:
            crp = CRPEP.objects.get(master_user_id=int(id))
        except (CRPEP.DoesNotExist, ValueError):
            return Response({'detail': 'CRP not found'}, status=status.HTTP_404_NOT_FOUND)

        data = CRPEPSerializer(crp).data
        fields_param = request.GET.get('fields')
        if fields_param:
            allowed = _parse_csv_param(fields_param)
            data = {k: v for k, v in data.items() if k in allowed}
        return Response(data)


class CRPPanchayatsUnderCrpView(APIView):
    """
    GET /api/v1/epsakhi/panchayats-under-crp/
    GET /api/v1/epsakhi/panchayats-under-crp/<member_code>/

    Optional Query Params:
        ?member_code=
        ?panchayat_id=
    """
    permission_classes = (IsAuthenticated,)

    def get(self, request, member_code=None):

        # Allow member_code from query param also
        member_code = member_code or request.GET.get("member_code")
        panchayat_id = request.GET.get("panchayat_id")

        # --------------------------------------------------
        # Base queryset
        # --------------------------------------------------
        assignment_qs = CRPEPToPanchayat.objects.filter(is_active=True)

        # --------------------------------------------------
        # Filter by member_code
        # --------------------------------------------------
        if member_code:
            try:
                crp = CRPEP.objects.get(lokos_member_code=member_code)
            except CRPEP.DoesNotExist:
                return Response(
                    {'detail': 'CRP not found'},
                    status=status.HTTP_404_NOT_FOUND
                )

            assignment_qs = assignment_qs.filter(
                crp_id=crp.master_user_id
            )

        # --------------------------------------------------
        # Filter by panchayat_id (NEW)
        # --------------------------------------------------
        if panchayat_id:
            assignment_qs = assignment_qs.filter(
                allocated_panchayat_id=panchayat_id
            )

        # --------------------------------------------------
        # Get Panchayat IDs with CRP ID
        # --------------------------------------------------
        assignments = list(
            assignment_qs.values(
                'id',
                'crp_id',
                'allocated_panchayat_id'
            )
        )

        if not assignments:
            return Response({
                "meta": {
                    "page": 1,
                    "page_size": 10,
                    "total": 0
                },
                "data": []
            })

        # --------------------------------------------------
        # Fetch Panchayat details
        # --------------------------------------------------
        panchayat_ids = list(
            set(a['allocated_panchayat_id'] for a in assignments)
        )

        panchayats = MasterPanchayat.objects.filter(
            panchayat_id__in=panchayat_ids
        ).values(
            'panchayat_id',
            'panchayat_name_en',
            'panchayat_name_local',
            'panchayat_code',
            'block_id',
            'district_id',
            'state_id',
        )

        panchayat_map = {
            p['panchayat_id']: p
            for p in panchayats
        }

        # --------------------------------------------------
        # Merge CRP ID + Panchayat Data
        # --------------------------------------------------
        rows = []
        for a in assignments:
            p_data = panchayat_map.get(a['allocated_panchayat_id'])
            if p_data:
                row = {
                    "id": a['id'],
                    "crp_id": a['crp_id'],
                    **p_data
                }
                rows.append(row)

        result = _paginate_plain_list(request, rows)
        return Response(result)

class CRPPanchayatViewSet(viewsets.ModelViewSet):
    """
    CRUD for CRPEPToPanchayat
    """
    serializer_class = CRPEPToPanchayatCRUDSerializer
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        queryset = CRPEPToPanchayat.objects.filter(is_active=True)

        member_code = self.request.query_params.get("member_code")
        panchayat_id = self.request.query_params.get("panchayat_id")

        # Filter by member_code
        if member_code:
            try:
                crp = CRPEP.objects.get(lokos_member_code=member_code)
                queryset = queryset.filter(crp_id=crp.master_user_id)
            except CRPEP.DoesNotExist:
                return CRPEPToPanchayat.objects.none()

        # Filter by panchayat_id
        if panchayat_id:
            queryset = queryset.filter(
                allocated_panchayat_id=panchayat_id
            )

        return queryset


class CRPPanchayatsUnderCrpByID(APIView):
    permission_classes = (IsAuthenticated,)

    # VUN-1: Admin Roles with Ellivated privileges to view all CRP-Panchayat mapping.
    # This is to support Admin Dashboard usecase where admin wants to view all mappings without restriction.
    ALLOWED_ROLES = [12, 10, 8, 9, 3, 2, 1]

    def _get_master_user(self, request):
        auth_user = request.user

        master_user = MasterUser.objects.filter(
            username=auth_user.username
        ).first()

        if not master_user:
            raise PermissionDenied("Invalid user.")

        return master_user

    def get(self, request, id=None):
        # VUN-1: ID here is master_user.id, NOT CRP ID. We will fetch CRP based on this master_user.id        
        master_user = self._get_master_user(request)
        role_id = getattr(master_user, "role_id", None)

        # ----------------------------------
        # VUN-1: CASE 1 - Admin / Higher Roles
        # ----------------------------------
        if role_id in self.ALLOWED_ROLES:
            qs = MasterPanchayat.objects.all().only(
                'panchayat_id',
                'panchayat_name_en',
                'panchayat_name_local',
                'panchayat_code',
                'block_id',
                'district_id',
                'state_id',
            )

            rows = list(
                qs.values(
                    'panchayat_id',
                    'panchayat_name_en',
                    'panchayat_name_local',
                    'panchayat_code',
                    'block_id',
                    'district_id',
                    'state_id',
                )
            )

        # ----------------------------------
        # VUN-1: CASE 2 - CRP User
        # ----------------------------------
        else:
            # VUN-1: CRP Validtation | ONLY CRP whom the Panchayats are assigned to can view them            
            crp = CRPEP.objects.filter(
                master_user_id=master_user.id
            ).first()

            if not crp:
                raise PermissionDenied("User not authorized to access panchayats.")

            panchayat_ids = list(
                CRPEPToPanchayat.objects.filter(
                    crp_id=master_user.id,  
                    is_active=True
                ).values_list('allocated_panchayat_id', flat=True)
            )

            if not panchayat_ids:
                rows = []
            else:
                qs = MasterPanchayat.objects.filter(
                    panchayat_id__in=panchayat_ids
                ).only(
                    'panchayat_id',
                    'panchayat_name_en',
                    'panchayat_name_local',
                    'panchayat_code',
                    'block_id',
                    'district_id',
                    'state_id',
                )

                rows = list(
                    qs.values(
                        'panchayat_id',
                        'panchayat_name_en',
                        'panchayat_name_local',
                        'panchayat_code',
                        'block_id',
                        'district_id',
                        'state_id',
                    )
                )

        # -----------------------------
        # Filters
        # -----------------------------
        filter_map = {
            'block_id': 'block_id',
            'district_id': 'district_id',
            'state_id': 'state_id',
        }
        rows = _apply_list_filters(rows, filter_map, request.GET)

        # -----------------------------
        # Search
        # -----------------------------
        rows = _apply_list_search(
            rows,
            request.GET.get('search'),
            ['panchayat_name_en', 'panchayat_name_local', 'panchayat_code'],
        )

        # -----------------------------
        # Ordering
        # -----------------------------
        rows = _apply_list_ordering(
            rows,
            request.GET.get('ordering'),
            allowed_fields={'panchayat_id', 'panchayat_name_en'},
        )

        # -----------------------------
        # Grouping
        # -----------------------------
        grouped = _apply_list_group_by(rows, request.GET.get('group_by'))
        if grouped is not None:
            grouped = _apply_fields_projection_list(grouped, request.GET.get('fields'))
            return Response(grouped)

        # -----------------------------
        # Fields projection
        # -----------------------------
        fields_param = request.GET.get('fields')
        if fields_param:
            rows = _apply_fields_projection_list(rows, fields_param)
        else:
            rows = [
                {
                    'panchayat_id': r['panchayat_id'],
                    'panchayat_name_en': r['panchayat_name_en'],
                    'block_id': r['block_id'],
                    'district_id': r['district_id'],
                    'state_id': r['state_id'],
                }
                for r in rows
            ]

        result = _paginate_plain_list(request, rows)
        return Response(result)

# -------------------------------------------------------------------
# 4) epsakhi-list & epsakhi-detail helpers
# -------------------------------------------------------------------

class EpsakhiListByShgView(APIView):
    """
    GET /api/v1/epsakhi/epsakhi-list/<shg_code>/

    Lists selected fields of BeneficiaryRecorded for given lokos_shg_code.
    """
    permission_classes = (IsAuthenticated,)

    def get(self, request, shg_code):
        qs = BeneficiaryRecorded.objects.filter(lokos_shg_code=shg_code).order_by('-created_at')
        default_fields = [
            'lokos_member_code',
            'TH_urid',
            'age',
            'mobile',
            'lokos_shg_code',
            'enterprise_id',
        ]
        rows = list(qs.values(*default_fields))

        rows = _apply_list_search(rows, request.GET.get('search'), ['lokos_member_code', 'mobile'])
        rows = _apply_list_ordering(rows, request.GET.get('ordering'), {'age', 'TH_urid'})

        grouped = _apply_list_group_by(rows, request.GET.get('group_by'))
        if grouped is not None:
            grouped = _apply_fields_projection_list(grouped, request.GET.get('fields'))
            return Response(grouped)

        fields_param = request.GET.get('fields')
        if fields_param:
            rows = _apply_fields_projection_list(rows, fields_param)

        result = _paginate_plain_list(request, rows)
        return Response(result)

class EpsakhiDetailByMemberView(APIView):
    """
    GET /api/v1/epsakhi/enterprise-full/<lokos_member_code>/

    Returns COMPLETE enterprise form (Existing OR New) with ALL nested data.
    """
    permission_classes = (IsAuthenticated,)

    def get(self, request, member_code):
        # --------------------------------------------------
        # 1. Latest BeneficiaryRecorded
        # --------------------------------------------------
        br = (
            BeneficiaryRecorded.objects
            .filter(lokos_member_code=member_code, is_active=True)
            .order_by('-created_at')
            .first()
        )

        if not br:
            return Response(
                {"detail": "No beneficiary found for this lokos_member_code"},
                status=status.HTTP_404_NOT_FOUND,
            )

        enterprise_th = br.enterprise_id  # THIS IS TH_urid

        response = {
            "beneficiary": BeneficiaryRecordedSerializer(br).data,
            "enterprise_type": None,
            "enterprise": None,
            "existing_enterprise": None,
            "shared": {
                "enterprise_types": [],
                "enterprise_support": [],
                "mandatory_fund": [],
                "training": [],
            },
        }

        if not enterprise_th:
            return Response(response)

        # --------------------------------------------------
        # 2. EXISTING ENTERPRISE
        # --------------------------------------------------
        existing = ExistingEnterprise.objects.filter(
            TH_urid=enterprise_th,
            is_active=True
        ).first()

        if existing:
            response["enterprise_type"] = "existing"
            response["enterprise"] = ExistingEnterpriseSerializer(existing).data

            # ---- FK CHILD TABLES (use enterprise_id__id) ----
            licenses = EnterpriseLicenses.objects.filter(
                enterprise_id=existing.id, is_active=True
            )

            loans = EnterpriseLoanDetail.objects.filter(
                enterprise_id=existing.id, is_active=True
            )

            subsidies = EnterpriseSubsidyDetail.objects.filter(
                enterprise_id=existing.id, is_active=True
            )

            shop = EnterpriseShop.objects.filter(
                enterprise_id=existing.id, is_active=True
            ).first()

            shop_media = (
                ShopMedia.objects.filter(product_id=shop.id, is_active=True)
                if shop else []
            )

            products = EnterpriseProduct.objects.filter(
                enterprise_id=existing.id, is_active=True
            )

            product_data = []
            for p in products:
                pdata = EnterpriseProductSerializer(p).data
                pdata["product_media"] = ProductMediaSerializer(
                    ProductMedia.objects.filter(product_id=p.id, is_active=True),
                    many=True
                ).data
                product_data.append(pdata)

            enterprise_media = EnterpriseMedia.objects.filter(
                enterprise_id=existing.id, is_active=True
            )

            response["existing_enterprise"] = {
                "licenses": EnterpriseLicensesSerializer(licenses, many=True).data,
                "loan_details": EnterpriseLoanDetailSerializer(loans, many=True).data,
                "subsidy_details": EnterpriseSubsidyDetailSerializer(subsidies, many=True).data,
                "shop": EnterpriseShopSerializer(shop).data if shop else None,
                "shop_media": ShopMediaSerializer(shop_media, many=True).data,
                "products": product_data,
                "enterprise_media": EnterpriseMediaSerializer(enterprise_media, many=True).data,
            }

        else:
            # --------------------------------------------------
            # 3. NEW ENTERPRISE
            # --------------------------------------------------
            new_ent = NewEnterprise.objects.filter(
                TH_urid=enterprise_th,
                is_active=True
            ).first()

            if new_ent:
                response["enterprise_type"] = "new"
                response["enterprise"] = NewEnterpriseSerializer(new_ent).data

        # --------------------------------------------------
        # 4. SHARED TABLES (TH_urid based)
        # --------------------------------------------------
        response["shared"]["enterprise_types"] = EnterpriseTypeCategorySerializer(
            EnterpriseTypeCategory.objects.filter(
                enterprise_id=enterprise_th, is_active=True
            ),
            many=True
        ).data

        response["shared"]["enterprise_support"] = EnterpriseSupportSerializer(
            EnterpriseSupport.objects.filter(
                enterprise_id=enterprise_th, is_active=True
            ),
            many=True
        ).data

        response["shared"]["mandatory_fund"] = EnterpriseMandatoryFundSerializer(
            EnterpriseMandatoryFund.objects.filter(
                enterprise_id=enterprise_th, is_active=True
            ),
            many=True
        ).data

        # --------------------------------------------------
        # 5. TRAINING + CERTIFICATES
        # --------------------------------------------------
        trainings = EnterpriseTrainingReq.objects.filter(
            enterprise_id=enterprise_th, is_active=True
        )

        training_data = []
        for t in trainings:
            tdata = EnterpriseTrainingReqSerializer(t).data
            tdata["certificates"] = TrainingCertificatesSerializer(
                TrainingCertificates.objects.filter(
                    training_id=t.id, is_active=True
                ),
                many=True
            ).data
            training_data.append(tdata)

        response["shared"]["training"] = training_data

        return Response(response)

# CRP-Panchayat mapping Form Views (NEW)
class CRPPanchayatBulkViewSet(viewsets.GenericViewSet):
    """
    Bulk Linking of CRP to Multiple Panchayats
    """
    serializer_class = CRPPanchayatBulkSerializer
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        return CRPEPToPanchayat.objects.filter(is_active=True)

    # Added *args, **kwargs to adhere to DRF standard signature
    def create(self, request, *args, **kwargs):
        auth_user = request.user

        try:
            master_user = MasterUser.objects.get(
                username=auth_user.username
            )
        except MasterUser.DoesNotExist:
            raise PermissionDenied("Invalid user")

        # 🔐 ONLY recorder user allowed
        allowed_ids = {1, 2, 3, 4, 9, 12}

        if master_user.role_id not in allowed_ids:
            raise PermissionDenied(
                "Not Authorized. Only CRP Recorder can access this API."
            )

        serializer = self.get_serializer(
            data=request.data,
            context={"request": request}
        )

        # This will trigger the updated validate_crp_id method
        serializer.is_valid(raise_exception=True)

        rows = serializer.save()

        return Response(
            {
                "message": "CRP Panchayats linked successfully",
                "rows_created": len(rows),
            },
            status=status.HTTP_201_CREATED
        )

# EPSMS Dashboard APIs
class BulkPanchayatDelete(APIView):
    """
    Bulk Deletion of CRP-Panchayat Mappings
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = RemoveCRPPanchayatSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        crpep_id = serializer.validated_data["crpep_id"]
        panchayat_ids = serializer.validated_data["panchayat_ids"]
        deleted_by = serializer.validated_data["deleted_by"]

        try:
            crpep = CRPEP.objects.get(master_user=crpep_id)
        except CRPEP.DoesNotExist:
            return Response(
                {
                    "status": False,
                    "message": "CRP-EP not found."
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if not crpep.master_user:
            return Response(
                {
                    "status": False,
                    "message": "CRP-EP has no linked Master User."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        deleted_count = CRPEPToPanchayat.objects.filter(
            crp=crpep.master_user,
            allocated_panchayat_id__in=panchayat_ids,
            is_active=True,
        ).update(
            is_active=False,
            deleted_at=timezone.now(),
            deleted_by_id=deleted_by,
        )

        return Response(
            {
                "status": True,
                "message": f"{deleted_count} Panchayat allocation(s) removed successfully.",
                "deleted_count": deleted_count,
            },
            status=status.HTTP_200_OK,
        )