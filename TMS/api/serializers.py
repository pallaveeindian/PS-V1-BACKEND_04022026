# TMS/api/serializers.py
import os
import uuid
import re
from rest_framework import serializers
from django.apps import apps
from datetime import datetime
from TMS import models as tms_models
from core import models as core_models
from PIL import Image
from PyPDF2 import PdfReader
from django.core.exceptions import ValidationError
from django.utils.text import get_valid_filename
from django.db.models import Sum, Count

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


# ----------------------------
# TrainingTheme + TrainingPlan
# ----------------------------

class TrainingThemeSerializer(SoftDeleteModelSerializer):
    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.TrainingTheme
        fields = "__all__"


class TrainingPlanSerializer(SoftDeleteModelSerializer):
    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.TrainingPlan
        fields = "__all__"


class TrainingPlanDetailSerializer(SoftDeleteModelSerializer):
    theme = TrainingThemeSerializer(read_only=True)
    requests = serializers.PrimaryKeyRelatedField(
        many=True,
        read_only=True,
    )

    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.TrainingPlan
        fields = "__all__"
        depth = 1


class TrainingThemeDetailSerializer(SoftDeleteModelSerializer):
    training_plans = TrainingPlanSerializer(
        many=True,
        read_only=True,
        source="THEME",  # related_name on TrainingPlan.theme
    )

    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.TrainingTheme
        fields = "__all__"
        depth = 1


# ----------------------------
# MasterTrainer & Certificates
# ----------------------------

class MasterTrainerSerializer(SoftDeleteModelSerializer):
    block_name_en = serializers.SerializerMethodField()
    district_name_en = serializers.SerializerMethodField()
    theme_name = serializers.SerializerMethodField()

    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.MasterTrainer
        fields = "__all__"  

    def get_block_name_en(self, obj):
        try:
            return obj.empanel_block.block_name_en if obj.empanel_block else None
        except:
            return None

    def get_district_name_en(self, obj):
        try:
            return obj.empanel_district.district_name_en if obj.empanel_district else None
        except:
            return None

    def get_theme_name(self, obj):
        try:
            return obj.theme.theme_name if obj.theme else None
        except:
            return None


class MasterTrainerCertificateSerializer(SoftDeleteModelSerializer):
    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.MasterTrainerCertificate
        fields = "__all__"


class MasterTrainerDetailSerializer(SoftDeleteModelSerializer):
    certificates = MasterTrainerCertificateSerializer(many=True, read_only=True)

    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.MasterTrainer
        fields = "__all__"
        depth = 1


# ----------------------------
# Training Partner + related
# ----------------------------

class TrainingPartnerSerializer(SoftDeleteModelSerializer):
    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.TrainingPartner
        fields = "__all__"


class TrainingPartnerBankSerializer(SoftDeleteModelSerializer):
    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.TrainingPartnerBank
        fields = "__all__"


class TrainingPartnerCPSerializer(SoftDeleteModelSerializer):
    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.TrainingPartnerCP
        fields = "__all__"

    # -----------------------------
    # Field level validations
    # -----------------------------

    def validate_name(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("Name is required")

        value = value.strip()

        if len(value) > 50:
            raise serializers.ValidationError(
                "Name must be max 50 characters"
            )

        if not re.match(r"^[A-Za-z\s]+$", value):
            raise serializers.ValidationError(
                "Only alphabets (A–Z, a–z) and spaces are allowed"
            )

        return value

    def validate_mobile_number(self, value):
        if not value:
            raise serializers.ValidationError(
                "Mobile number is required"
            )

        if not re.match(r"^\d{10}$", value):
            raise serializers.ValidationError(
                "Mobile number must be exactly 10 digits"
            )

        return value

    def validate_email(self, value):
        if not value:
            raise serializers.ValidationError("Email is required")

        # DRF EmailField already validates format,
        # but keeping explicit message for consistency
        email_regex = r"^[\w\.-]+@[\w\.-]+\.\w+$"

        if not re.match(email_regex, value):
            raise serializers.ValidationError(
                "Invalid email format (example@domain.com)"
            )

        return value

    def validate_address(self, value):
        if value and len(value) > 150:
            raise serializers.ValidationError(
                "Address must be max 150 characters"
            )
        return value

    # -----------------------------
    # Object level validation
    # -----------------------------

    def validate(self, attrs):

        # ---- master_user validation ----
        master_user = attrs.get(
            "master_user",
            getattr(self.instance, "master_user", None)
        )

        if not master_user:
            raise serializers.ValidationError({
                "master_user": "User ID is mandatory for Contact Person"
            })

        # ---- duplicate mobile check (per partner) ----
        mobile = attrs.get("mobile_number")
        partner = attrs.get("partner")

        if mobile and partner:
            qs = tms_models.TrainingPartnerCP.objects.filter(
                mobile_number=mobile,
                partner=partner,
            )

            # exclude self during update
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)

            if qs.exists():
                raise serializers.ValidationError({
                    "mobile_number": "Contact person with this mobile already exists"
                })

        return attrs


class TrainingPartnerCentreSerializer(SoftDeleteModelSerializer):
    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.TrainingPartnerCentre
        fields = "__all__"


class TrainingPartnerCentreRoomsSerializer(SoftDeleteModelSerializer):
    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.TrainingPartnerCentreRooms
        fields = "__all__"


class TPCPToCentreSerializer(SoftDeleteModelSerializer):

    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.TPCPToCentre
        fields = "__all__"

    def validate(self, attrs):
        request = self.context.get("request")
        if not request:
            return attrs

        auth_user = request.user
        master_user = core_models.MasterUser.objects.filter(
            username=auth_user.username
        ).first()

        if not master_user:
            raise serializers.ValidationError("Invalid user.")

        # Resolve instance for partial updates
        instance = getattr(self, "instance", None)
        cp = attrs.get("contact_person", instance.contact_person if instance else None)
        centre = attrs.get("allocated_centre", instance.allocated_centre if instance else None)

        if not cp or not centre:
            raise serializers.ValidationError("Invalid assignment data.")

        # 1. Structural Security Check: 
        # Ensure CP and Centre belong to SAME partner (Applies to EVERYONE, even Admins)
        if cp.partner_id != centre.partner_id:
            raise serializers.ValidationError(
                "Contact person and centre must belong to the same partner."
            )

        # 2. Determine User Role
        partner = tms_models.TrainingPartner.objects.filter(master_user=master_user, is_active=True).first()
        dtp = tms_models.DistrictTP.objects.filter(master_user=master_user, is_active=True).first()
        is_tpcp = tms_models.TrainingPartnerCP.objects.filter(master_user=master_user, is_active=True).exists()
        
        is_admin = not (partner or dtp or is_tpcp)

        # 3. Authorization Check (Skip for Admins)
        if not is_admin:
            authorized_partner_id = partner.id if partner else (dtp.partner_id if dtp else None)
            
            if not authorized_partner_id or cp.partner_id != authorized_partner_id:
                raise serializers.ValidationError(
                    "You do not have permission to manage assignments for this Training Partner."
                )

        # 4. Prevent Duplicate Mapping
        duplicate_qs = tms_models.TPCPToCentre.objects.filter(
            contact_person=cp,
            allocated_centre=centre,
            is_active=True
        )

        if instance:
            duplicate_qs = duplicate_qs.exclude(id=instance.id)

        if duplicate_qs.exists():
            raise serializers.ValidationError(
                "This contact person is already assigned to this centre."
            )

        return attrs
        
        
class TPCPToCentreDetailSerializer(SoftDeleteModelSerializer):
    """
    DETAIL serializer for centre including nested rooms.
    """
    allocated_centre = TrainingPartnerCentreSerializer(read_only=True)
    contact_person = TrainingPartnerCPSerializer(read_only=True)

    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.TPCPToCentre
        fields = "__all__"
        depth = 1

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".pdf"}
ALLOWED_MIME_TYPES = {
    "image/jpeg",
    "application/pdf",
}

DANGEROUS_FILENAMES = {
    ".htaccess",
    "web.config",
    "settings.py",
    "manage.py",
}

class TrainingPartnerSubmissionSerializer(SoftDeleteModelSerializer):
    class Meta:
        model = tms_models.TrainingPartnerSubmission
        fields = "__all__"

    def validate_file(self, file):

        if not file:
            return file

        original_name = file.name

        # ----------------------------
        # For empty or hidden filenames
        # ----------------------------
        if not original_name or original_name.startswith("."):
            raise serializers.ValidationError("Invalid file name.")

        # ----------------------------
        # To Block dangerous known filenames
        # ----------------------------
        if original_name.lower() in DANGEROUS_FILENAMES:
            raise serializers.ValidationError("Forbidden file name.")

        # ----------------------------
        # To Block double extensions
        # ----------------------------
        parts = original_name.split(".")
        if len(parts) > 2:
            raise serializers.ValidationError("Double extensions are not allowed.")

        # ----------------------------
        # Extension whitelist
        # ----------------------------
        ext = os.path.splitext(original_name)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise serializers.ValidationError("Unsupported file type.")

        # ----------------------------
        # Size limit (10 MB)
        # ----------------------------
        if file.size > 10 * 1024 * 1024:
            raise serializers.ValidationError("File must be <= 10 MB.")

        # ----------------------------
        # MIME type validation
        # ----------------------------
        if file.content_type not in ALLOWED_MIME_TYPES:
            raise serializers.ValidationError("Invalid content type.")

        # ----------------------------
        # Content validation
        # ----------------------------
        file.seek(0)

        if ext in (".jpg", ".jpeg"):
            try:
                Image.open(file).verify()
            except Exception:
                raise serializers.ValidationError("Invalid image file.")

        elif ext == ".pdf":
            try:
                PdfReader(file)
            except Exception:
                raise serializers.ValidationError("Invalid PDF file.")

        file.seek(0)
        return file

    def create(self, validated_data):
        file = validated_data.get("file")

        if file:
            ext = os.path.splitext(file.name)[1].lower()
            file.name = f"{uuid.uuid4().hex}{ext}"

        return super().create(validated_data)

class TrainingPartnerCentreDetailSerializer(SoftDeleteModelSerializer):
    """
    DETAIL serializer for centre including nested rooms.
    """
    rooms = TrainingPartnerCentreRoomsSerializer(many=True, read_only=True)
    submissions = serializers.SerializerMethodField()

    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.TrainingPartnerCentre
        fields = "__all__"
        depth = 1

    def get_submissions(self, obj):
        qs = obj.submissions.filter(is_active=True)
        return TrainingPartnerSubmissionSerializer(
            qs,
            many=True,
            context=self.context,
        ).data    


class TrainingPartnerDetailSerializer(SoftDeleteModelSerializer):
    banks = TrainingPartnerBankSerializer(many=True, read_only=True)
    contact_person = TrainingPartnerCPSerializer(many=True, read_only=True)
    centres = TrainingPartnerCentreSerializer(many=True, read_only=True)
    submissions = TrainingPartnerSubmissionSerializer(many=True, read_only=True)
    targets = serializers.PrimaryKeyRelatedField(many=True, read_only=True)

    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.TrainingPartner
        fields = "__all__"
        depth = 1


# ----------------------------
# TrainingPartnerTargets
# ----------------------------

class MasterDistrictTargetSerializer(SoftDeleteModelSerializer):
    class Meta(SoftDeleteModelSerializer.Meta):
        model = core_models.MasterDistrict
        fields = ['district_id', 'district_name_en', 'district_short_name_en']

class TrainingPartnerTargetsSerializer(SoftDeleteModelSerializer):
    partner_full = TrainingPartnerSerializer(source='partner', read_only=True)
    training_plan_full = TrainingPlanSerializer(source='training_plan', read_only=True)
    district_full = MasterDistrictTargetSerializer(source='district', read_only=True)

    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.TrainingPartnerTargets
        fields = "__all__"

class TrainingPartnerAchievementDetailedSerializer(serializers.ModelSerializer):
    class Meta:
        model = tms_models.TrainingPartnerAchievement
        fields = "__all__"
        depth = 1  

class TrainingPartnerTargetsDetailedSerializer(SoftDeleteModelSerializer):
    achievements = serializers.SerializerMethodField()

    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.TrainingPartnerTargets
        fields = "__all__"
        depth = 1  

    def get_achievements(self, obj):
        achs = obj.achievements.all()
        return TrainingPartnerAchievementDetailedSerializer(achs, many=True).data

# ----------------------------
# TRPUserScope
# ----------------------------

class TRPUserScopeSerializer(SoftDeleteModelSerializer):
    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.TRPUserScope
        fields = "__all__"


# ----------------------------
# TrainingRequest + TRBeneficiary + TRTrainer
# ----------------------------

class TrainingRequestSerializer(SoftDeleteModelSerializer):
    district_name_en = serializers.SerializerMethodField()
    block_name_en = serializers.SerializerMethodField()
    participant_count = serializers.SerializerMethodField()    

    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.TrainingRequest
        fields = "__all__" 

    def get_district_name_en(self, obj):
        try:
            return obj.district.district_name_en if obj.district else None
        except:
            return None

    def get_block_name_en(self, obj):
        try:
            return obj.block.block_name_en if obj.block else None
        except:
            return None

    def get_participant_count(self, obj):
        try:
            if obj.training_type == 'BENEFICIARY':
                return obj.beneficiary_registrations.filter(is_active=True).count()
            elif obj.training_type == 'TRAINER':
                return obj.trainer_registrations.filter(is_active=True).count()
        except:
            pass
        return 0            


class TRBeneficiarySerializer(SoftDeleteModelSerializer):
    district_name_en = serializers.SerializerMethodField()
    block_name_en = serializers.SerializerMethodField()

    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.TRBeneficiary
        fields = "__all__"

    def get_district_name_en(self, obj):
        try:
            return obj.district.district_name_en if obj.district else None
        except:
            return None

    def get_block_name_en(self, obj):
        try:
            return obj.block.block_name_en if obj.block else None
        except:
            return None        


class TRBeneficiaryDetailSerializer(SoftDeleteModelSerializer):
    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.TRBeneficiary
        fields = "__all__"
        depth = 1


class TRTrainerSerializer(SoftDeleteModelSerializer):
    district_name_en = serializers.SerializerMethodField()
    block_name_en = serializers.SerializerMethodField()

    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.TRTrainer
        fields = "__all__"

    def get_district_name_en(self, obj):
        try:
            return obj.district.district_name_en if obj.district else None
        except:
            return None

    def get_block_name_en(self, obj):
        try:
            return obj.block.block_name_en if obj.block else None
        except:
            return None             


class TRTrainerDetailSerializer(SoftDeleteModelSerializer):
    """
    DETAIL serializer for TRTrainer – includes nested trainer + training.
    """
    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.TRTrainer
        fields = "__all__"
        depth = 1


class TrainingRequestDetailSerializer(SoftDeleteModelSerializer):
    beneficiary_registrations = serializers.SerializerMethodField()
    trainer_registrations = serializers.SerializerMethodField()
    batches = serializers.SerializerMethodField()

    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.TrainingRequest
        fields = "__all__"
        depth = 1

    def get_beneficiary_registrations(self, obj):
        qs = obj.beneficiary_registrations.filter(is_active=True)
        return TRBeneficiarySerializer(qs, many=True, context=self.context).data

    def get_trainer_registrations(self, obj):
        qs = obj.trainer_registrations.filter(is_active=True)
        return TRTrainerSerializer(qs, many=True, context=self.context).data

    def get_batches(self, obj):
        qs = obj.batches.filter(is_active=True)
        return [b.id for b in qs]


# ----------------------------
# Batch + participants/trainers
# ----------------------------

class BatchSerializer(SoftDeleteModelSerializer):
    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.Batch
        fields = "__all__"
        read_only_fields = ["code"]

class BatchScheduleSerializer(SoftDeleteModelSerializer):
    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.BatchSchedule
        fields = "__all__"

class BatchMasterTrainerSerializer(SoftDeleteModelSerializer):
    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.BatchMasterTrainer
        fields = "__all__"


class BatchBeneficiarySerializer(SoftDeleteModelSerializer):
    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.BatchBeneficiary
        fields = "__all__"


class BatchTrainerSerializer(SoftDeleteModelSerializer):
    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.BatchTrainer
        fields = "__all__"


class BatchEkycVerificationSerializer(SoftDeleteModelSerializer):
    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.BatchEkycVerification
        fields = "__all__"


class BatchAttendanceSerializer(SoftDeleteModelSerializer):
    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.BatchAttendance
        fields = "__all__"


class ParticipantAttendanceSerializer(SoftDeleteModelSerializer):
    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.ParticipantAttendance
        fields = "__all__"


class BatchAttendanceDetailSerializer(SoftDeleteModelSerializer):
    participant_records = ParticipantAttendanceSerializer(many=True, read_only=True)

    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.BatchAttendance
        fields = "__all__"
        depth = 1

class TPBatchCostBreakupSerializer(SoftDeleteModelSerializer):
    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.TPBatchCostBreakup
        fields = "__all__"

class BatchCostSerializer(SoftDeleteModelSerializer):
    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.BatchCost
        fields = "__all__"

class BeneficiaryAttendanceSummarySerializer(SoftDeleteModelSerializer):
    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.BeneficiaryAttendanceSummary
        fields = "__all__"

class BatchClosureRequestSerializer(SoftDeleteModelSerializer):
    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.BatchClosureRequest
        fields = "__all__"

class BatchMediaSerializer(SoftDeleteModelSerializer):
    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.BatchMedia
        fields = "__all__"

class BatchReportSerializer(SoftDeleteModelSerializer):
    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.BatchReport
        fields = "__all__"

class BatchParticipantCertificateSerializer(SoftDeleteModelSerializer):
    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.BatchParticipantCertificate
        fields = "__all__"

# --- UPDATED MASTER DETAIL SERIALIZER ---

class BatchDetailSerializer(SoftDeleteModelSerializer):
    # --- SURGICAL FIX: Removed `request = TrainingRequestDetailSerializer(read_only=True)`
    # Since `Batch` no longer holds a direct `request` foreign key.
    
    centre = TrainingPartnerCentreSerializer(read_only=True)
    beneficiary = TRBeneficiarySerializer(many=True, read_only=True)
    trainer = TRTrainerSerializer(many=True, read_only=True)
    master_trainers = MasterTrainerSerializer(many=True, read_only=True)
    # ---------------------------------------------------------------------------

    # Participants
    master_trainer_participations = BatchMasterTrainerSerializer(many=True, read_only=True)
    trainer_participations = BatchTrainerSerializer(many=True, read_only=True)
    beneficiary_participations = BatchBeneficiarySerializer(many=True, read_only=True)
    
    # EKYC, Schedules, Raw Attendance
    ekyc_verifications = BatchEkycVerificationSerializer(many=True, read_only=True)
    attendances = BatchAttendanceDetailSerializer(many=True, read_only=True)
    schedules = BatchScheduleSerializer(many=True, read_only=True) 

    # Native Summaries & Costing
    beneficiary_summaries = BeneficiaryAttendanceSummarySerializer(many=True, read_only=True)
    batch_costing = BatchCostSerializer(read_only=True) # OneToOne
    participant_costs = TPBatchCostBreakupSerializer(many=True, read_only=True)

    # Media, Reports & Closure
    batch_closing = BatchClosureRequestSerializer(read_only=True) # OneToOne
    batch_pictures = BatchMediaSerializer(many=True, read_only=True)
    batch_report = BatchReportSerializer(many=True, read_only=True)
    batch_certificates = BatchParticipantCertificateSerializer(many=True, read_only=True)

    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.Batch
        fields = "__all__"
        
# ----------------------------
# Batch Closure & Certificates
# ----------------------------

class TPBatchCostBreakupSerializer(SoftDeleteModelSerializer):
    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.TPBatchCostBreakup
        fields = "__all__"


class BatchCostSerializer(SoftDeleteModelSerializer):
    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.BatchCost
        fields = "__all__"

class BatchCostDetailSerializer(SoftDeleteModelSerializer):
    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.BatchCost
        fields = "__all__"
        depth = 1

class BatchMediaSerializer(SoftDeleteModelSerializer):
    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.BatchMedia
        fields = "__all__"


class BatchClosureRequestSerializer(SoftDeleteModelSerializer):
    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.BatchClosureRequest
        fields = "__all__"


class BatchClosureRequestDetailSerializer(SoftDeleteModelSerializer):
    batch = BatchSerializer(read_only=True)
    batch_costing = BatchCostSerializer(read_only=True)

    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.BatchClosureRequest
        fields = "__all__"
        depth = 1

class BatchParticipantCertificateSerializer(SoftDeleteModelSerializer):
    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.BatchParticipantCertificate
        fields = "__all__"


class BatchParticipantCertificateDetailSerializer(SoftDeleteModelSerializer):
    batch = BatchSerializer(read_only=True)

    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.BatchParticipantCertificate
        fields = "__all__"
        depth = 1

# Batch List Serializer (for certificates)
class BatchDistrictSerializer(SoftDeleteModelSerializer):
    class Meta(SoftDeleteModelSerializer.Meta):
        model = core_models.MasterDistrict
        fields = ['district_id', 'district_name_en', 'district_short_name_en']

class BatchBlockSerializer(SoftDeleteModelSerializer):
    class Meta(SoftDeleteModelSerializer.Meta):
        model = core_models.MasterBlock
        fields = ['block_id', 'block_name_en', 'block_name_local', 'is_aspirational']

class BatchCentreSerializer(SoftDeleteModelSerializer):
    partner = TrainingPartnerSerializer(read_only=True)
    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.TrainingPartnerCentre
        fields = "__all__"
        
class BatchTRSerializer(SoftDeleteModelSerializer):
    district = BatchDistrictSerializer(read_only=True)
    block = BatchBlockSerializer(read_only=True)
    theme = TrainingThemeSerializer(read_only=True)
    
    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.TrainingRequest
        fields = "__all__"
       
class BatchListSerializer(serializers.ModelSerializer):
    district = BatchDistrictSerializer(read_only=True)
    block = BatchBlockSerializer(read_only=True)
    centre = BatchCentreSerializer()
    pax_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = tms_models.Batch
        fields = [
            'id',
            'code',
            'batch_type',
            'status',
            'start_date',
            'end_date',
            'time_of_training',
            'centre',
            'level',
            'district',
            'participant_type',
            'block',
            'pax_count',
        ]




# ----------------------------
# Reports
# ----------------------------

class MasterDistrictReportSerializer(SoftDeleteModelSerializer):
    class Meta(SoftDeleteModelSerializer.Meta):
        model = core_models.MasterDistrict
        fields = ['district_id', 'district_name_en', 'district_short_name_en']


class MasterBlockReportSerializer(SoftDeleteModelSerializer):
    class Meta(SoftDeleteModelSerializer.Meta):
        model = core_models.MasterBlock
        fields = ['block_id', 'block_name_en', 'block_name_local', 'is_aspirational']


class MasterPanchayatReportSerializer(SoftDeleteModelSerializer):
    class Meta(SoftDeleteModelSerializer.Meta):
        model = core_models.MasterPanchayat
        fields = ['panchayat_id', 'panchayat_name_en', 'panchayat_name_local']


class MasterVillageReportSerializer(SoftDeleteModelSerializer):
    class Meta(SoftDeleteModelSerializer.Meta):
        model = core_models.MasterVillage
        fields = ['village_id', 'village_name_english', 'village_name_local']

# ----------------------------
# TrainingTheme & TrainingPlan (EXACT fields)
# ----------------------------

class TrainingThemeReportSerializer(SoftDeleteModelSerializer):
    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.TrainingTheme
        fields = ['id', 'theme_name']


class TrainingPlanReportSerializer(SoftDeleteModelSerializer):
    theme = TrainingThemeReportSerializer(read_only=True)

    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.TrainingPlan
        fields = [
            'id',
            'training_name',
            'theme',
            'type_of_training',
            'level_of_training',
            'no_of_days',
            'approval_status',
        ]
# ----------------------------
# TrainingPartner (EXACT fields)
# ----------------------------

class TrainingPartnerReportSerializer(SoftDeleteModelSerializer):
    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.TrainingPartner
        fields = [
            'id',
            'name',
            'email',
            'address',
            'tpm_registration_no',
            'mou_form',
        ]

# ----------------------------
# TrainingPartnerCentre + Nested (EXACT model fields)
# ----------------------------

class TrainingPartnerCentreReportSerializer(SoftDeleteModelSerializer):
    district = MasterDistrictReportSerializer(read_only=True)
    block = MasterBlockReportSerializer(read_only=True)
    panchayat = MasterPanchayatReportSerializer(read_only=True)
    village = MasterVillageReportSerializer(read_only=True)

    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.TrainingPartnerCentre
        fields = [
            'id',
            'serial_number',
            'district',
            'block',
            'panchayat',
            'village',
            'venue_name',
            'venue_address',
            'training_hall_count',
            'training_hall_capacity',
            'security_arrangements',
            'toilets_bathrooms',
            'power_water_facility',
            'medical_kit',
            'centre_type',
            'open_space',
            'field_visit_facility',
            'transport_facility',
            'dining_facility',
            'other_details',
        ]

class TrainingPartnerCentreRoomsReportSerializer(SoftDeleteModelSerializer):
    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.TrainingPartnerCentreRooms
        fields = ['id', 'room_name', 'room_capacity']


class TrainingPartnerSubmissionReportSerializer(SoftDeleteModelSerializer):
    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.TrainingPartnerSubmission
        fields = ['category', 'file', 'notes']

# ----------------------------
# MasterTrainer (EXACT fields)
# ----------------------------

class MasterTrainerReportSerializer(SoftDeleteModelSerializer):
    empanel_district = MasterDistrictReportSerializer(read_only=True)
    empanel_block = MasterBlockReportSerializer(read_only=True)

    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.MasterTrainer
        fields = [
            'id',
            'full_name',
            'date_of_birth',
            'mobile_no',
            'aadhaar_no',
            'empanel_district',
            'empanel_block',
            'social_category',
            'gender',
            'education',
            'marital_status',
            'parent_or_spouse_name',
            'skills',
            'success_rate',
            'designation',
        ]

# ----------------------------
# TRBeneficiary (EXACT fields from model)
# ----------------------------

class TRBeneficiaryReportSerializer(SoftDeleteModelSerializer):
    district = MasterDistrictReportSerializer(read_only=True)
    block = MasterBlockReportSerializer(read_only=True)
    panchayat = MasterPanchayatReportSerializer(read_only=True)
    village = MasterVillageReportSerializer(read_only=True)

    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.TRBeneficiary
        fields = [
            'id',
            'lokos_shg_code',
            'lokos_member_code',
            'member_name',
            'age',
            'gender',
            'designation',
            'pld_status',
            'social_category',
            'religion',
            'mobile',
            'email',
            'education',
            'address',
            'district',
            'block',
            'panchayat',
            'village',
            'remarks',
            'attended',
            'is_replaced',
            'registered_on',
        ]

# ----------------------------
# Batch Nested Serializers (CORRECT related_names from models)
# ----------------------------

class BatchReportSerializer(SoftDeleteModelSerializer):
    centre = TrainingPartnerCentreReportSerializer(read_only=True)

    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.Batch
        fields = [
            'id',
            'centre',
            'batch_type',
            'code',
            'status',
            'start_date',
            'end_date',
            'time_of_training',
        ]


class BatchScheduleReportSerializer(SoftDeleteModelSerializer):
    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.BatchSchedule
        fields = ['id', 'schedule_date', 'start_time', 'remarks', 'batch']


class BatchMasterTrainerReportSerializer(SoftDeleteModelSerializer):
    master_trainer = MasterTrainerReportSerializer(read_only=True)

    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.BatchMasterTrainer
        fields = ['id', 'master_trainer', 'participated', 'status', 'remarks', 'batch']


class BatchBeneficiaryReportSerializer(SoftDeleteModelSerializer):
    beneficiary = TRBeneficiaryReportSerializer(read_only=True)

    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.BatchBeneficiary
        fields = ['id', 'beneficiary', 'registered_on', 'attended', 'is_replaced', 'batch']


class BatchTrainerReportSerializer(SoftDeleteModelSerializer):
    trainer = MasterTrainerReportSerializer(read_only=True)

    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.BatchTrainer
        fields = ['id', 'trainer', 'registered_on', 'attended', 'is_replaced', 'batch']

class BatchEkycVerificationReportSerializer(SoftDeleteModelSerializer):
    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.BatchEkycVerification
        fields = [
            'id',
            'participant_id',
            'participant_role',
            'ekyc_status',
            'ekyc_document',
            'verified_on',
            'remarks',
            'batch',
        ]


class BatchAttendanceReportSerializer(SoftDeleteModelSerializer):
    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.BatchAttendance
        fields = ['id', 'date', 'csv_upload', 'batch']


class ParticipantAttendanceReportSerializer(SoftDeleteModelSerializer):
    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.ParticipantAttendance
        fields = [
            'id',
            'participant_id',
            'participant_name',
            'participant_role',
            'present',
        ]


class TPBatchCostBreakupReportSerializer(SoftDeleteModelSerializer):
    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.TPBatchCostBreakup
        fields = [
            'id',
            'batch',
            'batch_beneficiary',
            'batch_trainer',
            'participant_type',
            'hra',
            'ta_da',
            'total_cost',
        ]


class BatchCostReportSerializer(SoftDeleteModelSerializer):
    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.BatchCost
        fields = [
            'id', 
            'training', 
            'batch', 
            'is_exposure_visit', 
            'exposure_visit_cost', 
            'is_field_visit', 
            'field_visit_cost', 
            'grand_total_cost'
        ]


class BatchMediaReportSerializer(SoftDeleteModelSerializer):
    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.BatchMedia
        fields = ['id', 'date', 'category', 'file', 'notes', 'batch']
        
class BatchCertificateSerializer(SoftDeleteModelSerializer):
    batch = BatchSerializer(read_only=True)

    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.BatchReport
        fields = "__all__"

# ----------------------------
# FINAL TrainingRequestReportSerializer - NO prefetch_related needed
# ----------------------------

class TrainingRequestReportSerializer(SoftDeleteModelSerializer):
    id = serializers.IntegerField()

    # --- Top-level ---
    training_plan = TrainingPlanReportSerializer(
        read_only=True
    )
    partner = TrainingPartnerReportSerializer(read_only=True)
    district = MasterDistrictReportSerializer(read_only=True)
    block = MasterBlockReportSerializer(read_only=True)

    # --- Deep Aggregations ---
    batch = serializers.SerializerMethodField()
    batch_schedule = serializers.SerializerMethodField()
    batch_master_trainer = serializers.SerializerMethodField()
    beneficiaries_in_batch = serializers.SerializerMethodField()
    trainers_in_batch = serializers.SerializerMethodField()
    batch_ekyc_participants = serializers.SerializerMethodField()
    batch_attendance_csv = serializers.SerializerMethodField()
    batch_participant_attendance = serializers.SerializerMethodField()
    batch_cost_breakup = serializers.SerializerMethodField()
    batch_overall_cost = serializers.SerializerMethodField()
    batch_media = serializers.SerializerMethodField()

    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.TrainingRequest
        fields = [
            'id',
            'training_plan',
            'partner',
            'training_type',
            'level',
            'status',
            'district',
            'block',

            'batch',
            'batch_schedule',
            'batch_master_trainer',
            'beneficiaries_in_batch',
            'trainers_in_batch',
            'batch_ekyc_participants',
            'batch_attendance_csv',
            'batch_participant_attendance',
            'batch_cost_breakup',
            'batch_overall_cost',
            'batch_media',
        ]

    # ---------------------------
    # ALL SerializerMethodFields
    # ---------------------------

    def get_batch(self, obj):
        qs = tms_models.Batch.objects.filter(
            request=obj,
            is_active=True
        )
        return BatchReportSerializer(qs, many=True, context=self.context).data

    def get_batch_schedule(self, obj):
        qs = tms_models.BatchSchedule.objects.filter(
            batch__request=obj,
            is_active=True
        )
        return BatchScheduleReportSerializer(qs, many=True).data

    def get_batch_master_trainer(self, obj):
        qs = tms_models.BatchMasterTrainer.objects.filter(
            batch__request=obj,
            is_active=True
        )
        return BatchMasterTrainerReportSerializer(qs, many=True).data

    def get_beneficiaries_in_batch(self, obj):
        qs = tms_models.BatchBeneficiary.objects.filter(
            batch__request=obj,
            is_active=True
        )
        return BatchBeneficiaryReportSerializer(qs, many=True).data

    def get_trainers_in_batch(self, obj):
        qs = tms_models.BatchTrainer.objects.filter(
            batch__request=obj,
            is_active=True
        )
        return BatchTrainerReportSerializer(qs, many=True).data

    def get_batch_ekyc_participants(self, obj):
        qs = tms_models.BatchEkycVerification.objects.filter(
            batch__request=obj,
            is_active=True
        )
        return BatchEkycVerificationReportSerializer(qs, many=True).data

    def get_batch_attendance_csv(self, obj):
        qs = tms_models.BatchAttendance.objects.filter(
            batch__request=obj,
            is_active=True
        )
        return BatchAttendanceReportSerializer(qs, many=True).data

    def get_batch_participant_attendance(self, obj):
        qs = tms_models.ParticipantAttendance.objects.filter(
            attendance__batch__request=obj,
            is_active=True
        )
        return ParticipantAttendanceReportSerializer(qs, many=True).data

    def get_batch_cost_breakup(self, obj):
        qs = tms_models.TPBatchCostBreakup.objects.filter(
            batch__request=obj,
            is_active=True
        )
        return TPBatchCostBreakupReportSerializer(qs, many=True).data

    def get_batch_overall_cost(self, obj):
        qs = tms_models.BatchCost.objects.filter(
            batch__request=obj,
            is_active=True
        )
        return BatchCostReportSerializer(qs, many=True).data

    def get_batch_media(self, obj):
        qs = tms_models.BatchMedia.objects.filter(
            batch__request=obj,
            is_active=True
        )
        return BatchMediaReportSerializer(qs, many=True).data
    
# TR list with filters
class TrainingRequestListSerializer(serializers.ModelSerializer):
    training_plan_name = serializers.CharField(
        source='training_plan.training_name', read_only=True
    )
    theme_id = serializers.IntegerField(
        source='training_plan.theme.id', read_only=True
    )
    theme_name = serializers.CharField(
        source='training_plan.theme.theme_name', read_only=True
    )
    district_name = serializers.CharField(
        source='district.district_name_en', read_only=True
    )
    block_name = serializers.CharField(
        source='block.block_name_en', read_only=True
    )
    partner_name = serializers.CharField(
        source='partner.name', read_only=True
    )
    participant_count = serializers.SerializerMethodField()

    class Meta:
        model = tms_models.TrainingRequest
        fields = [
            'id',
            'training_plan',
            'training_plan_name',
            'theme_id',
            'theme_name',
            'partner',
            'partner_name',
            'training_type',
            'level',
            'status',
            'district',
            'district_name',
            'block',
            'block_name',
            'created_at',
            'participant_count',
            'financial_year',
        ]

    # Serializer for TrainingRequest list endpoint with filters and participant count
    def get_participant_count(self, obj):
        try:
            if obj.training_type == 'BENEFICIARY':
                return obj.beneficiary_registrations.filter(deleted_at__isnull=True).count()
            elif obj.training_type == 'TRAINER':
                return obj.trainer_registrations.filter(deleted_at__isnull=True).count()
        except:
            pass
        return 0


# ============================================================
# SERIALIZERS
# ============================================================

class TPBatchCostBreakupInputSerializer(serializers.Serializer):
    """
    Represents ONE participant cost line-item.
    Exactly one of batch_beneficiary_id or batch_trainer_id must be provided.
    """
    batch_beneficiary_id = serializers.PrimaryKeyRelatedField(
        queryset=tms_models.BatchBeneficiary.objects.all(),
        required=False,
        allow_null=True,
        default=None
    )
    batch_trainer_id = serializers.PrimaryKeyRelatedField(
        queryset=tms_models.BatchTrainer.objects.all(),
        required=False,
        allow_null=True,
        default=None
    )
    hra = serializers.DecimalField(max_digits=12, decimal_places=2)
    ta_da = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_cost = serializers.DecimalField(max_digits=12, decimal_places=2)

    def validate(self, attrs):
        ben = attrs.get('batch_beneficiary_id')
        trainer = attrs.get('batch_trainer_id')
        if ben and trainer:
            raise serializers.ValidationError(
                "Each cost line-item must reference either a batch_beneficiary_id "
                "or a batch_trainer_id, not both."
            )
        if not ben and not trainer:
            raise serializers.ValidationError(
                "Each cost line-item must reference either a batch_beneficiary_id "
                "or a batch_trainer_id."
            )
        return attrs


class BatchClosureSubmitSerializer(serializers.Serializer):
    """
    Top-level payload sent by Training Partner to submit batch closure.
    """
    batch_id = serializers.PrimaryKeyRelatedField(
        queryset=tms_models.Batch.objects.select_related('request__training_plan__theme')
    )
    training_request_id = serializers.PrimaryKeyRelatedField(
        queryset=tms_models.TrainingRequest.objects.all()
    )

    # BatchCost fields
    is_exposure_visit = serializers.BooleanField(default=False)
    exposure_visit_cost = serializers.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )
    is_field_visit = serializers.BooleanField(default=False)
    field_visit_cost = serializers.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )
    grand_total_cost = serializers.DecimalField(max_digits=12, decimal_places=2)

    # Participant cost line-items (multiple)
    participant_costs = TPBatchCostBreakupInputSerializer(many=True, min_length=1)

    def validate(self, attrs):
        batch = attrs['batch_id']
        training_request = attrs['training_request_id']

        # Guard: batch must belong to the given training request
        if batch.request_id != training_request.id:
            raise serializers.ValidationError(
                "The provided batch does not belong to the provided training_request_id."
            )

        # Guard: BatchClosureRequest must not already exist for this batch
        if tms_models.BatchClosureRequest.objects.filter(batch=batch).exists():
            raise serializers.ValidationError(
                f"Closure Request for Batch '{batch.code or batch.id}' is already submitted."
            )

        # Guard: BatchCost must not already exist for this batch
        if tms_models.BatchCost.objects.filter(batch=batch).exists():
            raise serializers.ValidationError(
                f"Batch Cost for Batch '{batch.code or batch.id}' is already submitted."
            )

        # Validate all participant line-items belong to this batch
        costs = attrs['participant_costs']
        for idx, item in enumerate(costs):
            ben = item.get('batch_beneficiary_id')
            trainer = item.get('batch_trainer_id')
            if ben and ben.batch_id != batch.id:
                raise serializers.ValidationError(
                    f"participant_costs[{idx}]: BatchBeneficiary id={ben.id} "
                    f"does not belong to batch id={batch.id}."
                )
            if trainer and trainer.batch_id != batch.id:
                raise serializers.ValidationError(
                    f"participant_costs[{idx}]: BatchTrainer id={trainer.id} "
                    f"does not belong to batch id={batch.id}."
                )

        # Validate participant_type consistency: all must be same type
        types_in_payload = set()
        for item in costs:
            if item.get('batch_beneficiary_id'):
                types_in_payload.add('BENEFICIARY')
            else:
                types_in_payload.add('TRAINER')
        if len(types_in_payload) > 1:
            raise serializers.ValidationError(
                "participant_costs must be all BENEFICIARY or all TRAINER — never mixed."
            )

        return attrs


class TPBatchCostBreakupOutputSerializer(serializers.ModelSerializer):
    class Meta:
        model = tms_models.TPBatchCostBreakup
        fields = [
            'id', 'batch', 'batch_beneficiary', 'batch_trainer',
            'participant_type', 'hra', 'ta_da', 'total_cost',
            'created_at', 'updated_at',
        ]


class BatchCostOutputSerializer(serializers.ModelSerializer):
    class Meta:
        model = tms_models.BatchCost
        fields = [
            'id', 'batch', 'training',
            'is_exposure_visit', 'exposure_visit_cost',
            'is_field_visit', 'field_visit_cost',
            'grand_total_cost',
            'created_at', 'updated_at',
        ]


class BatchClosureRequestOutputSerializer(serializers.ModelSerializer):
    class Meta:
        model = tms_models.BatchClosureRequest
        fields = [
            'id', 'batch', 'batch_costing',
            'certificates_issued',
            'created_at', 'updated_at',
        ]


class BatchClosureSubmitResponseSerializer(serializers.Serializer):
    """Combined response showing all created rows."""
    participant_costs = TPBatchCostBreakupOutputSerializer(many=True)
    batch_cost = BatchCostOutputSerializer()
    closure_request = BatchClosureRequestOutputSerializer()
    batch_status = serializers.CharField()
