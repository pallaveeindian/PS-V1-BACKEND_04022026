# LDMS/api/analytics_views.py

import logging
from typing import Dict, Any, List

from django.conf import settings
from django.core.cache import cache

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.utils.timezone import now

from core.models import MasterBlock, MasterVillage, MasterDistrict
from core.api.upsrlm import (
    UpsrlmVoListView,
    UpsrlmClfListView,
)
from epSakhi.api.views import _call_apisetu_shg_list
from .district_analytic_helper import build_district_analytics

logger = logging.getLogger(__name__)

# Cache Keys and TTLs
DISTRICT_ANALYTICS_CACHE_KEY = "analytics:district:{district_id}"
DISTRICT_ANALYTICS_TTL = 60 * 60 * 24  # 24 hours

DISTRICTS_TOTAL_CACHE_KEY = "analytics:districts:total"
DISTRICTS_TOTAL_TTL = 60 * 60 * 24  # 24 hours

STATE_TOTAL_CACHE_KEY = "analytics:state:total"
STATE_TOTAL_TTL = 60 * 60 * 24  # 24 hours

STATE_CODE = "UP"
STATE_NAME = "UTTAR PRADESH"

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _normalize_list(raw):
    """
    Normalize APISetu responses to list[dict]
    """
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        return raw.get("data") or raw.get("shg_list") or raw.get("shgList") or []
    return []

# def build_all_district_totals_from_cache():
#     """
#     Builds totals for ALL districts by summing
#     block-level totals from cached district analytics.
#     """

#     districts = (
#         MasterDistrict.objects
#         .all()
#         .values("district_id", "district_name_en")
#     )

#     results = []

#     for d in districts:
#         district_id = d["district_id"]
#         cache_key = f"analytics:district:{district_id}"

#         cached = cache.get(cache_key)
#         if not cached:
#             # build & cache if missing
#             cached = build_district_analytics(district_id)
#             cache.set(
#                 cache_key,
#                 cached,
#                 timeout=DISTRICT_ANALYTICS_TTL,
#             )

#         blocks = cached.get("blocks", [])

#         total_vos = 0
#         total_clfs = 0
#         total_shgs = 0

#         for b in blocks:
#             total_vos += int(b.get("total_vos", 0))
#             total_clfs += int(b.get("total_clfs", 0))
#             total_shgs += int(b.get("total_shgs", 0))

#         results.append({
#             "district_id": district_id,
#             "district_name": d["district_name_en"],
#             "total_vos": total_vos,
#             "total_clfs": total_clfs,
#             "total_shgs": total_shgs,
#         })

#     return {
#         "generated_at": now(),
#         "districts": results,
#     }
    
# def build_state_totals_from_cache():
#     """
#     Build state-level grand totals by summing
#     cached district analytics (blocks[]).
#     """

#     districts = (
#         MasterDistrict.objects
#         .all()
#         .values("district_id")
#     )

#     state_total_vos = 0
#     state_total_clfs = 0
#     state_total_shgs = 0

#     for d in districts:
#         district_id = d["district_id"]
#         cache_key = f"analytics:district:{district_id}"

#         cached = cache.get(cache_key)
#         if not cached:
#             cached = build_district_analytics(district_id)
#             cache.set(
#                 cache_key,
#                 cached,
#                 timeout=DISTRICT_ANALYTICS_TTL,
#             )

#         blocks = cached.get("blocks", [])

#         for b in blocks:
#             state_total_vos += int(b.get("total_vos", 0))
#             state_total_clfs += int(b.get("total_clfs", 0))
#             state_total_shgs += int(b.get("total_shgs", 0))

#     return {
#         "generated_at": now(),
#         "state": {
#             "state_code": STATE_CODE,
#             "state_name": STATE_NAME,
#             "total_vos": state_total_vos,
#             "total_clfs": state_total_clfs,
#             "total_shgs": state_total_shgs,
#         },
#     }    
    
def build_block_analytics(block_id: int) -> Dict[str, Any]:
    """
    Build block analytics (NO village data).
    Intended for batch jobs / systemd timers.
    """

    block = MasterBlock.objects.get(block_id=block_id)

    vo_raw = UpsrlmVoListView().fetch_from_apisetu(
        f"analytics:vo:{block_id}",
        "vo/block",
        {"block_id": block_id},
    )
    clf_raw = UpsrlmClfListView().fetch_from_apisetu(
        f"analytics:clf:{block_id}",
        "clf/block",
        {"block_id": block_id},
    )
    shg_raw = _call_apisetu_shg_list(block_id)

    vo_list = _normalize_list(vo_raw)
    clf_list = _normalize_list(clf_raw)
    shg_list = _normalize_list(shg_raw)

    return {
        "block_id": block_id,
        "block_name": block.block_name_en,
        "totals": {
            "total_vos": len(vo_list),
            "total_clfs": len(clf_list),
            "total_shgs": len(shg_list),
        },
        "generated_at": now(),
    }
        
# ==================================================================
# Analytics API
# ==================================================================

class UpsrlmAnalyticsView(APIView):
    """
    GET /api/v1/analytics/upsrlm/

    Query Params:
      - block_id=<int>
      - district_id=<int>
      - detail=true|false

    Rules:
      - Either block_id OR district_id is required
      - detail=true works only with block_id
    """

    permission_classes = []  # internal / dashboard use

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def get(self, request):
        district_id = request.GET.get("district_id")
        block_id = request.GET.get("block_id")
        districts_total = request.GET.get("districts_total")
        state_total = request.GET.get("state_total")
        detail = str(request.GET.get("detail", "")).lower() in {"1", "true", "yes"}

        # ------------------------------------------------
        # STATE GRAND TOTAL
        # ------------------------------------------------
        if state_total is not None:
            cached = cache.get(STATE_TOTAL_CACHE_KEY)
            if cached:
                return Response(cached)
            if not cached:
                return Response(
                    {"detail": "State Analytics cache not ready"},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )
            return Response(cached)

        # ------------------------------------------------
        # ALL DISTRICTS TOTAL
        # ------------------------------------------------
        if districts_total is not None:
            cached = cache.get(DISTRICTS_TOTAL_CACHE_KEY)
            if cached:
                return Response(cached)
            if not cached:
                return Response(
                    {"detail": "Districts Analytics cache not ready"},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )
            return Response(cached)

        # ------------------------------------------------
        # VALIDATION
        # ------------------------------------------------
        if not block_id and not district_id:
            return Response(
                {"detail": "block_id or district_id is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if block_id:
            return self._block_analytics(int(block_id), detail)

        return self._district_analytics(int(district_id))

    # ------------------------------------------------------------------
    # DISTRICT LEVEL ANALYTICS
    # ------------------------------------------------------------------

    def _district_analytics(self, district_id: int):
        cache_key = f"analytics:district:{district_id}"

        cached = cache.get(cache_key)
        if cached:
            return Response(cached)

        return Response(
            {"detail": "District analytics cache not ready"},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    

    # ------------------------------------------------------------------
    # BLOCK LEVEL ANALYTICS (CACHED)
    # ------------------------------------------------------------------

    def _block_analytics(self, block_id: int, detail: bool):
        cache_key = f"analytics:block:{block_id}"

        # --------------------------------------------
        # DETAIL = TRUE → NO CACHE (ALWAYS FRESH)
        # --------------------------------------------
        if detail:
            try:
                response = build_block_analytics(block_id)
            except MasterBlock.DoesNotExist:
                return Response(
                    {"detail": f"Block {block_id} not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            vo_list = _normalize_list(
                UpsrlmVoListView().fetch_from_apisetu(
                    f"analytics:vo:{block_id}",
                    "vo/block",
                    {"block_id": block_id},
                )
            )

            shg_list = _normalize_list(
                _call_apisetu_shg_list(block_id)
            )

            response["village_wise"] = self._village_wise(
                block_id,
                vo_list,
                shg_list,
            )

            return Response(response)

        # --------------------------------------------
        # SUMMARY ONLY → CACHED
        # --------------------------------------------
        cached = cache.get(cache_key)
        if cached:
            return Response(cached)

        return Response(
            {"detail": "Block analytics cache not ready"},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    # ------------------------------------------------------------------
    # VILLAGE LEVEL ANALYTICS (CACHED)
    # ------------------------------------------------------------------

    def _village_wise(
        self,
        block_id: int,
        vo_list: List[Dict],
        shg_list: List[Dict],
    ):
        cache_key = f"analytics:village:block:{block_id}"

        cached = cache.get(cache_key)
        if cached:
            return cached

        village_stats: Dict[int, Dict[str, Any]] = {}

        # ------------------------------------
        # 1. SHG → Village mapping
        # ------------------------------------
        for shg in shg_list:
            village_id = shg.get("villageId")
            if not village_id:
                continue

            village_stats.setdefault(
                village_id,
                {
                    "village_id": village_id,
                    "village_name": None,
                    "total_shgs": 0,
                    "total_vos": 0,
                },
            )
            village_stats[village_id]["total_shgs"] += 1

        # ------------------------------------
        # 2. VO → Panchayat → Villages
        # ------------------------------------
        panchayat_ids = {
            vo.get("panchayatId")
            for vo in vo_list
            if vo.get("panchayatId")
        }

        if panchayat_ids:
            villages = (
                MasterVillage.objects
                .filter(
                    block_id=block_id,
                    panchayat_id__in=panchayat_ids,
                )
                .values("village_id")
            )

            for v in villages:
                vid = v["village_id"]
                village_stats.setdefault(
                    vid,
                    {
                        "village_id": vid,
                        "village_name": None,
                        "total_shgs": 0,
                        "total_vos": 0,
                    },
                )
                village_stats[vid]["total_vos"] += 1

        if not village_stats:
            return []

        # ------------------------------------
        # 3. Fetch village names (single query)
        # ------------------------------------
        village_names = {
            v.village_id: (v.village_name_english or v.village_name_local)
            for v in MasterVillage.objects.filter(
                village_id__in=village_stats.keys()
            )
        }

        for vid, stats in village_stats.items():
            stats["village_name"] = village_names.get(vid)

        result = list(village_stats.values())

        cache.set(
            cache_key,
            result,
            timeout=60 * 60 * 24,
        )

        return result
