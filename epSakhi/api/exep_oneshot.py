"""
ExistingEnterprise ZIP-based submission API
============================================
Frontend sends ONE multipart field: `zip_file`

The ZIP must contain:
  • payload.json              — full structured data (see PAYLOAD_SCHEMA below)
  • <filename>.<ext>          — every image / PDF referenced by name in payload.json

Flow:
  1.  Receive ZIP
  2.  Extract every entry → Django cache  (keyed per-job, TTL = 10 min)
  3.  Parse payload.json from cache
  4.  Run one atomic DB transaction (all inserts / file-saves happen here)
  5.  Flush all cache keys for this job
  6.  Return result (or roll-back details on failure)

PAYLOAD_SCHEMA (payload.json)
──────────────────────────────
{
  "beneficiary":      { ...BeneficiaryRecorded fields... },
  "enterprise":       { ...ExistingEnterprise fields... },
  "licenses":         [ { "license_category":"...", "license_name":"...",
                          "license_no":"...", "file_key":"license_0.pdf",
                          "created_by": 1 } ],
  "loans":            [ { "bank_name":"...", ... } ],
  "subsidies":        [ { "subsidy_type":"...", ... } ],
  "shops": [
    {
      "shop_category": "...", ...all EnterpriseShop fields...,
      "media": [
        { "front_key":"shop1_front.jpg",
          "inside_key":"shop1_inside.jpg",
          "others_key": null }
      ],
      "created_by": 1
    }
  ],
  "products": [
    {
      "main_product_name": "...", ...all EnterpriseProduct fields...,
      "media": [
        { "open_box_key":"prod1_open.jpg",
          "close_box_key":"prod1_close.jpg",
          "others_key": null }
      ],
      "created_by": 1
    }
  ],
  "enterprise_media": {
    "entrepreneur_key":"entrepreneur.jpg",
    "enterprise_key":"enterprise.jpg",
    "others_key": null,
    "created_by": 1
  },
  "categories":       [ { "parent_category":"...", "sub_category":"..." } ],
  "supports":         [ { "category":"...", "sub_category":"...",
                          "description":"...", "other_support":"..." } ],
  "mandatory_funds":  [ { "fund_type":"...", "have_received_part": true,
                          "amount_received":"...", "amount_repaid":"...",
                          "repayment_status":"PAID" } ],
  "training_requests":[ { "form_type":"rec",          // "rec" | "req"
                          "sector_type":"...", "sector":"...",
                          "department":"...", "training_type":"...",
                          "duration":"...", "location":"...",
                          "expected_income":"...",
                          "certificate_file_keys":["cert_0.pdf"],
                          "created_by": 1 } ]
}
"""

import json
import uuid
import zipfile
import os

from django.db import transaction
from django.core.cache import cache
from django.core.files.base import ContentFile
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser
from django.shortcuts import get_object_or_404

from epSakhi.models import (
    BeneficiaryRecorded,
    ExistingEnterprise,
    EnterpriseLicenses,
    EnterpriseLoanDetail,
    EnterpriseSubsidyDetail,
    EnterpriseShop,
    ShopMedia,
    EnterpriseProduct,
    ProductMedia,
    EnterpriseMedia,
    EnterpriseTypeCategory,
    EnterpriseSupport,
    EnterpriseMandatoryFund,
    EnterpriseTrainingReq,
    TrainingCertificates,
)

from core.models import MasterBlock, MasterPanchayat, MasterVillage

# ── Constants ─────────────────────────────────────────────────────────────────

CACHE_TTL = 600          # seconds (10 min) — well beyond any realistic request time
CACHE_NS  = "epsakhi"    # namespace prefix so keys never collide with other apps


# ── Helpers ───────────────────────────────────────────────────────────────────

def generate_custom_th_urid() -> str:
    return f"TH_{uuid.uuid4().hex[:12].upper()}"


def _cache_key_file(job_id: str, filename: str) -> str:
    return f"{CACHE_NS}_{job_id}_file_{filename}"


def _cache_key_payload(job_id: str) -> str:
    return f"{CACHE_NS}_{job_id}_payload"


def _flush_job_cache(job_id: str, file_names: list) -> None:
    """Best-effort deletion of every cache entry written for this job."""
    try:
        cache.delete(_cache_key_payload(job_id))
        for name in file_names:
            cache.delete(_cache_key_file(job_id, name))
    except Exception:
        pass   # cache flush failures must never mask DB errors


# ── Main View ─────────────────────────────────────────────────────────────────

class ExistingEnterpriseCreateAPIView(APIView):
    """
    POST /api/existing-enterprise/create/
    Accepts a single multipart field `zip_file`.
    """
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request, *args, **kwargs):

        # ── 0. Basic validation ───────────────────────────────────────────────
        zip_upload = request.FILES.get('zip_file')
        if not zip_upload:
            return Response(
                {"error": "Missing 'zip_file' field in request."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        zip_upload.seek(0)
        if not zipfile.is_zipfile(zip_upload):
            return Response(
                {"error": "Uploaded file is not a valid ZIP archive."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ── 1. Read ZIP in memory ─────────────────────────────────────────────
        payload = None
        extracted_paths = {}

        try:
            zip_upload.seek(0)
            with zipfile.ZipFile(zip_upload, 'r') as zf: # 🟢 Open Zip
                
                # First pass: Find payload and map file paths
                for entry in zf.namelist():
                    if entry.endswith('/'):
                        continue
                    basename = os.path.basename(entry)
                    if not basename:
                        continue

                    if basename == 'payload.json':
                        try:
                            payload = json.loads(zf.read(entry).decode('utf-8'))
                        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                            return Response(
                                {"error": f"payload.json is invalid: {exc}"},
                                status=status.HTTP_400_BAD_REQUEST,
                            )
                    else:
                        extracted_paths[basename] = entry

                if payload is None:
                    return Response(
                        {"error": "ZIP must contain a 'payload.json' file."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                # ── 2. On-Demand File Accessor (NOW INSIDE THE WITH BLOCK) ────
                def cf(filename, fallback_filename=None):
                    # 1. Try exact match from JSON first
                    if filename and filename in extracted_paths:
                        raw_bytes = zf.read(extracted_paths[filename])
                        return ContentFile(raw_bytes, name=filename)
                    
                    # 2. Try the fallback match (e.g., license_0.pdf)
                    if fallback_filename and fallback_filename in extracted_paths:
                        raw_bytes = zf.read(extracted_paths[fallback_filename])
                        # Save it to the DB using the originally requested filename
                        save_name = filename if filename else fallback_filename
                        return ContentFile(raw_bytes, name=save_name)

                    return None

                # ── 3. Atomic DB transaction (NOW INSIDE THE WITH BLOCK) ──────
                with transaction.atomic():

                    # ── A. BeneficiaryRecorded ────────────────────────────────────
                    bd = payload.get('beneficiary', {})
                    
                    # Extract IDs from payload
                    dist_id = bd.get('district_id')
                    blk_id = bd.get('block_id')
                    panch_id = bd.get('panchayat_id')
                    vill_id = bd.get('village_id')

                    # 3) Fallback: village_id given, but others are null
                    if not dist_id and not blk_id and not panch_id and vill_id:
                        try:
                            vill_obj = MasterVillage.objects.get(pk=vill_id)
                            dist_id = vill_obj.district_id
                            blk_id = vill_obj.block_id
                            panch_id = vill_obj.panchayat_id
                        except MasterVillage.DoesNotExist:
                            pass
                            
                    # 2) Fallback: panchayat_id given, but dist & block are null
                    elif not dist_id and not blk_id and panch_id:
                        try:
                            panch_obj = MasterPanchayat.objects.get(pk=panch_id)
                            dist_id = panch_obj.district_id
                            blk_id = panch_obj.block_id
                        except MasterPanchayat.DoesNotExist:
                            pass
                            
                    # 1) Fallback: block_id given, but dist is null
                    elif not dist_id and blk_id:
                        try:
                            blk_obj = MasterBlock.objects.get(pk=blk_id)
                            dist_id = blk_obj.district_id
                        except MasterBlock.DoesNotExist:
                            pass

                    # Create beneficiary using the updated IDs
                    beneficiary = BeneficiaryRecorded.objects.create(
                        lokos_member_code   = bd.get('lokos_member_code'),
                        applicant_name      = bd.get('applicant_name'),
                        age                 = bd.get('age'),
                        gender              = bd.get('gender'),
                        marital_status      = bd.get('marital_status'),
                        father_husband_name = bd.get('father_husband_name'),
                        category            = bd.get('category'),
                        pld_status          = bd.get('pld_status'),
                        enterprise_type     = 'exep',
                        special_category    = bd.get('special_category'),
                        education           = bd.get('education'),
                        address             = bd.get('address'),
                        district_id_id      = dist_id,   # Using fallback-checked variables
                        block_id_id         = blk_id,    # Using fallback-checked variables
                        panchayat_id_id     = panch_id,  # Using fallback-checked variables
                        village_id_id       = vill_id,   # Using fallback-checked variables
                        mobile              = bd.get('mobile'),
                        email               = bd.get('email'),
                        lokos_shg_code      = bd.get('lokos_shg_code'),
                        created_by_id       = bd.get('created_by'),
                    )

                    # ── B. ExistingEnterprise ─────────────────────────────────────
                    ed = payload.get('enterprise', {})
                    enterprise = ExistingEnterprise(
                        recorded_benef_id           = beneficiary,
                        enterprise_name             = ed.get('enterprise_name'),
                        ownership_type              = ed.get('ownership_type'),
                        owner_cadre                 = ed.get('owner_cadre'),
                        owner_designation           = ed.get('owner_designation'),
                        owner_special_category      = ed.get('owner_special_category'),
                        year_of_establishment       = ed.get('year_of_establishment'),
                        total_emp                   = ed.get('total_emp'),
                        number_of_shg_emp           = ed.get('number_of_shg_emp'),
                        workplace_type              = ed.get('workplace_type'),
                        electricity_available       = ed.get('electricity_available'),
                        water_available             = ed.get('water_available'),
                        transportation_availability = ed.get('transportation_availability'),
                        can_send_to_bijnor          = ed.get('can_send_to_bijnor', False),
                        need_transport_help         = ed.get('need_transport_help', False),
                        have_shop_based_prod        = ed.get('have_shop_based_prod', False),
                        monthly_income_estimate     = ed.get('monthly_income_estimate'),
                        annual_turnover             = ed.get('annual_turnover'),
                        gross_profit                = ed.get('gross_profit'),
                        working_capital_monthly     = ed.get('working_capital_monthly'),
                        initial_investment          = ed.get('initial_investment'),
                        source_of_investment        = ed.get('source_of_investment'),
                        has_taken_loan              = ed.get('has_taken_loan', False),
                        has_receieved_subsidy       = ed.get('has_received_subsidy', False),
                        has_shg_receieved_man_fund  = ed.get('has_shg_received_man_fund', False),
                        is_training_received        = ed.get('is_training_received', False),
                        is_training_required        = ed.get('is_training_required', False),
                        expansion_plan              = ed.get('expansion_plan'),
                        info_abt_gov_scheme         = ed.get('info_abt_gov_scheme'),
                        nearest_skill_centre        = ed.get('nearest_skill_centre'),
                        skill_centre_loc            = ed.get('skill_centre_loc'),
                        nearest_industry            = ed.get('nearest_industry'),
                        industry_loc                = ed.get('industry_loc'),
                        is_support_required         = ed.get('is_support_required'),
                        declaration_confirmed       = ed.get('declaration_confirmed', False),
                        declaration_date            = ed.get('declaration_date'),
                        verifier_name               = ed.get('verifier_name'),
                        created_by_id               = ed.get('created_by'),
                    )
                    th_urid = generate_custom_th_urid()
                    if hasattr(enterprise, 'TH_urid'):
                        enterprise.TH_urid = th_urid
                    enterprise.save()

                    final_th_urid = getattr(enterprise, 'TH_urid', str(enterprise.id))

                    # Link beneficiary back to enterprise
                    beneficiary.enterprise_id = final_th_urid
                    beneficiary.save(update_fields=['enterprise_id'])

                    # ── C. Licenses ───────────────────────────────────────────────
                    for idx, lic in enumerate(payload.get('licenses', [])):
                        fallback_key = f"license_{idx}.pdf"
                        
                        EnterpriseLicenses.objects.create(
                            enterprise_id    = enterprise,
                            license_category = lic.get('license_category'),
                            license_name     = lic.get('license_name'),
                            license_no       = lic.get('license_no'),
                            license_file     = cf(lic.get('file_key'), fallback_filename=fallback_key),
                            created_by_id    = lic.get('created_by'),
                        )

                    # ── D. Loans ──────────────────────────────────────────────────
                    for loan in payload.get('loans', []):
                        EnterpriseLoanDetail.objects.create(
                            enterprise_id    = enterprise,
                            form_type        = 'exep',
                            department       = loan.get('department'),
                            institution_name = loan.get('institution_name'),
                            bank_name        = loan.get('bank_name'),
                            bank_branch      = loan.get('bank_branch'),
                            loan_amount      = loan.get('loan_amount'),
                            repaid_amount    = loan.get('repaid_amount'),
                            date_taken       = loan.get('date_taken'),
                            repayment_status = loan.get('repayment_status'),
                            created_by_id    = loan.get('created_by'),
                        )

                    # ── E. Subsidies ──────────────────────────────────────────────
                    for sub in payload.get('subsidies', []):
                        EnterpriseSubsidyDetail.objects.create(
                            enterprise_id  = enterprise,
                            subsidy_type   = sub.get('subsidy_type'),
                            subsidy_name   = sub.get('subsidy_name'),
                            subsidy_detail = sub.get('subsidy_detail'),
                            created_by_id  = sub.get('created_by'),
                        )

                    # ── F. Shops + Shop Media ─────────────────────────────────────
                    # payload.shops[n].media is a LIST so multiple ShopMedia rows
                    # are supported: [{ front_key, inside_key, others_key }, ...]
                    for shop_data in payload.get('shops', []):
                        shop = EnterpriseShop.objects.create(
                            enterprise_id          = enterprise,
                            shop_category          = shop_data.get('shop_category'),
                            shop_type              = shop_data.get('shop_type'),
                            source_of_inventory    = shop_data.get('source_of_inventory'),
                            target_customers       = shop_data.get('target_customers'),
                            sales_area             = shop_data.get('sales_area'),
                            marketing_strategy     = shop_data.get('marketing_strategy'),
                            marketing_channels     = shop_data.get('marketing_channels'),
                            marketing_challenges   = shop_data.get('marketing_challenges'),
                            market_linkage         = shop_data.get('market_linkage', False),
                            accept_digital_payment = shop_data.get('accept_digital_payment', False),
                            avg_monthly_sales      = shop_data.get('avg_monthly_sales'),
                            avg_annual_sales       = shop_data.get('avg_annual_sales'),
                            created_by_id          = shop_data.get('created_by'),
                        )
                        for m in shop_data.get('media', []):
                            ShopMedia.objects.create(
                                product_id    = shop,
                                front_photo   = cf(m.get('front_key')),
                                inside_photo  = cf(m.get('inside_key')),
                                others        = cf(m.get('others_key')),
                                created_by_id = shop_data.get('created_by'),
                            )

                    # ── G. Products + Product Media ───────────────────────────────
                    # Same pattern: payload.products[n].media is a LIST
                    for prod in payload.get('products', []):
                        product = EnterpriseProduct.objects.create(
                            enterprise_id             = enterprise,
                            main_product_name         = prod.get('main_product_name'),
                            activity_or_product_type  = prod.get('activity_or_product_type'),
                            product_features          = prod.get('product_features'),
                            production_capacity       = prod.get('production_capacity'),
                            raw_material              = prod.get('raw_material'),
                            raw_material_source       = prod.get('raw_material_source'),
                            machinery_equipment       = prod.get('machinery_equipment'),
                            source_machinery          = prod.get('source_machinery'),
                            product_mrp               = prod.get('product_mrp'),
                            sales_area                = prod.get('sales_area'),
                            target_customers          = prod.get('target_customers'),
                            packaging_branding_status = prod.get('packaging_branding_status'),
                            marketing_strategy        = prod.get('marketing_strategy'),
                            marketing_channels        = prod.get('marketing_channels'),
                            marketing_challenges      = prod.get('marketing_challenges'),
                            market_linkage            = prod.get('market_linkage', False),
                            accept_digital_payment    = prod.get('accept_digital_payment', False),
                            avg_monthly_sales         = prod.get('avg_monthly_sales'),
                            avg_annual_sales          = prod.get('avg_annual_sales'),
                            created_by_id             = prod.get('created_by'),
                        )
                        for m in prod.get('media', []):
                            ProductMedia.objects.create(
                                product_id      = product,
                                open_box_photo  = cf(m.get('open_box_key')),
                                close_box_photo = cf(m.get('close_box_key')),
                                others          = cf(m.get('others_key')),
                                created_by_id   = prod.get('created_by'),
                            )

                    # ── H. Enterprise Media ───────────────────────────────────────
                    ep_media = payload.get('enterprise_media', {})
                    if ep_media:
                        EnterpriseMedia.objects.create(
                            enterprise_id      = enterprise,
                            photo_entrepreneur = cf(ep_media.get('entrepreneur_key')),
                            photo_enterprise   = cf(ep_media.get('enterprise_key')),
                            others             = cf(ep_media.get('others_key')),
                            created_by_id      = ep_media.get('created_by'),
                        )

                    # ── I. Type Categories ────────────────────────────────────────
                    for cat in payload.get('categories', []):
                        EnterpriseTypeCategory.objects.create(
                            enterprise_id   = final_th_urid,
                            form_type       = 'exep',
                            parent_category = cat.get('parent_category'),
                            sub_category    = cat.get('sub_category'),
                            created_by_id   = cat.get('created_by'),
                        )

                    # ── J. Support ────────────────────────────────────────────────
                    for support in payload.get('supports', []):
                        EnterpriseSupport.objects.create(
                            enterprise_id        = final_th_urid,
                            form_type            = 'exep',
                            support_category     = support.get('category'),
                            support_sub_category = support.get('sub_category'),
                            support_description  = support.get('description'),
                            other_support        = support.get('other_support'),
                            created_by_id        = support.get('created_by'),
                        )

                    # ── K. Mandatory Funds ────────────────────────────────────────
                    for fund in payload.get('mandatory_funds', []):
                        EnterpriseMandatoryFund.objects.create(
                            enterprise_id      = final_th_urid,
                            form_type          = 'exep',
                            fund_type          = fund.get('fund_type'),
                            have_received_part = fund.get('have_received_part', False),
                            amount_received    = fund.get('amount_received'),
                            amount_repaid      = fund.get('amount_repaid'),
                            repayment_status   = fund.get('repayment_status'),
                            created_by_id      = fund.get('created_by'),
                        )

                    # ── L. Training + Certificates ────────────────────────────────
                    for tr in payload.get('training_requests', []):
                        training = EnterpriseTrainingReq.objects.create(
                            enterprise_id   = final_th_urid,
                            form_type       = tr.get('form_type'),
                            sector_type     = tr.get('sector_type'),
                            sector          = tr.get('sector'),
                            department      = tr.get('department'),
                            training_type   = tr.get('training_type'),
                            duration        = tr.get('duration'),
                            location        = tr.get('location'),
                            expected_income = tr.get('expected_income'),
                            created_by_id   = tr.get('created_by'),
                        )
                        if tr.get('form_type') == 'rec':
                            for cert_key in tr.get('certificate_file_keys', []):
                                cert_file = cf(cert_key)
                                if cert_file:
                                    TrainingCertificates.objects.create(
                                        enterprise_id = final_th_urid,
                                        training_id   = training,
                                        certificates  = cert_file,
                                        created_by_id = tr.get('created_by'),
                                    )

                # Return success response from inside the zip context
                return Response(
                    {
                        "message": "Existing Enterprise created successfully.",
                        "enterprise_id": enterprise.id,
                        "TH_urid": getattr(enterprise, 'TH_urid', enterprise.id),
                        "recorded_benef_id": getattr(payload.get('beneficiary', {}), 'id', None),
                    },
                    status=status.HTTP_201_CREATED,
                ) # 🟢 End of Zip lifecycle (closes cleanly here)

        except Exception as exc:
            return Response(
                {
                    "error": "Transaction failed and was rolled back.",
                    "details": str(exc),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )


# ── Delete view (unchanged logic, same as before) ─────────────────────────────

class ExistingEnterpriseDeleteAPIView(APIView):
    """
    POST /api/existing-enterprise/delete/
    Body: { "enterprise_id": <int> }
    """
    def post(self, request, *args, **kwargs):
        enterprise_id = request.data.get('enterprise_id')
        if not enterprise_id:
            return Response(
                {"error": "enterprise_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        enterprise = get_object_or_404(ExistingEnterprise, id=enterprise_id)
        th_urid    = getattr(enterprise, 'TH_urid', str(enterprise.id))

        try:
            with transaction.atomic():
                # String-linked shared tables first (no DB cascade)
                EnterpriseTypeCategory.objects.filter(enterprise_id=th_urid, form_type='exep').delete()
                EnterpriseSupport.objects.filter(enterprise_id=th_urid,      form_type='exep').delete()
                EnterpriseMandatoryFund.objects.filter(enterprise_id=th_urid, form_type='exep').delete()
                # TrainingCertificates cascades from EnterpriseTrainingReq,
                # but explicit delete is safer for string-keyed rows
                TrainingCertificates.objects.filter(enterprise_id=th_urid).delete()
                EnterpriseTrainingReq.objects.filter(enterprise_id=th_urid).delete()

                # BeneficiaryRecorded
                if enterprise.recorded_benef_id:
                    enterprise.recorded_benef_id.delete()

                # ExistingEnterprise (cascades: Loans, Subsidies, Products,
                #                     Shops, Licenses, all Media)
                enterprise.delete()

            return Response(
                {"message": "Enterprise and all related records deleted successfully."},
                status=status.HTTP_200_OK,
            )

        except Exception as exc:
            return Response(
                {"error": "Deletion failed. Rolled back.", "details": str(exc)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
