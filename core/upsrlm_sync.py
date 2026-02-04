# core/upsrlm_sync.py

import os
import logging
from datetime import datetime

from django.conf import settings
from django.db import transaction

from core.models import (
    MasterState,
    MasterDistrict,
    MasterBlock,
    MasterPanchayat,
    MasterVillage,
    MasterShgList,
    MasterShgAddresses,
    MasterShgBanks,
    MasterShgPhone,
    MasterBeneficiary,
    MasterBeneficiaryAddress,
    MasterBeneficiaryBank,
    MasterBeneficiaryDesignation,
    MasterBeneficiaryPhone,
    MasterClfList,
    MasterClfAddresses,
    MasterClfBanks,
    MasterClfPhones,
    MasterClfVoDetails,
    MasterMembersUnderClf,
    MasterPanchayatsUnderClf,
    MasterVillagesUnderClf,
)

logger = logging.getLogger(__name__)

UPSRLM_IMPORT_LOG_DIR = getattr(
    settings,
    "UPSRLM_IMPORT_LOG_DIR",
    os.path.join(getattr(settings, "BASE_DIR", "."), "upsrlm_import_logs"),
)


def _ensure_log_dir():
    os.makedirs(UPSRLM_IMPORT_LOG_DIR, exist_ok=True)


def _append_log(filename: str, code: str):
    """
    Append a single code to a per-block log file, with timestamp.
    Used only when a row is CREATED (not updated).
    """
    _ensure_log_dir()
    path = os.path.join(UPSRLM_IMPORT_LOG_DIR, filename)
    try:
        with open(path, "a", encoding="utf-8") as f:
            ts = datetime.utcnow().isoformat()
            f.write(f"{ts}\t{code}\n")
    except Exception:
        logger.exception("Failed to append to UPSRLM import log %s", path)


def _parse_date(value):
    """
    Handle 'YYYY-MM-DD' or empty/null gracefully.
    """
    if not value:
        return None
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def _parse_datetime(value):
    """
    Handle 'YYYY-MM-DD' or 'YYYY-MM-DD HH:MM:SS' or empty/null gracefully.
    """
    if not value:
        return None
    text = str(value).strip()
    # Try full datetime first
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(text[:len(fmt)], fmt)
            return dt
        except Exception:
            continue
    return None


def _get_state(state_id):
    if not state_id:
        return None
    try:
        return MasterState.objects.get(pk=int(state_id))
    except Exception:
        return None


def _get_district(district_id):
    if not district_id:
        return None
    try:
        return MasterDistrict.objects.get(pk=int(district_id))
    except Exception:
        return None


def _get_block(block_id):
    if not block_id:
        return None
    try:
        return MasterBlock.objects.get(pk=int(block_id))
    except Exception:
        return None


def _get_panchayat(panchayat_id):
    if not panchayat_id:
        return None
    try:
        return MasterPanchayat.objects.get(pk=int(panchayat_id))
    except Exception:
        return None


def _get_village(village_id):
    if not village_id:
        return None
    try:
        return MasterVillage.objects.get(pk=int(village_id))
    except Exception:
        return None


def _ensure_list(raw):
    """
    Normalize raw JSON into list[dict] for list APIs.
    """
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        data = raw.get("data")
        if isinstance(data, list):
            return data
        return [raw]
    return []


# -------------------------------------------------------------------
# SHG LIST (shg/block?block_id=...)
# -------------------------------------------------------------------

@transaction.atomic
def sync_shg_list(block_id: int, raw_json):
    """
    Import / upsert SHG list into MasterShgList for a given block.

    raw_json is the JSON returned by:
        GET /shg/block?block_id=<block_id>
    which is typically a list of SHG dicts.
    """
    try:
        items = _ensure_list(raw_json)
        log_file = f"shg_list_{block_id}.log"

        for item in items:
            shg_code = item.get("code") or item.get("shg_code")
            if not shg_code:
                continue

            state_id = item.get("stateId")
            district_id = item.get("districtId")
            block_id_item = item.get("blockId") or block_id
            panchayat_id = item.get("panchayatId")
            village_id = item.get("villageId")

            defaults = {
                "name": item.get("name") or item.get("shgNameLocal"),
                "nic_code": item.get("nicCode"),
                "formation_date": _parse_date(item.get("formationDate")),
                "is_complete": int(item.get("isComplete")) if item.get("isComplete") not in (None, "") else None,
                "pfms_verified": int(item.get("pfmsVerified")) if item.get("pfmsVerified") not in (None, "") else None,
                "meeting_frequency": None,  # from detail API usually
                "latitude": None,
                "longitude": None,
                "created_by": None,
                "created_date": None,
                "updated_by": None,
                "updated_date": None,
                "is_active": 1,
                "state": _get_state(state_id),
                "district": _get_district(district_id),
                "block": _get_block(block_id_item),
                "panchayat": _get_panchayat(panchayat_id),
                "village": _get_village(village_id),
            }

            obj, created = MasterShgList.objects.update_or_create(
                shg_code=shg_code,
                defaults=defaults,
            )
            if created:
                _append_log(log_file, shg_code)

    except Exception:
        logger.exception("Error syncing SHG list for block_id=%s", block_id)


# -------------------------------------------------------------------
# SHG DETAIL (shg?shg_code=...)
# -------------------------------------------------------------------

@transaction.atomic
def sync_shg_detail(shg_json: dict):
    """
    Import/update:
      - MasterShgList
      - MasterShgAddresses
      - MasterShgBanks
      - MasterShgPhone
      - MasterBeneficiary + address/bank/designation/phone

    shg_json is the object returned by:
        GET /shg?shg_code=<shg_code>
    """
    if not isinstance(shg_json, dict):
        return

    shg_code = shg_json.get("shg_code") or shg_json.get("shgCode") or shg_json.get("code")
    if not shg_code:
        return

    # derive block_id from first address for logging
    addr0 = None
    shg_addresses = shg_json.get("shg_addresses") or []
    if shg_addresses:
        addr0 = shg_addresses[0]
    block_id = None
    if addr0:
        block_id = addr0.get("block_id") or addr0.get("blockId")

    log_file = f"shg_detail_{block_id}.log" if block_id else "shg_detail_unknown.log"

    # ---- MasterShgList (enriched) ----
    state_id = addr0.get("state_id") if addr0 else None
    district_id = addr0.get("district_id") if addr0 else None
    block_id_addr = addr0.get("block_id") if addr0 else None
    panchayat_id = addr0.get("panchayat_id") if addr0 else None
    village_id = addr0.get("village_id") if addr0 else None

    defaults = {
        "name": shg_json.get("shg_name"),
        "nic_code": shg_json.get("nic_shg_code"),
        "formation_date": _parse_date(shg_json.get("formation_date")),
        "is_complete": int(shg_json.get("is_complete")) if shg_json.get("is_complete") not in (None, "") else None,
        "pfms_verified": int(shg_json.get("pfms_verified")) if shg_json.get("pfms_verified") not in (None, "") else None,
        "meeting_frequency": shg_json.get("meeting_frequency"),
        "latitude": shg_json.get("latitude") or None,
        "longitude": shg_json.get("longitude") or None,
        "created_by": shg_json.get("created_by"),
        "created_date": _parse_datetime(shg_json.get("created_date")),
        "updated_by": shg_json.get("updated_by"),
        "updated_date": _parse_datetime(shg_json.get("updated_date")),
        "is_active": 1,
        "state": _get_state(state_id),
        "district": _get_district(district_id),
        "block": _get_block(block_id_addr),
        "panchayat": _get_panchayat(panchayat_id),
        "village": _get_village(village_id),
    }

    shg_obj, created = MasterShgList.objects.update_or_create(
        shg_code=shg_code,
        defaults=defaults,
    )
    if created:
        _append_log(log_file, shg_code)

    # ---- SHG addresses ----
    MasterShgAddresses.objects.filter(shg_code=shg_obj).delete()
    for a in shg_addresses:
        MasterShgAddresses.objects.create(
            shg_code=shg_obj,
            address_line1=a.get("address_line1"),
            address_line2=a.get("address_line2"),
            city_town=a.get("city_town"),
            landmark=a.get("landmark"),
            pincode=str(a.get("postal_code")) if a.get("postal_code") not in (None, "") else None,
            state_name=a.get("state_name"),
            state=_get_state(a.get("state_id")),
            district_name=a.get("district_name"),
            district=_get_district(a.get("district_id")),
            block_name=a.get("block_name"),
            block=_get_block(a.get("block_id")),
            panchayat_name=a.get("panchayat_name"),
            panchayat=_get_panchayat(a.get("panchayat_id")),
            village_name=a.get("village_name"),
            village=_get_village(a.get("village_id")),
            lgd_village=a.get("lgd_village"),
        )

    # ---- SHG banks ----
    MasterShgBanks.objects.filter(shg_code=shg_obj).delete()
    for b in shg_json.get("shg_banks") or []:
        MasterShgBanks.objects.create(
            shg_code=shg_obj,
            account_no=b.get("account_no"),
            account_opening_date=_parse_date(b.get("account_opening_date")),
            account_type=str(b.get("account_type")) if b.get("account_type") not in (None, "") else None,
            bank_branch_code=b.get("bank_branch_code"),
            bank_branch_name=b.get("bank_branch_name"),
            bank_code=b.get("bank_code"),
            bank_name=b.get("bank_name"),
            ifsc_code=b.get("ifsc_code"),
            is_default=1 if b.get("is_default") else 0,
            pfms_account_holder_name=b.get("pfms_account_holder_name"),
            pfms_ifsc_code=b.get("pfms_ifsc_code"),
            pfms_vendor_code=b.get("pfms_vendor_code"),
            pfms_verification=b.get("pfms_verification"),
        )

    # ---- SHG phones ----
    MasterShgPhone.objects.filter(shg_code=shg_obj).delete()
    for ph in shg_json.get("shg_phones") or []:
        MasterShgPhone.objects.create(
            shg_code=shg_obj,
            phone_no=str(ph.get("phone_no")) if ph.get("phone_no") not in (None, "") else None,
            is_default=int(ph.get("is_default")) if ph.get("is_default") not in (None, "") else None,
        )

    # ---- Beneficiaries (shg_members) ----
    members = shg_json.get("shg_members") or []
    for m in members:
        member_code = str(m.get("member_code") or "")
        if not member_code:
            continue

        # derive geo from member_addresses[0] if present, else fall back to SHG address
        m_addr0 = None
        m_addrs = m.get("member_addresses") or []
        if m_addrs:
            m_addr0 = m_addrs[0]
        geo = m_addr0 or addr0 or {}
        state_id = geo.get("state_id")
        district_id = geo.get("district_id")
        block_id_geo = geo.get("block_id")
        panchayat_id = geo.get("panchayat_id")
        village_id = geo.get("village_id")

        ben_defaults = {
            "shg_code": shg_obj,
            "state": _get_state(state_id),
            "district": _get_district(district_id),
            "block": _get_block(block_id_geo),
            "panchayat": _get_panchayat(panchayat_id),
            "village": _get_village(village_id),
            "member_name": m.get("member_name"),
            "dob": _parse_date(m.get("dob")),
            "gender": m.get("gender"),
            "marital_status": m.get("marital_status"),
            "education": m.get("education"),
            "religion": m.get("religion"),
            "social_category": m.get("social_category"),
            "relation_name": m.get("relation_name") or m.get("father_husband"),
            "aadhar_verified": 1 if m.get("aadhar_verified") else 0,
            "pld_status": 1 if m.get("pld_status") else 0,
            "created_by": m.get("created_by"),
            "created_date": _parse_datetime(m.get("created_date")),
            "updated_by": m.get("updated_by"),
            "updated_date": _parse_datetime(m.get("updated_date")),
        }

        ben_obj, _ = MasterBeneficiary.objects.update_or_create(
            member_code=member_code,
            defaults=ben_defaults,
        )

        # addresses
        MasterBeneficiaryAddress.objects.filter(member_code=ben_obj).delete()
        for a in m_addrs:
            MasterBeneficiaryAddress.objects.create(
                member_code=ben_obj,
                address_line1=a.get("address_line1"),
                address_line2=a.get("address_line2"),
                city_town=a.get("city_town"),
                landmark=a.get("landmark"),
                postal_code=str(a.get("postal_code")) if a.get("postal_code") not in (None, "") else None,
                state=_get_state(a.get("state_id")),
                state_code=a.get("state_code"),
                district=_get_district(a.get("district_id")),
                block=_get_block(a.get("block_id")),
                panchayat=_get_panchayat(a.get("panchayat_id")),
                village=_get_village(a.get("village_id")),
                village_code=a.get("village_code"),
            )

        # banks
        MasterBeneficiaryBank.objects.filter(member_code=ben_obj).delete()
        for b in m.get("member_banks") or []:
            MasterBeneficiaryBank.objects.create(
                member_code=ben_obj,
                account_no=b.get("account_no"),
                ifsc_code=b.get("ifsc_code"),
                account_type=str(b.get("account_type")) if b.get("account_type") not in (None, "") else None,
                bank_name=b.get("bank_name"),
                is_default=1 if b.get("is_default_account") else 0,
            )

        # designations
        MasterBeneficiaryDesignation.objects.filter(member_code=ben_obj).delete()
        for d in m.get("member_designations") or []:
            MasterBeneficiaryDesignation.objects.create(
                member_code=ben_obj,
                designation=d.get("designation"),
                is_signatory=d.get("is_signatory"),
                member_name=d.get("member_name"),
            )

        # phones
        MasterBeneficiaryPhone.objects.filter(member_code=ben_obj).delete()
        for ph in m.get("member_phones") or []:
            MasterBeneficiaryPhone.objects.create(
                member_code=ben_obj,
                phone_no=str(ph.get("phone_no")) if ph.get("phone_no") not in (None, "") else None,
                is_default=int(ph.get("is_default")) if ph.get("is_default") not in (None, "") else None,
            )


# -------------------------------------------------------------------
# CLF LIST (clf/block?block_id=...)
# -------------------------------------------------------------------

@transaction.atomic
def sync_clf_list(block_id: int, raw_json):
    """
    Import / upsert CLF list into MasterClfList for a given block.

    raw_json is the JSON returned by:
        GET /clf/block?block_id=<block_id>
    """
    try:
        items = _ensure_list(raw_json)
        log_file = f"clf_list_{block_id}.log"

        for item in items:
            clf_code = item.get("code") or item.get("clf_code")
            if not clf_code:
                continue

            state_id = item.get("stateId")
            district_id = item.get("districtId")
            block_id_item = item.get("blockId") or block_id

            defaults = {
                "code": item.get("code"),
                "name": item.get("name"),
                "nic_code": item.get("nicCode"),
                "formation_date": _parse_date(item.get("formationDate")),
                "is_complete": int(item.get("isComplete")) if item.get("isComplete") not in (None, "") else None,
                "pfms_verified": None,
                "meeting_frequency": None,
                "registration_act_name": None,
                "registration_date": None,
                "created_by": None,
                "created_date": None,
                "updated_by": None,
                "updated_date": None,
                "guid": None,
                "state": _get_state(state_id),
                "district": _get_district(district_id),
                "block": _get_block(block_id_item),
            }

            obj, created = MasterClfList.objects.update_or_create(
                clf_code=clf_code,
                defaults=defaults,
            )
            if created:
                _append_log(log_file, clf_code)
    except Exception:
        logger.exception("Error syncing CLF list for block_id=%s", block_id)


# -------------------------------------------------------------------
# CLF DETAIL (clf?clf_code=...)
# -------------------------------------------------------------------

@transaction.atomic
def sync_clf_detail(clf_json: dict):
    """
    Import/update:
      - MasterClfList
      - MasterClfAddresses
      - MasterClfBanks
      - MasterClfPhones
      - MasterClfVoDetails
      - MasterMembersUnderClf
      - MasterPanchayatsUnderClf
      - MasterVillagesUnderClf
    """
    if not isinstance(clf_json, dict):
        return

    clf_code = clf_json.get("clf_code") or clf_json.get("code")
    if not clf_code:
        return

    addr0 = None
    addresses = clf_json.get("clf_addresses") or []
    if addresses:
        addr0 = addresses[0]

    block_id = addr0.get("block_id") if addr0 else None
    log_file = f"clf_detail_{block_id}.log" if block_id else "clf_detail_unknown.log"

    state_id = addr0.get("state_id") if addr0 else None
    district_id = addr0.get("district_id") if addr0 else None
    block_id_addr = addr0.get("block_id") if addr0 else None

    defaults = {
        "code": clf_json.get("clf_code"),
        "name": clf_json.get("clf_name"),
        "nic_code": clf_json.get("clf_nic_code"),
        "block": _get_block(block_id_addr),
        "district": _get_district(district_id),
        "state": _get_state(state_id),
        "formation_date": _parse_date(clf_json.get("formation_date")),
        "is_complete": int(clf_json.get("is_complete")) if clf_json.get("is_complete") not in (None, "") else None,
        "pfms_verified": int(clf_json.get("pfms_verified")) if clf_json.get("pfms_verified") not in (None, "") else None,
        "meeting_frequency": clf_json.get("meeting_frequency"),
        "registration_act_name": clf_json.get("registration_act_name"),
        "registration_date": _parse_date(clf_json.get("registration_date")),
        "created_by": clf_json.get("created_by"),
        "created_date": _parse_datetime(clf_json.get("created_date")),
        "updated_by": clf_json.get("updated_by"),
        "updated_date": _parse_datetime(clf_json.get("updated_date")),
        "guid": clf_json.get("guid"),
    }

    clf_obj, created = MasterClfList.objects.update_or_create(
        clf_code=clf_code,
        defaults=defaults,
    )
    if created:
        _append_log(log_file, clf_code)

    # addresses
    MasterClfAddresses.objects.filter(clf_code=clf_obj).delete()
    for a in addresses:
        MasterClfAddresses.objects.create(
            clf_code=clf_obj,
            address_line1=a.get("address_line1"),
            address_line2=a.get("address_line2"),
            city_town=a.get("city_town"),
            landmark=a.get("landmark"),
            postal_code=str(a.get("postal_code")) if a.get("postal_code") not in (None, "") else None,
            state=_get_state(a.get("state_id")),
            district=_get_district(a.get("district_id")),
            block=_get_block(a.get("block_id")),
        )

    # banks
    MasterClfBanks.objects.filter(clf_code=clf_obj).delete()
    for b in clf_json.get("clf_banks") or []:
        MasterClfBanks.objects.create(
            clf_code=clf_obj,
            account_no=b.get("account_no"),
            account_opening_date=_parse_date(b.get("account_opening_date")),
            account_type=str(b.get("account_type")) if b.get("account_type") not in (None, "") else None,
            bank_branch_code=b.get("bank_branch_code"),
            bank_branch_name=b.get("bank_branch_name"),
            bank_code=b.get("bank_code"),
            bank_name=b.get("bank_name"),
            ifsc_code=b.get("ifsc_code"),
            is_default=1 if b.get("is_default") else 0,
            pfms_account_holder_name=b.get("pfms_account_holder_name"),
            pfms_ifsc_code=b.get("pfms_ifsc_code"),
            pfms_vendor_code=b.get("pfms_vendor_code"),
            pfms_verification=b.get("pfms_verification"),
        )

    # phones
    MasterClfPhones.objects.filter(clf_code=clf_obj).delete()
    for ph in clf_json.get("clf_phones") or []:
        MasterClfPhones.objects.create(
            clf_code=clf_obj,
            phone_no=str(ph.get("phone_no")) if ph.get("phone_no") not in (None, "") else None,
            is_default=int(ph.get("is_default")) if ph.get("is_default") not in (None, "") else None,
        )

    # VO details
    MasterClfVoDetails.objects.filter(clf_code=clf_obj).delete()
    for v in clf_json.get("clf_vo_details") or []:
        MasterClfVoDetails.objects.create(
            clf_code=clf_obj,
            vo_code=v.get("vo_code"),
            vo_id=v.get("vo_id"),
            vo_name=v.get("vo_name"),
            vo_formation_date=_parse_date(v.get("vo_formation_date")),
        )

    # Members under CLF
    MasterMembersUnderClf.objects.filter(clf_code=clf_obj).delete()
    for m in clf_json.get("member_designations") or []:
        MasterMembersUnderClf.objects.create(
            clf_code=clf_obj,
            member_code=m.get("member_code"),
            member_name=m.get("member_name"),
            designation=m.get("designation"),
            is_signatory=m.get("is_signatory"),
        )

    # Panchayats & villages under CLF
    MasterPanchayatsUnderClf.objects.filter(clf_code=clf_obj).delete()
    MasterVillagesUnderClf.objects.filter(clf_code=clf_obj).delete()

    for p in clf_json.get("clf_panchayat_details") or []:
        panchayat_id = p.get("panchayat_id")
        panchayat_obj = _get_panchayat(panchayat_id)
        p_obj = MasterPanchayatsUnderClf.objects.create(
            clf_code=clf_obj,
            panchayat=panchayat_obj,
            panchayat_code=p.get("panchayat_code"),
            panchayat_name=p.get("panchayat_name"),
            lgd_gp=p.get("lgd_gp"),
        )
        # villages
        for v in p.get("villages") or []:
            MasterVillagesUnderClf.objects.create(
                clf_code=clf_obj,
                panchayat=panchayat_obj,
                village=_get_village(v.get("village_id")),
                village_code=v.get("village_code"),
                village_name=v.get("village_name"),
                lgd_village=v.get("lgd_village"),
            )
