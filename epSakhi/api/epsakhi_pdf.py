import io
import os
import base64  # SURGICAL FIX: Import base64
from django.conf import settings
from django.http import HttpResponse
from django.template.loader import render_to_string
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
import weasyprint

from pypdf import PdfWriter

from epSakhi.models import *

# SURGICAL FIX: Helper function to convert any local image path directly into an embedded Base64 string
def get_image_base64(path):
    if not path or not os.path.exists(path):
        return ""
    
    ext = os.path.splitext(path)[1].lower()
    mime_type = "image/jpeg" if ext in ['.jpg', '.jpeg'] else "image/png"
    
    try:
        with open(path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
            return f"data:{mime_type};base64,{encoded_string}"
    except Exception as e:
        print(f"Error encoding image {path}: {e}")
        return ""


class BeneficiaryPDFExportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk, *args, **kwargs):
        try:
            beneficiary = BeneficiaryRecorded.objects.select_related(
                'district_id', 'block_id', 'panchayat_id', 'village_id'
            ).get(id=pk)
        except BeneficiaryRecorded.DoesNotExist:
            return Response({"error": "Beneficiary not found"}, status=status.HTTP_404_NOT_FOUND)

        # 1. Initialize Context and Attachment Lists
        context = {
            'beneficiary': beneficiary,
            'request': request,
            'image_attachments': [], # For HTML rendering
            
            # SURGICAL FIX: Embed static logos directly as Base64 text
            'prena_logo': get_image_base64(os.path.join(settings.BASE_DIR, 'templates', 'epSakhi', 'prena.png')),
            'upgov_logo': get_image_base64(os.path.join(settings.BASE_DIR, 'templates', 'epSakhi', 'upgov.png')),
        }
        pdf_attachments = [] # For appending at the end

        # Helper function to categorize files
        def process_file(file_field, title):
            if not file_field or not file_field.name:
                return
            ext = os.path.splitext(file_field.name)[1].lower()
            if ext == '.pdf':
                # PDFs just need the path for merging later
                pdf_attachments.append(file_field.path)
            elif ext in ['.jpg', '.jpeg', '.png']:
                # SURGICAL FIX: Read from absolute disk path (.path) and encode to Base64
                context['image_attachments'].append({
                    'title': title,
                    'url': get_image_base64(file_field.path)
                })

        # 2. Fetch Enterprise Data based on type
        ep_urid = beneficiary.enterprise_id
        
        if beneficiary.enterprise_type and beneficiary.enterprise_type.lower() == 'exep':
            enterprise = ExistingEnterprise.objects.filter(recorded_benef_id=beneficiary).first()
            context['enterprise'] = enterprise
            context['is_existing'] = True
            
            if enterprise:
                # Related Existing Tables
                context['loans'] = enterprise.exep_loan.all()
                context['subsidies'] = enterprise.exep_subsidy.all()
                
                shops = enterprise.exep_shop_media.all()
                context['shops'] = shops
                for shop in shops:
                    for media in shop.shop_media.all():
                        process_file(media.front_photo, f"Shop Front - {shop.shop_category}")
                        process_file(media.inside_photo, f"Shop Inside - {shop.shop_category}")
                        process_file(media.others, f"Shop Other - {shop.shop_category}")

                products = enterprise.exep_prod_media.all()
                context['products'] = products
                for prod in products:
                    for media in prod.prod_media.all():
                        process_file(media.open_box_photo, f"Product Open - {prod.main_product_name}")
                        process_file(media.close_box_photo, f"Product Closed - {prod.main_product_name}")
                        process_file(media.others, f"Product Other - {prod.main_product_name}")

                for media in enterprise.exep_media.all():
                    process_file(media.photo_entrepreneur, "Entrepreneur Photo")
                    
                    # SURGICAL FIX: Base64 the specific entrepreneur profile photo
                    context['entrepreneur_photo_url'] = get_image_base64(media.photo_entrepreneur.path) if media.photo_entrepreneur else None
                    
                    process_file(media.photo_enterprise, "Enterprise Photo")
                    process_file(media.others, "Enterprise Other Media")

                for license in enterprise.exep_licenses.all():
                    process_file(license.license_file, f"License: {license.license_name}")
                    
        else:
            # Handle New Enterprise
            enterprise = NewEnterprise.objects.filter(recorded_benef_id=beneficiary).first()
            context['enterprise'] = enterprise
            context['is_existing'] = False
            if enterprise:
                # This goes into PDF merging or image grid depending on extension
                process_file(enterprise.applicant_signature, "Applicant Signature")
                # Also expose it specifically for the HTML block
                if enterprise.applicant_signature:
                    context['applicant_signature_url'] = get_image_base64(enterprise.applicant_signature.path)

        # 3. Fetch Shared Tables (Mapped by string TH_urid)
        if ep_urid:
            context['categories'] = EnterpriseTypeCategory.objects.filter(enterprise_id=ep_urid)
            context['supports'] = EnterpriseSupport.objects.filter(enterprise_id=ep_urid)
            context['funds'] = EnterpriseMandatoryFund.objects.filter(enterprise_id=ep_urid)
            
            trainings = EnterpriseTrainingReq.objects.filter(enterprise_id=ep_urid)
            context['trainings'] = trainings
            for training in trainings:
                for cert in training.training_certificate.all():
                    process_file(cert.certificates, f"Training Certificate - {training.training_type}")

        # 4. Generate Main HTML PDF using WeasyPrint
        html_string = render_to_string('epSakhi/pdf_template.html', context)
        
        main_pdf_io = io.BytesIO()
        weasyprint.HTML(
            string=html_string, 
            base_url=request.build_absolute_uri('/')
        ).write_pdf(main_pdf_io)
        
        main_pdf_io.seek(0)

        # 5. Merge Main PDF with Attached PDFs
        merger = PdfWriter()
        merger.append(main_pdf_io)

        for pdf_path in pdf_attachments:
            if os.path.exists(pdf_path):
                merger.append(pdf_path)

        # 6. Finalize and Return
        final_pdf_io = io.BytesIO()
        merger.write(final_pdf_io)
        final_pdf_io.seek(0)

        response = HttpResponse(final_pdf_io, content_type='application/pdf')
        filename = f"Beneficiary_{beneficiary.lokos_member_code}_{beneficiary.applicant_name}.pdf"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        return response