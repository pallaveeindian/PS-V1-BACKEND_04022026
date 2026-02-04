import logging
from typing import Dict, Any, List

from django.conf import settings
from django.core.cache import cache

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.utils.timezone import now

from core.models import MasterBlock, MasterVillage
from core.api.upsrlm import (
    UpsrlmVoListView,
    UpsrlmClfListView,
)
from epSakhi.api.views import _call_apisetu_shg_list

logger = logging.getLogger(__name__)
DISTRICT_ANALYTICS_CACHE_KEY = "analytics:district:{district_id}"
DISTRICT_ANALYTICS_TTL = 60 * 60 * 24  # 24 hours

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

# District data helper
def build_district_analytics(district_id: int) -> dict:
    blocks = (
        MasterBlock.objects
        .filter(district_id=district_id)
        .values("block_id", "block_name_en")
    )

    result = {
        "district_id": district_id,
        "blocks": [],
        "generated_at": now(),
    }

    for blk in blocks:
        block_id = blk["block_id"]
        bcache = cache.get(f"analytics:block:{block_id}")

        if not bcache:
            logger.warning(
                "Block cache missing for block_id=%s (district=%s)",
                block_id, district_id
            )
            continue

        totals = bcache.get("totals", {})

        result["blocks"].append({
            "block_id": block_id,
            "block_name": blk["block_name_en"],
            "total_vos": totals.get("total_vos", 0),
            "total_clfs": totals.get("total_clfs", 0),
            "total_shgs": totals.get("total_shgs", 0),
        })

    return result