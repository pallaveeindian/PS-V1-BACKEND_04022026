# epSakhi/api/views.py

import json
import csv
from io import StringIO
from collections import defaultdict

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from django.conf import settings
from django.core.cache import cache
from django.db import transaction, models
from django.db.models import Q
from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page

from rest_framework import viewsets, status, filters, generics
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import (
    MasterUser,
    MasterPanchayat,
    MasterBlock,
    MasterDistrict,
    MasterGeoUserScope,
)
from epSakhi.models import (
    CRPEP,
    CRPEPToPanchayat,
    BeneficiaryRecorded,
    ExistingEnterprise,
    NewEnterprise,
    EnterpriseLoanDetail,
    EnterpriseSubsidyDetail,   
    EnterpriseTrainingReq,
    EnterpriseMedia,
    EnterpriseProduct,         
    EnterpriseTypeCategory,    
    NoEnterpriseForm,          
    NoEnterpriseWage,          
)

from .serializers import (
    CRPEPSerializer,
    BeneficiaryRecordedSerializer,
    ExistingEnterpriseSerializer,
    NewEnterpriseSerializer,
    EnterpriseLoanDetailSerializer,
    EnterpriseSupportDetailSerializer,  
    EnterpriseTrainingReqSerializer,
    EnterpriseMediaSerializer,
    EnterpriseProductSerializer,        
    EnterpriseTypeCategorySerializer,   
    NoEnterpriseFormSerializer,         
    NoEnterpriseWageSerializer,         
)
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
        timeout=(5, 60)   # connect timeout, read timeout
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
        timeout=(5, 60)   # connect timeout, read timeout
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
            ['shg_name', 'shg_code', 'village_name'],
        )
        rows = _apply_list_ordering(
            rows,
            request.GET.get('ordering'),
            allowed_fields={'shg_name', 'shg_code'},
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
            vals = qs.values(*keys).order_by().annotate(count=models.Count('TH_urid'))
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

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.GET
        if params.get('district_id'):
            qs = qs.filter(district_id=int(params['district_id']))
        if params.get('block_id'):
            qs = qs.filter(block_id=int(params['block_id']))
        if params.get('panchayat_id'):
            qs = qs.filter(panchayat_id=int(params['panchayat_id']))
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

class BeneficiaryRecordedViewSet(viewsets.ModelViewSet, BaseProjectionMixin):
    queryset = BeneficiaryRecorded.objects.all().order_by('-created_at')
    serializer_class = BeneficiaryRecordedSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['applicant_name', 'lokos_member_code', 'mobile', 'email', 'enterprise_id']
    ordering_fields = ['age', 'created_at']

    def get_queryset(self):
        qs = BeneficiaryRecorded.objects.all().order_by('-created_at')
        params = self.request.GET
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

class EnterpriseLoanDetailViewSet(viewsets.ModelViewSet):
    """
    /api/v1/epsakhi/enterprise-loan-details/

    Query params:
      - enterprise_id=<TH_urid> (optional filter)
    """
    queryset = EnterpriseLoanDetail.objects.all().order_by('-created_at')
    serializer_class = EnterpriseLoanDetailSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['enterprise_id', 'institution_name']
    ordering_fields = ['created_at', 'loan_amount', 'date_taken']

    def get_queryset(self):
        qs = super().get_queryset()
        enterprise_id = self.request.query_params.get('enterprise_id')
        if enterprise_id:
            qs = qs.filter(enterprise_id=enterprise_id)
        form_type = self.request.query_params.get('form_type')
        if form_type:
            qs = qs.filter(form_type=form_type)
        return qs


class EnterpriseSupportDetailViewSet(viewsets.ModelViewSet):
    """
    /api/v1/epsakhi/enterprise-support-details/

    NOTE:
    - Backward-compatible name; works on EnterpriseSubsidyDetail model.
    - One enterprise can have MANY subsidy rows (epSakhi_exEpSubsidy).
    """
    queryset = EnterpriseSupportDetail.objects.all().order_by('-created_at')
    serializer_class = EnterpriseSupportDetailSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['enterprise_id', 'subsidy_type', 'subsidy_name']
    ordering_fields = ['created_at']

    def get_queryset(self):
        qs = super().get_queryset()
        enterprise_id = self.request.query_params.get('enterprise_id')
        if enterprise_id:
            qs = qs.filter(enterprise_id=enterprise_id)
        return qs


class EnterpriseTrainingReqViewSet(viewsets.ModelViewSet):
    """
    /api/v1/epsakhi/enterprise-training-reqs/
    """
    queryset = EnterpriseTrainingReq.objects.all().order_by('-created_at')
    serializer_class = EnterpriseTrainingReqSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['enterprise_id', 'training_module_name', 'sector', 'department']
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


class EnterpriseMediaViewSet(viewsets.ModelViewSet):
    """
    /api/v1/epsakhi/enterprise-media/
    """
    queryset = EnterpriseMedia.objects.all().order_by('-created_at')
    serializer_class = EnterpriseMediaSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['enterprise_id']
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


# -------------------------------------------------------------------
# NEW: EnterpriseProduct / EnterpriseType / NoEnterprise* CRUD APIs
# -------------------------------------------------------------------

class EnterpriseProductViewSet(viewsets.ModelViewSet):
    """
    /api/v1/epsakhi/enterprise-products/
    """
    queryset = EnterpriseProduct.objects.all().order_by('-created_at')
    serializer_class = EnterpriseProductSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = [
        'enterprise_id',
        'main_product_name',
        'activity_or_product_type',
        'marketing_strategy',
        'marketing_channels',
    ]
    ordering_fields = ['created_at', 'avg_monthly_sales']

    def get_queryset(self):
        qs = super().get_queryset()
        enterprise_id = self.request.query_params.get('enterprise_id')
        if enterprise_id:
            qs = qs.filter(enterprise_id=enterprise_id)
        return qs


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

@method_decorator(cache_page(CACHE_TTL), name='get')
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


@method_decorator(cache_page(CACHE_TTL), name='get')
class CRPDetailView(APIView):
    """
    GET /api/v1/epsakhi/crp-detail/<member_code>/
    member_code = lokos_member_code of CRP.
    """
    permission_classes = (IsAuthenticated,)

    def get(self, request, member_code):
        try:
            crp = CRPEP.objects.get(lokos_member_code=member_code)
        except CRPEP.DoesNotExist:
            return Response({'detail': 'CRP not found'}, status=status.HTTP_404_NOT_FOUND)

        data = CRPEPSerializer(crp).data
        fields_param = request.GET.get('fields')
        if fields_param:
            allowed = _parse_csv_param(fields_param)
            data = {k: v for k, v in data.items() if k in allowed}
        return Response(data)


@method_decorator(cache_page(CACHE_TTL), name='get')
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


@method_decorator(cache_page(CACHE_TTL), name='get')
class CRPPanchayatsUnderCrpView(APIView):
    """
    GET /api/v1/epsakhi/panchayats-under-crp/<member_code>/
    member_code = CRPEP.lokos_member_code
    """
    permission_classes = (IsAuthenticated,)

    def get(self, request, member_code):
        try:
            crp = CRPEP.objects.get(lokos_member_code=member_code)
        except CRPEP.DoesNotExist:
            return Response({'detail': 'CRP not found'}, status=status.HTTP_404_NOT_FOUND)

        panchayat_ids = list(
            CRPEPToPanchayat.objects.filter(crp=crp).values_list('allocated_panchayat_id', flat=True)
        )

        if not panchayat_ids:
            rows = []
        else:
            qs = MasterPanchayat.objects.filter(panchayat_id__in=panchayat_ids).only(
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

        # Filters
        filter_map = {
            'block_id': 'block_id',
            'district_id': 'district_id',
            'state_id': 'state_id',
        }
        rows = _apply_list_filters(rows, filter_map, request.GET)

        # Search
        rows = _apply_list_search(
            rows,
            request.GET.get('search'),
            ['panchayat_name_en', 'panchayat_name_local', 'panchayat_code'],
        )

        # Ordering
        rows = _apply_list_ordering(
            rows,
            request.GET.get('ordering'),
            allowed_fields={'panchayat_id', 'panchayat_name_en'},
        )

        # Grouping
        grouped = _apply_list_group_by(rows, request.GET.get('group_by'))
        if grouped is not None:
            grouped = _apply_fields_projection_list(grouped, request.GET.get('fields'))
            return Response(grouped)

        # Fields projection (default subset)
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


@method_decorator(cache_page(CACHE_TTL), name='get')
class CRPPanchayatsUnderCrpByID(APIView):
    """
    GET /api/v1/epsakhi/panchayats-under-crp/id/<id>/
    id = master_user.id
    """
    permission_classes = (IsAuthenticated,)

    def get(self, request, id):
        try:
            user_id = int(id)
        except ValueError:
            return Response({'detail': 'Invalid user id'}, status=status.HTTP_400_BAD_REQUEST)

        # Fetch panchayat mappings where crp_id == user_id (master_user_id semantics)
        panchayat_ids = list(
            CRPEPToPanchayat.objects.filter(
                crp_id=user_id
            ).values_list('allocated_panchayat_id', flat=True)
        )

        if not panchayat_ids:
            # Distinguish between "no such CRP user" vs "no mappings"
            if not CRPEP.objects.filter(master_user_id=user_id).exists():
                return Response(
                    {'detail': 'CRP not found for given ID'},
                    status=status.HTTP_404_NOT_FOUND,
                )
            rows = []
        else:
            qs = MasterPanchayat.objects.filter(panchayat_id__in=panchayat_ids).only(
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

        # Filters
        filter_map = {
            'block_id': 'block_id',
            'district_id': 'district_id',
            'state_id': 'state_id',
        }
        rows = _apply_list_filters(rows, filter_map, request.GET)

        # Search
        rows = _apply_list_search(
            rows,
            request.GET.get('search'),
            ['panchayat_name_en', 'panchayat_name_local', 'panchayat_code'],
        )

        # Ordering
        rows = _apply_list_ordering(
            rows,
            request.GET.get('ordering'),
            allowed_fields={'panchayat_id', 'panchayat_name_en'},
        )

        # Grouping
        grouped = _apply_list_group_by(rows, request.GET.get('group_by'))
        if grouped is not None:
            grouped = _apply_fields_projection_list(grouped, request.GET.get('fields'))
            return Response(grouped)

        # Fields projection (default subset)
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
    GET /api/v1/epsakhi/epsakhi-detail/<member_code>/

    Returns an aggregate of:
      - latest BeneficiaryRecorded (by created_at) for given lokos_member_code
      - linked enterprise (ExistingEnterprise/NewEnterprise)
      - linked NoEnterpriseForm (if any)
      - child detail tables

    Response:
        {
          "beneficiary": {.},
          "enterprise_type": "existing" | "new" | null,
          "enterprise": {.} | null,

          # children for Existing / New enterprise (when BeneficiaryRecorded.enterprise_id is set)
          "enterprise_loan_details": [.],        # EnterpriseLoanDetail (only if has_taken_loan is True for Existing)
          "enterprise_support_details": [.],     # EnterpriseSubsidyDetail (only if has_receieved_subsidy is True for Existing)
          "enterprise_training_reqs": [.],       # EnterpriseTrainingReq filtered by is_training_received / is_training_required
          "enterprise_media": [.],               # EnterpriseMedia filtered by form_type (ex/new)
          "enterprise_products": [.],            # EnterpriseProduct (existing + new)
          "enterprise_type_categories": [.],     # EnterpriseTypeCategory (form_type ex/new)

          # No-Enterprise flow (when a NoEnterpriseForm exists for this recorded beneficiary)
          "no_enterprise_form": {.} | null,              # NoEnterpriseForm
          "no_enterprise_training_reqs": [.],            # EnterpriseTrainingReq (enterprise_id = NoEnterpriseForm.TH_urid, form_type='req')
          "no_enterprise_wage_details": [.],             # NoEnterpriseWage (enterprise_id = NoEnterpriseForm.TH_urid)
        }

    Supports:
      - fields: comma-separated list of top-level keys to return
                (e.g. fields=beneficiary,enterprise).
    """
    permission_classes = (IsAuthenticated,)

    def get(self, request, member_code):
        # take latest recorded beneficiary for this member_code
        br = (
            BeneficiaryRecorded.objects.filter(lokos_member_code=member_code)
            .order_by('-created_at')
            .first()
        )
        if not br:
            return Response(
                {'detail': 'No recorded beneficiary found for given member_code'},
                status=status.HTTP_404_NOT_FOUND,
            )

        beneficiary_data = BeneficiaryRecordedSerializer(br).data
        eid = br.enterprise_id

        enterprise_type = None
        enterprise_data = None
        loan_data = []
        support_data = []
        training_data = []
        media_data = []
        product_data = []
        type_cat_data = []

        # ---------- Existing / New enterprise branch (via BeneficiaryRecorded.enterprise_id) ----------
        if eid:
            existing = ExistingEnterprise.objects.filter(TH_urid=eid).first()
            if existing:
                enterprise_type = 'existing'
                enterprise_data = ExistingEnterpriseSerializer(existing).data

                # Loan details: only if has_taken_loan is True
                if existing.has_taken_loan:
                    loans = EnterpriseLoanDetail.objects.filter(enterprise_id=eid)
                    loan_data = EnterpriseLoanDetailSerializer(loans, many=True).data

                # Subsidy (support) details: only if has_receieved_subsidy is True
                if existing.has_receieved_subsidy:
                    supports = EnterpriseSupportDetail.objects.filter(enterprise_id=eid)
                    support_data = EnterpriseSupportDetailSerializer(supports, many=True).data

                # Training requirements:
                #   - if is_training_received is False -> drop form_type="rec"
                #   - if is_training_required is False -> drop form_type="req"
                trainings_qs = EnterpriseTrainingReq.objects.filter(enterprise_id=eid)
                if not existing.is_training_received:
                    trainings_qs = trainings_qs.exclude(form_type='rec')
                if not existing.is_training_required:
                    trainings_qs = trainings_qs.exclude(form_type='req')
                training_data = EnterpriseTrainingReqSerializer(trainings_qs, many=True).data

                # Media: only for this existing enterprise (form_type="ex")
                medias = EnterpriseMedia.objects.filter(enterprise_id=eid, form_type='ex')
                media_data = EnterpriseMediaSerializer(medias, many=True).data

                # Products: all EnterpriseProduct linked via enterprise_id
                products = EnterpriseProduct.objects.filter(enterprise_id=eid)
                product_data = EnterpriseProductSerializer(products, many=True).data

                # Type categories: only for this existing enterprise (form_type="ex")
                type_qs = EnterpriseTypeCategory.objects.filter(enterprise_id=eid, form_type='ex')
                type_cat_data = EnterpriseTypeCategorySerializer(type_qs, many=True).data

            else:
                new_ent = NewEnterprise.objects.filter(TH_urid=eid).first()
                if new_ent:
                    enterprise_type = 'new'
                    enterprise_data = NewEnterpriseSerializer(new_ent).data

                    # For NewEnterprise, loan_amount is on main form; no separate LoanDetail.
                    # Training requirements:
                    trainings_qs = EnterpriseTrainingReq.objects.filter(enterprise_id=eid)
                    if not new_ent.is_training_received:
                        trainings_qs = trainings_qs.exclude(form_type='rec')
                    if not new_ent.is_training_required:
                        trainings_qs = trainings_qs.exclude(form_type='req')
                    training_data = EnterpriseTrainingReqSerializer(trainings_qs, many=True).data

                    # Media: only for this new enterprise (form_type="new")
                    medias = EnterpriseMedia.objects.filter(enterprise_id=eid, form_type='new')
                    media_data = EnterpriseMediaSerializer(medias, many=True).data

                    # Products: all EnterpriseProduct linked via enterprise_id
                    products = EnterpriseProduct.objects.filter(enterprise_id=eid)
                    product_data = EnterpriseProductSerializer(products, many=True).data

                    # Type categories: only for this new enterprise (form_type="new")
                    type_qs = EnterpriseTypeCategory.objects.filter(enterprise_id=eid, form_type='new')
                    type_cat_data = EnterpriseTypeCategorySerializer(type_qs, many=True).data

        # ---------- No-Enterprise branch (linked via recorded_benef_id) ----------
        no_ent_form = NoEnterpriseForm.objects.filter(recorded_benef_id=br.TH_urid).first()
        no_ent_data = None
        no_ent_training_data = []
        wage_data = []

        if no_ent_form:
            no_ent_data = NoEnterpriseFormSerializer(no_ent_form).data

            # Training requirements (NoEnterprise):
            #   - only when is_training_required is True
            #   - enterprise_id in EnterpriseTrainingReq = NoEnterpriseForm.TH_urid
            if no_ent_form.is_training_required:
                no_ent_treqs = EnterpriseTrainingReq.objects.filter(
                    enterprise_id=no_ent_form.TH_urid,
                    form_type='req',
                )
                no_ent_training_data = EnterpriseTrainingReqSerializer(no_ent_treqs, many=True).data

            # Wage preferences when reason is "Interested in Wage Employment"
            reason = (no_ent_form.no_int_reason or '').strip()
            if reason == 'Interested in Wage Employment':
                wages = NoEnterpriseWage.objects.filter(enterprise_id=no_ent_form.TH_urid)
                wage_data = NoEnterpriseWageSerializer(wages, many=True).data

        # ---------- Assemble response ----------
        response_obj = {
            'beneficiary': beneficiary_data,
            'enterprise_type': enterprise_type,
            'enterprise': enterprise_data,
            'enterprise_loan_details': loan_data,
            'enterprise_support_details': support_data,
            'enterprise_training_reqs': training_data,
            'enterprise_media': media_data,
            'enterprise_products': product_data,
            'enterprise_type_categories': type_cat_data,
            'no_enterprise_form': no_ent_data,
            'no_enterprise_training_reqs': no_ent_training_data,
            'no_enterprise_wage_details': wage_data,
        }

        # Optional top-level field projection
        fields_param = request.GET.get('fields')
        if fields_param:
            allowed_keys = _parse_csv_param(fields_param)
            response_obj = {k: v for k, v in response_obj.items() if k in allowed_keys}

        return Response(response_obj)
