# Desktop/BDO_Projects/pragati_setu/TMS/api/EngagementCheck/views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated

# TMS models import
from TMS import models as tms_models
from TMS.api.mt_availibilityV2.serializers import AvailabilityBatchSerializer

class ParticipantStatusCheckAPI(APIView):
    """
    Unified API to check if Trainer or Beneficiary is FREE or BUSY.
    Required Parameter: ?type=trainer OR ?type=beneficiary
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        participant_type = request.query_params.get('type')

        if not participant_type or participant_type.lower() not in ['trainer', 'beneficiary']:
            return Response(
                {"error": "Please provide a valid 'type' parameter ('trainer' or 'beneficiary')."},
                status=status.HTTP_400_BAD_REQUEST
            )

        active_batch_statuses = ['DRAFT', 'PENDING', 'SCHEDULED', 'ONGOING',  'REJECTED']
        active_request_statuses = ['COMPLETED']
        # =========================================================================
        # 1. LOGIC FOR TRAINER 
        # =========================================================================
        if participant_type.lower() == 'trainer':
            trainer_id = request.query_params.get('trainer_id')
            name = request.query_params.get('name')
            mobile_no = request.query_params.get('mobile_no')

            if not any([trainer_id, name, mobile_no]):
                return Response(
                    {"error": "Please provide trainer_id, name, or mobile_no to search."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Base query for Trainers (Strictly Active)
            trainers_qs = tms_models.MasterTrainer.objects.filter(is_active=True)
            
            if trainer_id:
                trainers_qs = trainers_qs.filter(id=trainer_id)
            if name:
                trainers_qs = trainers_qs.filter(full_name__icontains=name)
            if mobile_no:
                trainers_qs = trainers_qs.filter(mobile_no__icontains=mobile_no)

            if not trainers_qs.exists():
                return Response({"success": True, "message": "No active trainer found.", "data": []}, status=status.HTTP_200_OK)

            results = []

            for trainer in trainers_qs:
                # Collect every active batch assignment, not only the first one.
                batch_engagements = list(tms_models.BatchMasterTrainer.objects.filter(
                    master_trainer=trainer,
                    is_active=True,
                    batch__is_active=True,
                    batch__status__in=active_batch_statuses
                ).select_related(
                    'batch', 'batch__centre', 'batch__training_plan', 
                    'batch__district', 'batch__block', 'batch__partner'
                ))

                # Keep the completed training-request route: a completed request
                # still engages the trainer when its linked batch is active.
                completed_request_ids = tms_models.TRTrainer.objects.filter(
                    trainer=trainer,
                    is_active=True,
                    training__is_active=True,
                    training__status__in=active_request_statuses
                ).values_list('training_id', flat=True)
                batch_engagements.extend(tms_models.BatchTrainer.objects.filter(
                    training_request_id__in=completed_request_ids,
                    trainer__trainer=trainer,
                    trainer__is_active=True,
                    training_request__status__in=active_request_statuses,
                    is_active=True,
                    is_replaced=False,
                    batch__is_active=True,
                    batch__status__in=active_batch_statuses
                ).select_related(
                    'batch', 'batch__centre', 'batch__training_plan',
                    'batch__district', 'batch__block', 'batch__partner'
                ))

                # Also include batch assignments from other request statuses.
                batch_engagements.extend(tms_models.BatchTrainer.objects.filter(
                    trainer__trainer=trainer,
                    trainer__is_active=True,
                    is_active=True,
                    is_replaced=False,
                    batch__is_active=True,
                    batch__status__in=active_batch_statuses
                ).select_related(
                    'batch', 'batch__centre', 'batch__training_plan',
                    'batch__district', 'batch__block', 'batch__partner'
                ))

                # A trainer may appear through more than one assignment path.
                batches_by_id = {}
                for engagement in batch_engagements:
                    batches_by_id.setdefault(engagement.batch_id, engagement.batch)

                batch_history = []
                for batch in sorted(
                    batches_by_id.values(),
                    key=lambda item: (item.start_date is None, item.start_date, item.id)
                ):
                    centre = batch.centre
                    training_plan_name = (
                        batch.training_plan.training_name
                        if batch.training_plan and batch.training_plan.is_active
                        else None
                    )
                    batch_data = dict(AvailabilityBatchSerializer(batch).data)
                    batch_data.update({
                        "batch_id": batch.id,
                        "batch_code": batch.code,
                        "training_plan": training_plan_name,
                        "training_plan_id": batch.training_plan_id,
                        "location": (
                            f"{centre.venue_name}, {centre.venue_address}"
                            if centre and centre.is_active
                            else "Not Mapped or Inactive Centre"
                        ),
                        "centre_details": ({
                            "id": centre.id,
                            "venue_name": centre.venue_name,
                            "venue_address": centre.venue_address,
                            "is_active": centre.is_active,
                        } if centre else None),
                        "district": (
                            getattr(batch.district, 'district_name_en', None)
                            if batch.district else None
                        ),
                        "district_id": batch.district_id,
                        "block": (
                            getattr(batch.block, 'block_name_local', None)
                            if batch.block else None
                        ),
                        "block_id": batch.block_id,
                        "training_partner": (
                            getattr(batch.partner, 'name', None)
                            if batch.partner else None
                        ),
                        "training_partner_id": batch.partner_id,
                    })
                    batch_history.append(batch_data)

                if batch_history:
                    results.append({
                        "trainer_name": trainer.full_name,
                        "trainer_id": trainer.id,
                        "mobile_no": trainer.mobile_no,
                        "is_busy": True,
                        "engaged_in": "BATCH",
                        "batch_count": len(batch_history),
                        "batch_data": batch_history[0],
                        "batch_history": batch_history,
                    })
                    continue

                # No active batch was found for this trainer ID.
                results.append({
                    "trainer_name": trainer.full_name,
                    "trainer_id": trainer.id,
                    "mobile_no": trainer.mobile_no,
                    "is_busy": False,
                    "engaged_in": None,
                    "batch_count": 0,
                    "batch_data": None,
                    "batch_history": [],
                    "message": "Trainer is completely FREE right now."
                })

            return Response({
                "success": True,
                "count": len(results),
                "data": results
            }, status=status.HTTP_200_OK)


        # =========================================================================
        # 2. LOGIC FOR BENEFICIARY 
        # =========================================================================
        elif participant_type.lower() == 'beneficiary':
            membercode = request.query_params.get('membercode')
            name = request.query_params.get('name')
            mobile_no = request.query_params.get('mobile_no')
           
            
            if not any([membercode, name, mobile_no]):
                return Response(
                    {"error": "Please provide membercode, name, mobile_no, or pld_status to search."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Fetch matching beneficiaries from Active TRBeneficiary
            bens_qs = tms_models.TRBeneficiary.objects.filter(is_active=True)
            if membercode:
                bens_qs = bens_qs.filter(lokos_member_code__icontains=membercode)
            if name:
                bens_qs = bens_qs.filter(member_name__icontains=name)
            if mobile_no:
                bens_qs = bens_qs.filter(mobile__icontains=mobile_no)
            

            unique_bens = {}
            for b in bens_qs:
                unique_bens[b.lokos_member_code] = {
                    "name": b.member_name,
                    "mobile": b.mobile
                }

            if not unique_bens:
                return Response({"success": True, "message": "No active Beneficiary found.", "data": []}, status=status.HTTP_200_OK)

            results = []

            for code, info in unique_bens.items():
                member_name = info["name"]
                mobile = info["mobile"]
                

                # Step A: Check Active Batch Engagement
                batch_eng = tms_models.BatchBeneficiary.objects.filter(
                    beneficiary__lokos_member_code=code,
                    is_active=True,
                    beneficiary__is_active=True,
                    batch__is_active=True,
                    batch__status__in=active_batch_statuses
                ).select_related(
                    'batch', 'batch__centre', 'batch__training_plan',
                    'batch__district', 'batch__block', 'batch__partner'
                ).first()

                if batch_eng:
                    batch = batch_eng.batch
                    centre = batch.centre
                    results.append({
                        "member_name": member_name,
                        "lokos_member_code": code,
                        "mobile_no": mobile,
                        "is_busy": True,
                        "engaged_in": "BATCH",
                        "attendance_status": "NOT_MARKED_YET" if batch.status == 'ONGOING' else "N/A",
                        "batch_data": {
                            "batch_id": batch.id,
                            "batch_code": batch.code,
                            "status": batch.status,
                            "start_date": batch.start_date,
                            "end_date": batch.end_date,
                            "time_of_training": batch.time_of_training,
                            "batch_type": batch.batch_type,
                            "level": batch.level,
                            "participant_type": batch.participant_type,
                            "financial_year": batch.financial_year,
                            "location": f"{centre.venue_name}, {centre.venue_address}" if (centre and centre.is_active) else "Not Mapped or Inactive Centre",
                            "training_plan": batch.training_plan.training_name if (batch.training_plan and batch.training_plan.is_active) else None,
                            "district": getattr(batch.district, 'district_name_en', None) if batch.district else None,
                            "block": getattr(batch.block, 'block_name_local', None) if batch.block else None,
                            "training_partner": getattr(batch.partner, 'name', None) if batch.partner else None,
                        }
                    })
                    continue

                # Step B: No active batch engagement was found.
                results.append({
                    "member_name": member_name,
                    "lokos_member_code": code,
                    "mobile_no": mobile,
                    "is_busy": False,
                    "engaged_in": None,
                    "attendance_status": "N/A",
                    "message": "Candidate is completely FREE right now."
                })

            return Response({
                "success": True,
                "count": len(results),
                "data": results
            }, status=status.HTTP_200_OK)