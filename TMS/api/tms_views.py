# TMS/api/tms_views.py
import os
import re

from django.shortcuts import get_object_or_404
import docx
from docx import Document
from docx.shared import Inches, Pt
from docx.enum.text import WD_PARAGRAPH_ALIGNMENT
from docx.enum.table import WD_TABLE_ALIGNMENT

from collections import defaultdict
from typing import Any, Dict, List, Optional
import tempfile
import zipfile
from io import BytesIO

from django.db import transaction
from django.db.models import Q
from django.db.models import QuerySet
from django.utils import timezone

from rest_framework.views import APIView
from rest_framework import status,generics
from django.http import HttpResponse
from django.conf import settings
from datetime import datetime
from rest_framework import serializers

from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from drf_yasg.utils import swagger_auto_schema
from drf_yasg.inspectors import SwaggerAutoSchema
from drf_yasg import openapi

from core.models import MasterUser
from TMS import models as tms_models
from TMS.api.serializers import *


# -------------------------------------------------------------------
# Common helpers
# -------------------------------------------------------------------

def _role_name(user: MasterUser) -> str:
    """
    Safely get role name (lowercased).
    """
    try:
        role = getattr(user, "role", None)
        if role and getattr(role, "name", None):
            return role.name.lower()
    except Exception:
        pass
    return ""

# --------------------------
# Helper utilities
# --------------------------
def parse_csv_param(val):
    if not val:
        return []
    return [p.strip() for p in val.split(',') if p.strip()]

# -------------------------------------------------------------------
# Swagger tagging helpers (drf_yasg)
# -------------------------------------------------------------------

class MastersSchema(SwaggerAutoSchema):
    def get_tags(self, operation_keys=None):
        return ["TMS – Masters & Themes"]


class PartnersSchema(SwaggerAutoSchema):
    def get_tags(self, operation_keys=None):
        return ["TMS – Training Partners"]


class TargetsSchema(SwaggerAutoSchema):
    def get_tags(self, operation_keys=None):
        return ["TMS – Targets & Authority"]


class RequestsSchema(SwaggerAutoSchema):
    def get_tags(self, operation_keys=None):
        return ["TMS – Training Requests"]


class BatchesSchema(SwaggerAutoSchema):
    def get_tags(self, operation_keys=None):
        return ["TMS – Batches & Attendance"]


class ClosureSchema(SwaggerAutoSchema):
    def get_tags(self, operation_keys=None):
        return ["TMS – Batch Closure & Certificates"]

class ReportsSchema(SwaggerAutoSchema):
    def get_tags(self, operation_keys=None):
        return ["TMS – Reports"]

# -------------------------------------------------------------------
# Base ViewSet with soft-delete support
# -------------------------------------------------------------------

class BaseTMSModelViewSet(viewsets.ModelViewSet):
    """
    Common base for TMS CRUD viewsets:

    - Applies IsAuthenticated.
    - Filters out soft-deleted rows (is_active=True / deleted_at is null).
    - Implements soft delete via .delete(by_user=...)
    """

    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        qs = super().get_queryset()
        # If model has is_active / deleted_at (SoftDeleteMixin), respect it.
        model = getattr(self, "queryset", None)
        model_cls = getattr(model, "model", None) or getattr(self, "serializer_class", None)
        # We keep it simple and just filter on is_active when present.
        if hasattr(qs.model, "is_active"):
            qs = qs.filter(is_active=True)
        return qs

    def perform_destroy(self, instance):
        # If SoftDeleteMixin is used, call its delete() so deleted_at & deleted_by are set.
        if hasattr(instance, "delete"):
            user = getattr(self.request, "user", None)
            try:
                instance.delete(by_user=user)
            except TypeError:
                # delete() might not accept by_user; fallback
                instance.delete()
        else:
            super().perform_destroy(instance)


# -------------------------------------------------------------------
# Masters & Themes
# -------------------------------------------------------------------

class TrainingThemeViewSet(BaseTMSModelViewSet):
    """
    CRUD for TrainingTheme.
    """
    swagger_schema = MastersSchema
    queryset = tms_models.TrainingTheme.objects.all()
    serializer_class = TrainingThemeSerializer
    filterset_fields = ["theme_name", "expert"]
    search_fields = ["theme_name"]
    ordering_fields = ["theme_name", "id"]


class TrainingPlanViewSet(BaseTMSModelViewSet):
    """
    CRUD for TrainingPlan.
    Used by SMMU to define modules to be targeted & requested.
    """
    swagger_schema = MastersSchema
    queryset = tms_models.TrainingPlan.objects.select_related("theme")
    serializer_class = TrainingPlanSerializer
    filterset_fields = [
        "id",
        "theme",
        "type_of_training",
        "level_of_training",
        "approval_status",
    ]
    search_fields = ["training_name"]
    ordering_fields = ["training_name", "id"]

    # -----------------------------------
    #   SURGICAL ADDITION: fields= support
    # -----------------------------------
    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset())

        # fields=id,training_name,type_of_training
        fields = request.GET.get("fields")
        if fields:
            qs = qs.values(*parse_csv_param(fields))
            page = self.paginate_queryset(qs)
            return self.get_paginated_response(
                list(page) if page is not None else list(qs)
            )

        return super().list(request, *args, **kwargs)
    
    @action(detail=True, methods=["get"], url_path="detail")
    def detail_view(self, request, pk=None):
        """
        DETAIL view – includes nested theme.
        """
        training_plan = self.get_object()
        serializer = TrainingPlanDetailSerializer(training_plan, context={"request": request})
        return Response(serializer.data)

# custom paginator
class TenPerPagePagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"  # optional: allow clients to change page size
    max_page_size = 100  # optional safeguard


    
class MasterTrainerViewSet(BaseTMSModelViewSet):
    """
    CRUD for MasterTrainer (BRP/DRP/SRP).
    """
    swagger_schema = MastersSchema
    queryset = tms_models.MasterTrainer.objects.select_related("empanel_district", "empanel_block")
    serializer_class = MasterTrainerSerializer
    filterset_fields = [
        "designation",
        "empanel_district",
        "empanel_block",
        "gender",
        "social_category",
    ]
    search_fields = ["full_name", "mobile_no", "id"]
    pagination_class = TenPerPagePagination    

    @swagger_auto_schema(
        operation_summary="Retrieve master trainer with certificates",
        responses={200: MasterTrainerDetailSerializer},
    )
    @action(detail=True, methods=["get"], url_path="detail")
    def detail_view(self, request, pk=None):
        """
        DETAIL view – includes nested certificates.
        """
        trainer = self.get_object()
        serializer = MasterTrainerDetailSerializer(trainer, context={"request": request})
        return Response(serializer.data)


class MasterTrainerCertificateViewSet(BaseTMSModelViewSet):
    """
    CRUD for MasterTrainerCertificate.
    Certificate numbers can be auto-generated in model save().
    """
    swagger_schema = MastersSchema
    queryset = tms_models.MasterTrainerCertificate.objects.select_related("trainer", "training_plan", "theme")
    serializer_class = MasterTrainerCertificateSerializer
    filterset_fields = ["trainer", "training_plan", "theme"]
    search_fields = ["certificate_no"]
    ordering_fields = ["issued_on", "id"]


# -------------------------------------------------------------------
# Training Partners & Centres
# -------------------------------------------------------------------

class TrainingPartnerViewSet(BaseTMSModelViewSet):
    """
    CRUD for TrainingPartner (org level).
    """
    swagger_schema = PartnersSchema
    queryset = tms_models.TrainingPartner.objects.all()
    serializer_class = TrainingPartnerSerializer
    filterset_fields = ["name", "id"]
    search_fields = ["name", "tpm_registration_no", "master_user__id"]
    ordering_fields = ["name", "id"]

    # -------------------------------
    #   SURGICAL ADDITION: fields= support
    # -------------------------------
    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset())

        # fields extraction
        fields = request.GET.get("fields")
        if fields:
            qs = qs.values(*parse_csv_param(fields))
            page = self.paginate_queryset(qs)
            return self.get_paginated_response(
                list(page) if page is not None else list(qs)
            )

        return super().list(request, *args, **kwargs)

    @swagger_auto_schema(
        operation_summary="Get partner with centres & banks",
        responses={200: TrainingPartnerSerializer},
    )
    @action(detail=True, methods=["get"], url_path="full-detail")
    def full_detail(self, request, pk=None):
        """
        DETAIL view – partner + banks + centres (via nested serializers).
        """
        partner = self.get_object()
        serializer = TrainingPartnerSerializer(partner, context={"request": request})
        return Response(serializer.data)



class TrainingPartnerBankViewSet(BaseTMSModelViewSet):
    """
    CRUD for TrainingPartnerBank.
    """
    swagger_schema = PartnersSchema
    queryset = tms_models.TrainingPartnerBank.objects.select_related("partner")
    serializer_class = TrainingPartnerBankSerializer
    filterset_fields = ["partner"]


class TrainingPartnerCPViewSet(BaseTMSModelViewSet):
    """
    CRUD for TrainingPartnerCP (contact persons).
    """
    swagger_schema = PartnersSchema
    queryset = tms_models.TrainingPartnerCP.objects.select_related("partner", "master_user")
    serializer_class = TrainingPartnerCPSerializer
    filterset_fields = ["partner", "master_user"]
    search_fields = ["name", "mobile_number", "email"]


class TrainingPartnerCentreViewSet(BaseTMSModelViewSet):
    """
    CRUD for TrainingPartnerCentre.
    """
    swagger_schema = PartnersSchema
    queryset = (
        tms_models.TrainingPartnerCentre.objects.select_related(
            "partner", "district", "block", "panchayat", "village"
        )
        .prefetch_related("rooms")
    )
    serializer_class = TrainingPartnerCentreSerializer
    filterset_fields = [
        "partner",
        "district",
        "block",
        "panchayat",
        "village",
    ]
    search_fields = ["venue_name", "venue_address"]

    @swagger_auto_schema(
        operation_summary="Retrieve centre with nested rooms",
        responses={200: TrainingPartnerCentreDetailSerializer},
    )
    @action(detail=True, methods=["get"], url_path="detail")
    def detail_view(self, request, pk=None):
        """
        DETAIL view – includes nested rooms for centre.
        """
        centre = self.get_object()
        serializer = TrainingPartnerCentreDetailSerializer(centre, context={"request": request})
        return Response(serializer.data)


class TrainingPartnerCentreRoomsViewSet(BaseTMSModelViewSet):
    """
    CRUD for TrainingPartnerCentreRooms.
    """
    swagger_schema = PartnersSchema
    queryset = tms_models.TrainingPartnerCentreRooms.objects.select_related("centre")
    serializer_class = TrainingPartnerCentreRoomsSerializer
    filterset_fields = ["centre"]


class TPCPToCentreViewSet(BaseTMSModelViewSet):
    """
    Maps TrainingPartnerCP → TrainingPartnerCentre.
    Used when partner assigns contact person for centre.
    """
    swagger_schema = PartnersSchema
    queryset = tms_models.TPCPToCentre.objects.select_related("contact_person", "allocated_centre")
    serializer_class = TPCPToCentreSerializer   
    filterset_fields = ["contact_person", "allocated_centre"]
    
class TPCPCentreDetailViewSet(BaseTMSModelViewSet):
    """
    ViewSet to get details of TrainingPartnerCP along with allocated centres.
    """
    swagger_schema = PartnersSchema
    queryset = tms_models.TPCPToCentre.objects.select_related("contact_person", "allocated_centre")
    serializer_class = TPCPToCentreDetailSerializer
    filterset_fields = ["contact_person", "allocated_centre"]    


class TrainingPartnerSubmissionViewSet(BaseTMSModelViewSet):
    """
    Image/PDF submissions by partners for centres (fooding, toilets, etc.).
    """
    swagger_schema = PartnersSchema
    queryset = tms_models.TrainingPartnerSubmission.objects.select_related("partner", "centre")
    serializer_class = TrainingPartnerSubmissionSerializer
    filterset_fields = ["partner", "centre", "category"]


# -------------------------------------------------------------------
# Targets & Authority
# -------------------------------------------------------------------

class TrainingPartnerTargetsViewSet(BaseTMSModelViewSet):
    """
    Targets assigned by SMMU to Training Partners (Module/District/Theme).
    """
    swagger_schema = TargetsSchema
    queryset = tms_models.TrainingPartnerTargets.objects.select_related("partner", "training_plan", "district")
    serializer_class = TrainingPartnerTargetsSerializer
    filterset_fields = ["partner", "target_type", "training_plan", "district", "theme", "financial_year"]
    search_fields = ["theme", "financial_year"]


class TRPUserScopeViewSet(BaseTMSModelViewSet):
    """
    Participant selection authority mapping (role → training_id).
    Used by BMMU to see eligible TrainingPlans.
    """
    swagger_schema = TargetsSchema
    queryset = tms_models.TRPUserScope.objects.all()
    serializer_class = TRPUserScopeSerializer
    filterset_fields = ["user_role_id", "training_id"]


# -------------------------------------------------------------------
# Training Requests (BMMU → TP)
# -------------------------------------------------------------------

class TrainingRequestViewSet(BaseTMSModelViewSet):
    """
    TrainingRequest:
    - Created by BMMU.
    - training_type (Beneficiary / Trainer).
    - Goes to assigned TrainingPartner for batching.
    """
    swagger_schema = RequestsSchema
    queryset = (
        tms_models.TrainingRequest.objects.select_related("training_plan", "partner")
        .prefetch_related("beneficiary_registrations", "trainer_registrations")
    )
    serializer_class = TrainingRequestSerializer
    filterset_fields = ["status", "level", "training_type", "training_plan", "partner", "created_by", "block", "district"]
    search_fields = ["id"]

    @swagger_auto_schema(
        operation_summary="Retrieve training request with nested participants",
        responses={200: TrainingRequestDetailSerializer},
    )
    @action(detail=True, methods=["get"], url_path="detail")
    def detail_view(self, request, pk=None):
        """
        DETAIL view – includes nested TRBeneficiary/TRTrainer.
        """
        tr = self.get_object()
        serializer = TrainingRequestDetailSerializer(tr, context={"request": request})
        return Response(serializer.data)

    @swagger_auto_schema(
        method="post",
        operation_summary="BMMU: attach beneficiaries to training request",
        request_body=TRBeneficiarySerializer(many=True),
        responses={200: TRBeneficiarySerializer(many=True)},
    )
    @action(detail=True, methods=["post"], url_path="attach-beneficiaries")
    def attach_beneficiaries(self, request, pk=None):
        """
        BMMU step: attach a list of beneficiaries to this TrainingRequest.
        Body: [ { TRBeneficiary fields... }, ... ]
        """
        tr = self.get_object()
        many_serializer = TRBeneficiarySerializer(
            data=request.data, many=True, context={"request": request}
        )
        many_serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            objs = []
            for payload in many_serializer.validated_data:
                obj = tms_models.TRBeneficiary.objects.create(training=tr, **payload)
                objs.append(obj)
        return Response(TRBeneficiarySerializer(objs, many=True).data, status=status.HTTP_201_CREATED)

    @swagger_auto_schema(
        method="post",
        operation_summary="BMMU: attach trainers to training request",
        request_body=TRTrainerSerializer(many=True),
        responses={200: TRTrainerSerializer(many=True)},
    )
    @action(detail=True, methods=["post"], url_path="attach-trainers")
    def attach_trainers(self, request, pk=None):
        """
        BMMU step: attach a list of trainers to this TrainingRequest.
        """
        tr = self.get_object()
        many_serializer = TRTrainerSerializer(
            data=request.data, many=True, context={"request": request}
        )
        many_serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            objs = []
            for payload in many_serializer.validated_data:
                obj = tms_models.TRTrainer.objects.create(training=tr, **payload)
                objs.append(obj)
        return Response(TRTrainerSerializer(objs, many=True).data, status=status.HTTP_201_CREATED)

    @swagger_auto_schema(
        method="post",
        operation_summary="BMMU → TP: submit training request to partner",
        request_body=None,
        responses={200: TrainingRequestSerializer},
    )
    @action(detail=True, methods=["post"], url_path="submit-to-partner")
    def submit_to_partner(self, request, pk=None):
        """
        BMMU calls this when finalizing a TrainingRequest and sending to TP.
        We simply flip status (if all good).
        """
        tr = self.get_object()
        if tr.status not in ["BATCHING", "PENDING"]:
            return Response(
                {"detail": f"Cannot submit request in status {tr.status}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Basic guard: must have at least 1 participant
        total_bens = tr.beneficiary_registrations.count()
        total_trainers = tr.trainer_registrations.count()
        if total_bens == 0 and total_trainers == 0:
            return Response(
                {"detail": "TrainingRequest has no participants attached."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Move to PENDING for partner batching
        tr.status = "PENDING"
        tr.save(update_fields=["status"])
        return Response(TrainingRequestSerializer(tr, context={"request": request}).data)
        

class TRBeneficiaryViewSet(BaseTMSModelViewSet):
    """
    CRUD for TRBeneficiary (registrations against TrainingRequest).
    """
    swagger_schema = RequestsSchema
    queryset = tms_models.TRBeneficiary.objects.select_related(
        "training", "district", "block", "panchayat", "village"
    )
    serializer_class = TRBeneficiarySerializer
    filterset_fields = ["training", "district", "block", "pld_status"]
    search_fields = ["member_name", "lokos_member_code", "lokos_shg_code"]

    @swagger_auto_schema(
        operation_summary="Retrieve beneficiary registration with nested training request",
        responses={200: TRBeneficiaryDetailSerializer},
    )
    @action(detail=True, methods=["get"], url_path="detail")
    def detail_view(self, request, pk=None):
        ben = self.get_object()
        serializer = TRBeneficiaryDetailSerializer(ben, context={"request": request})
        return Response(serializer.data)


class TRTrainerViewSet(BaseTMSModelViewSet):
    """
    CRUD for TRTrainer (trainer registrations per TrainingRequest).
    """
    swagger_schema = RequestsSchema
    queryset = tms_models.TRTrainer.objects.select_related("training", "trainer")
    serializer_class = TRTrainerSerializer
    filterset_fields = ["training", "trainer" , "district" , "block"]

    @swagger_auto_schema(
        operation_summary="Retrieve trainer registration with nested training & trainer",
        responses={200: TRTrainerDetailSerializer},
    )
    @action(detail=True, methods=["get"], url_path="detail")
    def detail_view(self, request, pk=None):
        tr_trainer = self.get_object()
        serializer = TRTrainerDetailSerializer(tr_trainer, context={"request": request})
        return Response(serializer.data)


# -------------------------------------------------------------------
# Batches (TP → DMMU) & Attendance
# -------------------------------------------------------------------

class BatchViewSet(BaseTMSModelViewSet):
    """
    Batch:
    - Created by Training Partner against one (or more) TrainingRequests.
    - Can be combined/separate, with TRBeneficiary/TRTrainer attached.
    - Goes to DMMU for approval.
    """
    swagger_schema = BatchesSchema
    queryset = (
        tms_models.Batch.objects.select_related("request", "centre")
        .prefetch_related("beneficiary_participations", "trainer_participations", "master_trainer_participations")
    )
    serializer_class = BatchSerializer
    filterset_fields = ["request", "centre", "status", "start_date", "end_date"]
    search_fields = ["code"]

    @swagger_auto_schema(
        operation_summary="Retrieve batch with nested participants and eKYC/attendance summary",
        responses={200: BatchDetailSerializer},
    )
    @action(detail=True, methods=["get"], url_path="detail")
    def detail_view(self, request, pk=None):
        batch = self.get_object()
        serializer = BatchDetailSerializer(batch, context={"request": request})
        return Response(serializer.data)

    @swagger_auto_schema(
        method="post",
        operation_summary="TP: attach participants (beneficiaries/trainers) to batch",
        request_body=BatchDetailSerializer,
        responses={200: BatchDetailSerializer},
    )
    @action(detail=True, methods=["post"], url_path="attach-participants")
    def attach_participants(self, request, pk=None):
        """
        TP step: attach TRBeneficiary/TRTrainer to this batch.
        Body:
        {
          "beneficiary_ids": [1,2,...],
          "trainer_ids": [10,11,...]
        }
        """
        batch = self.get_object()
        beneficiary_ids = request.data.get("beneficiary_ids") or []
        trainer_ids = request.data.get("trainer_ids") or []

        with transaction.atomic():
            if beneficiary_ids:
                existing = set(
                    tms_models.BatchBeneficiary.objects.filter(
                        batch=batch, beneficiary_id__in=beneficiary_ids
                    ).values_list("beneficiary_id", flat=True)
                )
                new_ids = [bid for bid in beneficiary_ids if bid not in existing]
                to_create = [
                    tms_models.BatchBeneficiary(batch=batch, beneficiary_id=bid)
                    for bid in new_ids
                ]
                if to_create:
                    tms_models.BatchBeneficiary.objects.bulk_create(to_create)

            if trainer_ids:
                existing = set(
                    tms_models.BatchTrainer.objects.filter(
                        batch=batch, trainer_id__in=trainer_ids
                    ).values_list("trainer_id", flat=True)
                )
                new_ids = [tid for tid in trainer_ids if tid not in existing]
                to_create = [
                    tms_models.BatchTrainer(batch=batch, trainer_id=tid)
                    for tid in new_ids
                ]
                if to_create:
                    tms_models.BatchTrainer.objects.bulk_create(to_create)

        serializer = BatchDetailSerializer(batch, context={"request": request})
        return Response(serializer.data)

    @swagger_auto_schema(
        method="post",
        operation_summary="TP → DMMU: propose batch for approval",
        request_body=None,
        responses={200: BatchSerializer},
    )
    @action(detail=True, methods=["post"], url_path="propose")
    def propose(self, request, pk=None):
        """
        TP calls this after setting centre + dates.
        Moves status to 'PENDING' (for DMMU approval) if allowed.
        """
        batch = self.get_object()
        if batch.status not in ["DRAFT", "REJECTED", "SCHEDULED"]:
            return Response(
                {"detail": f"Cannot propose batch in status {batch.status}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not batch.centre or not batch.start_date or not batch.end_date:
            return Response(
                {"detail": "Batch requires centre, start_date and end_date before proposing."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        batch.status = "PENDING"
        batch.save(update_fields=["status"])
        return Response(BatchSerializer(batch, context={"request": request}).data)

class BatchListPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = None
    max_page_size = 10

class BatchesListView(APIView):
    def get(self, request):
        request_id = request.GET.get('request')
        district_id = request.GET.get('district_id')
        block_id = request.GET.get('block_id')
        theme_id = request.GET.get('theme_id')
        batch_type = request.GET.get('batch_type')
        status = request.GET.get('status')
        ordering = request.GET.get('ordering', 'start_date')

        qs = tms_models.Batch.objects.select_related(
            'request',
            'request__district',
            'request__block',
            'request__training_plan',
            'request__training_plan__theme',
            'centre',
            'centre__partner',
        )

        location_filter = Q()
        if district_id:
            location_filter |= Q(request__district_id=district_id)
        if block_id:
            location_filter |= Q(request__block_id=block_id)
        if theme_id:
            location_filter |= Q(request__training_plan__theme=theme_id)

        if location_filter:
            qs = qs.filter(location_filter)

        if batch_type:
            qs = qs.filter(batch_type=batch_type)

        if request_id:
            qs = qs.filter(request=request_id)

        if status:
            qs = qs.filter(status=status)

        allowed_ordering = {
            'start_date', '-start_date',
            'end_date', '-end_date'
        }
        if ordering not in allowed_ordering:
            ordering = 'start_date'

        qs = qs.order_by(ordering)

        paginator = BatchListPagination()
        page = paginator.paginate_queryset(qs, request)

        serializer = BatchListSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

class BatchScheduleViewSet(BaseTMSModelViewSet):
    """
    Batch Schedule – per batch per day schedule details.
    """
    swagger_schema = BatchesSchema
    queryset = tms_models.BatchSchedule.objects.select_related("batch")
    serializer_class = BatchScheduleSerializer
    filterset_fields = ["batch", "schedule_date"]

class BatchMasterTrainerViewSet(BaseTMSModelViewSet):
    """
    M2M join: Batch ↔ MasterTrainer.
    """
    swagger_schema = BatchesSchema
    queryset = tms_models.BatchMasterTrainer.objects.select_related("batch", "master_trainer")
    serializer_class = BatchMasterTrainerSerializer
    filterset_fields = ["batch", "master_trainer", "status"]


class BatchBeneficiaryViewSet(BaseTMSModelViewSet):
    """
    M2M join: Batch ↔ TRBeneficiary.
    """
    swagger_schema = BatchesSchema
    queryset = tms_models.BatchBeneficiary.objects.select_related("batch", "beneficiary")
    serializer_class = BatchBeneficiarySerializer
    filterset_fields = ["batch"]
    search_fields = ["beneficiary__member_name", "beneficiary__lokos_member_code"]


class BatchTrainerViewSet(BaseTMSModelViewSet):
    """
    M2M join: Batch ↔ TRTrainer.
    """
    swagger_schema = BatchesSchema
    queryset = tms_models.BatchTrainer.objects.select_related("batch", "trainer")
    serializer_class = BatchTrainerSerializer
    filterset_fields = ["batch"]


class BatchEkycVerificationViewSet(BaseTMSModelViewSet):
    """
    eKYC verification per participant per batch.
    Typically used at Contact Person level on day-1.
    """
    swagger_schema = BatchesSchema
    queryset = tms_models.BatchEkycVerification.objects.select_related("batch")
    serializer_class = BatchEkycVerificationSerializer
    filterset_fields = ["batch", "participant_role", "ekyc_status"]
    search_fields = ["participant_id"]


class BatchAttendanceViewSet(BaseTMSModelViewSet):
    """
    BatchAttendance – per batch per day.
    """
    swagger_schema = BatchesSchema
    queryset = tms_models.BatchAttendance.objects.select_related("batch")
    serializer_class = BatchAttendanceSerializer
    filterset_fields = ["batch", "date"]

    @swagger_auto_schema(
        operation_summary="Get participant attendance list for this batch-date",
        responses={200: ParticipantAttendanceSerializer(many=True)},
    )
    @action(detail=True, methods=["get"], url_path="participants")
    def participants(self, request, pk=None):
        """
        Returns all ParticipantAttendance records for this BatchAttendance row.
        """
        attendance = self.get_object()
        qs = attendance.participant_records.all()
        serializer = ParticipantAttendanceSerializer(qs, many=True, context={"request": request})
        return Response(serializer.data)


class ParticipantAttendanceViewSet(BaseTMSModelViewSet):
    """
    ParticipantAttendance – trainer/beneficiary presence records.
    """
    swagger_schema = BatchesSchema
    queryset = tms_models.ParticipantAttendance.objects.select_related("attendance", "attendance__batch")
    serializer_class = ParticipantAttendanceSerializer
    filterset_fields = ["attendance", "participant_role", "present"]
    search_fields = ["participant_id", "participant_name"]


# -------------------------------------------------------------------
# Batch Closure, Costing & Certificates (CP → TP → DMMU)
# -------------------------------------------------------------------

class TPBatchCostBreakupViewSet(BaseTMSModelViewSet):
    """
    Detailed partner-side batch cost breakup (centre, hostel, fooding, etc.).
    Usually filled by Contact Person post-training.
    """
    swagger_schema = ClosureSchema
    queryset = tms_models.TPBatchCostBreakup.objects.select_related("batch")
    serializer_class = TPBatchCostBreakupSerializer
    filterset_fields = ["batch"]


class BatchParticipantCertificateViewSet(BaseTMSModelViewSet):
    """
    Participant certificates for a batch.
    Model handles auto-generation of issue_code.
    """
    swagger_schema = ClosureSchema
    queryset = tms_models.BatchParticipantCertificate.objects.select_related("batch")
    serializer_class = BatchParticipantCertificateSerializer
    filterset_fields = ["batch"]
    search_fields = ["issue_code", "participant_id"]


class BatchCostViewSet(BaseTMSModelViewSet):
    """
    Aggregated trainer + TP parts + detailed cost (TPBatchCostBreakup).
    """
    swagger_schema = ClosureSchema
    queryset = tms_models.BatchCost.objects.select_related("training", "batch", "batch_expenses")
    @action(detail=True, methods=["get"], url_path="detail")
    def detail_view(self, request, pk=None):
        batch = self.get_object()
        serializer = BatchCostDetailSerializer(batch, context={"request": request})
        return Response(serializer.data)    
    serializer_class = BatchCostSerializer
    filterset_fields = ["batch", "training"]


class BatchMediaViewSet(BaseTMSModelViewSet):
    """
    Media files per batch (classroom photos, fooding, etc.).
    """
    swagger_schema = ClosureSchema
    queryset = tms_models.BatchMedia.objects.select_related("batch")
    serializer_class = BatchMediaSerializer
    filterset_fields = ["batch", "category", "date"]


class BatchClosureRequestViewSet(BaseTMSModelViewSet):
    """
    Batch-level closure request from Contact Person → Training Partner.
    Later aggregated into Training Request closure by TP → DMMU.
    """
    swagger_schema = ClosureSchema
    queryset = tms_models.BatchClosureRequest.objects.select_related("batch", "batch_costing")
    serializer_class = BatchClosureRequestSerializer
    filterset_fields = ["batch", "certificates_issued"]

    @swagger_auto_schema(
        method="post",
        operation_summary="CP → TP: submit batch closure request",
        request_body=None,
        responses={200: BatchClosureRequestSerializer},
    )
    @action(detail=True, methods=["post"], url_path="submit")
    def submit(self, request, pk=None):
        """
        Minimal hook to mark a batch closure request as submitted.
        (You can add fields like 'submitted_on' in model later.)
        """
        obj = self.get_object()
        # no special flags for now – just return current state
        serializer = BatchClosureRequestSerializer(obj, context={"request": request})
        return Response(serializer.data)


class TRClosureViewSet(BaseTMSModelViewSet):
    """
    Training Request closure at DMMU level.
    Links all batches in a training request with HRA / TA-DA docs.
    """
    swagger_schema = ClosureSchema
    queryset = tms_models.TRClosure.objects.select_related("training")
    serializer_class = TRClosureSerializer
    filterset_fields = ["training"]
    
class BatchReportViewSet(BaseTMSModelViewSet):
    """
    Batch Report – per batch full report details.
    """
    swagger_schema = ReportsSchema
    queryset = tms_models.BatchReport.objects.select_related("batch")
    serializer_class = BatchCertificateSerializer
    filterset_fields = ["batch"]    

class TrainingReportView(APIView):
    """
    FULL Training Request Report API

    URL:
      /training-report/<training_request_id>/

    Scope:
      Returns a fully nested, read-only report of a TrainingRequest
      including TrainingPlan, Partner, District, Block, Batches,
      Centres, Trainers, Beneficiaries, Attendance, Costs, Media, Closure Docs.
    """
    def get(self, request, id):
        training_request = get_object_or_404(
            tms_models.TrainingRequest.objects.filter(
                id=id,
                is_active=True
            )
        )

        serializer = TrainingRequestReportSerializer(
            training_request,
            context={"request": request}
        )

        return Response(serializer.data, status=status.HTTP_200_OK)