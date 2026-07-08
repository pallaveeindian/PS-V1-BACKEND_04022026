import io
from pathlib import Path
from django.conf import settings
from django.http import HttpResponse
from django.template.loader import render_to_string
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from weasyprint import HTML
from TMS.models import BatchParticipantCertificate

class DownloadParticipantCertificateAPIView(APIView):
    """
    API to generate and download a participant's certificate using their issue_code.
    Strictly restricted to batches that have a 'CLOSED' status.
    """
    def get(self, request, *args, **kwargs):
        issue_code = request.GET.get('issue_code')
        if not issue_code:
            return Response({"error": "issue_code is required."}, status=status.HTTP_400_BAD_REQUEST)

        # 1. Fetch the certificate and all related geographical/participant data
        try:
            cert = BatchParticipantCertificate.objects.select_related(
                'batch', 
                'batch__training_plan',
                'tr_beneficiary',
                'tr_beneficiary__district',
                'tr_beneficiary__block',
                'tr_beneficiary__panchayat',
                'tr_trainer',
                'tr_trainer__trainer',
                'tr_trainer__district',
                'tr_trainer__block'
            ).get(issue_code=issue_code)
        except BatchParticipantCertificate.DoesNotExist:
            return Response({"error": "Certificate not found."}, status=status.HTTP_404_NOT_FOUND)

        batch = cert.batch
        
        # 2. Strict Check: Only Closed Batches
        if not batch or batch.status != 'CLOSED':
            return Response(
                {"error": "Certificates are only available for CLOSED batches."}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        # 3. Setup Logos & Translators
        left_logo = Path(settings.BASE_DIR) / "templates" / "tms" / "logos" / "left.png"
        right_logo = Path(settings.BASE_DIR) / "templates" / "tms" / "logos" / "right.png"

        LEVEL_HI = {
            "BLOCK": "ब्लॉक", "DISTRICT": "जिला", "STATE": "राज्य", 
            "VILLAGE": "ग्राम", "SHG": "एसएचजी", "CLF": "सीएलएफ"
        }
        raw_level = batch.training_plan.level_of_training if batch.training_plan else "BLOCK"
        level_hi = LEVEL_HI.get(raw_level, raw_level)

        # Helper function to safely extract Hindi/Local names from core models
        def get_local_name(obj):
            if not obj:
                return "—"
            # Try specific language fields first, fallback to standard string representation
            for attr in ['district_name_en', 'block_name_en', 'panchayat_name_en', 
                         'district_name_local', 'block_name_local', 'panchayat_name_local',
                         'district_name_en', 'block_name_en', 'panchayat_name_en']:
                if hasattr(obj, attr) and getattr(obj, attr):
                    return getattr(obj, attr)
            return str(obj)

        # 4. Extract Participant Details (Handling both Beneficiary and Trainer)
        participant_name = "—"
        father_husband_name = "—"
        district_name = "—"
        block_name = "—"
        gram_panchayat = "—"
        cadre = "—"

        if cert.tr_beneficiary:
            tb = cert.tr_beneficiary
            participant_name = tb.member_name or "—"
            # TRBeneficiary doesn't have father/husband name in current models, leave blank
            father_husband_name = "—" 
            district_name = get_local_name(tb.district or batch.district)
            block_name = get_local_name(tb.block or batch.block)
            gram_panchayat = get_local_name(tb.panchayat)
            cadre = tb.designation or "—"
            
        elif cert.tr_trainer:
            tt = cert.tr_trainer
            participant_name = tt.full_name or (tt.trainer.full_name if tt.trainer else "—")
            if tt.trainer and tt.trainer.parent_or_spouse_name:
                father_husband_name = tt.trainer.parent_or_spouse_name
                
            district_name = get_local_name(tt.district or batch.district)
            block_name = get_local_name(tt.block or batch.block)
            gram_panchayat = "—" # Trainers don't map to GP in TRTrainer
            
            if tt.trainer and tt.trainer.designation:
                cadre = tt.trainer.designation
            else:
                cadre = "Master Trainer"

        # 5. Build HTML Context
        context = {
            'level_hi': level_hi,
            'financial_year': batch.financial_year or "—",
            'participant_name': participant_name,
            'father_husband_name': father_husband_name,
            'district_name': district_name,
            'block_name': block_name,
            'gram_panchayat': gram_panchayat,
            'cadre': cadre,
            'start_str': batch.start_date.strftime("%d/%m/%Y") if batch.start_date else "—",
            'end_str': batch.end_date.strftime("%d/%m/%Y") if batch.end_date else "—",
            'left_logo': left_logo.as_uri() if left_logo.exists() else "",
            'right_logo': right_logo.as_uri() if right_logo.exists() else "",
            # Optional: Add md_signature_url here if you have it in settings
        }

        # 6. Render HTML & Generate PDF
        html_string = render_to_string('tms/pdf/participant_certificate.html', context)
        
        pdf_buffer = io.BytesIO()
        HTML(string=html_string).write_pdf(pdf_buffer)
        pdf_buffer.seek(0)
        
        # 7. Return PDF Response
        response = HttpResponse(pdf_buffer, content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="Certificate_{issue_code}.pdf"'
        return response