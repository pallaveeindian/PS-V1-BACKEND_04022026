# LDMS/api/serializers.py

from rest_framework import serializers
from django.apps import apps
from datetime import datetime
from LDMS import models as ldms_models
from core import models as core_models
from TMS import models as tms_models


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

# --------------------
# Department + Scheme
# --------------------

class DepartmentSerializer(SoftDeleteModelSerializer):
    class Meta(SoftDeleteModelSerializer.Meta):
        model = ldms_models.Department
        fields = "__all__"


class SchemeSerializer(SoftDeleteModelSerializer):
    class Meta(SoftDeleteModelSerializer.Meta):
        model = ldms_models.Scheme
        fields = "__all__"


class SchemeDetailSerializer(SoftDeleteModelSerializer):
    department = DepartmentSerializer(read_only=True)

    class Meta(SoftDeleteModelSerializer.Meta):
        model = ldms_models.Scheme
        fields = "__all__"
        depth = 1

# ----------------------------
# Support Capture Serializers
# ----------------------------

class recordedPLDSerializer(SoftDeleteModelSerializer):
    class Meta(SoftDeleteModelSerializer.Meta):
        model = ldms_models.recorded_benefs
        fields = "__all__"
        
class recordedPLDDetailSerializer(SoftDeleteModelSerializer):
    class Meta(SoftDeleteModelSerializer.Meta):
        model = ldms_models.recorded_benefs
        fields = "__all__"
        depth = 1

class SBtypeSerializer(SoftDeleteModelSerializer):
    class Meta(SoftDeleteModelSerializer.Meta):
        model = ldms_models.SBtypes
        fields = "__all__"

class SupportBucketSerializer(SoftDeleteModelSerializer):
    class Meta(SoftDeleteModelSerializer.Meta):
        model = ldms_models.SupportBucket
        fields = "__all__"

class TrainingSupportSerializer(SoftDeleteModelSerializer):
    class Meta(SoftDeleteModelSerializer.Meta):
        model = ldms_models.TrainingSupport
        fields = "__all__"        
        
class BucketApprovalSerializer(SoftDeleteModelSerializer):
    class Meta(SoftDeleteModelSerializer.Meta):
        model = ldms_models.Bucket_Approval
        fields = "__all__"        
        
        
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