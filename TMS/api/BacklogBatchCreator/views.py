from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.db import transaction
from django.utils import timezone
from django.shortcuts import get_object_or_404
import base64                                 
from django.core.files.base import ContentFile
import decimal

from core.models import MasterUser
from TMS.models import (
    Batch, TrainingPlan, MasterDistrict, MasterBlock, TrainingPartner, TrainingPartnerCentre,
    TrainingRequest, TRBeneficiary, TRTrainer, TRStaff, MasterTrainer,
    BatchBeneficiary, BatchTrainer, BatchStaff, BatchMasterTrainer,
    BatchBlockCoverage, BatchEkycVerification, BatchSchedule, BatchAttendance,
    ParticipantAttendance, BeneficiaryAttendanceSummary, TPBatchCostBreakup, BatchCost,
    BatchMedia, BatchClosureRequest, BatchHistory
)
from .serializers import BacklogBatchOneShotSerializer

class BacklogBatchOneShotAPIView(APIView):
    """
    Creates a comprehensive Offline Backlog Batch in ONE atomic transaction.
    Enforces strict is_old=True checks, evaluates attendance rules, and manages TR closure.
    """
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        serializer = BacklogBatchOneShotSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        user = get_object_or_404(
            MasterUser,
            username=request.user.username
        )
        now = timezone.now()

        b_info = data['batch_info']
        participant_type = b_info.get('participant_type', '').upper()
        p_ids = [p['id'] for p in data['participants']]

        # ---------------------------------------------------------
        # 1. SELECT PARTICIPANT MODEL & PRIMARY CHECK (is_old=True)
        # ---------------------------------------------------------
        if participant_type == 'BENEFICIARY':
            ParticipantModel = TRBeneficiary
        elif participant_type == 'TRAINER':
            ParticipantModel = TRTrainer
        elif participant_type == 'STAFF':
            ParticipantModel = TRStaff
        else:
            return Response({"error": "Invalid participant_type."}, status=status.HTTP_400_BAD_REQUEST)

        # STRICT PRIMARY CHECK
        invalid_participants = ParticipantModel.objects.filter(id__in=p_ids, training__is_old=False)
        if invalid_participants.exists():
            return Response({
                "error": "CRITICAL: All requested participants MUST belong to a Training Request where is_old=True."
            }, status=status.HTTP_403_FORBIDDEN)

        # Fetch participants safely
        participants_db = ParticipantModel.objects.select_related('training').filter(id__in=p_ids)
        if participants_db.count() != len(p_ids):
            return Response({"error": "One or more participant IDs are invalid."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # ---------------------------------------------------------
            # 2. CREATE BATCH (Force Status = REVIEW, is_old = True)
            # ---------------------------------------------------------
            training_plan = TrainingPlan.objects.get(id=b_info.get('training_plan_id'))
            total_days = training_plan.no_of_days or 1

            batch = Batch.objects.create(
                training_plan_id=b_info.get('training_plan_id'),
                district_id=b_info.get('district_id'),
                block_id=b_info.get('block_id'),
                partner_id=b_info.get('partner_id'),
                centre_id=b_info.get('centre_id'),
                level=b_info.get('level'),
                participant_type=participant_type,
                batch_type=b_info.get('batch_type'),
                status='REVIEW',       # ALWAYS FORCED
                is_old=True,           # ALWAYS FORCED
                start_date=b_info.get('start_date'),
                end_date=b_info.get('end_date'),
                time_of_training=b_info.get('time_of_training'),
                financial_year=b_info.get('financial_year'),
                created_by=user
            )

            # ---------------------------------------------------------
            # 3. CREATE BLOCK COVERAGES
            # ---------------------------------------------------------
            for cov in data['blocks_coverage']:
                BatchBlockCoverage.objects.create(
                    batch=batch,
                    block_id=cov['block_id'],
                    participant_count=cov.get('participant_count', 0)
                )

            # ---------------------------------------------------------
            # 4. MAP & ONBOARD MASTER TRAINERS
            # ---------------------------------------------------------
            trainer_map = {} # Maps Source MT ID -> BatchMasterTrainer ID
            for mt_data in data['master_trainers']:
                bmt = BatchMasterTrainer.objects.create(
                    batch=batch, 
                    master_trainer_id=mt_data['id'], 
                    status=mt_data.get('status', 'AVAILABLE'),
                    participated=True
                )
                trainer_map[str(mt_data['id'])] = bmt

            # ---------------------------------------------------------
            # 5. MAP & ONBOARD PARTICIPANTS & UPDATE CB_SELECTED
            # ---------------------------------------------------------
            trainee_map = {} # Maps Source TR_Participant ID -> BatchParticipant Instance
            
            for p_obj in participants_db:
                p_obj.CB_selected = True
                p_obj.save(update_fields=['CB_selected'])

                if participant_type == 'BENEFICIARY':
                    bp = BatchBeneficiary.objects.create(batch=batch, beneficiary=p_obj, training_request=p_obj.training)
                    trainee_map[str(p_obj.id)] = bp
                elif participant_type == 'TRAINER':
                    bp = BatchTrainer.objects.create(batch=batch, trainer=p_obj, training_request=p_obj.training)
                    trainee_map[str(p_obj.id)] = bp
                elif participant_type == 'STAFF':
                    bp = BatchStaff.objects.create(batch=batch, staff=p_obj, training_request=p_obj.training)
                    trainee_map[str(p_obj.id)] = bp

            # ---------------------------------------------------------
            # 6. SCHEDULES, EKYC, & ATTENDANCES
            # ---------------------------------------------------------
            for sch in data['schedules']:
                BatchSchedule.objects.create(batch=batch, schedule_date=sch['schedule_date'], start_time=sch.get('start_time'), remarks=sch.get('remarks'))

            for kyc in data['ekyc_verifications']:
                # Map payload source ID to newly generated Batch Participant ID
                src_id = str(kyc['participant_id'])
                role = kyc.get('participant_role', 'trainee')
                mapped_id = str(trainee_map[src_id].id) if role == 'trainee' else str(trainer_map[src_id].id)
                
                BatchEkycVerification.objects.create(
                    batch=batch, participant_id=mapped_id, participant_role=role,
                    ekyc_status=kyc.get('ekyc_status', 'VERIFIED'), verified_on=now
                )

            attendance_tracker = {} # Track days present per mapped participant ID

            for day in data['attendances']:
                s_date = day['date']
                batt = BatchAttendance.objects.create(batch=batch, date=s_date)

                for att in day.get('participant_records', []):
                    src_id = str(att['participant_id'])
                    role = att.get('participant_role', 'trainee')
                    is_present = att.get('present', False)

                    p_obj = trainee_map.get(src_id) if role == 'trainee' else trainer_map.get(src_id)
                    if p_obj:
                        mapped_id = str(p_obj.id)
                        ParticipantAttendance.objects.create(
                            attendance=batt, participant_id=mapped_id,
                            participant_role=role, present=is_present,
                            participant_name=att.get('participant_name', 'Unknown')
                        )
                        if is_present:
                            attendance_tracker[mapped_id] = attendance_tracker.get(mapped_id, 0) + 1

                for media in day.get('media', []):
                    b64_data = media.get('file')
                    category = media.get('category', 'OTHER')
                    
                    if b64_data and ';base64,' in b64_data:
                        # Split the Base64 header from the data
                        format_str, imgstr = b64_data.split(';base64,')
                        
                        # Extract extension (e.g., 'data:image/jpeg' -> 'jpeg', 'data:application/pdf' -> 'pdf')
                        ext = format_str.split('/')[-1]
                        
                        # Generate a unique filename
                        file_name = f"media_batch_{batch.id}_{s_date}_{category}.{ext}"
                        
                        # Create Django ContentFile from decoded bytes
                        file_obj = ContentFile(base64.b64decode(imgstr), name=file_name)
                        
                        BatchMedia.objects.create(
                            batch=batch, 
                            date=s_date, 
                            category=category, 
                            file=file_obj
                        )

            # ---------------------------------------------------------
            # 7. RULES MATRIX & SUMMARIES (SUCCESS CALCULATION)
            # ---------------------------------------------------------
            MIN_ATTENDANCE_REQ = {
                1: 1, 2: 2, 3: 3, 4: 3, 5: 4, 6: 5, 7: 6, 8: 7, 9: 7,
                10: 8, 11: 9, 12: 10, 13: 11, 14: 12, 15: 12
            }
            required_days = MIN_ATTENDANCE_REQ.get(total_days, max(1, int(total_days * 0.8)))

            # SURGICAL FIX: Get a fallback TR ID to satisfy NOT NULL constraints for Master Trainers
            fallback_tr_id = participants_db[0].training_id if len(participants_db) > 0 else None

            def process_summary(obj, field_name, is_trainee=True):
                mapped_id = str(obj.id)
                present_days = attendance_tracker.get(mapped_id, 0)
                att_pct = min((present_days / total_days) * 100, 100.0) if total_days > 0 else 0.0
                is_successful = (present_days >= required_days)

                if is_trainee:
                    obj.attended = is_successful
                    obj.save(update_fields=['attended'])
                    underlying = getattr(obj, field_name.split('_')[1], None) 
                    if underlying:
                        underlying.attended = is_successful
                        underlying.save(update_fields=['attended'])

                defaults = {
                    'batch': batch, 'total_training_days': total_days, 'days_present': present_days,
                    'attendance_percentage': decimal.Decimal(att_pct), 'is_dropout': False, 'is_successful': is_successful
                }
                
                # SURGICAL FIX: Apply explicit mapping for both Trainees and Trainers
                if is_trainee:
                    defaults['training_request'] = obj.training_request
                else:
                    defaults['training_request_id'] = fallback_tr_id

                BeneficiaryAttendanceSummary.objects.create(**{field_name: obj}, **defaults)

            if participant_type == 'BENEFICIARY':
                for obj in trainee_map.values(): process_summary(obj, 'batch_beneficiary', True)
            elif participant_type == 'TRAINER':
                for obj in trainee_map.values(): process_summary(obj, 'batch_trainer', True)
            elif participant_type == 'STAFF':
                for obj in trainee_map.values(): process_summary(obj, 'batch_staff', True)

            for obj in trainer_map.values():
                process_summary(obj, 'batch_master_trainer', False)

            # ---------------------------------------------------------
            # 8. COSTS & CLOSURE
            # ---------------------------------------------------------
            for c in data['participant_costs']:
                src_id = str(c['participant_id'])
                role = c.get('participant_role', 'trainee')
                
                if role == 'trainee':
                    p_obj = trainee_map.get(src_id)
                    if p_obj and getattr(p_obj, 'attended', False): # Only successful
                        TPBatchCostBreakup.objects.create(
                            batch=batch, participant_type=participant_type,
                            batch_beneficiary=p_obj if participant_type == 'BENEFICIARY' else None,
                            batch_trainer=p_obj if participant_type == 'TRAINER' else None,
                            batch_staff=p_obj if participant_type == 'STAFF' else None,
                            ta_da=c.get('ta_da', 0), total_cost=c.get('total_cost', 0)
                        )
                elif role == 'trainer':
                    p_obj = trainer_map.get(src_id)
                    summary = BeneficiaryAttendanceSummary.objects.filter(batch_master_trainer=p_obj).first()
                    if p_obj and summary and summary.is_successful:
                        TPBatchCostBreakup.objects.create(
                            batch=batch, participant_type='MASTER_TRAINER', batch_mastertrainer=p_obj,
                            ta_da=c.get('ta_da', 0), total_cost=c.get('total_cost', 0)
                        )

            bc_data = data['batch_cost']
            bc = BatchCost.objects.create(
                batch=batch, is_field_visit=bc_data.get('is_field_visit', False),
                field_visit_cost=bc_data.get('field_visit_cost', 0),
                grand_total_cost=bc_data.get('grand_total_cost', 0)
            )

            cr_data = data['closure_request']
            BatchClosureRequest.objects.create(
                batch=batch, batch_costing=bc, certificates_issued=cr_data.get('certificates_issued', True)
            )

            # ---------------------------------------------------------
            # 9. BATCH HISTORY & TR RACE-CONDITION STATUS UPDATE
            # ---------------------------------------------------------
            BatchHistory.objects.create(
                batch=batch, status="REVIEW", 
                remarks=f"Created Backlog Batch of date {b_info.get('start_date')} by {user.username}.",
                created_by=user
            )

            # Get distinct TR IDs mapped
            tr_ids = set(p.training_id for p in participants_db)
            for tr_id in tr_ids:
                # select_for_update() prevents race conditions if multiple batches compile simultaneously
                tr = TrainingRequest.objects.select_for_update().get(id=tr_id)
                total_p = ParticipantModel.objects.filter(training_id=tr_id).count()
                selected_p = ParticipantModel.objects.filter(training_id=tr_id, CB_selected=True).count()
                
                if total_p > 0 and total_p == selected_p:
                    tr.status = "COMPLETED"
                    tr.save(update_fields=['status'])

            return Response({
                "message": "Offline Backlog Batch Processed Successfully.",
                "batch_id": batch.id,
                "batch_code": batch.code
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)