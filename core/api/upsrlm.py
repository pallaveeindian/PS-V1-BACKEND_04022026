# core/api/upsrlm.py

import logging
from typing import List, Dict, Any, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from django.conf import settings
from django.core.cache import cache
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page

from rest_framework import status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
# from core.upsrlm_sync import sync_clf_list, sync_clf_detail

logger = logging.getLogger(__name__)

# -------------------------------------------------------------------
# Config
# -------------------------------------------------------------------

def get_upsrlm_base():
    return getattr(
        settings,
        "UPSRLM_APISETU_BASE",
        "https://apisetu.gov.in/mord/lokos/srv/v1/up",
    )
    
UPSRLM_CACHE_TTL = getattr(settings, "CACHE_TTL", 300)

def get_apisetu_headers() -> Dict[str, str]:
    """
    Build headers required by APISetu UPSRLM LokOS endpoints.
    You MUST set these in your settings.py or environment:

        APISETU_CLIENT_ID = '...'
        APISETU_API_KEY = '...'
    """
    client_id = settings.APISETU_CLIENT_ID
    api_key = settings.APISETU_API_KEY

    if not client_id or not api_key:
        raise RuntimeError(
            "APISETU_CLIENT_ID / APISETU_API_KEY are not configured "
        )

    return {
        "X-APISETU-CLIENTID": client_id,
        "X-APISETU-APIKEY": api_key,
        # "scope": "lgd",
        "accept": "application/json",
    }


# -------------------------------------------------------------------
# Small helpers for query params & JSON manipulation
# -------------------------------------------------------------------

def parse_csv_param(value: Optional[str]) -> List[str]:
    if not value:
        return []
    return [v.strip() for v in str(value).split(",") if v.strip()]


def is_truthy(value: Optional[str]) -> bool:
    if value is None:
        return False
    return str(value).lower() in {"1", "true", "yes", "y", "on"}


class SimpleListPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 100


def _as_list(raw: Any) -> List[Dict[str, Any]]:
    """
    Normalize raw JSON from APISetu into a list[dict].
    APISetu usually returns either:
      - a list of dicts, OR
      - a single dict (detail), OR
      - sometimes {"data": [...]} style.
    """
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        # Common pattern: { "data": [...] }
        data = raw.get("data")
        if isinstance(data, list):
            return data
        # Fallback: treat dict as single record
        return [raw]
    return []


def filter_json_list(
    data: List[Dict[str, Any]],
    request,
    allowed_filters: Dict[str, str],
) -> List[Dict[str, Any]]:
    """
    allowed_filters: { query_param -> json_field_name }
    Uses equality match; multiple values via CSV.
    """
    for param, json_field in allowed_filters.items():
        raw_val = request.GET.get(param)
        if raw_val is None:
            continue

        values = parse_csv_param(raw_val)
        if not values:
            continue
        values_set = {str(v) for v in values}

        filtered = []
        for item in data:
            val = item.get(json_field)
            if val is None:
                continue
            if str(val) in values_set:
                filtered.append(item)
        data = filtered
    return data


def search_json_list(
    data: List[Dict[str, Any]],
    request,
    search_fields: List[str],
) -> List[Dict[str, Any]]:
    """
    Simple case-insensitive substring search on given JSON fields.
    """
    search_param = request.GET.get("search")
    if not search_param:
        return data

    tokens = parse_csv_param(search_param)
    if not tokens:
        return data

    def matches(item: Dict[str, Any]) -> bool:
        for tok in tokens:
            tok_lower = tok.lower()
            for field in search_fields:
                val = item.get(field)
                if val is None:
                    continue
                if tok_lower in str(val).lower():
                    return True
        return False

    return [item for item in data if matches(item)]


def order_json_list(
    data: List[Dict[str, Any]],
    request,
    allowed_ordering: Dict[str, str],
) -> List[Dict[str, Any]]:
    """
    allowed_ordering: { public_field_name -> json_field_name }
    ordering=? supports "-field" as usual.
    Only the first ordering key is used for simplicity (matches most use-cases).
    """
    order_param = request.GET.get("ordering")
    if not order_param:
        return data

    orderings = parse_csv_param(order_param)
    if not orderings:
        return data

    first = orderings[0]
    desc = first.startswith("-")
    field_name = first[1:] if desc else first

    if field_name not in allowed_ordering:
        return data

    json_field = allowed_ordering[field_name]

    try:
        return sorted(data, key=lambda x: x.get(json_field), reverse=desc)
    except Exception:
        # Don't break if sorting fails for some weird value combination
        logger.exception("Failed to sort UPSRLM data by %s", json_field)
        return data


def group_json_list(
    data: List[Dict[str, Any]],
    request,
    allowed_group_by: Dict[str, str],
) -> Optional[List[Dict[str, Any]]]:
    """
    allowed_group_by: { public_field_name -> json_field_name }
    Returns list of { group_fields..., count } or None if no grouping requested.
    """
    group_param = request.GET.get("group_by")
    if not group_param:
        return None

    groups = parse_csv_param(group_param)
    chosen = [g for g in groups if g in allowed_group_by]
    if not chosen:
        return None

    from collections import defaultdict

    counters = defaultdict(int)
    for item in data:
        key_vals = []
        for field_name in chosen:
            json_field = allowed_group_by[field_name]
            key_val = item.get(json_field)
            key_vals.append(key_val)
        counters[tuple(key_vals)] += 1

    results = []
    for key_tuple, count in counters.items():
        row = {field: key_tuple[idx] for idx, field in enumerate(chosen)}
        row["count"] = count
        results.append(row)

    # Stable ordering by group fields
    def sort_key(row):
        return tuple(str(row[f]) for f in chosen)

    results.sort(key=sort_key)
    return results


def project_fields_json_list(
    data: List[Dict[str, Any]],
    request,
) -> List[Dict[str, Any]]:
    """
    fields=field1,field2
    Only keep those keys for each item; silently ignore missing keys.
    """
    fields_param = request.GET.get("fields")
    if not fields_param:
        return data

    fields = parse_csv_param(fields_param)
    if not fields:
        return data

    projected = []
    for item in data:
        projected.append({k: item.get(k) for k in fields if k in item})
    return projected


# -------------------------------------------------------------------
# Base class for UPSRLM JSON list endpoints
# -------------------------------------------------------------------

class BaseUpsrlmView(APIView):
    """
    Base for all UPSRLM proxy endpoints:
      - Fetch from APISetu with proper headers.
      - Cache responses for TTL.
      - Provide pagination over Python lists.
    """

    # NOTE: individual views can override this (e.g. IsAuthenticated)
    permission_classes = (permissions.AllowAny,)
    pagination_class = SimpleListPagination
    cache_ttl = UPSRLM_CACHE_TTL

    def get_paginator(self) -> SimpleListPagination:
        if not hasattr(self, "_paginator"):
            self._paginator = self.pagination_class()
        return self._paginator

    def paginate_list(self, request, data: List[Dict[str, Any]]) -> Response:
        paginator = self.get_paginator()
        page = paginator.paginate_queryset(data, request, view=self)
        if page is not None:
            return paginator.get_paginated_response(page)
        return Response(data)

    def fetch_from_apisetu(
        self,
        cache_key: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """
        Fetch from UPSRLM+APISetu with caching + master_* sync.
        """
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        url = f"{get_upsrlm_base().rstrip('/')}/{path.lstrip('/')}"
        headers = get_apisetu_headers()

        # -------------------------------
        # NEW (SURGICAL): retries + backoff
        # -------------------------------
        session = requests.Session()

        retry = Retry(
            total=3,
            backoff_factor=1,               # 1s, 2s, 4s
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
            raise_on_status=False,
        )

        adapter = HTTPAdapter(max_retries=retry)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        # -------------------------------

        try:
            resp = session.get(
                url,
                headers=headers,
                params=params or {},
                timeout=(5, 60),   # connect timeout, read timeout
            )
        except requests.RequestException as exc:
            logger.exception("Error calling UPSRLM API (%s)", url)
            raise RuntimeError("Error calling UPSRLM APISetu gateway") from exc

        if resp.status_code != 200:
            logger.warning(
                "UPSRLM API non-200. url=%s status=%s body=%s",
                url,
                resp.status_code,
                resp.text[:500],
            )
            raise RuntimeError(f"UPSRLM API error {resp.status_code}")

        try:
            data = resp.json()
        except ValueError:
            raise RuntimeError("Invalid JSON from UPSRLM API")

        # # NEW: sync into master_* tables based on which endpoint this is
        # try:
        #     if path == "clf/block":
        #         block_id = (params or {}).get("block_id")
        #         if block_id is not None:
        #             sync_clf_list(int(block_id), data)
        #     elif path == "clf":
        #         sync_clf_detail(data)
        #     # you can later add VO sync here if you create VO master tables
        # except Exception:
        #     logger.exception("Failed to sync UPSRLM CLF data for path=%s params=%s", path, params)

        cache.set(cache_key, data, timeout=self.cache_ttl)
        return data


# ===================================================================
# 1. CLF list by block (upsrlm-clf-list/<block_id>)
# ===================================================================

@method_decorator(cache_page(UPSRLM_CACHE_TTL), name="get")
class UpsrlmClfListView(BaseUpsrlmView):
    """
    GET /api/v1/lookups/upsrlm-clf-list/<block_id>/

    - Fetches CLF list from UPSRLM LokOS:
        GET /clf/block?block_id=<block_id>
    - Caches the raw JSON.
    - Supports:
        * Pagination: page, page_size
        * Filters: isComplete, block_id, district_id
        * Search: block_id, district_id, clf_code, clf_name, nic_code
        * Ordering: formation_date, -formation_date
        * Grouping: isComplete, block_id, district_id
        * Fields projection: fields=field1,field2
    """

    # Map between query param names and JSON keys in APISetu response
    FILTERS = {
        "isComplete": "isComplete",
        "block_id": "blockId",
        "district_id": "districtId",
    }
    SEARCH_FIELDS = ["blockId", "districtId", "code", "name", "nicCode"]
    ORDERING = {
        "formation_date": "formationDate",
    }
    GROUP_BY = {
        "isComplete": "isComplete",
        "block_id": "blockId",
        "district_id": "districtId",
    }

    def get(self, request, block_id: Optional[int] = None):
        if not block_id:
            return Response(
                {"detail": "block_id path parameter is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cache_key = f"upsrlm:clf-list:{block_id}"
        try:
            raw = self.fetch_from_apisetu(
                cache_key, "clf/block", params={"block_id": block_id}
            )
        except RuntimeError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        data = _as_list(raw)

        # Pipeline: filters -> search -> ordering -> (optional group) -> fields -> pagination
        data = filter_json_list(data, request, self.FILTERS)
        data = search_json_list(data, request, self.SEARCH_FIELDS)
        data = order_json_list(data, request, self.ORDERING)

        grouped = group_json_list(data, request, self.GROUP_BY)
        if grouped is not None:
            grouped = project_fields_json_list(grouped, request)
            return Response(grouped)

        data = project_fields_json_list(data, request)
        return self.paginate_list(request, data)


# ===================================================================
# 2. CLF detail (core info) (upsrlm-clf-detail/<clf_code>)
# ===================================================================

@method_decorator(cache_page(UPSRLM_CACHE_TTL), name="get")
class UpsrlmClfDetailView(BaseUpsrlmView):
    """
    GET /api/v1/lookups/upsrlm-clf-detail/<clf_code>/

    - Fetches CLF detail from UPSRLM LokOS:
        GET /clf?clf_code=<clf_code>
    - The raw JSON is cached under a single key and re-used by:
        * UpsrlmClfVoListView
        * UpsrlmClfPanchayatListView
        * UpsrlmClfMembersView
    - This *detail* endpoint returns all top-level fields EXCEPT:
        "clf_panchayat_details", "clf_vo_details", "member_designations"

    Filters:
      - meeting_frequency
      - registration_act_name
      - pfms_verified

      (For district_id, block_id – applied on clf_addresses; we keep
       only addresses matching those, but do not drop the CLF itself.)

    Ordering:
      - registration_date, -registration_date

    Grouping:
      - meeting_frequency
      - district_id (derived from first address)
      - block_id (derived from first address)

    Fields projection & pagination work on the (single-element) list as well.
    """

    ORDERING = {"registration_date": "registration_date"}

    def _derive_primary_geo(self, clf: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enrich the CLF dict with primary_district_id / primary_block_id
        from first clf_addresses entry (if any).
        """
        addresses = clf.get("clf_addresses") or []
        if addresses and isinstance(addresses, list):
            first = addresses[0]
            clf.setdefault("primary_district_id", first.get("district_id"))
            clf.setdefault("primary_block_id", first.get("block_id"))
        return clf

    def get(self, request, clf_code: Optional[str] = None):
        if not clf_code:
            return Response(
                {"detail": "clf_code path parameter is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cache_key = f"upsrlm:clf-detail:{clf_code}"
        try:
            raw = self.fetch_from_apisetu(
                cache_key, "clf", params={"clf_code": clf_code}
            )
        except RuntimeError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        if not isinstance(raw, dict):
            return Response(
                {
                    "detail": "Unexpected CLF detail format from UPSRLM",
                    "raw": raw,
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        # Keep full raw CLF in cache (done in fetch_from_apisetu). Now prepare "core" view.
        core_clf = {
            k: v
            for k, v in raw.items()
            if k not in ("clf_panchayat_details", "clf_vo_details", "member_designations")
        }
        core_clf = self._derive_primary_geo(core_clf)

        # Apply top-level filters: if they don't match, return empty.
        def _matches_filters(rec: Dict[str, Any]) -> bool:
            mf = request.GET.get("meeting_frequency")
            if mf and str(rec.get("meeting_frequency")) != mf:
                return False
            ra = request.GET.get("registration_act_name")
            if ra and str(rec.get("registration_act_name")) != ra:
                return False
            pf = request.GET.get("pfms_verified")
            if pf is not None:
                # compare stringified values
                if str(rec.get("pfms_verified")) != str(pf):
                    return False
            # clf_addresses nested district/block filter: we *trim* addresses
            district_param = request.GET.get("district_id")
            block_param = request.GET.get("block_id")
            if district_param or block_param:
                addresses = rec.get("clf_addresses") or []
                filtered_addr = []
                for addr in addresses:
                    ok = True
                    if district_param and str(addr.get("district_id")) != str(district_param):
                        ok = False
                    if block_param and str(addr.get("block_id")) != str(block_param):
                        ok = False
                    if ok:
                        filtered_addr.append(addr)
                rec["clf_addresses"] = filtered_addr
            return True

        if not _matches_filters(core_clf):
            return Response([], status=status.HTTP_200_OK)

        # Ordering doesn't make much sense for a single element, but we support
        # registration_date ordering by returning [clf] unchanged.
        data = [core_clf]

        # Grouping: meeting_frequency, primary_district_id, primary_block_id
        allowed_group = {
            "meeting_frequency": "meeting_frequency",
            "district_id": "primary_district_id",
            "block_id": "primary_block_id",
        }
        grouped = group_json_list(data, request, allowed_group)
        if grouped is not None:
            grouped = project_fields_json_list(grouped, request)
            return Response(grouped)

        # Projection & pagination over a single-element list
        data = project_fields_json_list(data, request)
        return self.paginate_list(request, data)


# ===================================================================
# 3. CLF VO list (upsrlm-clf-vo/<clf_code>)
# ===================================================================

@method_decorator(cache_page(UPSRLM_CACHE_TTL), name="get")
class UpsrlmClfVoListView(BaseUpsrlmView):
    """
    GET /api/v1/lookups/upsrlm-clf-vo/<clf_code>/

    - Reads cached CLF detail (UpsrlmClfDetailView) and returns
      the "clf_vo_details" list.

    Pagination: page, page_size
    Search: vo_code, vo_name, vo_id
    Ordering: vo_formation_date, -vo_formation_date
    Fields projection: fields=...
    """

    SEARCH_FIELDS = ["vo_code", "vo_name", "vo_id"]
    ORDERING = {"vo_formation_date": "vo_formation_date"}

    def get(self, request, clf_code: Optional[str] = None):
        if not clf_code:
            return Response(
                {"detail": "clf_code path parameter is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cache_key = f"upsrlm:clf-detail:{clf_code}"
        try:
            raw = self.fetch_from_apisetu(
                cache_key, "clf", params={"clf_code": clf_code}
            )
        except RuntimeError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        if not isinstance(raw, dict):
            return Response(
                {"detail": "Unexpected CLF detail format for VO list"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        vo_list = raw.get("clf_vo_details") or []
        if not isinstance(vo_list, list):
            vo_list = _as_list(vo_list)

        data = search_json_list(vo_list, request, self.SEARCH_FIELDS)
        data = order_json_list(data, request, self.ORDERING)
        data = project_fields_json_list(data, request)
        return self.paginate_list(request, data)


# ===================================================================
# 4. Panchayats in CLF (upsrlm-panchayats-in-clf/<clf_code>)
# ===================================================================

@method_decorator(cache_page(UPSRLM_CACHE_TTL), name="get")
class UpsrlmClfPanchayatListView(BaseUpsrlmView):
    """
    GET /api/v1/lookups/upsrlm-panchayats-in-clf/<clf_code>/

    - Reads cached CLF detail and returns "clf_panchayat_details" list.

    Pagination: page, page_size
    Filters: panchayat_name, panchayat_id, panchayat_code
    Search: panchayat_name, panchayat_id, panchayat_code,
            village_code, village_id, village_name
    Custom param:
      - all_villages=1  -> returns a *flat* list of all villages across
                           all panchayats, with keys:
                           lgd_village, village_code, village_id, village_name
    Fields projection: fields=...
    """

    FILTERS = {
        "panchayat_name": "panchayat_name",
        "panchayat_id": "panchayat_id",
        "lgd_gp": "lgd_gp",
        "panchayat_code": "panchayat_code",
    }

    def _search_panchayats(self, data, request):
        search_param = request.GET.get("search")
        if not search_param:
            return data

        tokens = parse_csv_param(search_param)
        if not tokens:
            return data

        def matches(p):
            for tok in tokens:
                tl = tok.lower()
                # top-level panchayat fields
                for key in ("panchayat_name", "panchayat_id", "panchayat_code"):
                    val = p.get(key)
                    if val is not None and tl in str(val).lower():
                        return True
                # nested villages
                for v in p.get("villages") or []:
                    for key in ("village_code", "village_id", "village_name"):
                        val = v.get(key)
                        if val is not None and tl in str(val).lower():
                            return True
            return False

        return [p for p in data if matches(p)]

    def _flat_villages(self, panchayats: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen = set()
        villages = []
        for p in panchayats:
            for v in p.get("villages") or []:
                key = v.get("village_id") or v.get("village_code") or v.get("lgd_village")
                if key in seen:
                    continue
                seen.add(key)
                villages.append(
                    {
                        "lgd_village": v.get("lgd_village"),
                        "village_code": v.get("village_code"),
                        "village_id": v.get("village_id"),
                        "village_name": v.get("village_name"),
                    }
                )
        return villages

    def get(self, request, clf_code: Optional[str] = None):
        if not clf_code:
            return Response(
                {"detail": "clf_code path parameter is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cache_key = f"upsrlm:clf-detail:{clf_code}"
        try:
            raw = self.fetch_from_apisetu(
                cache_key, "clf", params={"clf_code": clf_code}
            )
        except RuntimeError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        if not isinstance(raw, dict):
            return Response(
                {"detail": "Unexpected CLF detail format for panchayats"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        panchayats = raw.get("clf_panchayat_details") or []
        if not isinstance(panchayats, list):
            panchayats = _as_list(panchayats)

        # Custom: all_villages=1
        if is_truthy(request.GET.get("all_villages")):
            flat = self._flat_villages(panchayats)
            flat = project_fields_json_list(flat, request)
            return self.paginate_list(request, flat)

        # Normal panchayat list
        data = filter_json_list(panchayats, request, self.FILTERS)
        data = self._search_panchayats(data, request)
        data = project_fields_json_list(data, request)
        return self.paginate_list(request, data)


# ===================================================================
# 5. CLF Members (upsrlm-clf-members/<clf_code>)
# ===================================================================

@method_decorator(cache_page(UPSRLM_CACHE_TTL), name="get")
class UpsrlmClfMembersView(BaseUpsrlmView):
    """
    GET /api/v1/lookups/upsrlm-clf-members/<clf_code>/

    - Reads cached CLF detail and returns "member_designations" list.

    Pagination: page, page_size
    Filters: is_signatory, designation
    Search: member_code, member_name
    Grouping: is_signatory, designation
    Fields projection: fields=...
    """

    FILTERS = {
        "is_signatory": "is_signatory",
        "designation": "designation",
    }
    SEARCH_FIELDS = ["member_code", "member_name"]
    GROUP_BY = {
        "is_signatory": "is_signatory",
        "designation": "designation",
    }

    def get(self, request, clf_code: Optional[str] = None):
        if not clf_code:
            return Response(
                {"detail": "clf_code path parameter is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cache_key = f"upsrlm:clf-detail:{clf_code}"
        try:
            raw = self.fetch_from_apisetu(
                cache_key, "clf", params={"clf_code": clf_code}
            )
        except RuntimeError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        if not isinstance(raw, dict):
            return Response(
                {"detail": "Unexpected CLF detail format for members"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        members = raw.get("member_designations") or []
        if not isinstance(members, list):
            members = _as_list(members)

        data = filter_json_list(members, request, self.FILTERS)
        data = search_json_list(data, request, self.SEARCH_FIELDS)

        grouped = group_json_list(data, request, self.GROUP_BY)
        if grouped is not None:
            grouped = project_fields_json_list(grouped, request)
            return Response(grouped)

        data = project_fields_json_list(data, request)
        return self.paginate_list(request, data)


# ===================================================================
# 6. VO List by block (upsrlm-vo-list/<block_id>)
# ===================================================================

@method_decorator(cache_page(UPSRLM_CACHE_TTL), name="get")
class UpsrlmVoListView(BaseUpsrlmView):
    """
    GET /api/v1/lookups/upsrlm-vo-list/<block_id>/

    - Fetches VO list from UPSRLM LokOS:
        GET /vo/block?block_id=<block_id>

    Pagination: page, page_size
    Filters: isComplete, block_id, district_id, panchayat_id
    Search: block_id, district_id, vo_code, vo_name, nic_code, panchayat_id
    Ordering: formation_date, -formation_date
    Grouping: isComplete, block_id, district_id, panchayat_id
    Fields projection: fields=...
    """

    FILTERS = {
        "isComplete": "isComplete",
        "block_id": "blockId",
        "district_id": "districtId",
        "panchayat_id": "panchayatId",
    }
    SEARCH_FIELDS = [
        "blockId",
        "districtId",
        "code",
        "name",
        "nicCode",
        "panchayatId",
    ]
    ORDERING = {"formation_date": "formationDate"}
    GROUP_BY = {
        "isComplete": "isComplete",
        "block_id": "blockId",
        "district_id": "districtId",
        "panchayat_id": "panchayatId",
    }

    def get(self, request, block_id: Optional[int] = None):
        if not block_id:
            return Response(
                {"detail": "block_id path parameter is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cache_key = f"upsrlm:vo-list:{block_id}"
        try:
            raw = self.fetch_from_apisetu(
                cache_key, "vo/block", params={"block_id": block_id}
            )
        except RuntimeError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        data = _as_list(raw)

        data = filter_json_list(data, request, self.FILTERS)
        data = search_json_list(data, request, self.SEARCH_FIELDS)
        data = order_json_list(data, request, self.ORDERING)

        grouped = group_json_list(data, request, self.GROUP_BY)
        if grouped is not None:
            grouped = project_fields_json_list(grouped, request)
            return Response(grouped)

        data = project_fields_json_list(data, request)
        return self.paginate_list(request, data)


# ===================================================================
# 7. VO detail (core info) (upsrlm-vo-detail/<vo_code>)
# ===================================================================

@method_decorator(cache_page(UPSRLM_CACHE_TTL), name="get")
class UpsrlmVoDetailView(BaseUpsrlmView):
    """
    GET /api/v1/lookups/upsrlm-vo-detail/<vo_code>/

    - Fetches VO detail from UPSRLM LokOS:
        GET /vo?vo_code=<vo_code>
    - Returns all fields EXCEPT "vo_shg_details" and "member_designations".

    Filters:
      - meeting_frequency
      - registration_act_name
      - pfms_verified
      - clf_code, clf_id, clf_name
      - district_id, block_id, panchayat_id (via vo_addresses)

    Ordering:
      - formation_date, -formation_date
      - registration_date, -registration_date

    Grouping:
      - meeting_frequency
      - registration_act_name
      - pfms_verified
      - clf_code, clf_id, clf_name
      - district_id, block_id, panchayat_id (derived from first vo_address)
    """

    ORDERING = {
        "formation_date": "formation_date",
        "registration_date": "registration_date",
    }

    def _derive_primary_geo(self, vo: Dict[str, Any]) -> Dict[str, Any]:
        addresses = vo.get("vo_addresses") or []
        if addresses and isinstance(addresses, list):
            first = addresses[0]
            vo.setdefault("primary_district_id", first.get("district_id"))
            vo.setdefault("primary_block_id", first.get("block_id"))
            vo.setdefault("primary_panchayat_id", first.get("panchayat_id"))
        return vo

    def get(self, request, vo_code: Optional[str] = None):
        if not vo_code:
            return Response(
                {"detail": "vo_code path parameter is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cache_key = f"upsrlm:vo-detail:{vo_code}"
        try:
            raw = self.fetch_from_apisetu(
                cache_key, "vo", params={"vo_code": vo_code}
            )
        except RuntimeError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        if not isinstance(raw, dict):
            return Response(
                {"detail": "Unexpected VO detail format from UPSRLM"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        core_vo = {
            k: v
            for k, v in raw.items()
            if k not in ("vo_shg_details", "member_designations")
        }
        core_vo = self._derive_primary_geo(core_vo)

        # Apply simple filters
        def _matches(rec: Dict[str, Any]) -> bool:
            # simple top-level
            for key in (
                "meeting_frequency",
                "registration_act_name",
                "pfms_verified",
                "clf_code",
                "clf_id",
                "clf_name",
            ):
                val = request.GET.get(key)
                if val is not None:
                    if str(rec.get(key)) != str(val):
                        return False

            # address-based district/block/panchayat
            district = request.GET.get("district_id")
            block = request.GET.get("block_id")
            panchayat = request.GET.get("panchayat_id")
            if any([district, block, panchayat]):
                addresses = rec.get("vo_addresses") or []
                filtered = []
                for addr in addresses:
                    ok = True
                    if district and str(addr.get("district_id")) != str(district):
                        ok = False
                    if block and str(addr.get("block_id")) != str(block):
                        ok = False
                    if panchayat and str(addr.get("panchayat_id")) != str(panchayat):
                        ok = False
                    if ok:
                        filtered.append(addr)
                rec["vo_addresses"] = filtered
            return True

        if not _matches(core_vo):
            return Response([], status=status.HTTP_200_OK)

        data = [core_vo]

        # Grouping
        allowed_group = {
            "meeting_frequency": "meeting_frequency",
            "registration_act_name": "registration_act_name",
            "pfms_verified": "pfms_verified",
            "clf_code": "clf_code",
            "clf_id": "clf_id",
            "clf_name": "clf_name",
            "district_id": "primary_district_id",
            "block_id": "primary_block_id",
            "panchayat_id": "primary_panchayat_id",
        }
        grouped = group_json_list(data, request, allowed_group)
        if grouped is not None:
            grouped = project_fields_json_list(grouped, request)
            return Response(grouped)

        # Ordering: only one record, so just ignore.
        data = project_fields_json_list(data, request)
        return self.paginate_list(request, data)


# ===================================================================
# 8. VO SHG list (upsrlm-vo-shg/<vo_code>)
# ===================================================================

@method_decorator(cache_page(UPSRLM_CACHE_TTL), name="get")
class UpsrlmVoShgListView(BaseUpsrlmView):
    """
    GET /api/v1/lookups/upsrlm-vo-shg/<vo_code>/

    - Reads cached VO detail and returns "vo_shg_details" list.

    Pagination: page, page_size
    Filters: special_shg, shg_type, social_category
    Search: shg_code, shg_name, nic_shg_code, shg_id
    Ordering: shg_formation_date, -shg_formation_date
    Fields projection: fields=...
    """

    FILTERS = {
        "special_shg": "special_shg",
        "shg_type": "shg_type",
        "social_category": "social_category",
    }
    SEARCH_FIELDS = ["shg_code", "shg_name", "nic_shg_code", "shg_id"]
    ORDERING = {"shg_formation_date": "shg_formation_date"}

    def get(self, request, vo_code: Optional[str] = None):
        if not vo_code:
            return Response(
                {"detail": "vo_code path parameter is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cache_key = f"upsrlm:vo-detail:{vo_code}"
        try:
            raw = self.fetch_from_apisetu(
                cache_key, "vo", params={"vo_code": vo_code}
            )
        except RuntimeError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        if not isinstance(raw, dict):
            return Response(
                {"detail": "Unexpected VO detail format for SHGs"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        shgs = raw.get("vo_shg_details") or []
        if not isinstance(shgs, list):
            shgs = _as_list(shgs)

        data = filter_json_list(shgs, request, self.FILTERS)
        data = search_json_list(data, request, self.SEARCH_FIELDS)
        data = order_json_list(data, request, self.ORDERING)
        data = project_fields_json_list(data, request)
        return self.paginate_list(request, data)


# ===================================================================
# 9. VO Members (upsrlm-vo-members/<vo_code>)
# ===================================================================

@method_decorator(cache_page(UPSRLM_CACHE_TTL), name="get")
class UpsrlmVoMembersView(BaseUpsrlmView):
    """
    GET /api/v1/lookups/upsrlm-vo-members/<vo_code>/

    - Reads cached VO detail and returns "member_designations" list.

    Pagination: page, page_size
    Filters: is_signatory, designation
    Search: member_code, member_name
    Grouping: is_signatory, designation
    Fields projection: fields=...
    """

    FILTERS = {
        "is_signatory": "is_signatory",
        "designation": "designation",
    }
    SEARCH_FIELDS = ["member_code", "member_name"]
    GROUP_BY = {
        "is_signatory": "is_signatory",
        "designation": "designation",
    }

    def get(self, request, vo_code: Optional[str] = None):
        if not vo_code:
            return Response(
                {"detail": "vo_code path parameter is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cache_key = f"upsrlm:vo-detail:{vo_code}"
        try:
            raw = self.fetch_from_apisetu(
                cache_key, "vo", params={"vo_code": vo_code}
            )
        except RuntimeError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        if not isinstance(raw, dict):
            return Response(
                {"detail": "Unexpected VO detail format for members"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        members = raw.get("member_designations") or []
        if not isinstance(members, list):
            members = _as_list(members)

        data = filter_json_list(members, request, self.FILTERS)
        data = search_json_list(data, request, self.SEARCH_FIELDS)

        grouped = group_json_list(data, request, self.GROUP_BY)
        if grouped is not None:
            grouped = project_fields_json_list(grouped, request)
            return Response(grouped)

        data = project_fields_json_list(data, request)
        return self.paginate_list(request, data)
