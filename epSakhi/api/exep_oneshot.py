import json
import uuid
from django.db import transaction
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser
from django.shortcuts import get_object_or_404

from epSakhi.models import *

def generate_custom_th_urid():
    return f"TH_{uuid.uuid4().hex[:12].upper()}"

class ExistingEnterpriseCreateAPIView(APIView):
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request, *args, **kwargs):
        from django.core.files.storage import default_storage
        from datetime import datetime

        def transpose_media_data(media_data, keys, folder):
            """
            Organizes flat files into rows. 
            Example: open_box_key='p1,p2', close_box_key='p3' -> 
            Rows: [{'open': 'p1', 'close': 'p3'}, {'open': 'p2', 'close': None}]
            """
            rows = []
            # Gather all files per category
            data_map = {}
            for field in keys:
                key_str = media_data.get(field, "")
                paths = []
                for k in str(key_str).split(','):
                    k = k.strip()
                    file_obj = request.FILES.get(k)
                    if file_obj:
                        now = datetime.now()
                        save_path = f"{folder}/{now.year}/{now.strftime('%m')}/{file_obj.name}"
                        paths.append(default_storage.save(save_path, file_obj))
                data_map[field] = paths

            # Determine max rows needed
            max_len = max([len(p) for p in data_map.values()] or [0])
            for i in range(max_len):
                row = {}
                for field in keys:
                    row[field] = data_map[field][i] if i < len(data_map[field]) else None
                rows.append(row)
            return rows

        # 1. Parse the JSON payload
        raw_payload = request.data.get('data_payload')
        if not raw_payload:
            return Response({"error": "Missing 'data_payload' JSON string."}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            payload = json.loads(raw_payload)
        except json.JSONDecodeError:
            return Response({"error": "Invalid JSON in 'data_payload'."}, status=status.HTTP_400_BAD_REQUEST)

        files = request.FILES

        # 2. Start ATOMIC Transaction
        try:
            with transaction.atomic():
                
                # --- A. CREATE BENEFICIARY RECORDED ---
                benef_data = payload.get('beneficiary', {})
                beneficiary = BeneficiaryRecorded.objects.create(
                    lokos_member_code=benef_data.get('lokos_member_code'),
                    applicant_name=benef_data.get('applicant_name'),
                    age=benef_data.get('age'),
                    gender=benef_data.get('gender'),
                    marital_status=benef_data.get('marital_status'),
                    father_husband_name=benef_data.get('father_husband_name'),
                    category=benef_data.get('category'),
                    pld_status=benef_data.get('pld_status'),

                    enterprise_type='exep',
                    special_category=benef_data.get('special_category'),

                    education=benef_data.get('education'),
                    address=benef_data.get('address'),

                    district_id_id=benef_data.get('district_id'),
                    block_id_id=benef_data.get('block_id'),
                    panchayat_id_id=benef_data.get('panchayat_id'),
                    village_id_id=benef_data.get('village_id'),

                    mobile=benef_data.get('mobile'),
                    email=benef_data.get('email'),
                    lokos_shg_code=benef_data.get('lokos_shg_code'),
                    created_by_id=benef_data.get('created_by'), # CHANGED
                )

                # --- B. CREATE EXISTING ENTERPRISE ---
                ep_data = payload.get('enterprise', {})
                enterprise = ExistingEnterprise(
                    recorded_benef_id=beneficiary,

                    enterprise_name=ep_data.get('enterprise_name'),
                    ownership_type=ep_data.get('ownership_type'),
                    owner_cadre=ep_data.get('owner_cadre'),
                    owner_designation=ep_data.get('owner_designation'),
                    owner_special_category=ep_data.get('owner_special_category'),

                    year_of_establishment=ep_data.get('year_of_establishment'),
                    total_emp=ep_data.get('total_emp'),
                    number_of_shg_emp=ep_data.get('number_of_shg_emp'),
                    workplace_type=ep_data.get('workplace_type'),

                    electricity_available=ep_data.get('electricity_available'),
                    water_available=ep_data.get('water_available'),
                    transportation_availability=ep_data.get('transportation_availability'),

                    can_send_to_bijnor=ep_data.get('can_send_to_bijnor', False),
                    need_transport_help=ep_data.get('need_transport_help', False),

                    have_shop_based_prod=ep_data.get('have_shop_based_prod', False),

                    monthly_income_estimate=ep_data.get('monthly_income_estimate'),
                    annual_turnover=ep_data.get('annual_turnover'),
                    gross_profit=ep_data.get('gross_profit'),
                    working_capital_monthly=ep_data.get('working_capital_monthly'),
                    initial_investment=ep_data.get('initial_investment'),
                    source_of_investment=ep_data.get('source_of_investment'),

                    has_taken_loan=ep_data.get('has_taken_loan', False),
                    has_receieved_subsidy=ep_data.get('has_received_subsidy', False),
                    has_shg_receieved_man_fund=ep_data.get('has_shg_received_man_fund', False),

                    is_training_received=ep_data.get('is_training_received', False),
                    is_training_required=ep_data.get('is_training_required', False),
                    expansion_plan=ep_data.get('expansion_plan', False),
                    info_abt_gov_scheme=ep_data.get('info_abt_gov_scheme', False),
                    nearest_skill_centre=ep_data.get('nearest_skill_centre'),
                    skill_centre_loc=ep_data.get('skill_centre_loc'),
                    nearest_industry=ep_data.get('nearest_industry'),
                    industry_loc=ep_data.get('industry_loc'),

                    is_support_required=ep_data.get('is_support_required', False),

                    declaration_confirmed=ep_data.get('declaration_confirmed', False),
                    declaration_date=ep_data.get('declaration_date'),
                    verifier_name=ep_data.get('verifier_name'),
                    created_by_id=ep_data.get('created_by'), # CHANGED
                )
                
                # Assign a TH_urid if your model relies on generating it manually
                th_urid = generate_custom_th_urid()
                if hasattr(enterprise, 'TH_urid'):
                    enterprise.TH_urid = th_urid
                
                enterprise.save()

                # Get the final TH_urid to use for shared tables
                final_th_urid = getattr(enterprise, 'TH_urid', str(enterprise.id))

                # --- C. LINK BENEFICIARY BACK TO ENTERPRISE ---
                beneficiary.enterprise_id = final_th_urid
                beneficiary.save(update_fields=['enterprise_id'])

                # --- D. LICENSES ---
                for idx, lic_data in enumerate(payload.get('licenses', [])):
                    file_key = lic_data.get('file_key') # Frontend sends the key name, e.g., 'license_0'
                    EnterpriseLicenses.objects.create(
                        enterprise_id=enterprise,
                        license_category=lic_data.get('license_category'),
                        license_name=lic_data.get('license_name'),
                        license_no=lic_data.get('license_no'),
                        license_file=files.get(file_key) if file_key else None,
                        created_by_id=lic_data.get('created_by') # CHANGED (fixed files.get bug too)
                    )

                # --- E. LOANS & SUBSIDIES ---
                for loan in payload.get('loans', []):
                    EnterpriseLoanDetail.objects.create(
                        enterprise_id=enterprise,
                        form_type='exep',
                        department=loan.get('department'),
                        institution_name=loan.get('institution_name'),
                        bank_name=loan.get('bank_name'),
                        bank_branch=loan.get('bank_branch'),
                        loan_amount=loan.get('loan_amount'),
                        repaid_amount=loan.get('repaid_amount'),
                        date_taken=loan.get('date_taken'),
                        repayment_status=loan.get('repayment_status'),
                        created_by_id=loan.get('created_by'), # CHANGED
                    )

                for sub in payload.get('subsidies', []):
                    EnterpriseSubsidyDetail.objects.create(
                        enterprise_id=enterprise,
                        subsidy_type=sub.get('subsidy_type'),
                        subsidy_name=sub.get('subsidy_name'),
                        subsidy_detail=sub.get('subsidy_detail'),
                        created_by_id=sub.get('created_by'), # CHANGED
                    )

                # --- F. SHOP & SHOP MEDIA ---
                shop_data_list = payload.get('shops', [])
                for shop_data in shop_data_list:
                    shop = EnterpriseShop.objects.create(
                        enterprise_id=enterprise,
                        shop_category=shop_data.get('shop_category'),
                        shop_type=shop_data.get('shop_type'),
                        source_of_inventory=shop_data.get('source_of_inventory'),

                        target_customers=shop_data.get('target_customers'),
                        sales_area=shop_data.get('sales_area'),
                        marketing_strategy=shop_data.get('marketing_strategy'),
                        marketing_channels=shop_data.get('marketing_channels'),
                        marketing_challenges=shop_data.get('marketing_challenges'),
                        market_linkage=shop_data.get('market_linkage', False),
                        
                        accept_digital_payment=shop_data.get('accept_digital_payment', False),

                        avg_monthly_sales=shop_data.get('avg_monthly_sales'),
                        avg_annual_sales=shop_data.get('avg_annual_sales'),
                        created_by_id=shop_data.get('created_by'), # CHANGED
                    )
                    
                    # Shop Media
                    media_data = shop_data.get('media', {})
                    media_rows = transpose_media_data(
                        media_data, ['front_key', 'inside_key', 'others_key'], 'epSakhi/media/shops'
                    )
                    for m in media_rows:
                        ShopMedia.objects.create(
                            product_id=shop,
                            front_photo=m.get('front_key'),
                            inside_photo=m.get('inside_key'),
                            others=m.get('others_key'),
                            created_by_id=shop_data.get('created_by'),
                        )

                # --- G. PRODUCTS & PRODUCT MEDIA ---
                for prod_data in payload.get('products', []):
                    product = EnterpriseProduct.objects.create(
                        enterprise_id=enterprise,
                        main_product_name=prod_data.get('main_product_name'),
                        activity_or_product_type=prod_data.get('activity_or_product_type'),
                        product_features=prod_data.get('product_features'),
                        production_capacity=prod_data.get('production_capacity'),
                        raw_material=prod_data.get('raw_material'),
                        raw_material_source=prod_data.get('raw_material_source'),
                        machinery_equipment=prod_data.get('machinery_equipment'),
                        source_machinery=prod_data.get('source_machinery'),
                        product_mrp=prod_data.get('product_mrp'),

                        sales_area=prod_data.get('sales_area'),
                        target_customers=prod_data.get('target_customers'),
                        packaging_branding_status=prod_data.get('packaging_branding_status', False),

                        marketing_strategy=prod_data.get('marketing_strategy'),
                        marketing_channels=prod_data.get('marketing_channels'),
                        marketing_challenges=prod_data.get('marketing_challenges'),
                        market_linkage=prod_data.get('market_linkage', False),

                        accept_digital_payment=prod_data.get('accept_digital_payment', False),

                        avg_monthly_sales=prod_data.get('avg_monthly_sales'),
                        avg_annual_sales=prod_data.get('avg_annual_sales'),
                        created_by_id=prod_data.get('created_by'), # CHANGED
                    )
                    
                    media_data = prod_data.get('media', {})
                    media_rows = transpose_media_data(
                        media_data, ['open_box_key', 'close_box_key', 'others_key'], 'epSakhi/media/products'
                    )
                    for m in media_rows:
                        ProductMedia.objects.create(
                            product_id=product,
                            open_box_photo=m.get('open_box_key'),
                            close_box_photo=m.get('close_box_key'),
                            others=m.get('others_key'),
                            created_by_id=prod_data.get('created_by'),
                        )

                # --- H. ENTERPRISE MEDIA (Standalone) ---
                ep_media = payload.get('enterprise_media', {})
                if ep_media:
                    media_rows = transpose_media_data(
                        ep_media, ['entrepreneur_key', 'enterprise_key', 'others_key'], 'epSakhi/media/enterprise'
                    )
                    for m in media_rows:
                        EnterpriseMedia.objects.create(
                            enterprise_id=enterprise,
                            photo_entrepreneur=m.get('entrepreneur_key'),
                            photo_enterprise=m.get('enterprise_key'),
                            others=m.get('others_key'),
                            created_by_id=ep_media.get('created_by'),
                        )

                # ==========================================
                # SHARED TABLES (Linked via string TH_urid)
                # ==========================================

                # --- I. ENTERPRISE TYPE CATEGORIES ---
                for type_data in payload.get('categories', []):
                    EnterpriseTypeCategory.objects.create(
                        enterprise_id=final_th_urid,
                        form_type='exep',
                        parent_category=type_data.get('parent_category'),
                        sub_category=type_data.get('sub_category'),
                        created_by_id=type_data.get('created_by'), # CHANGED
                    )

                # --- J. SUPPORT & MANDATORY FUNDS ---
                for support in payload.get('supports', []):
                    EnterpriseSupport.objects.create(
                        enterprise_id=final_th_urid,
                        form_type='exep',
                        support_category=support.get('category'),
                        support_sub_category=support.get('sub_category'),
                        support_description=support.get('description'),
                        other_support= support.get('other_support'),
                        created_by_id=support.get('created_by'), # CHANGED
                    )

                for fund in payload.get('mandatory_funds', []):
                    EnterpriseMandatoryFund.objects.create(
                        enterprise_id=final_th_urid,
                        form_type='exep',
                        fund_type=fund.get('fund_type'),
                        have_received_part=fund.get('have_received_part', False),
                        amount_received=fund.get('amount_received'),
                        amount_repaid=fund.get('amount_repaid'),
                        repayment_status=fund.get('repayment_status'),
                        created_by_id=fund.get('created_by'), # CHANGED
                    )

                # --- K. TRAINING REQUIRED / RECEIVED & CERTIFICATES ---
                for tr_req in payload.get('training_requests', []):
                    tr_form_type = tr_req.get('form_type') 
                    
                    training = EnterpriseTrainingReq.objects.create(
                        enterprise_id=final_th_urid,
                        form_type=tr_form_type,
                        sector_type=tr_req.get('sector_type'),
                        sector=tr_req.get('sector'),
                        department=tr_req.get('department'),
                        training_type=tr_req.get('training_type'),
                        duration=tr_req.get('duration'),
                        location=tr_req.get('location'),
                        expected_income=tr_req.get('expected_income'),
                        created_by_id=tr_req.get('created_by'), # CHANGED
                    )

                    # If received, handle certificates
                    if tr_form_type == 'rec':
                        cert_keys = tr_req.get('certificate_file_keys', [])
                        for cert_key in cert_keys:
                            if files.get(cert_key):
                                TrainingCertificates.objects.create(
                                    enterprise_id=final_th_urid,
                                    training_id=training,
                                    certificates=files.get(cert_key),
                                    created_by_id=tr_req.get('created_by'), # CHANGED (fixed files.get bug too)
                                )

            # If execution reaches here, the transaction is committed successfully.
            return Response({
                "message": "Existing Enterprise created successfully.",
                "enterprise_id": enterprise.id,
                "TH_urid": final_th_urid,
                "recorded_benef_id": beneficiary.id
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            # The context manager automatically rolls back the DB here.
            return Response({
                "error": "Transaction failed and was rolled back.",
                "details": str(e)
            }, status=status.HTTP_400_BAD_REQUEST)


class ExistingEnterpriseDeleteAPIView(APIView):
    """
    Deletes an Existing Enterprise and manually cleans up the string-linked shared tables.
    """
    def post(self, request, *args, **kwargs):
        enterprise_id = request.data.get('enterprise_id')
        
        if not enterprise_id:
            return Response({"error": "enterprise_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        enterprise = get_object_or_404(ExistingEnterprise, id=enterprise_id)
        
        # Extract the TH_urid before deleting so we can clean up shared tables
        th_urid = getattr(enterprise, 'TH_urid', str(enterprise.id))
        
        try:
            with transaction.atomic():
                # 1. Delete the string-linked shared tables explicitly
                EnterpriseTypeCategory.objects.filter(enterprise_id=th_urid, form_type='exep').delete()
                EnterpriseSupport.objects.filter(enterprise_id=th_urid, form_type='exep').delete()
                EnterpriseMandatoryFund.objects.filter(enterprise_id=th_urid, form_type='exep').delete()
                
                # Trainings and their cascaded certificates
                EnterpriseTrainingReq.objects.filter(enterprise_id=th_urid).delete()
                # (Note: TrainingCertificates cascades from EnterpriseTrainingReq, but we can also explicitly delete)
                TrainingCertificates.objects.filter(enterprise_id=th_urid).delete()

                # 2. Delete the BeneficiaryRecorded
                if enterprise.recorded_benef_id:
                    enterprise.recorded_benef_id.delete()

                # 3. Delete the ExistingEnterprise (Cascades to Loans, Subsidies, Products, Shops, Licenses)
                enterprise.delete()

            return Response({"message": "Enterprise and all related records deleted successfully."}, status=status.HTTP_200_OK)
        
        except Exception as e:
            return Response({
                "error": "Deletion failed. Rolled back.",
                "details": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)