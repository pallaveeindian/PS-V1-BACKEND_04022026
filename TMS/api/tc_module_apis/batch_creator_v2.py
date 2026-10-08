from django.db import transaction
from django.db.models import Count, Q
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from core.models import MasterUser
from TMS.models import *

class CreateOneShotBatchAPIView(APIView):
    """
    Creates a Batch and maps participants in a single atomic transaction.
    STRICTLY checks past successful completion history and active date overlaps 
    BEFORE initiating the transaction.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        data = request.data
        
        participant_type = data.get("participant_type", "").upper()
        batch_type = data.get("batch_type", "").upper()
        district_tp_user_id = data.get("district_tp_user_id")
        
        if participant_type not in ["BENEFICIARY", "TRAINER", "STAFF"]:
            return Response({"error": "Invalid participant_type."}, status=status.HTTP_400_BAD_REQUEST)
        if batch_type not in ["SEPARATE", "COMBINED"]:
            return Response({"error": "Invalid batch_type."}, status=status.HTTP_400_BAD_REQUEST)
            
        if participant_type == "STAFF" and batch_type != "SEPARATE":
            return Response({"error": "STAFF batches must be SEPARATE batches."}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            user = MasterUser.objects.get(username=request.user.username)
        except MasterUser.DoesNotExist:
            return Response({"error": "Authenticated MasterUser not found."}, status=status.HTTP_403_FORBIDDEN)

        # Flatten participant IDs and construct mapping structure
        all_participant_ids = []
        parsed_mappings = [] 
        
        if batch_type == "SEPARATE":
            p_ids = data.get("participant_ids", [])
            block_id = data.get("block_id")
            if not p_ids or (not block_id and participant_type not in ["TRAINER", "STAFF"]):
                return Response({"error": "SEPARATE batch requires 'participant_ids'. 'block_id' is required unless participant_type is TRAINER or STAFF."}, status=status.HTTP_400_BAD_REQUEST)
            all_participant_ids = [int(pid) for pid in p_ids]
            
            final_block_id = None if participant_type == "STAFF" else block_id
            
            for pid in all_participant_ids:
                parsed_mappings.append({'p_id': pid, 'block_id': final_block_id})
                
        elif batch_type == "COMBINED":
            blocks_data = data.get("blocks", [])
            if not blocks_data:
                return Response({"error": "COMBINED batch requires 'blocks' array."}, status=status.HTTP_400_BAD_REQUEST)
                
            for b in blocks_data:
                b_id = b.get("block_id")
                for tr in b.get("training_requests", []):
                    for pid in tr.get("participant_ids", []):
                        pid_int = int(pid)
                        all_participant_ids.append(pid_int)
                        parsed_mappings.append({'p_id': pid_int, 'block_id': b_id})

        if not all_participant_ids:
            return Response({"error": "No participants provided."}, status=status.HTTP_400_BAD_REQUEST)

        if participant_type == "BENEFICIARY":
            ParticipantModel = TRBeneficiary
        elif participant_type == "TRAINER":
            ParticipantModel = TRTrainer
        else:
            ParticipantModel = TRStaff

		# =====================================================================
        # PRE-TRANSACTION STRICT ENGAGEMENT & HISTORY CHECK
        # =====================================================================
        new_start = data.get("start_date")
        new_end = data.get("end_date")
        fin_year = data.get("financial_year")
        plan_id = data.get("training_plan_id")
        
        active_statuses = ['DRAFT', 'PENDING', 'SCHEDULED', 'ONGOING', 'REJECTED']
        engaged_rows = []

        if participant_type == "BENEFICIARY":
            participants = TRBeneficiary.objects.filter(id__in=all_participant_ids, is_active=True)
            for p in participants:
                is_engaged = False
                engage_reason = ""
                overlap_data = None
                
                # Check 1: Already successful in this plan + year
                if fin_year and plan_id:
                    already_done = BeneficiaryAttendanceSummary.objects.filter(
                        is_active=True,
                        is_successful=True,
                        batch_beneficiary__beneficiary__lokos_shg_code=p.lokos_shg_code,
                        batch_beneficiary__beneficiary__lokos_member_code=p.lokos_member_code,
                        training_request__training_plan_id=plan_id,
                        training_request__financial_year=fin_year
                    ).exists()
                    if already_done:
                        is_engaged = True
                        engage_reason = "Already successfully completed this training plan in this financial year."

                # Check 2: Date overlap in active batches
                if not is_engaged and new_start and new_end:
                    # SURGICAL FIX 2: Removed .exclude() (not needed in create) & fixed .values() keys
                    overlap_data = BatchBeneficiary.objects.filter(
                        is_active=True,
                        beneficiary__lokos_shg_code=p.lokos_shg_code,
                        beneficiary__lokos_member_code=p.lokos_member_code,
                        batch__is_active=True,
                        batch__status__in=active_statuses,
                        batch__start_date__lte=new_end,
                        batch__end_date__gte=new_start
                    ).values("batch_id", "batch__code").first()
                    
                    if overlap_data:
                        is_engaged = True
                        engage_reason = f"Overlapping dates with an active batch."

                if is_engaged:
                    row = {
                        "id": p.id,
                        "name": p.member_name,
                        "lokos_shg_code": p.lokos_shg_code,
                        "lokos_member_code": p.lokos_member_code,
                        "reason": engage_reason
                    }
                    if overlap_data:
                        row["batch_id"] = overlap_data["batch_id"]
                        row["batch_code"] = overlap_data["batch__code"]
                    engaged_rows.append(row)

        elif participant_type == "TRAINER":
            participants = TRTrainer.objects.filter(id__in=all_participant_ids, is_active=True)
            for p in participants:
                if not p.trainer or not p.trainer.mobile_no:
                    continue
                mobile = p.trainer.mobile_no
                is_engaged = False
                engage_reason = ""
                overlap_data = None

                # Check 1: Already successful
                if fin_year and plan_id:
                    done_tr = BeneficiaryAttendanceSummary.objects.filter(
                        is_active=True, is_successful=True,
                        batch_trainer__trainer__trainer__mobile_no=mobile,
                        training_request__training_plan_id=plan_id,
                        training_request__financial_year=fin_year
                    ).exists()
                    done_mt = BeneficiaryAttendanceSummary.objects.filter(
                        is_active=True, is_successful=True,
                        batch_master_trainer__master_trainer__mobile_no=mobile,
                        training_request__training_plan_id=plan_id,
                        training_request__financial_year=fin_year
                    ).exists()
                    
                    if done_tr or done_mt:
                        is_engaged = True
                        engage_reason = "Already successfully completed this training plan in this financial year."

                # Check 2: Date Overlap
                if not is_engaged and new_start and new_end:
                    overlap_data = BatchTrainer.objects.filter(
                        is_active=True,
                        trainer__trainer__mobile_no=mobile,
                        batch__is_active=True,
                        batch__status__in=active_statuses,
                        batch__start_date__lte=new_end,
                        batch__end_date__gte=new_start
                    ).values("batch_id", "batch__code").first()

                    if not overlap_data:
                        overlap_data = BatchMasterTrainer.objects.filter(
                            is_active=True,
                            master_trainer__mobile_no=mobile,
                            batch__is_active=True,
                            batch__status__in=active_statuses,
                            batch__start_date__lte=new_end,
                            batch__end_date__gte=new_start
                        ).values("batch_id", "batch__code").first()

                    if overlap_data:
                        is_engaged = True
                        engage_reason = "Overlapping dates with an active batch."

                if is_engaged:
                    row = {
                        "id": p.id,
                        "name": p.full_name,
                        "mobile_no": mobile,
                        "reason": engage_reason
                    }
                    if overlap_data:
                        row["batch_id"] = overlap_data["batch_id"]
                        row["batch_code"] = overlap_data["batch__code"]
                    engaged_rows.append(row)

        elif participant_type == "STAFF":
            participants = TRStaff.objects.filter(id__in=all_participant_ids, is_active=True)
            for p in participants:
                if not p.staff or not p.staff.employee_id:
                    continue
                emp_id = p.staff.employee_id
                is_engaged = False
                engage_reason = ""
                overlap_data = None

                # Check 1: Already successful
                if fin_year and plan_id:
                    already_done = BeneficiaryAttendanceSummary.objects.filter(
                        is_active=True,
                        is_successful=True,
                        batch_staff__staff__staff__employee_id=emp_id,
                        training_request__training_plan_id=plan_id,
                        training_request__financial_year=fin_year
                    ).exists()
                    if already_done:
                        is_engaged = True
                        engage_reason = "Already successfully completed this training plan in this financial year."

                # Check 2: Date Overlap
                if not is_engaged and new_start and new_end:
                    overlap_data = BatchStaff.objects.filter(
                        is_active=True,
                        staff__staff__employee_id=emp_id,
                        batch__is_active=True,
                        batch__status__in=active_statuses,
                        batch__start_date__lte=new_end,
                        batch__end_date__gte=new_start
                    ).values("batch_id", "batch__code").first()
                    
                    if overlap_data:
                        is_engaged = True
                        engage_reason = "Overlapping dates with an active batch."

                if is_engaged:
                    row = {
                        "id": p.id,
                        "name": p.full_name,
                        "employee_id": emp_id,
                        "reason": engage_reason
                    }
                    if overlap_data:
                        row["batch_id"] = overlap_data["batch_id"]
                        row["batch_code"] = overlap_data["batch__code"]
                    engaged_rows.append(row)

        # Halt immediately if ANY participant fails validation
        if engaged_rows:
            return Response({
                "error": "One or more participants are already engaged or have successfully completed this training.",
                "engaged_participants": engaged_rows
            }, status=status.HTTP_409_CONFLICT)
        # =====================================================================

        # BEGIN ATOMIC TRANSACTION
        try:
            with transaction.atomic():
                
                # 1. Resolve Partner
                try:
                    dtp = DistrictTP.objects.select_related('partner').get(master_user_id=district_tp_user_id)
                    partner = dtp.partner
                except DistrictTP.DoesNotExist:
                    try:
                        partner = TrainingPartner.objects.get(master_user_id=district_tp_user_id)
                    except TrainingPartner.DoesNotExist:
                        raise ValueError(f"Neither DistrictTP nor TrainingPartner found for user ID: {district_tp_user_id}")

                # Fetch all valid participants from DB to ensure they exist
                participants_db = ParticipantModel.objects.filter(id__in=all_participant_ids)
                if participants_db.count() != len(all_participant_ids):
                    raise ValueError("One or more participant IDs provided do not exist in the database.")

                # Prevent Duplicate Candidates in a Single Batch
                if participant_type == "BENEFICIARY":
                    identifiers = list(ParticipantModel.objects.filter(id__in=all_participant_ids)
                                       .exclude(lokos_member_code__in=[None, ""])
                                       .values_list('lokos_member_code', flat=True))
                elif participant_type == "TRAINER":
                    identifiers = list(ParticipantModel.objects.filter(id__in=all_participant_ids)
                                       .exclude(trainer__master_user_id__isnull=True)
                                       .values_list('trainer__master_user_id', flat=True))
                elif participant_type == "STAFF":
                    identifiers = list(ParticipantModel.objects.filter(id__in=all_participant_ids)
                                       .exclude(staff__employee_id__in=[None, ""])
                                       .values_list('staff__employee_id', flat=True))
                else:
                    identifiers = []

                if len(identifiers) != len(set(identifiers)):
                    raise ValueError(f"Duplicate Candidate Detected: A {participant_type.capitalize()} is repeated in this batch based on their unique identifier.")

                p_db_map = {p.id: p for p in participants_db}
                
                batch_block_id = data.get("block_id") if batch_type == "SEPARATE" else None
                if participant_type == "STAFF":
                    batch_block_id = None

                # 3. Create the Batch
                batch = Batch.objects.create(
                    training_plan_id=data.get("training_plan_id"),
                    partner=partner,
                    participant_type=participant_type,
                    centre_id=data.get("centre_id"),
                    district_id=data.get("district_id"),
                    block_id=batch_block_id,
                    batch_type=batch_type,
                    level=data.get("level", "BLOCK"),
                    status=data.get("status", "DRAFT"),
                    financial_year=data.get("financial_year"),
                    start_date=data.get("start_date"),
                    end_date=data.get("end_date"),
                    created_by=user
                )

                touched_tr_ids = set()
                combined_block_counts = {}

                # 4. Create Batch Participants & Traceability Mappings
                for mapping in parsed_mappings:
                    p_id = mapping['p_id']
                    p_obj = p_db_map[p_id]
                    
                    tr_id = p_obj.training_id
                    touched_tr_ids.add(tr_id)
                    
                    if batch_type == "COMBINED":
                        b_id = mapping['block_id']
                        combined_block_counts[b_id] = combined_block_counts.get(b_id, 0) + 1

                    if participant_type == "BENEFICIARY":
                        BatchBeneficiary.objects.create(batch=batch, beneficiary=p_obj, training_request_id=tr_id)
                    elif participant_type == "TRAINER":
                        BatchTrainer.objects.create(batch=batch, trainer=p_obj, training_request_id=tr_id)
                    elif participant_type == "STAFF":
                        BatchStaff.objects.create(batch=batch, staff=p_obj, training_request_id=tr_id)

                # 5. Create BatchBlockCoverage for COMBINED batches
                if batch_type == "COMBINED":
                    true_block_counts = {}
                    for p_obj in participants_db:
                        blk_id = p_obj.block_id or getattr(p_obj.training, 'block_id', None)
                        if blk_id:
                            true_block_counts[blk_id] = true_block_counts.get(blk_id, 0) + 1
                    
                    for blk_id, count in true_block_counts.items():
                        BatchBlockCoverage.objects.create(
                            batch=batch,
                            block_id=blk_id,
                            participant_count=count
                        )
                        
                # 6. Flag Participants as Selected
                ParticipantModel.objects.filter(id__in=all_participant_ids).update(CB_selected=True)

                # 7. Evaluate and Update Training Request Statuses
                for tr_id in touched_tr_ids:
                    total_p = ParticipantModel.objects.filter(training_id=tr_id).count()
                    selected_p = ParticipantModel.objects.filter(training_id=tr_id, CB_selected=True).count()
                    
                    if total_p > 0 and total_p == selected_p:
                        TrainingRequest.objects.filter(id=tr_id).update(status="COMPLETED")

            return Response({
                "message": f"Successfully created {batch_type} Batch.",
                "batch_id": batch.id,
                "batch_code": batch.code,
                "participants_added": len(all_participant_ids)
            }, status=status.HTTP_201_CREATED)

        except ValueError as ve:
            return Response({"error": str(ve)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"error": f"Internal Server Error: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class OneShotUpdateBatchAPIView(APIView):
    """
    Updates a Batch and its participant mappings atomically.
    STRICTLY checks past successful completion history and active date overlaps 
    BEFORE initiating the transaction, excluding the current batch being updated.
    """
    permission_classes = [IsAuthenticated]

    def put(self, request, batch_id, *args, **kwargs):
        data = request.data
        
        participant_type = data.get("participant_type", "").upper()
        batch_type = data.get("batch_type", "").upper()
        district_tp_user_id = data.get("district_tp_user_id")
        
        if participant_type not in ["BENEFICIARY", "TRAINER", "STAFF"]:
            return Response({"error": "Invalid participant_type."}, status=status.HTTP_400_BAD_REQUEST)
        if batch_type not in ["SEPARATE", "COMBINED"]:
            return Response({"error": "Invalid batch_type."}, status=status.HTTP_400_BAD_REQUEST)
        if participant_type == "STAFF" and batch_type != "SEPARATE":
            return Response({"error": "STAFF batches must be SEPARATE batches."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = MasterUser.objects.get(username=request.user.username)
        except MasterUser.DoesNotExist:
            return Response({"error": "Authenticated MasterUser not found."}, status=status.HTTP_403_FORBIDDEN)

        batch = get_object_or_404(Batch, id=batch_id)

        all_participant_ids = []
        parsed_mappings = []
        
        if batch_type == "SEPARATE":
            p_ids = data.get("participant_ids", [])
            block_id = data.get("block_id")
            if not p_ids or (not block_id and participant_type not in ["TRAINER", "STAFF"]):
                return Response({"error": "SEPARATE batch requires 'participant_ids'. 'block_id' is required unless participant_type is TRAINER or STAFF."}, status=status.HTTP_400_BAD_REQUEST)
            all_participant_ids = [int(pid) for pid in p_ids]
            
            final_block_id = None if participant_type == "STAFF" else block_id
            
            for pid in all_participant_ids:
                parsed_mappings.append({'p_id': pid, 'tr_id': None, 'block_id': final_block_id})
                
        elif batch_type == "COMBINED":
            blocks_data = data.get("blocks", [])
            if not blocks_data:
                return Response({"error": "COMBINED batch requires 'blocks' array."}, status=status.HTTP_400_BAD_REQUEST)
                
            for b in blocks_data:
                b_id = b.get("block_id")
                for tr in b.get("training_requests", []):
                    tr_id = tr.get("tr_id")
                    for pid in tr.get("participant_ids", []):
                        pid_int = int(pid)
                        all_participant_ids.append(pid_int)
                        parsed_mappings.append({'p_id': pid_int, 'tr_id': tr_id, 'block_id': b_id})

        if not all_participant_ids:
            return Response({"error": "No participants provided."}, status=status.HTTP_400_BAD_REQUEST)

        if participant_type == "BENEFICIARY":
            ParticipantModel = TRBeneficiary
            MappingModel = BatchBeneficiary
            mapping_filter_kwarg = "beneficiary_id"
        elif participant_type == "TRAINER":
            ParticipantModel = TRTrainer
            MappingModel = BatchTrainer
            mapping_filter_kwarg = "trainer_id"
        else:
            ParticipantModel = TRStaff
            MappingModel = BatchStaff
            mapping_filter_kwarg = "staff_id"

		# =====================================================================
        # PRE-TRANSACTION STRICT ENGAGEMENT & HISTORY CHECK (EXCLUDING CURRENT BATCH)
        # =====================================================================
        new_start = data.get("start_date")
        new_end = data.get("end_date")
        fin_year = data.get("financial_year")
        plan_id = data.get("training_plan_id")
        
        active_statuses = ['DRAFT', 'PENDING', 'SCHEDULED', 'ONGOING', 'REJECTED']
        engaged_rows = []

        if participant_type == "BENEFICIARY":
            participants = TRBeneficiary.objects.filter(id__in=all_participant_ids, is_active=True)
            for p in participants:
                is_engaged = False
                engage_reason = ""
                overlap_data = None
                
                # Check 1: Already successful in this plan + year (Exclude current batch)
                if fin_year and plan_id:
                    already_done = BeneficiaryAttendanceSummary.objects.filter(
                        is_active=True,
                        is_successful=True,
                        batch_beneficiary__beneficiary__lokos_shg_code=p.lokos_shg_code,
                        batch_beneficiary__beneficiary__lokos_member_code=p.lokos_member_code,
                        training_request__training_plan_id=plan_id,
                        training_request__financial_year=fin_year
                    ).exclude(batch_id=batch_id).exists()
                    
                    if already_done:
                        is_engaged = True
                        engage_reason = "Already successfully completed this training plan in this financial year."

                # Check 2: Date overlap in active batches (Exclude current batch)
                if not is_engaged and new_start and new_end:
                    # SURGICAL FIX 3: Properly mapped .exclude(batch_id=batch_id) & .values() keys
                    overlap_data = BatchBeneficiary.objects.filter(
                        is_active=True,
                        beneficiary__lokos_shg_code=p.lokos_shg_code,
                        beneficiary__lokos_member_code=p.lokos_member_code,
                        batch__is_active=True,
                        batch__status__in=active_statuses,
                        batch__start_date__lte=new_end,
                        batch__end_date__gte=new_start
                    ).exclude(batch_id=batch_id).values("batch_id", "batch__code").first()
                    
                    if overlap_data:
                        is_engaged = True
                        engage_reason = "Overlapping dates with an active batch."

                if is_engaged:
                    row = {
                        "id": p.id,
                        "name": p.member_name,
                        "lokos_shg_code": p.lokos_shg_code,
                        "lokos_member_code": p.lokos_member_code,
                        "reason": engage_reason
                    }
                    if overlap_data:
                        row["batch_id"] = overlap_data["batch_id"]
                        row["batch_code"] = overlap_data["batch__code"]
                    engaged_rows.append(row)

        elif participant_type == "TRAINER":
            participants = TRTrainer.objects.filter(id__in=all_participant_ids, is_active=True)
            for p in participants:
                if not p.trainer or not p.trainer.mobile_no:
                    continue
                mobile = p.trainer.mobile_no
                is_engaged = False
                engage_reason = ""
                overlap_data = None

                # Check 1: Already successful
                if fin_year and plan_id:
                    done_tr = BeneficiaryAttendanceSummary.objects.filter(
                        is_active=True, is_successful=True,
                        batch_trainer__trainer__trainer__mobile_no=mobile,
                        training_request__training_plan_id=plan_id,
                        training_request__financial_year=fin_year
                    ).exclude(batch_id=batch_id).exists()
                    
                    done_mt = BeneficiaryAttendanceSummary.objects.filter(
                        is_active=True, is_successful=True,
                        batch_master_trainer__master_trainer__mobile_no=mobile,
                        training_request__training_plan_id=plan_id,
                        training_request__financial_year=fin_year
                    ).exclude(batch_id=batch_id).exists()
                    
                    if done_tr or done_mt:
                        is_engaged = True
                        engage_reason = "Already successfully completed this training plan in this financial year."

                # Check 2: Date Overlap
                if not is_engaged and new_start and new_end:
                    overlap_data = BatchTrainer.objects.filter(
                        is_active=True,
                        trainer__trainer__mobile_no=mobile,
                        batch__is_active=True,
                        batch__status__in=active_statuses,
                        batch__start_date__lte=new_end,
                        batch__end_date__gte=new_start
                    ).exclude(batch_id=batch_id).values("batch_id", "batch__code").first()

                    if not overlap_data:
                        overlap_data = BatchMasterTrainer.objects.filter(
                            is_active=True,
                            master_trainer__mobile_no=mobile,
                            batch__is_active=True,
                            batch__status__in=active_statuses,
                            batch__start_date__lte=new_end,
                            batch__end_date__gte=new_start
                        ).exclude(batch_id=batch_id).values("batch_id", "batch__code").first()

                    if overlap_data:
                        is_engaged = True
                        engage_reason = "Overlapping dates with an active batch."

                if is_engaged:
                    row = {
                        "id": p.id,
                        "name": p.full_name,
                        "mobile_no": mobile,
                        "reason": engage_reason
                    }
                    if overlap_data:
                        row["batch_id"] = overlap_data["batch_id"]
                        row["batch_code"] = overlap_data["batch__code"]
                    engaged_rows.append(row)

        elif participant_type == "STAFF":
            participants = TRStaff.objects.filter(id__in=all_participant_ids, is_active=True)
            for p in participants:
                if not p.staff or not p.staff.employee_id:
                    continue
                emp_id = p.staff.employee_id
                is_engaged = False
                engage_reason = ""
                overlap_data = None

                # Check 1: Already successful
                if fin_year and plan_id:
                    already_done = BeneficiaryAttendanceSummary.objects.filter(
                        is_active=True,
                        is_successful=True,
                        batch_staff__staff__staff__employee_id=emp_id,
                        training_request__training_plan_id=plan_id,
                        training_request__financial_year=fin_year
                    ).exclude(batch_id=batch_id).exists()
                    
                    if already_done:
                        is_engaged = True
                        engage_reason = "Already successfully completed this training plan in this financial year."

                # Check 2: Date Overlap
                if not is_engaged and new_start and new_end:
                    overlap_data = BatchStaff.objects.filter(
                        is_active=True,
                        staff__staff__employee_id=emp_id,
                        batch__is_active=True,
                        batch__status__in=active_statuses,
                        batch__start_date__lte=new_end,
                        batch__end_date__gte=new_start
                    ).exclude(batch_id=batch_id).values("batch_id", "batch__code").first()
                    
                    if overlap_data:
                        is_engaged = True
                        engage_reason = "Overlapping dates with an active batch."

                if is_engaged:
                    row = {
                        "id": p.id,
                        "name": p.full_name,
                        "employee_id": emp_id,
                        "reason": engage_reason
                    }
                    if overlap_data:
                        row["batch_id"] = overlap_data["batch_id"]
                        row["batch_code"] = overlap_data["batch__code"]
                    engaged_rows.append(row)

        if engaged_rows:
            return Response({
                "error": "One or more participants are already engaged or have successfully completed this training.",
                "engaged_participants": engaged_rows
            }, status=status.HTTP_409_CONFLICT)
        # =====================================================================

        try:
            with transaction.atomic():
                try:
                    dtp = DistrictTP.objects.select_related('partner').get(master_user_id=district_tp_user_id)
                    partner = dtp.partner
                except DistrictTP.DoesNotExist:
                    try:
                        partner = TrainingPartner.objects.get(master_user_id=district_tp_user_id)
                    except TrainingPartner.DoesNotExist:
                        raise ValueError(f"Neither DistrictTP nor TrainingPartner found for user ID: {district_tp_user_id}")

                # 2. Identify Old vs New Participants
                existing_mappings = MappingModel.objects.filter(batch=batch)
                old_p_ids = set(existing_mappings.values_list(mapping_filter_kwarg, flat=True))
                new_p_ids_set = set(all_participant_ids)

                removed_ids = old_p_ids - new_p_ids_set
                added_ids = new_p_ids_set - old_p_ids

                # Fetch all valid participants to ensure existence
                participants_db = ParticipantModel.objects.filter(id__in=all_participant_ids)
                if participants_db.count() != len(all_participant_ids):
                    raise ValueError("One or more participant IDs provided do not exist in the database.")

                # Prevent Duplicate Candidates in a Single Batch
                if participant_type == "BENEFICIARY":
                    identifiers = list(ParticipantModel.objects.filter(id__in=all_participant_ids)
                                       .exclude(lokos_member_code__in=[None, ""])
                                       .values_list('lokos_member_code', flat=True))
                elif participant_type == "TRAINER":
                    identifiers = list(ParticipantModel.objects.filter(id__in=all_participant_ids)
                                       .exclude(trainer__master_user_id__isnull=True)
                                       .values_list('trainer__master_user_id', flat=True))
                elif participant_type == "STAFF":
                    identifiers = list(ParticipantModel.objects.filter(id__in=all_participant_ids)
                                       .exclude(staff__employee_id__in=[None, ""])
                                       .values_list('staff__employee_id', flat=True))
                else:
                    identifiers = []

                if len(identifiers) != len(set(identifiers)):
                    raise ValueError(f"Duplicate Candidate Detected: A {participant_type.capitalize()} is repeated in this batch based on their unique identifier.")

                p_db_map = {p.id: p for p in participants_db}
                touched_tr_ids = set()

                # 4. Handle REMOVED Participants
                if removed_ids:
                    removed_mappings = existing_mappings.filter(**{f"{mapping_filter_kwarg}__in": removed_ids})
                    tr_ids_to_revert = set(removed_mappings.values_list("training_request_id", flat=True))
                    touched_tr_ids.update(tr_ids_to_revert)
                    
                    removed_mappings.delete()
                    ParticipantModel.objects.filter(id__in=removed_ids).update(CB_selected=False)

                batch_block_id = data.get("block_id") if batch_type == "SEPARATE" else None
                if participant_type == "STAFF":
                    batch_block_id = None

                # 5. Update Batch Details
                batch.training_plan_id = data.get("training_plan_id")
                batch.partner = partner
                batch.participant_type = participant_type
                batch.centre_id = data.get("centre_id")
                batch.district_id = data.get("district_id")
                batch.block_id = batch_block_id
                batch.batch_type = batch_type
                batch.level = data.get("level", batch.level) 
                batch.status = data.get("status", batch.status)
                batch.financial_year = data.get("financial_year")
                batch.start_date = data.get("start_date")
                batch.end_date = data.get("end_date")
                batch.updated_by = user
                batch.save()

                # 6. Rebuild Mappings & Coverages
                BatchBlockCoverage.objects.filter(batch=batch).delete()
                combined_block_counts = {}

                for mapping in parsed_mappings:
                    p_id = mapping['p_id']
                    
                    if p_id in added_ids:
                        p_obj = p_db_map[p_id]
                        tr_id = mapping['tr_id'] or p_obj.training_id
                        touched_tr_ids.add(tr_id)
                        
                        if participant_type == "BENEFICIARY":
                            MappingModel.objects.create(batch=batch, beneficiary=p_obj, training_request_id=tr_id)
                        elif participant_type == "TRAINER":
                            MappingModel.objects.create(batch=batch, trainer=p_obj, training_request_id=tr_id)
                        elif participant_type == "STAFF":
                            MappingModel.objects.create(batch=batch, staff=p_obj, training_request_id=tr_id)
                    else:
                        p_obj = p_db_map[p_id]
                        tr_id = mapping['tr_id'] or p_obj.training_id
                        touched_tr_ids.add(tr_id)

                    if batch_type == "COMBINED":
                        b_id = mapping['block_id']
                        combined_block_counts[b_id] = combined_block_counts.get(b_id, 0) + 1

                # 7. Create New BatchBlockCoverage for COMBINED batches
                if batch_type == "COMBINED":
                    for blk_id, count in combined_block_counts.items():
                        BatchBlockCoverage.objects.create(batch=batch, block_id=blk_id, participant_count=count)

                # 8. Flag NEW Participants as Selected
                if added_ids:
                    ParticipantModel.objects.filter(id__in=added_ids).update(CB_selected=True)

                # 9. Evaluate and Update Training Request Statuses
                for tr_id in touched_tr_ids:
                    if not tr_id:
                        continue
                    total_p = ParticipantModel.objects.filter(training_id=tr_id).count()
                    selected_p = ParticipantModel.objects.filter(training_id=tr_id, CB_selected=True).count()
                    
                    if total_p > 0 and total_p == selected_p:
                        TrainingRequest.objects.filter(id=tr_id).update(status="COMPLETED")
                    else:
                        TrainingRequest.objects.filter(id=tr_id).update(status="BATCHING")

            return Response({
                "message": "Batch updated successfully.",
                "batch_id": batch.id,
                "participants_total": len(all_participant_ids)
            }, status=status.HTTP_200_OK)

        except ValueError as ve:
            return Response({"error": str(ve)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"error": f"Internal Server Error: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class OneShotDeleteBatchAPIView(APIView):
    """
    Deletes a Batch atomically.
    Reverts all associated participants' CB_selected flags to False.
    Reverts all associated Training Requests to BATCHING.
    Clears BatchBlockCoverage automatically.
    Soft deletes associated Master Trainers.
    Prevents deletion if any eKYC records exist.
    """
    permission_classes = [IsAuthenticated]

    def delete(self, request, batch_id, *args, **kwargs):
        try:
            user = MasterUser.objects.get(username=request.user.username)
        except MasterUser.DoesNotExist:
            return Response({"error": "Authenticated MasterUser not found."}, status=status.HTTP_403_FORBIDDEN)

        batch = get_object_or_404(Batch, id=batch_id)

        # SURGICAL ADDITION: Block deletion if eKYC verification records exist
        if BatchEkycVerification.objects.filter(batch=batch, is_active=True).exists():
            return Response(
                {"error": "Batch cannot be deleted because it contains eKYC verification records."}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            with transaction.atomic():
                b_bens = BatchBeneficiary.objects.filter(batch=batch)
                b_trainers = BatchTrainer.objects.filter(batch=batch)
                b_staff = BatchStaff.objects.filter(batch=batch) 
                b_mtrainers = BatchMasterTrainer.objects.filter(batch=batch)
                
                touched_tr_ids = set()

                # Handle Beneficiaries
                if b_bens.exists():
                    p_ids = list(b_bens.values_list('beneficiary_id', flat=True))
                    tr_ids = list(b_bens.values_list('training_request_id', flat=True))
                    touched_tr_ids.update(tr_ids)
                    
                    # Free up participants
                    TRBeneficiary.objects.filter(id__in=p_ids).update(CB_selected=False)
                    # Hard delete mappings to clean db
                    b_bens.delete()

                # Handle Trainers
                if b_trainers.exists():
                    p_ids = list(b_trainers.values_list('trainer_id', flat=True))
                    tr_ids = list(b_trainers.values_list('training_request_id', flat=True))
                    touched_tr_ids.update(tr_ids)
                    
                    # Free up participants
                    TRTrainer.objects.filter(id__in=p_ids).update(CB_selected=False)
                    # Hard delete mappings
                    b_trainers.delete()

                # Handle Staff
                if b_staff.exists():
                    p_ids = list(b_staff.values_list('staff_id', flat=True))
                    tr_ids = list(b_staff.values_list('training_request_id', flat=True))
                    touched_tr_ids.update(tr_ids)
                    
                    # Free up participants
                    TRStaff.objects.filter(id__in=p_ids).update(CB_selected=False)
                    # Hard delete mappings
                    b_staff.delete()

                # SURGICAL ADDITION: Handle Master Trainers (Soft Deletion)
                if b_mtrainers.exists():
                    for bmt in b_mtrainers:
                        bmt.delete(by_user=user)

                # Revert Training Request Statuses
                valid_tr_ids = [tid for tid in touched_tr_ids if tid is not None]
                if valid_tr_ids:
                    TrainingRequest.objects.filter(id__in=valid_tr_ids).update(status="BATCHING")

                # Clear Coverage tracking
                BatchBlockCoverage.objects.filter(batch=batch).delete()

                # Delete the Batch (using the custom SoftDeleteMixin signature)
                batch.delete(by_user=user)

            return Response({"message": "Batch deleted and participants reverted successfully."}, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"error": f"Internal Server Error: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)