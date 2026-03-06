# LDMS/api/serializers.py

from rest_framework import serializers
from django.apps import apps
from datetime import datetime
from LDMS import models as ldms_models
from core import models as core_models
from TMS import models as tms_models
from .validators import *
import re

class SoftDeleteModelSerializer(serializers.ModelSerializer):
    """
    Base serializer for all models using SoftDeleteMixin.
    Common audit fields are read-only.
    """

    class Meta:
        abstract = True
        read_only_fields = (
            "id",
            "TH_urid",
            "created_at",
            "updated_at",
            "deleted_at",
        )

# -------------------------------------------------------
# DEPARTMENT SERIALIZER (SECURE)
# -------------------------------------------------------

class DepartmentSerializer(SoftDeleteModelSerializer):

    class Meta(SoftDeleteModelSerializer.Meta):
        model = ldms_models.Department
        fields = "__all__"

    def validate_name(self, value):
        value = validate_no_xss(value)
        validate_safe_text(value)
        return value.strip()

    def validate(self, attrs):
        # Optional: prevent duplicate department names (case insensitive)
        name = attrs.get("name")
        if name:
            qs = ldms_models.Department.objects.filter(
                name__iexact=name,
                is_active=True
            )
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    {"name": "Department with this name already exists."}
                )
        return attrs


# -------------------------------------------------------
# SCHEME SERIALIZER (SECURE)
# -------------------------------------------------------

class SchemeSerializer(SoftDeleteModelSerializer):

    class Meta(SoftDeleteModelSerializer.Meta):
        model = ldms_models.Scheme
        fields = "__all__"

    # ---------- Field-Level XSS Protection ----------

    def validate_name(self, value):
        value = validate_no_xss(value)
        validate_safe_text(value)
        return value.strip()

    def validate_code(self, value):
        if value:
            value = validate_no_xss(value)
            validate_safe_text(value)
            return value.strip()
        return value

    def validate_assistance(self, value):
        return validate_no_xss(value)

    def validate_elligibility(self, value):
        return validate_no_xss(value)

    def validate_scope(self, value):
        return validate_no_xss(value)

    def validate_funding(self, value):
        return validate_no_xss(value)

    def validate_contact_point(self, value):
        return validate_no_xss(value)

    # ---------- Cross Validation ----------

    def validate(self, attrs):
        name = attrs.get("name")

        if name:
            qs = ldms_models.Scheme.objects.filter(
                name__iexact=name,
                department=attrs.get("department"),
                is_active=True
            )
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)

            if qs.exists():
                raise serializers.ValidationError(
                    {"name": "Scheme already exists for this department."}
                )

        return attrs


# -------------------------------------------------------
# SCHEME DETAIL SERIALIZER (READ ONLY SAFE)
# -------------------------------------------------------

class SchemeDetailSerializer(SoftDeleteModelSerializer):

    department = DepartmentSerializer(read_only=True)

    class Meta(SoftDeleteModelSerializer.Meta):
        model = ldms_models.Scheme
        fields = "__all__"
        depth = 1

# -------------------------------------------------------
# RECORDED BENEFICIARY (PLD)
# -------------------------------------------------------

class recordedPLDSerializer(SoftDeleteModelSerializer):

    class Meta(SoftDeleteModelSerializer.Meta):
        model = ldms_models.recorded_benefs
        fields = "__all__"

    # -------- XSS Protection --------

    def validate_member_name(self, value):
        return validate_no_xss(value)

    def validate_designation(self, value):
        return validate_no_xss(value)

    def validate_gender(self, value):
        return validate_no_xss(value)

    def validate_religion(self, value):
        return validate_no_xss(value)

    def validate_marital_status(self, value):
        return validate_no_xss(value)

    def validate_father_husband_name(self, value):
        return validate_no_xss(value)

    def validate_social_category(self, value):
        return validate_no_xss(value)

    def validate_education(self, value):
        return validate_no_xss(value)

    def validate_address(self, value):
        return validate_no_xss(value)

    def validate_lokos_member_code(self, value):
        return validate_no_xss(value)

    def validate_lokos_shg_code(self, value):
        return validate_no_xss(value)

    # -------- Mobile Validation --------

    def validate_mobile(self, value):
        validate_mobile(value)
        return value

    # -------- Age Validation --------

    def validate_age(self, value):
        if value is not None:
            validate_positive_integer(value)
            if value > 120:
                raise serializers.ValidationError("Invalid age.")
        return value
    
    def validate(self, attrs):
        lokos_member_code = attrs.get("lokos_member_code")
        support_bucket = attrs.get("support_bucket")

        if lokos_member_code and support_bucket:
            qs = ldms_models.recorded_benefs.objects.filter(
                lokos_member_code=lokos_member_code,
                support_bucket=support_bucket,
                is_active=True
            )

            # Exclude current instance during update
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)

            if qs.exists():
                raise serializers.ValidationError(
                    {
                        "support_bucket":
                        "This beneficiary has already been assigned this support bucket."
                    }
                )

        return attrs    


# Read-only detail version (safe by default)
class recordedPLDDetailSerializer(SoftDeleteModelSerializer):
    class Meta(SoftDeleteModelSerializer.Meta):
        model = ldms_models.recorded_benefs
        fields = "__all__"
        depth = 1

class SBtypeSerializer(SoftDeleteModelSerializer):

    class Meta(SoftDeleteModelSerializer.Meta):
        model = ldms_models.SBtypes
        fields = "__all__"

    def validate_bucket_type(self, value):
        return validate_no_xss(value.strip())

class SupportBucketSerializer(SoftDeleteModelSerializer):

    class Meta(SoftDeleteModelSerializer.Meta):
        model = ldms_models.SupportBucket
        fields = "__all__"

    def validate_benefit_name(self, value):
        return validate_no_xss(value)

    def validate_benefit_description(self, value):
        return validate_no_xss(value)

    def validate_benefit_amount(self, value):
        if value is not None:
            validate_decimal_amount(value)
        return value

class TrainingSupportSerializer(SoftDeleteModelSerializer):

    class Meta(SoftDeleteModelSerializer.Meta):
        model = ldms_models.TrainingSupport
        fields = "__all__"

    def validate(self, attrs):
        # Prevent duplicate mapping
        qs = ldms_models.TrainingSupport.objects.filter(
            training_theme=attrs.get("training_theme"),
            training_plan=attrs.get("training_plan"),
            support_bucket=attrs.get("support_bucket"),
            is_active=True
        )

        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)

        if qs.exists():
            raise serializers.ValidationError(
                "This training support mapping already exists."
            )

        return attrs      
        
class BucketApprovalSerializer(SoftDeleteModelSerializer):

    class Meta(SoftDeleteModelSerializer.Meta):
        model = ldms_models.Bucket_Approval
        fields = "__all__"

    def validate_rejection_reason(self, value):
        return validate_no_xss(value)

    def validate(self, attrs):
        status = attrs.get("approval_status")
        rejection_reason = attrs.get("rejection_reason")
        approval_date = attrs.get("approval_date")

        # Enforce rejection reason
        validate_bucket_approval(status, rejection_reason)

        # Approval date cannot be future
        if approval_date:
            if approval_date > timezone.now().date():
                raise serializers.ValidationError(
                    {"approval_date": "Approval date cannot be in the future."}
                )

        # Prevent approving without approver
        if status == "APPROVED" and not attrs.get("approved_by"):
            raise serializers.ValidationError(
                {"approved_by": "Approved by is required when status is APPROVED."}
            )

        return attrs
        
# -------------------------------------------
# Support Approval DETAIL Serializer Section
# -------------------------------------------

# -----------------------------
# TMS nested serializers
# -----------------------------

class TrainingThemeDetailSerializer(SoftDeleteModelSerializer):
    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.TrainingTheme
        fields = "__all__"


class TrainingPlanDetailSerializer(SoftDeleteModelSerializer):
    theme = TrainingThemeDetailSerializer(read_only=True)

    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.TrainingPlan
        fields = "__all__"


class TrainingSupportDetailSerializer(SoftDeleteModelSerializer):
    training_theme = TrainingThemeDetailSerializer(read_only=True)
    training_plan = TrainingPlanDetailSerializer(read_only=True)

    class Meta(SoftDeleteModelSerializer.Meta):
        model = ldms_models.TrainingSupport
        fields = "__all__"


# -----------------------------
# LDMS nested serializers
# -----------------------------

class SBtypeDetailSerializer(SoftDeleteModelSerializer):
    class Meta(SoftDeleteModelSerializer.Meta):
        model = ldms_models.SBtypes
        fields = "__all__"


class DepartmentDetailSerializer(SoftDeleteModelSerializer):
    class Meta(SoftDeleteModelSerializer.Meta):
        model = ldms_models.Department
        fields = "__all__"


class SchemeDetailSerializer(SoftDeleteModelSerializer):
    department = DepartmentDetailSerializer(read_only=True)

    class Meta(SoftDeleteModelSerializer.Meta):
        model = ldms_models.Scheme
        fields = "__all__"


class RecordedBeneficiaryDetailSerializer(SoftDeleteModelSerializer):
    class Meta(SoftDeleteModelSerializer.Meta):
        model = ldms_models.recorded_benefs
        fields = "__all__"


class SupportBucketDetailSerializer(SoftDeleteModelSerializer):
    bucket_type = SBtypeDetailSerializer(read_only=True)
    department = DepartmentDetailSerializer(read_only=True)
    scheme = SchemeDetailSerializer(read_only=True)
    recorded_benefs = serializers.SerializerMethodField()
    training_support = serializers.SerializerMethodField()

    class Meta(SoftDeleteModelSerializer.Meta):
        model = ldms_models.SupportBucket
        fields = "__all__"

    def get_recorded_benefs(self, obj):
        qs = ldms_models.recorded_benefs.objects.filter(
            support_bucket=obj,
            is_active=True
        )
        return RecordedBeneficiaryDetailSerializer(qs, many=True).data

    def get_training_support(self, obj):
        ts = ldms_models.TrainingSupport.objects.filter(
            support_bucket=obj,
            is_active=True
        ).select_related(
            "training_theme",
            "training_plan",
            "training_plan__theme"
        ).first()
        return (
            TrainingSupportDetailSerializer(ts).data
            if ts else None
        )


class BucketApprovalDetailSerializer(SoftDeleteModelSerializer):
    support_bucket = SupportBucketDetailSerializer(read_only=True)

    class Meta(SoftDeleteModelSerializer.Meta):
        model = ldms_models.Bucket_Approval
        fields = "__all__"
        
# -------------------------------------------------------
# DLCC MEETING LIST
# -------------------------------------------------------

class DLCCMeetListSerializer(SoftDeleteModelSerializer):

    class Meta(SoftDeleteModelSerializer.Meta):
        model = ldms_models.DLCC_Meeting_List
        fields = "__all__"

    # 🔒 Field-level validation
    def validate_notif_date(self, value):
        return validate_no_xss(value)

    def validate_meeting_month(self, value):
        # Validate format YYYY-MM
        if not re.match(r"^\d{4}-(0[1-9]|1[0-2])$", value):
            raise serializers.ValidationError(
                "meeting_month must be in YYYY-MM format."
            )
        return value

    def validate_no_of_meetings(self, value):
        validate_positive_integer(value)
        return value


# -------------------------------------------------------
# DLCC MEETING
# -------------------------------------------------------

class DLCCMeetSerializer(SoftDeleteModelSerializer):

    mom = serializers.FileField(
        required=False,
        validators=[validate_pdf_file]
    )

    class Meta(SoftDeleteModelSerializer.Meta):
        model = ldms_models.DLCC_Meeting
        fields = "__all__"

    def validate_meeting_date(self, value):
        return validate_not_future_date(value)

    def validate(self, attrs):
        if attrs.get("mom"):
            attrs["is_uploaded"] = True
        return attrs


# -------------------------------------------------------
# BLCC MEETING LIST
# -------------------------------------------------------

class BLCCMeetListSerializer(SoftDeleteModelSerializer):

    class Meta(SoftDeleteModelSerializer.Meta):
        model = ldms_models.BLCC_Meeting_List
        fields = "__all__"

    def validate_notif_date(self, value):
        return validate_no_xss(value)

    def validate_meeting_month(self, value):
        if not re.match(r"^\d{4}-(0[1-9]|1[0-2])$", value):
            raise serializers.ValidationError(
                "meeting_month must be in YYYY-MM format."
            )
        return value

    def validate_no_of_meetings(self, value):
        validate_positive_integer(value)
        return value

    def validate_blocks_notif_issued(self, value):
        if value is not None:
            validate_positive_integer(value)
        return value


# -------------------------------------------------------
# BLCC MEETING
# -------------------------------------------------------

class BLCCMeetSerializer(SoftDeleteModelSerializer):

    mom = serializers.FileField(
        required=False,
        validators=[validate_pdf_file]
    )

    class Meta(SoftDeleteModelSerializer.Meta):
        model = ldms_models.BLCC_Meeting
        fields = "__all__"

    def validate_meeting_date(self, value):
        return validate_not_future_date(value)

    def validate(self, attrs):
        if attrs.get("mom"):
            attrs["is_uploaded"] = True
        return attrs