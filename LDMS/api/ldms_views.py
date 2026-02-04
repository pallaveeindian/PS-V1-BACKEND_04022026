# LDMS/api/ldms_views.py
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
from django.db.models import Q, Min, Subquery
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

from core.models import *
from LDMS.models import *
from LDMS.api.serializers import *


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

class DeparmentSchema(SwaggerAutoSchema):
    def get_tags(self, operation_keys=None):
        return ["LDMS – Departments & Schemes"]

class SupportCaptureSchema(SwaggerAutoSchema):
    def get_tags(self, operation_keys=None):
        return ["LDMS – Support Capture APIs"]

# -------------------------------------------------------------------
# Base ViewSet with soft-delete support
# -------------------------------------------------------------------

class BaseLDMSModelViewSet(viewsets.ModelViewSet):
    """
    Common base for LDMS CRUD viewsets:

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

# Departments and Scheme Views
class DepartmentViewSet(BaseLDMSModelViewSet):
    """
    CRUD for Department.
    """
    swagger_schema = DeparmentSchema
    queryset = Department.objects.all()
    serializer_class = DepartmentSerializer
    filterset_fields = ["id"]
    search_fields = ["name"]
    ordering_fields = ["name", "id"]

class SchemeViewSet(BaseLDMSModelViewSet):
    """
    CRUD for Scheme.
    """
    swagger_schema = DeparmentSchema
    queryset = Scheme.objects.select_related("department")
    serializer_class = SchemeSerializer
    filterset_fields = [
        "id",
        "department",
        "scope",
        "funding",
        "contact_point",
    ]
    search_fields = ["name", "code"]
    ordering_fields = ["name", "id"]

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
        DETAIL view – includes nested department.
        """
        scheme = self.get_object()
        serializer = SchemeDetailSerializer(scheme, context={"request": request})
        return Response(serializer.data)            
    
# Support Capture Views   
class recordedPLDViewset (BaseLDMSModelViewSet):
    """
    CRUD for recordedPLD.
    """
    swagger_schema = SupportCaptureSchema
    queryset = recorded_benefs.objects.all().order_by('-created_at')
    serializer_class = recordedPLDSerializer
    filterset_fields = [
        "id",
        "age",
        "gender",
        "marital_status",
        "social_category",
        "district_id",
        "block_id",
        "panchayat_id",
        "village_id",
        "pld_status",
        "designation",
        "religion",
        "support_bucket",
    ]
    search_fields = ["member_name", "lokos_shg_code", "lokos_member_code", "mobile"]
    ordering_fields = ["member_name", "id", "created_at", "updated_at", "age", "created_at", "updated_at"]
    
class SBtypeViewset(BaseLDMSModelViewSet):
    """
    CRUD for SBtype.
    Returns ONLY distinct bucket_type rows.
    """

    swagger_schema = SupportCaptureSchema
    serializer_class = SBtypeSerializer

    def get_queryset(self):
        # Step 1: Get one ID per distinct bucket_type
        distinct_ids = (
            SBtypes.objects
            .values("bucket_type")
            .annotate(min_id=Min("id"))
            .values("min_id")
        )

        # Step 2: Fetch full model objects
        return (
            SBtypes.objects
            .filter(id__in=Subquery(distinct_ids))
            .order_by("bucket_type")
        )

    filterset_fields = ["id"]
    search_fields = ["bucket_type"]
    ordering_fields = ["id", "bucket_type", "created_at", "updated_at"]

class SupportBucketViewset (BaseLDMSModelViewSet):
    """
    CRUD for SupportBucket.
    """
    swagger_schema = SupportCaptureSchema
    queryset = SupportBucket.objects.all().order_by('-created_at')
    serializer_class = SupportBucketSerializer
    filterset_fields = [
        "id",
        "bucket_type",
        "department",
        "scheme",
    ]
    search_fields = ["benefit_name"]
    ordering_fields = ["id", "support_bucket_name", "created_at", "updated_at", ]

class TrainingSupportViewset (BaseLDMSModelViewSet):
    """
    CRUD for TrainingSupport.
    """
    swagger_schema = SupportCaptureSchema
    queryset = TrainingSupport.objects.all().order_by('-created_at')
    serializer_class = TrainingSupportSerializer
    filterset_fields = [
        "id",
        "training_theme",
        "training_plan",
        "support_bucket",
    ]
    search_fields = ["id"]
    ordering_fields = ["id", "updated_at", "created_at"]    
    
class BucketApprovalViewset (BaseLDMSModelViewSet):
    """
    CRUD for BucketApproval.
    """
    swagger_schema = SupportCaptureSchema
    queryset = Bucket_Approval.objects.all()
    serializer_class = BucketApprovalSerializer
    filterset_fields = [
        "id",
        "approval_status",
        "approval_date",
        "support_bucket",
        "block_id",
        "panchayat_id",
    ]
    search_fields = ["id", "approved_by"]
    ordering_fields = ["id", "updated_at", "created_at"]  
    
    def get_queryset(self):
        """
        Supports:
        - ?mandal_id=
        - ?district_id=
        - ?dc_id= (district category)
        """
        qs = super().get_queryset().order_by("-created_at")

        request = self.request
        params = request.query_params

        mandal_id = params.get("mandal_id")
        district_id = params.get("district_id")
        dc_id = params.get("dc_id")

        # ----------------------------------
        # Filter by Mandal (via District → Block)
        # ----------------------------------
        if mandal_id:
            block_ids = MasterBlock.objects.filter(
                district__mandal_id=mandal_id
            ).values_list("block_id", flat=True)

            qs = qs.filter(block_id__in=block_ids)

        # ----------------------------------
        # Filter by District
        # ----------------------------------
        if district_id:
            block_ids = MasterBlock.objects.filter(
                district_id=district_id
            ).values_list("block_id", flat=True)

            qs = qs.filter(block_id__in=block_ids)

        # ----------------------------------
        # Filter by District Category (dc_id)
        # ----------------------------------
        if dc_id:
            district_ids = MasterDistrictCategoryMapping.objects.filter(
                category_id=dc_id
            ).values_list("district_id", flat=True)

            block_ids = MasterBlock.objects.filter(
                district_id__in=district_ids
            ).values_list("block_id", flat=True)

            qs = qs.filter(block_id__in=block_ids)

        return qs

    @action(
        detail=True,
        methods=["get"],
        url_path="full-detail"
    )
    def full_detail(self, request, pk=None):
        """
        FULL DETAIL view for a Bucket Approval:
        - BucketApproval
        - SupportBucket
        - SBtypes
        - Department
        - Scheme
        - Recorded Beneficiaries
        - Training Support (Theme + Plan)
        """
        approval = (
            self.get_queryset()
            .select_related(
                "support_bucket",
                "support_bucket__bucket_type",
                "support_bucket__department",
                "support_bucket__scheme",
            )
            .get(pk=pk)
        )

        serializer = BucketApprovalDetailSerializer(
            approval,
            context={"request": request}
        )
        return Response(serializer.data)      