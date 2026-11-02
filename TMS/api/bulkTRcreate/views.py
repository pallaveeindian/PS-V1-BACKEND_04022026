import logging
from django.db import transaction
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from TMS.models import *
from .serializers import BulkTrainingRequestOneShotSerializer

logger = logging.getLogger(__name__)

class CreateBulkTrainingRequestOneShotAPIView(APIView):
    """
    Creates one or multiple TrainingRequests along with all of their
    respective participants (TRBeneficiary / TRTrainer / TRStaff) inside
    a single strict atomic transaction. Automatically generates requests
    for subsequent sequence steps if defined in TrainingPlanSequence.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = BulkTrainingRequestOneShotSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        tr_list_data = serializer.validated_data["training_requests"]
        request_user = request.user if getattr(request.user, "is_authenticated", False) else None

        # =================================================================
        # PRE-TRANSACTION CHECK: PARTICIPANT NOT IN ANOTHER 'BATCHING' TR
        # (Same financial_year, district, and training_plan as payload TR)
        # =================================================================
        engaged_participants = []

        for tr_data in tr_list_data:
            t_type = tr_data["training_type"]
            participants_data = tr_data["validated_participants"]
            fin_year = tr_data["financial_year"]
            district = tr_data["district"]
            base_training_plan = tr_data["training_plan"]

            if t_type == "BENEFICIARY":
                for p in participants_data:
                    member_code = p["lokos_member_code"]
                    shg_code = p.get("lokos_shg_code") or ""

                    existing_ben = TRBeneficiary.objects.filter(
                        is_active=True,
                        lokos_member_code=member_code,
                        training__is_active=True,
                        training__status="BATCHING",
                        training__financial_year=fin_year,
                        training__district=district,
                        training__training_plan=base_training_plan,
                    ).select_related("training").first()

                    if existing_ben:
                        engaged_participants.append({
                            "training_type": "BENEFICIARY",
                            "member_name": p["member_name"],
                            "lokos_shg_code": shg_code,
                            "lokos_member_code": member_code,
                            "training_request_id": existing_ben.training_id,
                            "training_plan_id": base_training_plan.id,
                            "district_id": district.district_id if district else None,
                            "financial_year": fin_year,
                            "reason": "Participant is already in an active Training Request with status BATCHING for this financial year, district, and training plan.",
                        })

            elif t_type == "TRAINER":
                for p in participants_data:
                    mt = p["trainer"]
                    mobile = p.get("mobile_no") or getattr(mt, "mobile_no", None)

                    trainer_q = Q(trainer=mt, trainer__is_active=True)
                    if mobile:
                        trainer_q |= Q(mobile_no=mobile) | Q(trainer__mobile_no=mobile, trainer__is_active=True)

                    existing_tr = TRTrainer.objects.filter(
                        trainer_q,
                        is_active=True,
                        training__is_active=True,
                        training__status="BATCHING",
                        training__financial_year=fin_year,
                        training__district=district,
                        training__training_plan=base_training_plan,
                    ).select_related("training").first()

                    if existing_tr:
                        engaged_participants.append({
                            "training_type": "TRAINER",
                            "trainer_id": mt.id,
                            "full_name": p.get("full_name") or mt.full_name or "",
                            "mobile_no": mobile or "",
                            "training_request_id": existing_tr.training_id,
                            "training_plan_id": base_training_plan.id,
                            "district_id": district.district_id if district else None,
                            "financial_year": fin_year,
                            "reason": "Participant is already in an active Training Request with status BATCHING for this financial year, district, and training plan.",
                        })

            elif t_type == "STAFF":
                for p in participants_data:
                    sp = p["staff"]
                    emp_id = getattr(sp, "employee_id", None)

                    staff_q = Q(staff=sp, staff__is_active=True)
                    if emp_id:
                        staff_q |= Q(staff__employee_id=emp_id, staff__is_active=True)

                    existing_st = TRStaff.objects.filter(
                        staff_q,
                        is_active=True,
                        training__is_active=True,
                        training__status="BATCHING",
                        training__financial_year=fin_year,
                        training__district=district,
                        training__training_plan=base_training_plan,
                    ).select_related("training").first()

                    if existing_st:
                        engaged_participants.append({
                            "training_type": "STAFF",
                            "staff_id": sp.id,
                            "full_name": p.get("full_name") or sp.full_name or "",
                            "employee_id": emp_id or "",
                            "training_request_id": existing_st.training_id,
                            "training_plan_id": base_training_plan.id,
                            "district_id": district.district_id if district else None,
                            "financial_year": fin_year,
                            "reason": "Participant is already in an active Training Request with status BATCHING for this financial year, district, and training plan.",
                        })

        if engaged_participants:
            return Response(
                {
                    "error": "One or more participants are already engaged in an active Training Request with status BATCHING for the same financial year, district, and training plan.",
                    "engaged_participants": engaged_participants,
                },
                status=status.HTTP_409_CONFLICT,
            )

        created_requests_summary = []

        try:
            # =================================================================
            # STRICT ATOMIC TRANSACTION: ALL TRs + ALL SEQUENTIAL STEPS OR NOTHING
            # =================================================================
            with transaction.atomic():
                for tr_data in tr_list_data:
                    t_type = tr_data["training_type"]
                    participants_data = tr_data["validated_participants"]
                    creator = tr_data.get("created_by") or request_user
                    base_training_plan = tr_data["training_plan"]

                    # 1. Determine all training plans to create (Base plan + any subsequent sequence steps)
                    current_seq = TrainingPlanSequence.objects.filter(
                        training_plan=base_training_plan,
                        is_active=True,
                        training_plan__is_active=True,
                    ).first()

                    plans_to_create = [base_training_plan]

                    if current_seq:
                        sequence_steps = TrainingPlanSequence.objects.filter(
                            sequence_group_name=current_seq.sequence_group_name,
                            step_order__gte=current_seq.step_order,  # includes step 2 and later
                            is_active=True,
                            training_plan__isnull=False,
                            training_plan__is_active=True,
                        ).order_by("step_order")

                        plans_to_create = list(
                            dict.fromkeys(step.training_plan for step in sequence_steps)
                        )

                    # 2. Iterate and create a TrainingRequest and duplicate participants for each plan in the chain
                    for plan_obj in plans_to_create:
                        tr_instance = TrainingRequest.objects.create(
                            financial_year=tr_data["financial_year"],
                            training_plan=plan_obj,
                            partner=tr_data["partner"],
                            training_type=t_type,
                            level=tr_data.get("level", "BLOCK"),
                            status=tr_data.get("status", "BATCHING"),
                            district=tr_data["district"],
                            block=tr_data.get("block"),
                            remarks=tr_data.get("remarks") or "",
                            is_old=tr_data.get("is_old", False),
                            created_by=creator,
                            is_active=True,
                        )

                        created_participants_count = 0

                        if t_type == "BENEFICIARY":
                            beneficiary_objs = [
                                TRBeneficiary(
                                    training=tr_instance,
                                    lokos_shg_code=p.get("lokos_shg_code") or "",
                                    lokos_shg_name=p.get("lokos_shg_name") or "",
                                    lokos_member_code=p["lokos_member_code"],
                                    member_name=p["member_name"],
                                    relation=p.get("relation") or "",
                                    relation_name=p.get("relation_name") or "",
                                    age=p.get("age"),
                                    gender=p.get("gender") or "",
                                    designation=p.get("designation") or "",
                                    pld_status=p.get("pld_status") or "NO",
                                    social_category=p.get("social_category") or "",
                                    religion=p.get("religion") or "",
                                    mobile=p.get("mobile") or "",
                                    email=p.get("email") or "",
                                    education=p.get("education") or "",
                                    address=p.get("address") or "",
                                    district=p.get("district") or tr_instance.district,
                                    block=p.get("block") or tr_instance.block,
                                    panchayat=p.get("panchayat"),
                                    village=p.get("village"),
                                    remarks=p.get("remarks") or "",
                                    created_by=creator,
                                    is_active=True,
                                )
                                for p in participants_data
                            ]
                            TRBeneficiary.objects.bulk_create(beneficiary_objs)
                            created_participants_count = len(beneficiary_objs)

                        elif t_type == "TRAINER":
                            trainer_objs = []
                            for p in participants_data:
                                mt = p["trainer"]
                                trainer_objs.append(
                                    TRTrainer(
                                        training=tr_instance,
                                        trainer=mt,
                                        full_name=p.get("full_name") or mt.full_name or "",
                                        mobile_no=p.get("mobile_no") or mt.mobile_no or "",
                                        aadhaar_no=p.get("aadhaar_no") or mt.aadhaar_no or "",
                                        district=p.get("district") or mt.empanel_district or tr_instance.district,
                                        block=p.get("block") or mt.empanel_block or tr_instance.block,
                                        remarks=p.get("remarks") or "",
                                        created_by=creator,
                                        is_active=True,
                                    )
                                )
                            TRTrainer.objects.bulk_create(trainer_objs)
                            created_participants_count = len(trainer_objs)

                        elif t_type == "STAFF":
                            staff_objs = []
                            for p in participants_data:
                                sp = p["staff"]
                                staff_objs.append(
                                    TRStaff(
                                        training=tr_instance,
                                        staff=sp,
                                        full_name=p.get("full_name") or sp.full_name or "",
                                        designation=p.get("designation") or sp.designation or "",
                                        theme=p.get("theme") or sp.theme,
                                        district=p.get("district") or sp.district or tr_instance.district,
                                        block=p.get("block") or sp.block or tr_instance.block,
                                        remarks=p.get("remarks") or "",
                                        created_by=creator,
                                        is_active=True,
                                    )
                                )
                            TRStaff.objects.bulk_create(staff_objs)
                            created_participants_count = len(staff_objs)

                        created_requests_summary.append({
                            "training_request_id": tr_instance.id,
                            "TH_urid": tr_instance.TH_urid,
                            "training_type": tr_instance.training_type,
                            "training_plan_id": tr_instance.training_plan_id,
                            "level": tr_instance.level,
                            "status": tr_instance.status,
                            "district_id": tr_instance.district_id,
                            "block_id": tr_instance.block_id,
                            "participants_created": created_participants_count,
                        })

            return Response(
                {
                    "message": f"Successfully created {len(created_requests_summary)} Training Request(s) including auto-generated sequential steps.",
                    "total_requests_created": len(created_requests_summary),
                    "results": created_requests_summary,
                },
                status=status.HTTP_201_CREATED,
            )

        except Exception as e:
            logger.exception(f"Atomic TrainingRequest creation failed: {e}")
            return Response(
                {
                    "error": "Failed to create Training Request(s). Transaction rolled back completely.",
                    "detail": str(e),
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )