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

class NewEnterpriseCreateAPIView(APIView):
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request, *args, **kwargs):
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

                    enterprise_type='newep',
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
                    created_by_id=benef_data.get('created_by')                    
                )

                # --- B. CREATE NEW ENTERPRISE ---
                ep_data = payload.get('enterprise', {})
                signature_key = ep_data.get('signature_file_key') # Extract the key for the signature file

                enterprise = NewEnterprise(
                    recorded_benef_id=beneficiary,

                    applicant_special_category=ep_data.get('applicant_special_category'),
                    applicant_cadre=ep_data.get('applicant_cadre'),
                    applicant_designation=ep_data.get('applicant_designation'),
                    prefered_location=ep_data.get('prefered_location'),

                    has_shg_receieved_man_fund=ep_data.get('has_shg_received_man_fund', False),

                    is_training_received=ep_data.get('is_training_received', False),
                    is_training_required=ep_data.get('is_training_required', False),

                    nearest_skill_centre=ep_data.get('nearest_skill_centre'),
                    skill_centre_loc=ep_data.get('skill_centre_loc'),
                    nearest_industry=ep_data.get('nearest_industry'),
                    industry_loc=ep_data.get('industry_loc'),

                    is_support_required=ep_data.get('is_support_required'),

                    declaration_confirmed=ep_data.get('declaration_confirmed', False),
                    declaration_date=ep_data.get('declaration_date'),
                    applicant_signature=files.get(signature_key) if signature_key else None,
                    created_by_id=ep_data.get('created_by')
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

                # ==========================================
                # SHARED TABLES (Linked via string TH_urid)
                # ==========================================

                # --- D. ENTERPRISE TYPE CATEGORIES ---
                for type_data in payload.get('categories', []):
                    EnterpriseTypeCategory.objects.create(
                        enterprise_id=final_th_urid,
                        form_type='newep',
                        parent_category=type_data.get('parent_category'),
                        sub_category=type_data.get('sub_category'),
                        created_by_id=type_data.get('created_by')
                    )

                # --- E. SUPPORT ---
                for support in payload.get('supports', []):
                    EnterpriseSupport.objects.create(
                        enterprise_id=final_th_urid,
                        form_type='newep',
                        support_category=support.get('category'),
                        support_sub_category=support.get('sub_category'),
                        support_description=support.get('support_description'),
                        other_support=support.get('other_support'),
                        created_by_id=support.get('created_by')
                    )

                # --- F. MANDATORY FUNDS ---
                for fund in payload.get('mandatory_funds', []):
                    EnterpriseMandatoryFund.objects.create(
                        enterprise_id=final_th_urid,
                        form_type='newep',
                        fund_type=fund.get('fund_type'),
                        have_received_part=fund.get('have_received_part', False),
                        amount_received=fund.get('amount_received'),
                        amount_repaid=fund.get('amount_repaid'),
                        repayment_status=fund.get('repayment_status', 'NOT PAID'),
                        created_by_id=fund.get('created_by')
                    )

                # --- G. TRAINING REQUIRED / RECEIVED & CERTIFICATES ---
                for tr_req in payload.get('training_requests', []):
                    # form_type here will be 'rec' or 'req' passed from frontend
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
                        created_by_id=tr_req.get('created_by')
                    )

                    # If received, process certificates
                    if tr_form_type == 'rec':
                        cert_keys = tr_req.get('certificate_file_keys', [])
                        for cert_key in cert_keys:
                            if files.get(cert_key):
                                TrainingCertificates.objects.create(
                                    enterprise_id=final_th_urid,
                                    training_id=training,
                                    certificates=files.get(cert_key),
                                    created_by_id=tr_req.get('created_by')
                                )

            # If execution reaches here, the transaction is completely committed.
            return Response({
                "message": "New Enterprise created successfully.",
                "enterprise_id": enterprise.id,
                "TH_urid": final_th_urid,
                "recorded_benef_id": beneficiary.id
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            # Automatic Rollback happens here
            return Response({
                "error": "Validation failed, transaction rolled back completely.",
                "details": str(e)
            }, status=status.HTTP_400_BAD_REQUEST)


class NewEnterpriseDeleteAPIView(APIView):
    """
    Deletes a New Enterprise and strictly cleans up the string-linked shared tables.
    """
    def post(self, request, *args, **kwargs):
        enterprise_id = request.data.get('enterprise_id')
        
        if not enterprise_id:
            return Response({"error": "enterprise_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        enterprise = get_object_or_404(NewEnterprise, id=enterprise_id)
        th_urid = getattr(enterprise, 'TH_urid', str(enterprise.id))
        
        try:
            with transaction.atomic():
                # 1. Delete the string-linked shared tables explicitly
                EnterpriseTypeCategory.objects.filter(enterprise_id=th_urid, form_type='newep').delete()
                EnterpriseSupport.objects.filter(enterprise_id=th_urid, form_type='newep').delete()
                EnterpriseMandatoryFund.objects.filter(enterprise_id=th_urid, form_type='newep').delete()
                
                # 2. Delete Trainings and cascaded certificates
                # Filter specifically for trainings associated with this TH_urid
                EnterpriseTrainingReq.objects.filter(enterprise_id=th_urid).delete()
                TrainingCertificates.objects.filter(enterprise_id=th_urid).delete()

                # 3. Delete the BeneficiaryRecorded
                if enterprise.recorded_benef_id:
                    enterprise.recorded_benef_id.delete()

                # 4. Delete the NewEnterprise
                enterprise.delete()

            return Response({"message": "New Enterprise and all related records deleted successfully."}, status=status.HTTP_200_OK)
        
        except Exception as e:
            return Response({
                "error": "Deletion failed. Rolled back.",
                "details": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)