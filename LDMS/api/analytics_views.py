# LDMS/api/analytics_views.py

import logging
from typing import Dict, Any, List

from django.utils.timezone import now
from django.db.models import Sum

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from core.models import MasterBlock, MasterDistrict, MasterVillage
from LDMS.models import (
    Block_Analytics,
    District_Analytics,
    State_Analytics,
)
from core.api.upsrlm import (
    UpsrlmVoListView,
    UpsrlmClfListView,
)
from epSakhi.api.views import _call_apisetu_shg_list

logger = logging.getLogger(__name__)

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
# Analytics API (DB SOURCE OF TRUTH)
# ==================================================================

class UpsrlmAnalyticsView(APIView):
    """
    GET /api/v1/analytics/upsrlm/

    Query Params:
      - block_id=<int>
      - district_id=<int>
      - districts_total=true
      - state_total=true
      - detail=true|false

    RULES:
    - API NEVER rebuilds analytics
    - API uses DB as source of truth
    - APISetu is called ONLY for block+detail
    """

    permission_classes = []

    # ------------------------------------------------------------------
    # Entry
    # ------------------------------------------------------------------

    def get(self, request):
        block_id = request.GET.get("block_id")
        district_id = request.GET.get("district_id")
        districts_total = request.GET.get("districts_total")
        state_total = request.GET.get("state_total")
        detail = str(request.GET.get("detail", "")).lower() in {"1", "true", "yes"}

        if state_total is not None:
            return self._state_total()

        if districts_total is not None:
            return self._districts_total()

        if not block_id and not district_id:
            return Response(
                {"detail": "block_id or district_id is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if block_id:
            return self._block_analytics(int(block_id), detail)

        # ✅ NEW BEHAVIOR
        if district_id and detail:
            return self._district_blocks_detail(int(district_id))

        return self._district_analytics(int(district_id))

    # ------------------------------------------------------------------
    # BLOCK ANALYTICS
    # ------------------------------------------------------------------

    def _block_analytics(self, block_id: int, detail: bool):
        if not detail:
            try:
                block = Block_Analytics.objects.select_related("block").get(
                    block_id=block_id,
                    is_active=True,
                )
            except Block_Analytics.DoesNotExist:
                return Response(
                    {"detail": "Block analytics not ready"},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )

            return Response({
                "block_id": block.block.block_id,
                "block_name": block.block.block_name_en,
                "total_vos": block.total_vos,
                "total_clfs": block.total_clfs,
                "total_shgs": block.total_shgs,
                "total_rural_hh": block.total_rural_hh,
                "total_hh_under_shgs": block.total_hh_under_shgs,
                "updated_at": block.updated_at,
            })

        # DETAIL MODE → APISETU
        try:
            vo_raw = UpsrlmVoListView().fetch_from_apisetu(
                f"analytics:vo:{block_id}",
                "vo/block",
                {"block_id": block_id},
            )
            shg_raw = _call_apisetu_shg_list(block_id)
        except Exception:
            logger.exception("Village analytics failed for block %s", block_id)
            return Response(
                {"detail": "Village analytics unavailable"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response({
            "block_id": block_id,
            "generated_at": now(),
            "village_wise": self._village_wise(
                block_id,
                _normalize_list(vo_raw),
                _normalize_list(shg_raw),
            ),
        })

    # ------------------------------------------------------------------
    # ✅ DISTRICT → BLOCK DETAIL (NEW)
    # ------------------------------------------------------------------

    def _district_blocks_detail(self, district_id: int):
        try:
            district = MasterDistrict.objects.get(district_id=district_id)
        except MasterDistrict.DoesNotExist:
            return Response(
                {"detail": "District not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        blocks = (
            Block_Analytics.objects
            .filter(block__district_id=district_id, is_active=True)
            .select_related("block")
            .order_by("block__block_name_en")
        )

        if not blocks.exists():
            return Response(
                {"detail": "Block analytics not ready for district"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        data = []
        for b in blocks:
            data.append({
                "block_id": b.block.block_id,
                "block_name": b.block.block_name_en,
                "total_vos": b.total_vos,
                "total_clfs": b.total_clfs,
                "total_shgs": b.total_shgs,
                "total_rural_hh": b.total_rural_hh,
                "total_hh_under_shgs": b.total_hh_under_shgs,
                "updated_at": b.updated_at,
            })

        return Response({
            "district_id": district.district_id,
            "district_name": district.district_name_en,
            "generated_at": now(),
            "block_count": len(data),
            "blocks": data,
        })

    # ------------------------------------------------------------------
    # DISTRICT SUMMARY
    # ------------------------------------------------------------------

    def _district_analytics(self, district_id: int):
        try:
            district = District_Analytics.objects.select_related("district").get(
                district_id=district_id,
                is_active=True,
            )
        except District_Analytics.DoesNotExist:
            return Response(
                {"detail": "District analytics not ready"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response({
            "district_id": district.district.district_id,
            "district_name": district.district.district_name_en,
            "total_vos": district.total_vos,
            "total_clfs": district.total_clfs,
            "total_shgs": district.total_shgs,
            "total_rural_hh": district.total_rural_hh,
            "total_hh_under_shgs": district.total_hh_under_shgs,
            "updated_at": district.updated_at,
        })

    # ------------------------------------------------------------------
    # ALL DISTRICTS TOTAL
    # ------------------------------------------------------------------

    def _districts_total(self):
        qs = District_Analytics.objects.filter(is_active=True)

        if not qs.exists():
            return Response(
                {"detail": "District analytics not ready"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response({
            "generated_at": now(),
            "district_count": qs.count(),
            "districts": [
                {
                    "district_id": d.district.district_id,
                    "district_name": d.district.district_name_en,
                    "total_vos": d.total_vos,
                    "total_clfs": d.total_clfs,
                    "total_shgs": d.total_shgs,
                    "total_rural_hh": d.total_rural_hh,
                    "total_hh_under_shgs": d.total_hh_under_shgs,
                }
                for d in qs.select_related("district")
            ],
        })

    # ------------------------------------------------------------------
    # STATE TOTAL
    # ------------------------------------------------------------------

    def _state_total(self):
        try:
            state = State_Analytics.objects.filter(is_active=True).latest("updated_at")
        except State_Analytics.DoesNotExist:
            return Response(
                {"detail": "State analytics not ready"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response({
            "generated_at": state.updated_at,
            "state": {
                "total_vos": state.total_vos,
                "total_clfs": state.total_clfs,
                "total_shgs": state.total_shgs,
                "total_rural_hh": state.total_rural_hh,
                "total_hh_under_shgs": state.total_hh_under_shgs,
            },
        })

    # ------------------------------------------------------------------
    # VILLAGE ANALYTICS (DERIVED)
    # ------------------------------------------------------------------

    def _village_wise(
        self,
        block_id: int,
        vo_list: List[Dict],
        shg_list: List[Dict],
    ):
        """
        Village analytics are derived on-demand
        using APISetu VO + SHG data.
        """

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
                .values(
                    "village_id",
                    "village_name_english",
                    "village_name_local",
                )
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
                village_stats[vid]["village_name"] = (
                    v["village_name_english"] or v["village_name_local"]
                )

        if not village_stats:
            return []

        return list(village_stats.values())

