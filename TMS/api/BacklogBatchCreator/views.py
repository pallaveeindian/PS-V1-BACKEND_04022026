import json
import decimal
from django.http import StreamingHttpResponse
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from django.db import transaction
from django.utils import timezone

from core.models import (
    MasterDistrict, MasterBlock
)

from TMS.models import (
    Batch, TrainingPlan, TrainingPartner, TrainingPartnerCentre,
    TrainingRequest, TRBeneficiary, TRTrainer, TRStaff, MasterTrainer,
    BatchBeneficiary, BatchTrainer, BatchStaff, BatchMasterTrainer,
    BatchBlockCoverage, BatchEkycVerification, BatchSchedule, BatchAttendance,
    ParticipantAttendance, BeneficiaryAttendanceSummary, TPBatchCostBreakup, BatchCost
)

class BacklogBatchOneShotAPIView(APIView):
    """
    API to create a complete Backlog (Offline) Batch in a single transaction.
    Requires is_old=True for the source Training Request.
    Streams progress updates back to the frontend using Server-Sent Events (SSE).
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        # We extract data here to avoid passing the whole request object into the generator
        data = request.data
        user = request.user
        now = timezone.now()

        def stream_response():
            try:
                with transaction.atomic():
                    # --- STEP 1 ---
                    yield f"data: {json.dumps({'status': 'progress', 'step': 'Extracting Base Batch Data...'})}\n\n"
                    
                    training_plan_id = data.get('training_plan_id')
                    district_id = data.get('district_id')
                    blocks_raw = str(data.get('block_id', ''))
                    blocks_list = [b.strip() for b in blocks_raw.split(',') if b.strip()]
                    primary_block_id = blocks_list[0] if blocks_list else None
                    
                    partner_id = data.get('partner_id')
                    centre_id = data.get('centre_id')
                    participant_type = data.get('participant_type')

                    training_plan = TrainingPlan.objects.select_related('theme').get(id=training_plan_id)
                    total_days = training_plan.no_of_days or 0

                    # --- STEP 2 ---
                    yield f"data: {json.dumps({'status': 'progress', 'step': 'Creating Batch rows...'})}\n\n"
                    
                    batch = Batch.objects.create(
                        training_plan=training_plan,
                        district_id=district_id,
                        block_id=primary_block_id,
                        partner_id=partner_id,
                        centre_id=centre_id,
                        level=data.get('level'),
                        participant_type=participant_type,
                        batch_type=data.get('batch_type'),
                        status='REVIEW',
                        is_old=True,
                        start_date=data.get('start_date'),
                        end_date=data.get('end_date'),
                        time_of_training=data.get('time_of_training'),
                        financial_year=data.get('financial_year'),
                        created_by=user
                    )

                    # --- STEP 3 ---
                    yield f"data: {json.dumps({'status': 'progress', 'step': 'Mapping Block Coverages...'})}\n\n"
                    
                    for b_id in blocks_list:
                        BatchBlockCoverage.objects.create(batch=batch, block_id=b_id)

                    # --- STEP 4 ---
                    yield f"data: {json.dumps({'status': 'progress', 'step': 'Creating Participant rows...'})}\n\n"
                    
                    p_ids = [pid.strip() for pid in str(data.get('tr_participant_ids', '')).split(',') if pid.strip()]
                    trainee_map = {}  

                    if participant_type == 'BENEFICIARY':
                        trs = TRBeneficiary.objects.filter(id__in=p_ids, training__is_old=True).select_related('training', 'beneficiary')
                        if trs.count() != len(p_ids):
                            raise ValueError("One or more TRBeneficiaries are invalid or do not belong to an is_old=True Training Request.")
                        for tr in trs:
                            bb = BatchBeneficiary.objects.create(batch=batch, beneficiary=tr, training_request=tr.training)
                            trainee_map[str(tr.id)] = bb

                    elif participant_type == 'TRAINER':
                        trs = TRTrainer.objects.filter(id__in=p_ids, training__is_old=True).select_related('training')
                        if trs.count() != len(p_ids):
                            raise ValueError("One or more TRTrainers are invalid or do not belong to an is_old=True Training Request.")
                        for tr in trs:
                            bt = BatchTrainer.objects.create(batch=batch, trainer=tr, training_request=tr.training)
                            trainee_map[str(tr.id)] = bt

                    elif participant_type == 'STAFF':
                        trs = TRStaff.objects.filter(id__in=p_ids, training__is_old=True).select_related('training')
                        if trs.count() != len(p_ids):
                            raise ValueError("One or more TRStaff are invalid or do not belong to an is_old=True Training Request.")
                        for tr in trs:
                            bs = BatchStaff.objects.create(batch=batch, staff=tr, training_request=tr.training)
                            trainee_map[str(tr.id)] = bs

                    # --- STEP 5 ---
                    yield f"data: {json.dumps({'status': 'progress', 'step': 'Creating Master Trainer rows...'})}\n\n"
                    
                    mt_ids = [mid.strip() for mid in str(data.get('master_trainer_ids', '')).split(',') if mid.strip()]
                    mts = MasterTrainer.objects.filter(id__in=mt_ids)
                    trainer_map = {}  
                    for mt in mts:
                        bmt = BatchMasterTrainer.objects.create(batch=batch, master_trainer=mt, participated=True)
                        trainer_map[str(mt.id)] = bmt

                    # --- STEP 6 ---
                    yield f"data: {json.dumps({'status': 'progress', 'step': 'Auto-verifying EKYC...'})}\n\n"
                    
                    for src_id, obj in trainee_map.items():
                        BatchEkycVerification.objects.create(
                            batch=batch, participant_id=str(obj.id), participant_role='trainee',
                            ekyc_status='VERIFIED', verified_on=now, remarks='OFFLINE BACKLOG AUTO-VERIFIED'
                        )
                    for src_id, obj in trainer_map.items():
                        BatchEkycVerification.objects.create(
                            batch=batch, participant_id=str(obj.id), participant_role='trainer',
                            ekyc_status='VERIFIED', verified_on=now, remarks='OFFLINE BACKLOG AUTO-VERIFIED'
                        )

                    # --- STEP 7 ---
                    yield f"data: {json.dumps({'status': 'progress', 'step': 'Creating Attendance rows...'})}\n\n"
                    
                    attendance_tracker = {} 
                    for day in data.get('schedules_and_attendance', []):
                        s_date = day.get('schedule_date')
                        
                        BatchSchedule.objects.create(
                            batch=batch, schedule_date=s_date, start_time=day.get('start_time'), remarks=day.get('remarks')
                        )
                        
                        batt = BatchAttendance.objects.create(batch=batch, date=s_date)

                        for att in day.get('attendance', []):
                            role = att.get('role')
                            src_id = str(att.get('source_id'))
                            is_present = att.get('present', False)

                            p_obj = None
                            p_name = "Unknown"
                            actual_role = "trainee"
                            
                            if role == 'trainee':
                                p_obj = trainee_map.get(src_id)
                                if p_obj:
                                    actual_role = 'trainee'
                                    if participant_type == 'BENEFICIARY':
                                        p_name = getattr(p_obj.beneficiary, 'member_name', "Unknown")
                                    elif participant_type == 'TRAINER':
                                        p_name = getattr(p_obj.trainer, 'full_name', getattr(p_obj.trainer, 'member_name', "Unknown"))
                                    elif participant_type == 'STAFF':
                                        p_name = getattr(p_obj.staff, 'full_name', "Unknown")
                            elif role == 'trainer':
                                p_obj = trainer_map.get(src_id)
                                if p_obj:
                                    actual_role = 'trainer'
                                    p_name = getattr(p_obj.master_trainer, 'full_name', "Unknown")

                            if p_obj:
                                p_id_str = str(p_obj.id)
                                ParticipantAttendance.objects.create(
                                    attendance=batt, participant_id=p_id_str, participant_name=p_name,
                                    participant_role=actual_role, present=is_present
                                )
                                if is_present:
                                    attendance_tracker[p_id_str] = attendance_tracker.get(p_id_str, 0) + 1

                    # --- STEP 8 ---
                    yield f"data: {json.dumps({'status': 'progress', 'step': 'Applying Attendance Rules & Summaries...'})}\n\n"
                    
                    MIN_ATTENDANCE_REQ = {
                        1: 1, 2: 2, 3: 3, 4: 3, 5: 4, 6: 5, 7: 6, 8: 7, 9: 7,
                        10: 8, 11: 9, 12: 10, 13: 11, 14: 12, 15: 12
                    }
                    required_days = MIN_ATTENDANCE_REQ.get(total_days, max(1, int(total_days * 0.8)))

                    def create_summary(obj, field_name, is_trainee=True):
                        p_id_str = str(obj.id)
                        present_days = attendance_tracker.get(p_id_str, 0)
                        attendance_percentage = min((present_days / total_days) * 100, 100.0) if total_days > 0 else 0.0
                        is_successful = (present_days >= required_days)
                        
                        if is_trainee:
                            obj.attended = is_successful
                            obj.save(update_fields=['attended'])
                            underlying = getattr(obj, field_name.split('_')[1], None) 
                            if underlying:
                                underlying.attended = is_successful
                                underlying.save(update_fields=['attended'])

                        defaults = {
                            'batch': batch,
                            'total_training_days': total_days,
                            'days_present': present_days,
                            'attendance_percentage': decimal.Decimal(attendance_percentage),
                            'is_dropout': False, 
                            'is_successful': is_successful
                        }
                        if is_trainee:
                            defaults['training_request'] = obj.training_request

                        kwargs = {field_name: obj}
                        BeneficiaryAttendanceSummary.objects.create(**kwargs, **defaults)

                    if participant_type == 'BENEFICIARY':
                        for obj in trainee_map.values(): create_summary(obj, 'batch_beneficiary', True)
                    elif participant_type == 'TRAINER':
                        for obj in trainee_map.values(): create_summary(obj, 'batch_trainer', True)
                    elif participant_type == 'STAFF':
                        for obj in trainee_map.values(): create_summary(obj, 'batch_staff', True)

                    for obj in trainer_map.values():
                        create_summary(obj, 'batch_master_trainer', False)

                    # --- STEP 9 ---
                    yield f"data: {json.dumps({'status': 'progress', 'step': 'Calculating Final Costs...'})}\n\n"
                    
                    for cost in data.get('participant_costs', []):
                        role = cost.get('role')
                        src_id = str(cost.get('source_id'))
                        
                        if role == 'trainee':
                            p_obj = trainee_map.get(src_id)
                            if p_obj and getattr(p_obj, 'attended', False):
                                TPBatchCostBreakup.objects.create(
                                    batch=batch,
                                    batch_beneficiary=p_obj if participant_type == 'BENEFICIARY' else None,
                                    batch_trainer=p_obj if participant_type == 'TRAINER' else None,
                                    batch_staff=p_obj if participant_type == 'STAFF' else None,
                                    participant_type=participant_type,
                                    ta_da=cost.get('ta_da', 0),
                                    total_cost=cost.get('total_cost', 0)
                                )
                        elif role == 'trainer':
                            p_obj = trainer_map.get(src_id)
                            summary = BeneficiaryAttendanceSummary.objects.filter(batch_master_trainer=p_obj).first()
                            if p_obj and summary and summary.is_successful:
                                TPBatchCostBreakup.objects.create(
                                    batch=batch,
                                    batch_mastertrainer=p_obj,
                                    participant_type='MASTER_TRAINER',
                                    ta_da=cost.get('ta_da', 0),
                                    total_cost=cost.get('total_cost', 0)
                                )

                    bc = data.get('batch_cost', {})
                    BatchCost.objects.create(
                        batch=batch,
                        is_field_visit=bc.get('is_field_visit', False),
                        field_visit_cost=bc.get('field_visit_cost', 0),
                        grand_total_cost=bc.get('grand_total_cost', 0)
                    )

                    # --- SUCCESS YIELD ---
                    yield f"data: {json.dumps({'status': 'success', 'message': 'Backlog Batch created successfully.', 'batch_code': batch.code, 'batch_id': batch.id})}\n\n"

            except TrainingPlan.DoesNotExist:
                yield f"data: {json.dumps({'status': 'error', 'message': 'Training Plan not found.'})}\n\n"
            except ValueError as e:
                yield f"data: {json.dumps({'status': 'error', 'message': str(e)})}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'status': 'error', 'message': f'An error occurred: {str(e)}'})}\n\n"

        # Return the generator directly as a Streaming Response over SSE
        return StreamingHttpResponse(stream_response(), content_type='text/event-stream')