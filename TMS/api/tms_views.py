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

import pandas as pd
from django.db import transaction
from django.db.models import Q, Prefetch
from django.db.models import QuerySet
from django.utils import timezone

from rest_framework.views import APIView
from rest_framework import status,generics
from django.http import HttpResponse, FileResponse
from django.conf import settings
from datetime import datetime
from rest_framework import serializers
from rest_framework.authentication import SessionAuthentication
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action, api_view, permission_classes, authentication_classes
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from drf_yasg.utils import swagger_auto_schema
from drf_yasg.inspectors import SwaggerAutoSchema
from drf_yasg import openapi

from core.models import MasterUser, MasterDistrictCategoryMapping, MasterDistrict
from TMS import models as tms_models
from TMS.api.serializers import *
from rest_framework.viewsets import ReadOnlyModelViewSet
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.exceptions import PermissionDenied, NotFound

from django.db.models import F
import xlsxwriter

# Certificate
from .certificate_gen import generate_batch_certificate_pdf

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

def get_master_user_from_request(request):
    try:
        return MasterUser.objects.get(username=request.user.username)
    except MasterUser.DoesNotExist:
        return None

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
# Get MasterUser
# -------------------------------------------------------------------

def get_master_user(request):
    django_user = request.user

    if not django_user or not django_user.is_authenticated:
        raise PermissionDenied("Authentication required.")

    try:
        return MasterUser.objects.get(username=django_user.username)
    except MasterUser.DoesNotExist:
        raise PermissionDenied("Master user not found.")

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

# Targets pagination class (for listing targets with achievements)
class TargetsPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = 'page_size'
    max_page_size = 100

# -------------------------------------------------------------------
# Masters & Themes
# -------------------------------------------------------------------

class TrainingThemeViewSet(BaseTMSModelViewSet):
    """
    CRUD for TrainingTheme.
    """
    swagger_schema = MastersSchema
    queryset = tms_models.TrainingTheme.objects.filter(is_active=True)
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
    max_page_size = 100000  # optional safeguard

  
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
    serializer_class = TrainingPartnerCPSerializer
    queryset = tms_models.TrainingPartnerCP.objects.select_related(
        "partner", "master_user"
    )
    filterset_fields = ["id", "partner", "master_user"]
    
    def get_queryset(self):
        auth_user = self.request.user

        try:
            master_user = core_models.MasterUser.objects.get(
                username=auth_user.username
            )
        except core_models.MasterUser.DoesNotExist:
            return tms_models.TrainingPartnerCP.objects.none()

        queryset = super().get_queryset()

        # 1. Determine the user's role context
        is_tp_owner = tms_models.TrainingPartner.objects.filter(master_user=master_user).exists()
        is_tpcp = tms_models.TrainingPartnerCP.objects.filter(master_user=master_user).exists()
        is_dtp = tms_models.DistrictTP.objects.filter(master_user=master_user).exists()

        # 2. Apply strict filtering ONLY if the user belongs to the Training Partner domain.
        # This allows Admin/State users (who have no TP profiles) to bypass and see results.
        if is_tp_owner or is_tpcp or is_dtp:
            queryset = queryset.filter(
                Q(partner__master_user=master_user) |               # Training Partner Owner
                Q(master_user=master_user) |                        # Contact Person
                Q(partner__district_nodes__master_user=master_user) # District TP Node
            )

        # 3. Introduce district_id OR created_by filtering
        # Includes CPs mapped to the district OR newly created CPs by the user (not mapped yet)
        district_id = self.request.query_params.get("district_id")
        created_by_param = self.request.query_params.get("created_by")

        if district_id or created_by_param:
            param_q = Q()
            if district_id:
                param_q |= Q(
                    tpcptocentre__allocated_centre__district_id=district_id,
                    tpcptocentre__is_active=True,
                    tpcptocentre__allocated_centre__is_active=True
                )
            if created_by_param:
                param_q |= Q(created_by_id=created_by_param)
                
            queryset = queryset.filter(param_q)

        # 4. Distinct must be called at the very end to clean up the INNER JOIN duplicates
        return queryset.distinct()

    def perform_create(self, serializer):
        auth_user = self.request.user

        master_user = core_models.MasterUser.objects.get(
            username=auth_user.username
        )

        partner = tms_models.TrainingPartner.objects.filter(
            master_user=master_user
        ).first()

        # Fallback: Allow District TPs to create CPs for their partner
        if not partner:
            dtp = tms_models.DistrictTP.objects.filter(master_user=master_user).first()
            if dtp:
                partner = dtp.partner

        # Fallback: If Admin, extract from request payload
        if not partner:
            partner_id = self.request.data.get("partner")
            if partner_id:
                partner = tms_models.TrainingPartner.objects.filter(id=partner_id).first()

        if not partner:
            raise NotFound("Training Partner not found or you lack permission.")

        serializer.save(
            partner=partner,
            created_by=master_user
        )
        
    def perform_update(self, serializer):
        instance = self.get_object()
        master_user = get_master_user_from_request(self.request)

        is_dtp = instance.partner.district_nodes.filter(master_user=master_user).exists()
        is_admin = not (
            tms_models.TrainingPartner.objects.filter(master_user=master_user).exists() or
            tms_models.TrainingPartnerCP.objects.filter(master_user=master_user).exists() or
            tms_models.DistrictTP.objects.filter(master_user=master_user).exists()
        )

        if not (
            instance.partner.master_user == master_user
            or instance.master_user == master_user
            or is_dtp
            or is_admin
        ):
            raise PermissionDenied("Unauthorized update attempt")

        serializer.save(updated_by=master_user)

    def get_object(self):
        obj = super().get_object()
        master_user = get_master_user_from_request(self.request)

        if not master_user:
            raise NotFound()

        is_dtp = obj.partner.district_nodes.filter(master_user=master_user).exists()
        is_admin = not (
            tms_models.TrainingPartner.objects.filter(master_user=master_user).exists() or
            tms_models.TrainingPartnerCP.objects.filter(master_user=master_user).exists() or
            tms_models.DistrictTP.objects.filter(master_user=master_user).exists()
        )

        if not (
            obj.partner.master_user == master_user
            or obj.master_user == master_user
            or is_dtp
            or is_admin
        ):
            raise PermissionDenied("Unauthorized access")

        return obj

class TrainingPartnerCentreViewSet(BaseTMSModelViewSet):
    """
    CRUD for TrainingPartnerCentre.
    """
    swagger_schema = PartnersSchema
    queryset = (
        tms_models.TrainingPartnerCentre.objects
        .select_related("partner", "district", "block", "panchayat", "village")
        .prefetch_related(
            "rooms",
            Prefetch(
                "submissions",
                queryset=tms_models.TrainingPartnerSubmission.objects.filter(is_active=True),
            )
        )
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

    def get_queryset(self):
        qs = super().get_queryset()
        auth_user = self.request.user

        master_user = core_models.MasterUser.objects.filter(username=auth_user.username).first()
        if not master_user:
            return qs.none()

        is_tp_owner = tms_models.TrainingPartner.objects.filter(master_user=master_user).exists()
        is_tpcp = tms_models.TrainingPartnerCP.objects.filter(master_user=master_user).exists()
        is_dtp = tms_models.DistrictTP.objects.filter(master_user=master_user).exists()
        is_admin = not (is_tp_owner or is_tpcp or is_dtp)

        # Non-admin users see only their respective Partner's centres
        if not is_admin:
            qs = qs.filter(
                Q(partner__master_user=master_user) |               # TP Owner
                Q(partner__contact_person__master_user=master_user) | # TP Contact Person
                Q(partner__district_nodes__master_user=master_user) # District TP Node
            ).distinct()

        return qs

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

    def get_queryset(self):
        qs = super().get_queryset()
        auth_user = self.request.user

        master_user = core_models.MasterUser.objects.filter(username=auth_user.username).first()
        if not master_user:
            return qs.none()

        is_tp_owner = tms_models.TrainingPartner.objects.filter(master_user=master_user).exists()
        is_tpcp = tms_models.TrainingPartnerCP.objects.filter(master_user=master_user).exists()
        is_dtp = tms_models.DistrictTP.objects.filter(master_user=master_user).exists()
        is_admin = not (is_tp_owner or is_tpcp or is_dtp)

        if not is_admin:
            qs = qs.filter(
                Q(centre__partner__master_user=master_user) |
                Q(centre__partner__contact_person__master_user=master_user) |
                Q(centre__partner__district_nodes__master_user=master_user)
            ).distinct()

        return qs

class TPCPToCentreViewSet(BaseTMSModelViewSet):
    """
    Maps TrainingPartnerCP → TrainingPartnerCentre.
    Used when partner assigns contact person for centre.
    """
    swagger_schema = PartnersSchema
    
    # --- ADDED: Base queryset to resolve the AssertionError ---
    queryset = tms_models.TPCPToCentre.objects.all()
    
    serializer_class = TPCPToCentreSerializer
    filterset_fields = ["contact_person", "allocated_centre", "created_by"]

    # ----------------------------------
    # Access Resolver
    # ----------------------------------
    def _get_access(self):
        auth_user = self.request.user

        master_user = core_models.MasterUser.objects.filter(
            username=auth_user.username
        ).first()

        if not master_user:
            raise PermissionDenied("Invalid user.")

        # Partner owner
        partner = tms_models.TrainingPartner.objects.filter(
            master_user=master_user,
            is_active=True
        ).first()

        # Contact person
        contact_person = tms_models.TrainingPartnerCP.objects.filter(
            master_user=master_user,
            is_active=True
        ).first()

        # District TP
        dtp = tms_models.DistrictTP.objects.filter(
            master_user=master_user,
            is_active=True
        ).first()

        is_admin = not (partner or contact_person or dtp)

        if not partner and not contact_person and not dtp and not is_admin:
            raise PermissionDenied("User has no partner access.")

        return master_user, partner, contact_person, dtp, is_admin

    # ----------------------------------
    # Queryset
    # ----------------------------------
    def get_queryset(self):
        master_user, partner, contact_person, dtp, is_admin = self._get_access()

        queryset = (
            super().get_queryset()
            .select_related(
                "contact_person__partner",
                "allocated_centre__partner",
            )
            .filter(is_active=True)
        )

        if is_admin:
            return queryset

        # Standardize filtering for TP, CP, and DTP using the central relation
        queryset = queryset.filter(
            Q(contact_person__partner__master_user=master_user) |               # TP Owner
            Q(contact_person__master_user=master_user) |                        # Contact Person Specific
            Q(contact_person__partner__district_nodes__master_user=master_user) # District TP Node
        ).distinct()

        return queryset

    # ----------------------------------
    # Create
    # ----------------------------------
    def perform_create(self, serializer):
        master_user, partner, contact_person, dtp, is_admin = self._get_access()

        # 1. Permission Check
        if not (partner or dtp or is_admin):
            raise PermissionDenied("Only Training Partners, District TPs, or Admins can assign centres.")

        # 2. Get the requested objects from the payload
        contact_person_id = self.request.data.get("contact_person")
        centre_id = self.request.data.get("allocated_centre")

        cp_obj = tms_models.TrainingPartnerCP.objects.select_related("partner").get(id=contact_person_id)
        centre_obj = tms_models.TrainingPartnerCentre.objects.select_related("partner").get(id=centre_id)

        # 3. Structural Validation: Ensure they belong to the same partner
        if cp_obj.partner_id != centre_obj.partner_id:
            raise ValidationError("The Contact Person and Centre must belong to the same Training Partner.")

        # 4. Authorization Validation: Ensure the user owns this specific partner
        # (Skip if admin)
        if not is_admin:
            authorized_partner = partner if partner else dtp.partner
            if cp_obj.partner_id != authorized_partner.id:
                raise PermissionDenied("You do not have access to assign this partner's resources.")

        serializer.save(created_by=master_user)

    # ----------------------------------
    # Update
    # ----------------------------------
    def perform_update(self, serializer):
        master_user, partner, contact_person, dtp, is_admin = self._get_access()
        instance = self.get_object()

        if not is_admin:
            instance_partner = instance.contact_person.partner
            user_is_authorized = False

            if partner and instance_partner == partner:
                user_is_authorized = True
            elif dtp and instance_partner == dtp.partner:
                user_is_authorized = True
            elif contact_person and instance.contact_person == contact_person:
                user_is_authorized = True

            if not user_is_authorized:
                raise PermissionDenied("Unauthorized access.")

        serializer.save(updated_by=master_user)

    # ----------------------------------
    # Delete
    # ----------------------------------
    def perform_destroy(self, instance):
        master_user, partner, contact_person, dtp, is_admin = self._get_access()

        if not is_admin:
            instance_partner = instance.contact_person.partner
            user_is_authorized = False

            if partner and instance_partner == partner:
                user_is_authorized = True
            elif dtp and instance_partner == dtp.partner:
                user_is_authorized = True
            elif contact_person and instance.contact_person == contact_person:
                user_is_authorized = True

            if not user_is_authorized:
                raise PermissionDenied("Unauthorized access.")

        instance.delete(by_user=master_user)
                
class TPCPCentreDetailViewSet(BaseTMSModelViewSet):
    """
    ViewSet to get details of TrainingPartnerCP along with allocated centres.
    """
    swagger_schema = PartnersSchema
    queryset = tms_models.TPCPToCentre.objects.select_related("contact_person", "allocated_centre")
    serializer_class = TPCPToCentreDetailSerializer
    filterset_fields = ["contact_person", "allocated_centre", "created_by"]    

    def get_queryset(self):
        qs = super().get_queryset()
        auth_user = self.request.user

        master_user = core_models.MasterUser.objects.filter(username=auth_user.username).first()
        if not master_user:
            return qs.none()

        is_tp_owner = tms_models.TrainingPartner.objects.filter(master_user=master_user).exists()
        is_tpcp = tms_models.TrainingPartnerCP.objects.filter(master_user=master_user).exists()
        is_dtp = tms_models.DistrictTP.objects.filter(master_user=master_user).exists()
        is_admin = not (is_tp_owner or is_tpcp or is_dtp)

        if not is_admin:
            qs = qs.filter(
                Q(contact_person__partner__master_user=master_user) |               # TP Owner
                Q(contact_person__master_user=master_user) |                        # Contact Person Specific
                Q(contact_person__partner__district_nodes__master_user=master_user) # District TP Node
            ).distinct()

        return qs

class TrainingPartnerSubmissionViewSet(BaseTMSModelViewSet):
    """
    Image/PDF submissions by partners for centres (fooding, toilets, etc.).
    """
    swagger_schema = PartnersSchema
    queryset = (
        tms_models.TrainingPartnerSubmission.objects
        .select_related("partner", "centre")
        .filter(is_active=1)
    )
    serializer_class = TrainingPartnerSubmissionSerializer
    filterset_fields = ["partner", "centre", "category"]
    parser_classes = [MultiPartParser, FormParser]

    def get_queryset(self):
        qs = super().get_queryset()
        auth_user = self.request.user

        master_user = core_models.MasterUser.objects.filter(username=auth_user.username).first()
        if not master_user:
            return qs.none()

        is_tp_owner = tms_models.TrainingPartner.objects.filter(master_user=master_user).exists()
        is_tpcp = tms_models.TrainingPartnerCP.objects.filter(master_user=master_user).exists()
        is_dtp = tms_models.DistrictTP.objects.filter(master_user=master_user).exists()
        is_admin = not (is_tp_owner or is_tpcp or is_dtp)

        if not is_admin:
            qs = qs.filter(
                Q(partner__master_user=master_user) |               # TP Owner
                Q(partner__contact_person__master_user=master_user) | # TP Contact Person
                Q(partner__district_nodes__master_user=master_user) # District TP Node
            ).distinct()

        return qs

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def download_submission(request, pk):
    submission = get_object_or_404(
        tms_models.TrainingPartnerSubmission,
        pk=pk,
        is_active=1,
    )

    safe_path = os.path.normpath(submission.file.name).lstrip("/")
    file_path = os.path.join(settings.MEDIA_ROOT, safe_path)
    
    if not os.path.exists(file_path):
        raise Http404("File not found")

    return FileResponse(
        open(file_path, "rb"),
        as_attachment=True,
        filename=os.path.basename(file_path),
    )    
    

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def preview_submission(request, pk):
    submission = get_object_or_404(
        tms_models.TrainingPartnerSubmission,
        pk=pk,
        is_active=1,
    )

    safe_path = os.path.normpath(submission.file.name).lstrip("/")

    response = HttpResponse()
    response["X-Accel-Redirect"] = f"/media/{safe_path}"
    response["Content-Type"] = submission.file.file.content_type
    response["X-Content-Type-Options"] = "nosniff"
    return response

# -------------------------------------------------------------------
# Targets & Authority
# -------------------------------------------------------------------

class TrainingPartnerTargetsViewSet(BaseTMSModelViewSet):
    """
    Targets assigned by SMMU to Training Partners (Module/District/Theme).
    """
    swagger_schema = TargetsSchema
    filterset_fields = ["partner", "target_type", "training_plan", "district", "theme", "financial_year", "created_by"]
    search_fields = ["theme", "financial_year"]
    
    # --- SURGICAL ADDITION: 25 items per page pagination ---
    pagination_class = TargetsPagination
    # -------------------------------------------------------

    def get_queryset(self):
        # Base Queryset with select_related for standard foreign keys
        qs = tms_models.TrainingPartnerTargets.objects.select_related(
            "partner", "training_plan", "district"
        )

        if self.request.query_params.get('ach') == '1':
            # Prefetch achievements to avoid N+1 database query crashing
            qs = qs.prefetch_related('achievements', 'achievements__partner', 'achievements__training_plan', 'achievements__district')
            
            # Map the '?year=' query param to the 'financial_year' field
            year = self.request.query_params.get('year')
            if year:
                qs = qs.filter(financial_year=year)

        # ==========================================================
        # SURGICAL FIX: SERVER-SIDE FILTERING FOR PAGINATION
        # ==========================================================
        
        # 1. Filter by comma-separated themes (e.g. "?themes=FNHW,Health")
        themes_param = self.request.query_params.get('themes')
        if themes_param:
            theme_list = [t.strip() for t in themes_param.split(',') if t.strip()]
            if theme_list:
                qs = qs.filter(theme__in=theme_list)
                
        # 2. Search by partner name 
        partner_name = self.request.query_params.get('partner_name')
        if partner_name:
            qs = qs.filter(partner__name__icontains=partner_name)

        return qs

    def get_serializer_class(self):
        # --- SURGICAL ADDITION: Switch Serializers Dynamically ---
        if self.request.query_params.get('ach') == '1':
            return TrainingPartnerTargetsDetailedSerializer
        # ---------------------------------------------------------
        
        return TrainingPartnerTargetsSerializer

    # =====================================================
    # SURGICAL ADDITION: PATCH OVERRIDE FOR ACHIEVEMENT
    # =====================================================
    def partial_update(self, request, *args, **kwargs):
        # 1. Intercept the custom payload from the frontend
        if "achieved_count" in request.data:
            target = self.get_object()
            new_count = int(request.data.get("achieved_count", 0))

            # 2. Get the auto-created achievement record (from your save override)
            achievement = target.achievements.first()

            if achievement:
                # Update existing
                achievement.batches_completed = new_count
                achievement.save()
            else:
                # Failsafe: Create if it somehow doesn't exist
                target.achievements.create(
                    partner=target.partner,
                    batches_completed=new_count,
                    financial_year=target.financial_year,
                    training_plan=target.training_plan,
                    district=target.district,
                )
            
            return Response({"detail": "Achievement updated successfully."}, status=status.HTTP_200_OK)
            
        # 3. Fallback to default DRF behavior for other normal target updates
        return super().partial_update(request, *args, **kwargs)

    # =====================================================
    # SURGICAL ADDITION: LIST OVERRIDE FOR EXPORT
    # =====================================================
    def list(self, request, *args, **kwargs):
        if request.query_params.get("export") == "excel":
            # Apply all filters/search to the export queryset
            queryset = self.filter_queryset(self.get_queryset())
            return self._export_excel(queryset)
        
        # Standard default DRF behavior handles the 25-item JSON pagination
        return super().list(request, *args, **kwargs)

    # =====================================================
    # SURGICAL ADDITION: EXCEL STREAMER (FIXED)
    # =====================================================
    def _export_excel(self, queryset):
        output = BytesIO()
        workbook = xlsxwriter.Workbook(output, {"constant_memory": True})
        worksheet = workbook.add_worksheet("Targets")

        # Blue background and white text as requested
        header_format = workbook.add_format({
            "bold": True,
            "bg_color": "#1565C0",  # Deep Blue
            "color": "#FFFFFF",     # White Text
            "border": 1,
        })

        columns = [
            ("partner_name", "Training Partner"),
            ("target_type", "Target Type"),
            ("plan_name", "Training Plan"),
            ("district_name", "District"),
            ("theme", "Theme"),
            ("financial_year", "Financial Year"),
        ]

        # Header
        for col, (_, title) in enumerate(columns):
            worksheet.write(0, col, title, header_format)

        # EXACT MODEL FIELD MAPPING FIXES
        values_qs = queryset.values(
            "target_type",
            "theme",
            "financial_year",
            partner_name=F("partner__name"),                   # Matches TrainingPartner.name
            plan_name=F("training_plan__training_name"),       # Matches TrainingPlan.training_name
            district_name=F("district__district_name_en")      # Matches MasterDistrict.district_name_en
        )

        row = 1
        for record in values_qs.iterator(chunk_size=5000):
            for col, (key, _) in enumerate(columns):
                worksheet.write(row, col, record.get(key) or "")
            row += 1

        workbook.close()
        # Ensure we are reading from the start of the BytesIO buffer
        output.seek(0)

        filename = f"Training_Partner_Targets_{datetime.now().date()}.xlsx"

        # SURGICAL FIX: Use HttpResponse and output.getvalue() to prevent binary corruption
        response = HttpResponse(
            output.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

class BulkAssignTargetsAPIView(APIView):
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request, *args, **kwargs):
        file_obj = request.FILES.get('file')
        if not file_obj:
            return Response({"error": "No file uploaded."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # 1. Read file in memory
            if file_obj.name.endswith('.csv'):
                df = pd.read_csv(file_obj)
            elif file_obj.name.endswith(('.xls', '.xlsx')):
                df = pd.read_excel(file_obj)
            else:
                return Response(
                    {"error": "Invalid file format. Please upload a CSV or Excel file."}, 
                    status=status.HTTP_400_BAD_REQUEST
                )

            success_count = 0
            errors = []

            # 2. Open an atomic transaction
            with transaction.atomic():
                for index, row in df.iterrows():
                    row_number = index + 2  # +2 accounts for 0-index and header row

                    try:
                        # --- SAFE EXTRACTION: Handle pandas NaN explicitly ---
                        partner_id = row.get('partner_id')
                        if pd.isna(partner_id):
                            raise ValueError("partner_id is required.")

                        target_type = row.get('target_type')
                        target_type = "MODULE" if pd.isna(target_type) else str(target_type).strip().upper()
                        
                        training_plan_id = row.get('training_plan_id')
                        training_plan_id = None if pd.isna(training_plan_id) else training_plan_id
                        
                        # Fix for the NaN issue
                        district_id = row.get('district_id')
                        district_id = None if pd.isna(district_id) else int(district_id)
                        
                        district_name_en = row.get('district_name_en')
                        district_name_en = None if pd.isna(district_name_en) else str(district_name_en).strip()
                        
                        target_count = row.get('target_count', 0)
                        target_count = 0 if pd.isna(target_count) else int(target_count)
                        
                        financial_year = row.get('financial_year')
                        financial_year = None if pd.isna(financial_year) else str(financial_year).strip()
                        
                        notes = row.get('notes')
                        notes = None if pd.isna(notes) else str(notes).strip()

                        # --- Validation: Either ID or Name MUST exist ---
                        if not district_id and not district_name_en:
                            raise ValueError("Either 'district_id' or 'district_name_en' must be provided.")

                        # Fetch Partner
                        partner = tms_models.TrainingPartner.objects.filter(id=partner_id).first()
                        if not partner:
                            raise ValueError(f"TrainingPartner with ID {partner_id} not found.")

                        # Fetch Training Plan
                        training_plan = tms_models.TrainingPlan.objects.filter(id=training_plan_id).first() if training_plan_id else None

                        # --- Fetch District by ID or Name ---
                        district = None
                        if district_id:
                            district = MasterDistrict.objects.filter(pk=district_id).first()
                            if not district:
                                raise ValueError(f"District with ID {district_id} not found.")
                        elif district_name_en:
                            district = MasterDistrict.objects.filter(district_name_en__iexact=district_name_en).first()
                            if not district:
                                raise ValueError(f"District with name '{district_name_en}' not found.")

                        # 3. Constraint Check
                        exists = tms_models.TrainingPartnerTargets.objects.filter(
                            partner=partner,
                            target_type=target_type,
                            training_plan=training_plan,
                            district=district,
                            financial_year=financial_year
                        ).exists()

                        if exists:
                            raise ValueError(f"Target already exists for this Partner, Module, District, and FY ({financial_year}).")

                        # 4. Create Instance
                        target = tms_models.TrainingPartnerTargets(
                            partner=partner,
                            target_type=target_type,
                            training_plan=training_plan,
                            district=district,
                            target_count=target_count,
                            financial_year=financial_year,
                            notes=notes
                        )
                        
                        target.save()
                        success_count += 1

                    except Exception as e:
                        errors.append(f"Row {row_number}: {str(e)}")

                # Rollback if errors exist
                if errors:
                    raise Exception("Validation errors occurred. Transaction rolled back.")

            return Response(
                {"message": f"Successfully created {success_count} targets."}, 
                status=status.HTTP_201_CREATED
            )

        except Exception as e:
            if errors:
                return Response({
                    "error": "Upload failed due to data errors.",
                    "details": errors
                }, status=status.HTTP_400_BAD_REQUEST)
            
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


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
    filterset_fields = ["training", "district", "block", "pld_status", "training__partner",]
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
    filterset_fields = ["training", "trainer" , "district" , "block", "training__partner",]

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
    serializer_class = BatchSerializer
    filterset_fields = ["centre", "status", "start_date", "end_date", "created_by"]
    search_fields = ["code"]

    def get_queryset(self):
        # 1. select_related for ForeignKeys and OneToOne fields directly on Batch
        qs = tms_models.Batch.objects.select_related(
            "centre", 
            "training_plan", # --- SURGICAL FIX: Changed from request__training_plan
        )
        
        # 2. prefetch_related for reverse relations (only active on detail views to save memory)
        if self.action in ['retrieve', 'detail_view']:
            qs = qs.prefetch_related(
                # --- SURGICAL FIX: Bulletproof prefetches ---
                "batch_costing", # Moved here to prevent 500 if DB isn't perfectly migrated
                "batch_closing", # Moved here to prevent 500 if DB isn't perfectly migrated
                "beneficiary",
                "trainer",
                "master_trainers",                
                # --------------------------------------------

                # Participants
                Prefetch("beneficiary_participations", queryset=tms_models.BatchBeneficiary.objects.filter(is_active=True).select_related('beneficiary')),
                Prefetch("trainer_participations", queryset=tms_models.BatchTrainer.objects.filter(is_active=True).select_related('trainer')),
                Prefetch("master_trainer_participations", queryset=tms_models.BatchMasterTrainer.objects.filter(is_active=True).select_related('master_trainer')),
                
                # Operations & eKYC
                Prefetch("ekyc_verifications", queryset=tms_models.BatchEkycVerification.objects.filter(is_active=True)),
                Prefetch("schedules", queryset=tms_models.BatchSchedule.objects.filter(is_active=True)),
                
                # Attendance (Raw & Summary)
                Prefetch(
                    "attendances",
                    queryset=tms_models.BatchAttendance.objects.filter(is_active=True).prefetch_related(
                        Prefetch("participant_records", queryset=tms_models.ParticipantAttendance.objects.filter(is_active=True))
                    )
                ),
                Prefetch("beneficiary_summaries", queryset=tms_models.BeneficiaryAttendanceSummary.objects.filter(is_active=True)),

                # Costing Breakdowns
                Prefetch("participant_costs", queryset=tms_models.TPBatchCostBreakup.objects.filter(is_active=True)),

                # Closure, Media, Certificates
                Prefetch("batch_pictures", queryset=tms_models.BatchMedia.objects.filter(is_active=True)),
                Prefetch("batch_report", queryset=tms_models.BatchReport.objects.filter(is_active=True)),
                Prefetch("batch_certificates", queryset=tms_models.BatchParticipantCertificate.objects.filter(is_active=True)),
            )
        return qs

    @swagger_auto_schema(
        operation_summary="Retrieve absolutely everything related to the batch (Participants, Attendance, Costing, eKYC)",
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
                        batch=batch,
                        beneficiary_id__in=beneficiary_ids,
                        is_active=True,
                    ).values_list("beneficiary_id", flat=True)
                )

                # Reactivate soft-deleted beneficiaries
                tms_models.BatchBeneficiary.objects.filter(
                    batch=batch,
                    beneficiary_id__in=beneficiary_ids,
                    is_active=False,
                ).update(is_active=True)

                new_ids = [bid for bid in beneficiary_ids if bid not in existing]
                tms_models.BatchBeneficiary.objects.bulk_create(
                    [tms_models.BatchBeneficiary(batch=batch, beneficiary_id=bid) for bid in new_ids]
                )

            if trainer_ids:
                existing = set(
                    tms_models.BatchTrainer.objects.filter(
                        batch=batch,
                        trainer_id__in=trainer_ids,
                        is_active=True,
                    ).values_list("trainer_id", flat=True)
                )

                # Reactivate soft-deleted trainers
                tms_models.BatchTrainer.objects.filter(
                    batch=batch,
                    trainer_id__in=trainer_ids,
                    is_active=False,
                ).update(is_active=True)

                new_ids = [tid for tid in trainer_ids if tid not in existing]
                tms_models.BatchTrainer.objects.bulk_create(
                    [tms_models.BatchTrainer(batch=batch, trainer_id=tid) for tid in new_ids]
                )

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

    @swagger_auto_schema(
        method="get",
        operation_summary="Generate batch certificate PDF in Hindi (BMMU/DMMU/SMMU only)",
        manual_parameters=[
            openapi.Parameter(
                "financial_year",
                openapi.IN_QUERY,
                description="वित्तीय वर्ष, e.g. 2024-25",
                type=openapi.TYPE_STRING,
                required=True,
            )
        ],
        responses={
            200: openapi.Response(description="PDF file download"),
            400: "Batch not eligible — not CLOSED or certificates not issued.",
            500: "Font file missing — see server logs.",
        },
    )
    @action(detail=True, methods=["get"], url_path="gen-cert")
    def gen_cert(self, request, pk=None):
        """
        Generate and stream a Hindi certificate PDF for a closed batch.
        Guards:
        - batch.status must be 'CLOSED'
        - BatchClosureRequest.certificates_issued must be True

        Query param:
        - financial_year (required) e.g. 2024-25
        """
        financial_year = request.query_params.get("financial_year", "").strip()
        if not financial_year:
            return Response(
                {"detail": "'financial_year' query parameter is required (उदाहरण: 2024-25)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ── Fetch batch with ALL required relations ──
        try:
            batch = (
                tms_models.Batch.objects
                .select_related(
                    # --- SURGICAL FIX: Replaced `request__` lookups with direct relations ---
                    "training_plan",
                    "training_plan__theme",
                    "district",
                    "block",
                    "centre",
                    "batch_closing",   # OneToOne
                )
                .prefetch_related(
                    Prefetch(
                        "beneficiary_participations",
                        queryset=tms_models.BatchBeneficiary.objects.filter(is_active=True)
                        .select_related(
                            "beneficiary",
                            "beneficiary__district",
                            "beneficiary__block",
                            "attendance_summary",
                        ),
                    ),
                    Prefetch(
                        "trainer_participations",
                        queryset=tms_models.BatchTrainer.objects.filter(is_active=True)
                        .select_related("trainer", "trainer__trainer"),
                    ),
                    Prefetch(
                        "master_trainer_participations",
                        queryset=tms_models.BatchMasterTrainer.objects.filter(is_active=True)
                        .select_related("master_trainer"),
                    ),
                )
                .get(pk=pk)
            )
        except tms_models.Batch.DoesNotExist:
            return Response({"detail": "Batch not found."}, status=status.HTTP_404_NOT_FOUND)

        # ── Guard 1: CLOSED status ──
        if batch.status != "CLOSED":
            return Response(
                {
                    "detail": (
                        f"प्रमाण पत्र केवल 'CLOSED' स्थिति वाले बैच के लिए उत्पन्न होता है। "
                        f"वर्तमान स्थिति: {batch.status}"
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ── Guard 2: certificates_issued = True ──
        try:
            closure = batch.batch_closing
            if not closure.certificates_issued:
                return Response(
                    {
                        "detail": (
                            "DMMU द्वारा certificates_issued=True किए जाने के बाद "
                            "ही प्रमाण पत्र जनरेट किया जा सकता है।"
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
        except tms_models.BatchClosureRequest.DoesNotExist:
            return Response(
                {"detail": "इस बैच के लिए कोई Closure Request नहीं मिली।"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ── Determine role ──
        master_user = get_master_user_from_request(request)
        role_id = getattr(master_user.role, "id", None) if master_user and master_user.role else None
        role_label = {1: "bmmu", 2: "dmmu", 3: "smmu"}.get(role_id, "dmmu")

        # ── Generate PDF ──
        try:
            pdf_buffer = generate_batch_certificate_pdf(
                batch=batch,
                financial_year=financial_year,
                master_user=master_user,
                role_label=role_label,
            )
        except RuntimeError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        filename = f"pragati_setu_certificate_batch_{batch.code or batch.id}.pdf"
        response = HttpResponse(pdf_buffer.read(), content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="{filename}"'
        return response

class BatchListPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = None
    max_page_size = 10

class BatchesListView(APIView):
    """
    Unified Batches List API with full filtering support.

    Filters supported:
    - Geography:
        mandal_id
        district_category_id
        district_id
        block_id

    - Training / Batch:
        centre_id
        batch_type
        status

    - Training Plan (via request):
        training_plan_id
        theme_id
        partner_id
        training_type

    - Ownership:
        created_by

    Ordering:
        start_date, -start_date
        end_date, -end_date
    """

    def get(self, request):
        params = request.GET

        qs = (
            tms_models.Batch.objects
            .filter(is_active=True)
            .select_related(
                "district",
                "block",
                "training_plan",
                "training_plan__theme",
                "centre",
                "centre__partner",
            )
            .annotate(
                pax_count=Count('beneficiary', distinct=True) + Count('trainer', distinct=True)
            )
        )

        # -------------------------
        # GEOGRAPHICAL FILTERS
        # -------------------------

        mandal_id = params.get("mandal_id")
        district_category_id = params.get("district_category_id")
        district_id = params.get("district_id")
        block_id = params.get("block_id")

        if mandal_id:
            qs = qs.filter(district__mandal_id=mandal_id)

        if district_category_id:
            qs = qs.filter(
                district__masterdistrictcategorymapping__category_id=district_category_id
            )

        if district_id:
            qs = qs.filter(district=district_id)

        if block_id:
            # SURGICAL CHANGE: Check both the direct block AND the block_coverages mapping
            qs = qs.filter(
                Q(block=block_id) | Q(block_coverages__block=block_id)
            ).distinct()

        # -------------------------
        # TRAINING / BATCH FILTERS
        # -------------------------

        centre_id = params.get("centre_id")
        batch_type = params.get("batch_type")
        status = params.get("status")

        if centre_id:
            qs = qs.filter(centre_id=centre_id)

        if batch_type:
            qs = qs.filter(batch_type=batch_type)

        if status:
            qs = qs.filter(status=status)

        # -------------------------
        # TRAINING PLAN FILTERS 
        # -------------------------

        training_plan_id = params.get("training_plan_id")
        theme_id = params.get("theme_id")
        partner_id = params.get("partner_id")
        training_type = params.get("training_type")

        if training_plan_id:
            qs = qs.filter(training_plan_id=training_plan_id)

        if theme_id:
            qs = qs.filter(training_plan__theme_id=theme_id)

        if partner_id:
            qs = qs.filter(training_plan__partner_id=partner_id)

        if training_type:
            qs = qs.filter(participant_type=training_type)

        # -------------------------
        # OWNERSHIP FILTER
        # -------------------------

        created_by = params.get("created_by")
        if created_by:
            qs = qs.filter(created_by_id=created_by)

        # -------------------------
        # ORDERING
        # -------------------------

        ordering = params.get("ordering", "start_date")
        allowed_ordering = {
            "start_date", "-start_date",
            "end_date", "-end_date",
        }

        if ordering not in allowed_ordering:
            ordering = "start_date"

        qs = qs.order_by(ordering)

        # -------------------------
        # PAGINATION
        # -------------------------

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
    Line-item cost for a SINGLE successful participant (HRA + TA/DA).
    """
    swagger_schema = ClosureSchema
    queryset = tms_models.TPBatchCostBreakup.objects.select_related("batch")
    serializer_class = TPBatchCostBreakupSerializer
    filterset_fields = ["batch", "batch_beneficiary", "batch_trainer"]

    # --- SURGICAL ADDITION: Auto-calculate line item total ---
    def perform_create(self, serializer):
        hra = serializer.validated_data.get('hra', 0)
        ta_da = serializer.validated_data.get('ta_da', 0)
        serializer.save(total_cost=hra + ta_da)

    def perform_update(self, serializer):
        hra = serializer.validated_data.get('hra', 0)
        ta_da = serializer.validated_data.get('ta_da', 0)
        serializer.save(total_cost=hra + ta_da)


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
    Master invoice for the entire Batch.
    """
    swagger_schema = ClosureSchema
    queryset = tms_models.BatchCost.objects.select_related("training", "batch")
    serializer_class = BatchCostSerializer
    filterset_fields = ["batch", "training"]

    @action(detail=True, methods=["get"], url_path="detail")
    def detail_view(self, request, pk=None):
        batch_cost = get_object_or_404(
            tms_models.BatchCost.objects.select_related("training", "batch"),
            batch_id=pk
        )
        serializer = BatchCostDetailSerializer(batch_cost, context={"request": request})
        return Response(serializer.data)

    # --- SURGICAL ADDITION: Auto-calculate Master Invoice Total ---
    def _calculate_grand_total(self, obj):
        breakups = tms_models.TPBatchCostBreakup.objects.filter(batch=obj.batch, is_active=True)
        total_breakups = sum(b.total_cost for b in breakups)
        obj.grand_total_cost = total_breakups + obj.exposure_visit_cost + obj.field_visit_cost
        obj.save(update_fields=['grand_total_cost'])

    def perform_create(self, serializer):
        obj = serializer.save()
        self._calculate_grand_total(obj)

    def perform_update(self, serializer):
        obj = serializer.save()
        self._calculate_grand_total(obj)


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
    Batch-level closure request: Training Partner → DMMU.

    Standard CRUD operates on BatchClosureRequest rows.
    The `submit` action is the entry point for TP to submit a full
    closure package (costs + closure request) in a single atomic call.

    When DMMU later sets certificates_issued=True via a PATCH/PUT,
    perform_update auto-generates BatchParticipantCertificate rows.
    """
    swagger_schema = ClosureSchema
    queryset = tms_models.BatchClosureRequest.objects.select_related(
        "batch", "batch_costing"
    )
    serializer_class = BatchClosureRequestSerializer
    filterset_fields = ["batch", "certificates_issued"]

    # ------------------------------------------------------------------
    # EXISTING: Auto-Generate Certificates when DMMU approves
    # ------------------------------------------------------------------
    def perform_update(self, serializer):
        original_instance = self.get_object()
        was_issued = original_instance.certificates_issued

        instance = serializer.save()

        # TRIGGER: If certificates_issued flips to True
        if instance.certificates_issued and not was_issued:
            batch = instance.batch
            
            # --- SURGICAL FIX: Natively pull training_plan from Batch ---
            training_plan = batch.training_plan
            theme = training_plan.theme if training_plan else None

            # 1. Generate Certificates for SUCCESSFUL Beneficiaries
            successful_bens = tms_models.BatchBeneficiary.objects.filter(
                batch=batch,
                attendance_summary__is_successful=True,
                is_active=True
            ).select_related('beneficiary')

            for bb in successful_bens:
                tms_models.BatchParticipantCertificate.objects.get_or_create(
                    batch=batch,
                    tr_beneficiary=bb.beneficiary
                )

            # 2. Generate Certificates for SUCCESSFUL Trainers
            # --- SURGICAL FIX: Standardized to use attendance_summary__is_successful ---
            successful_trainers = tms_models.BatchTrainer.objects.filter(
                batch=batch,
                attendance_summary__is_successful=True,
                is_active=True
            ).select_related('trainer')

            for bt in successful_trainers:
                tms_models.BatchParticipantCertificate.objects.get_or_create(
                    batch=batch,
                    tr_trainer=bt.trainer
                )

    # ------------------------------------------------------------------
    # NEW: TP submits full closure package atomically
    # ------------------------------------------------------------------
    @swagger_auto_schema(
        method="post",
        operation_summary="TP → DMMU: Submit full batch closure package",
        operation_description=(
            "Training Partner submits participant cost breakups, "
            "master batch cost, and creates the BatchClosureRequest "
            "in a single atomic call. Batch status is flipped to REVIEW."
        ),
        request_body=BatchClosureSubmitSerializer,
        responses={
            201: openapi.Response(
                description="Closure package created successfully.",
                schema=BatchClosureSubmitResponseSerializer(),
            ),
            400: "Validation error or closure already submitted.",
        },
    )
    @action(detail=False, methods=["post"], url_path="submit-closure")
    def submit_closure(self, request):
        """
        Atomic endpoint for Training Partner to submit a batch closure.

        Steps performed inside a DB transaction:
          1. Validate the full payload (see BatchClosureSubmitSerializer).
          2. Bulk-create TPBatchCostBreakup rows (one per participant).
          3. Create BatchCost (master invoice) linked to the batch.
          4. Create BatchClosureRequest linked to both batch and BatchCost.
          5. Flip Batch.status → REVIEW.
        """
        serializer = BatchClosureSubmitSerializer(
            data=request.data,
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data

        batch = validated['batch_id']                          # Batch instance
        training_request = validated['training_request_id']   # TrainingRequest instance

        with transaction.atomic():
            # ── STEP 1: Bulk-create TPBatchCostBreakup rows ──────────────
            cost_breakup_objs = []
            for item in validated['participant_costs']:
                ben_obj     = item.get('batch_beneficiary_id')   # BatchBeneficiary | None
                trainer_obj = item.get('batch_trainer_id')       # BatchTrainer     | None

                participant_type = 'BENEFICIARY' if ben_obj else 'TRAINER'

                cost_breakup_objs.append(
                    tms_models.TPBatchCostBreakup(
                        batch=batch,
                        batch_beneficiary=ben_obj,
                        batch_trainer=trainer_obj,
                        participant_type=participant_type,
                        hra=item['hra'],
                        ta_da=item['ta_da'],
                        total_cost=item['total_cost'],
                    )
                )

            created_breakups = tms_models.TPBatchCostBreakup.objects.bulk_create(
                cost_breakup_objs
            )

            # ── STEP 2: Create BatchCost (master invoice) ─────────────────
            batch_cost = tms_models.BatchCost.objects.create(
                batch=batch,
                training=training_request,
                is_exposure_visit=validated['is_exposure_visit'],
                exposure_visit_cost=validated['exposure_visit_cost'],
                is_field_visit=validated['is_field_visit'],
                field_visit_cost=validated['field_visit_cost'],
                grand_total_cost=validated['grand_total_cost'],
            )

            # ── STEP 3: Create BatchClosureRequest, linked to BatchCost ───
            closure_request = tms_models.BatchClosureRequest.objects.create(
                batch=batch,
                batch_costing=batch_cost,
                certificates_issued=False,
            )

            # ── STEP 4: Flip Batch.status → REVIEW ───────────────────────
            batch.status = 'REVIEW'
            batch.save(update_fields=['status', 'updated_at'])

        # ── Build response ────────────────────────────────────────────────
        response_data = BatchClosureSubmitResponseSerializer({
            'participant_costs': created_breakups,
            'batch_cost': batch_cost,
            'closure_request': closure_request,
            'batch_status': batch.status,
        }).data

        return Response(response_data, status=status.HTTP_201_CREATED)
    
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
    
# TR list with filters    
class TrainingRequestListViewSet(ReadOnlyModelViewSet):
    serializer_class = TrainingRequestListSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        params = self.request.query_params

        qs = (
            tms_models.TrainingRequest.objects
            .select_related(
                'training_plan',
                'training_plan__theme',
                'partner',
                'district',
                'block',
                'district__mandal',
            )
            .filter(deleted_at__isnull=True)
            .order_by('-id')
        )

        # --------------------------------------------------
        # ✅ PURE FILTERS (NO ROLE / NO GEO ENFORCEMENT)
        # --------------------------------------------------

        if params.get('theme_id'):
            qs = qs.filter(training_plan__theme_id=params['theme_id'])

        if params.get('training_plan_id'):
            qs = qs.filter(training_plan_id=params['training_plan_id'])

        if params.get('partner_id'):
            qs = qs.filter(partner_id=params['partner_id'])

        if params.get('training_type'):
            qs = qs.filter(training_type=params['training_type'])

        if params.get('level'):
            qs = qs.filter(level=params['level'])

        if params.get('status'):
            qs = qs.filter(status=params['status'])

        if params.get('mandal_id'):
            qs = qs.filter(district__mandal_id=params['mandal_id'])

        if params.get('district_category_id'):
            district_ids = MasterDistrictCategoryMapping.objects.filter(
                category_id=params['district_category_id']
            ).values_list('district_id', flat=True)

            qs = qs.filter(district_id__in=district_ids)

        if params.get('district_id'):
            qs = qs.filter(district_id=params['district_id'])

        if params.get('block_id'):
            qs = qs.filter(block_id=params['block_id'])

        if params.get('financial_year'):
            qs = qs.filter(financial_year=params['financial_year'])            

        # --------------------------------------------------
        # ✅ NEW: CREATED_AT FILTERS
        # --------------------------------------------------

        # Exact date
        if params.get('created_at'):
            qs = qs.filter(created_at__date=params['created_at'])

        # Range filtering
        if params.get('created_from'):
            qs = qs.filter(
                created_at__gte=datetime.strptime(params['created_from'], "%Y-%m-%d")
            )

        if params.get('created_to'):
            qs = qs.filter(
                created_at__lte=datetime.strptime(params['created_to'], "%Y-%m-%d").replace(hour=23, minute=59, second=59)
            )

        return qs

# Check if participants are engaged in ongoing trainings (bulk API for TP onboarding)
class BulkTrainingEngagementCheckAPI(APIView):
    """
    Bulk check if participants are engaged in ongoing trainings.

    Input:
    {
        "participant_type": "BENEFICIARY" | "TRAINER",
        "financial_year": "2023-24",  # Optional but recommended
        "ids": ["id1", "id2", ...]
    }

    Output:
    {
        "eligible_ids": [...],
        "engaged_ids": [...]
    }
    """

    def post(self, request):
        participant_type = request.data.get("participant_type")
        financial_year = request.data.get("financial_year")
        ids = request.data.get("ids", [])

        if participant_type not in ["BENEFICIARY", "TRAINER"]:
            return Response(
                {"error": "Invalid participant_type"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not isinstance(ids, list) or not ids:
            return Response(
                {"error": "ids must be a non-empty list"},
                status=status.HTTP_400_BAD_REQUEST
            )

        engaged_ids = set()

        # -------------------------------
        # BENEFICIARY CASE
        # -------------------------------
        if participant_type == "BENEFICIARY":
            # Rule 1: Check TRBeneficiary (Engaged if TrainingRequest is NOT COMPLETED/REJECTED)
            tr_bens_qs = tms_models.TRBeneficiary.objects.exclude(
                training__status__in=["COMPLETED", "REJECTED"]
            ).filter(
                lokos_member_code__in=ids
            )
            
            # Apply strict Financial Year filter if provided
            if financial_year:
                tr_bens_qs = tr_bens_qs.filter(training__financial_year=financial_year, is_active=True)
                
            engaged_tr_bens = tr_bens_qs.values_list("lokos_member_code", flat=True)

            # Rule 2: Check BatchBeneficiary (Engaged if Batch is NOT COMPLETED/CLOSED/REJECTED)
            batch_bens_qs = tms_models.BatchBeneficiary.objects.exclude(
                batch__status__in=["COMPLETED", "CLOSED", "REJECTED"]
            ).filter(
                beneficiary__lokos_member_code__in=ids
            )
            
            # Apply strict Financial Year filter if provided
            if financial_year:
                batch_bens_qs = batch_bens_qs.filter(batch__financial_year=financial_year, is_active=True)
                
            engaged_batch_bens = batch_bens_qs.values_list("beneficiary__lokos_member_code", flat=True)

            engaged_ids = set(map(str, engaged_tr_bens)).union(set(map(str, engaged_batch_bens)))

        # -------------------------------
        # TRAINER CASE
        # -------------------------------
        elif participant_type == "TRAINER":
            # Rule 3: Check TRTrainer (Engaged if TrainingRequest is NOT COMPLETED/REJECTED)
            tr_trainers_qs = tms_models.TRTrainer.objects.exclude(
                training__status__in=["COMPLETED", "REJECTED"]
            ).filter(
                trainer_id__in=ids
            )
            
            if financial_year:
                tr_trainers_qs = tr_trainers_qs.filter(training__financial_year=financial_year, is_active=True)
                
            engaged_tr_trainers = tr_trainers_qs.values_list("trainer_id", flat=True)

            # Rule 4: Check BatchMasterTrainer (Engaged if Batch is NOT COMPLETED/CLOSED/REJECTED)
            batch_master_trainers_qs = tms_models.BatchMasterTrainer.objects.exclude(
                batch__status__in=["COMPLETED", "CLOSED", "REJECTED"]
            ).filter(
                master_trainer_id__in=ids
            )
            
            if financial_year:
                batch_master_trainers_qs = batch_master_trainers_qs.filter(batch__financial_year=financial_year, is_active=True)
                
            engaged_batch_master_trainers = batch_master_trainers_qs.values_list("master_trainer_id", flat=True)

            # Rule 5: Check BatchTrainer (Engaged if Batch is NOT COMPLETED/CLOSED/REJECTED)
            batch_trainers_qs = tms_models.BatchTrainer.objects.exclude(
                batch__status__in=["COMPLETED", "CLOSED", "REJECTED"]
            ).filter(
                trainer__trainer_id__in=ids
            )
            
            if financial_year:
                batch_trainers_qs = batch_trainers_qs.filter(batch__financial_year=financial_year)
                
            engaged_batch_trainers = batch_trainers_qs.values_list("trainer__trainer_id", flat=True)

            engaged_ids = set(map(str, engaged_tr_trainers)) \
                .union(set(map(str, engaged_batch_master_trainers))) \
                .union(set(map(str, engaged_batch_trainers)))

        # -------------------------------
        # FINAL RESPONSE
        # -------------------------------
        input_ids_set = set(map(str, ids))
        eligible_ids = list(input_ids_set - engaged_ids)

        return Response({
            "eligible_ids": eligible_ids,
            "engaged_ids": list(engaged_ids)
        }, status=status.HTTP_200_OK)

# Resolve Partner id from given DTP user_id
class DTPUserPartnerResolveView(APIView):
    """
    Resolve the Partner ID associated with a given DTP user_id.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        dtp_user_id = get_master_user_from_request(request).id
        try:
            dtp_user = MasterUser.objects.get(id=dtp_user_id)
            dtp_profile = tms_models.DistrictTP.objects.filter(master_user=dtp_user).first()
            if not dtp_profile:
                return Response(
                    {"detail": f"No DTP profile found for user_id {dtp_user_id}."},
                    status=status.HTTP_404_NOT_FOUND
                )
            partner_id = dtp_profile.partner.id if dtp_profile.partner else None
            return Response({"partner_id": partner_id}, status=status.HTTP_200_OK)
        except MasterUser.DoesNotExist:
            return Response(
                {"detail": f"DTP user with user_id {dtp_user_id} not found."},
                status=status.HTTP_404_NOT_FOUND
            )

# -------------------------------------------------------------------
# Deleted Participants & Related TRs View
# -------------------------------------------------------------------
class DeletedParticipantsView(APIView):
    """
    API View to retrieve soft-deleted participants (TRBeneficiary or TRTrainer) 
    for a given TrainingRequest, and parse the `remarks` to fetch related TrainingRequests.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, tr_id):
        # Use _base_manager in case the target TR itself is soft-deleted
        tr = get_object_or_404(tms_models.TrainingRequest._base_manager, id=tr_id)
        
        # 1. Fetch deleted participants based on training_type
        deleted_participants_data = []
        if tr.training_type == 'BENEFICIARY':
            # is_active=False identifies the soft-deleted rows
            participants = tms_models.TRBeneficiary._base_manager.filter(training=tr, is_active=False)
            deleted_participants_data = TRBeneficiarySerializer(participants, many=True).data
        elif tr.training_type == 'TRAINER':
            participants = tms_models.TRTrainer._base_manager.filter(training=tr, is_active=False)
            deleted_participants_data = TRTrainerSerializer(participants, many=True).data

        # 2. Parse remarks for related TrainingRequest IDs
        related_tr_ids = set()
        if tr.remarks:
            # Regex to find IDs from "MOVED TO <id> ," pattern
            moved_to_ids = re.findall(r'MOVED TO\s+(\d+)\s*,', tr.remarks)
            
            # Regex to find IDs from "COMBINED from <id>-<district>-<block> ," pattern
            combined_from_ids = re.findall(r'COMBINED from\s+(\d+)-', tr.remarks)
            
            for tid in moved_to_ids + combined_from_ids:
                try:
                    related_tr_ids.add(int(tid))
                except ValueError:
                    continue

        # 3. Fetch related TrainingRequests
        related_trs_data = []
        if related_tr_ids:
            related_trs = tms_models.TrainingRequest._base_manager.filter(id__in=related_tr_ids)
            related_trs_data = TrainingRequestSerializer(related_trs, many=True).data

        return Response({
            "training_request_id": tr.id,
            "training_type": tr.training_type,
            "remarks": tr.remarks,
            "deleted_participants": deleted_participants_data,
            "related_training_requests": related_trs_data
        }, status=status.HTTP_200_OK)        


# First Login Password Change API
class TMSFirstLoginVerifyOldPasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        master_user = get_master_user_from_request(request)
        if not master_user:
            return Response(
                {"detail": "Master user not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        # 1. Verify the First Login Tracker exists and requires a password change
        try:
            tracker = tms_models.TMSFirstLoginTracker.objects.get(master_user=master_user)
            if not tracker.must_change_password:
                return Response(
                    {"detail": "Password change is not required or has already been completed."},
                    status=status.HTTP_403_FORBIDDEN
                )
        except tms_models.TMSFirstLoginTracker.DoesNotExist:
            return Response(
                {"detail": "No TMS login record found for this user."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 2. Extract and verify the old password
        old_password = request.data.get("old_password")
        if not old_password:
            return Response(
                {"detail": "The 'old_password' parameter is required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 3. Cleartext comparison
        if master_user.password != old_password:
            return Response(
                {"detail": "Incorrect old password."},
                status=status.HTTP_400_BAD_REQUEST
            )

        return Response(
            {"detail": "Old password verified successfully."},
            status=status.HTTP_200_OK
        )
        

class TMSFirstLoginPasswordChangeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        Check if the current user needs to change their password 
        for their first TMS login.
        """
        master_user = get_master_user_from_request(request)
        if not master_user:
            return Response(
                {"detail": "Master user not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        try:
            tracker = tms_models.TMSFirstLoginTracker.objects.get(master_user=master_user)
            return Response(
                {"must_change_password": tracker.must_change_password},
                status=status.HTTP_200_OK
            )
        except tms_models.TMSFirstLoginTracker.DoesNotExist:
            # If the tracker doesn't exist, they don't have a pending first-login mandate
            return Response(
                {"must_change_password": False},
                status=status.HTTP_200_OK
            )

    def post(self, request):
        master_user = get_master_user_from_request(request)
        if not master_user:
            return Response(
                {"detail": "Master user not found."}, 
                status=status.HTTP_404_NOT_FOUND
            )

        # 1. Verify the First Login Tracker exists and requires a password change
        try:
            tracker = tms_models.TMSFirstLoginTracker.objects.get(master_user=master_user)
        except tms_models.TMSFirstLoginTracker.DoesNotExist:
            return Response(
                {"detail": "No TMS login record found for this user."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not tracker.must_change_password:
            return Response(
                {"detail": "Password change is not required or has already been completed."},
                status=status.HTTP_403_FORBIDDEN
            )

        # 2. Extract the new password
        new_password = request.data.get("new_password")
        if not new_password:
            return Response(
                {"detail": "The 'new_password' parameter is required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 3. Validations
        if new_password == master_user.password:
            return Response(
                {"detail": "New password cannot be the same as the old password."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if len(new_password) < 8:
            return Response(
                {"detail": "Password must be at least 8 characters long."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not re.search(r"[A-Z]", new_password):
            return Response(
                {"detail": "Password must contain at least one uppercase letter."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not re.search(r"[a-z]", new_password):
            return Response(
                {"detail": "Password must contain at least one lowercase letter."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not re.search(r"\d", new_password):
            return Response(
                {"detail": "Password must contain at least one digit."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", new_password):
            return Response(
                {"detail": "Password must contain at least one special character."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 4. Store the password in CLEARTEXT and update MasterUser audit fields
        master_user.password = new_password
        master_user.pass_updated_at = timezone.now()
        master_user.pass_updated_by = master_user
        master_user.save(update_fields=["password", "pass_updated_at", "pass_updated_by"])

        # 5. Clear the must_change_password flag so they can't hit this API again
        tracker.must_change_password = False
        tracker.save(update_fields=["must_change_password"])

        return Response(
            {"detail": "Password updated successfully."}, 
            status=status.HTTP_200_OK
        )