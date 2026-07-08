from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404

from TMS.models import *

class TrainingRequestParticipantsAPIView(APIView):
    """
    Fetches ALL participants (Beneficiary or Trainer) for a given Training Request ID.
    If a participant has CB_selected=True, it includes fully nested Batch details.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, tr_id, *args, **kwargs):
        # 1. Fetch the Training Request
        tr = get_object_or_404(TrainingRequest, id=tr_id, is_active=True)
        
        # 2. Helper to deeply serialize a Batch object
        def serialize_batch(batch):
            if not batch:
                return None
            return {
                "id": batch.id,
                "code": batch.code,
                "batch_type": batch.batch_type,
                "status": batch.status,
                "start_date": batch.start_date,
                "end_date": batch.end_date,
                "time_of_training": batch.time_of_training,
                "training_plan": {
                    "id": batch.training_plan.id,
                    "name": batch.training_plan.training_name,
                    "theme": batch.training_plan.theme.theme_name if batch.training_plan.theme else None,
                } if batch.training_plan else None,
                "district": {
                    "id": batch.district.district_id,
                    "name": batch.district.district_name_en,
                } if batch.district else None,
                "block": {
                    "id": batch.block.block_id,
                    "name": batch.block.block_name_en,
                } if batch.block else None,
                "partner": {
                    "id": batch.partner.id,
                    "name": batch.partner.name,
                } if batch.partner else None,
                "centre": {
                    "id": batch.centre.id,
                    "venue_name": batch.centre.venue_name,
                    "address": batch.centre.venue_address,
                } if batch.centre else None,
            }

        results = []

        # ==========================================
        # 3A. Process BENEFICIARY Training Requests
        # ==========================================
        if tr.training_type == 'BENEFICIARY':
            participants = TRBeneficiary.objects.filter(training=tr, is_active=True)
            
            # Pre-fetch batches for selected participants to avoid N+1 DB queries
            selected_ids = participants.filter(CB_selected=True).values_list('id', flat=True)
            
            batch_mappings = BatchBeneficiary.objects.filter(
                beneficiary_id__in=selected_ids,
                batch__is_active=True
            ).select_related(
                'batch', 
                'batch__training_plan', 
                'batch__training_plan__theme',
                'batch__district', 
                'batch__block', 
                'batch__partner', 
                'batch__centre'
            )
            
            # Create an O(1) lookup dictionary: beneficiary_id -> batch object
            batch_map = {mapping.beneficiary_id: mapping.batch for mapping in batch_mappings}

            for p in participants:
                data = {
                    "id": p.id,
                    "member_name": p.member_name,
                    "lokos_member_code": p.lokos_member_code,
                    "lokos_shg_code": p.lokos_shg_code,
                    "age": p.age,
                    "gender": p.gender,
                    "social_category": p.social_category,
                    "pld_status": p.pld_status,
                    "mobile": p.mobile,
                    "district_id": p.district_id,
                    "block_id": p.block_id,
                    "panchayat_id": p.panchayat_id,
                    "village_id": p.village_id,
                    "CB_selected": p.CB_selected,
                    "attended": p.attended,
                    "is_replaced": p.is_replaced,
                    "batch_details": serialize_batch(batch_map.get(p.id)) if p.CB_selected else None
                }
                results.append(data)

        # ==========================================
        # 3B. Process TRAINER Training Requests
        # ==========================================
        elif tr.training_type == 'TRAINER':
            participants = TRTrainer.objects.filter(training=tr, is_active=True)
            
            # Pre-fetch batches for selected participants to avoid N+1 DB queries
            selected_ids = participants.filter(CB_selected=True).values_list('id', flat=True)
            
            batch_mappings = BatchTrainer.objects.filter(
                trainer_id__in=selected_ids,
                batch__is_active=True
            ).select_related(
                'batch', 
                'batch__training_plan', 
                'batch__training_plan__theme',
                'batch__district', 
                'batch__block', 
                'batch__partner', 
                'batch__centre'
            )
            
            # Create an O(1) lookup dictionary: trainer_id -> batch object
            batch_map = {mapping.trainer_id: mapping.batch for mapping in batch_mappings}

            for p in participants:
                data = {
                    "id": p.id,
                    "full_name": p.full_name,
                    "master_trainer_id": p.trainer_id,
                    "mobile_no": p.mobile_no,
                    "aadhaar_no": p.aadhaar_no,
                    "district_id": p.district_id,
                    "block_id": p.block_id,
                    "CB_selected": p.CB_selected,
                    "attended": p.attended,
                    "is_replaced": p.is_replaced,
                    "batch_details": serialize_batch(batch_map.get(p.id)) if p.CB_selected else None
                }
                results.append(data)

        # 4. Return Output
        return Response({
            "training_request_id": tr.id,
            "training_type": tr.training_type,
            "total_participants": len(results),
            "results": results
        }, status=status.HTTP_200_OK)