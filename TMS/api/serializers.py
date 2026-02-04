# TMS/api/serializers.py

from rest_framework import serializers
from django.apps import apps
from datetime import datetime
from TMS import models as tms_models
from core import models as core_models


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
    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.MasterTrainer
        fields = "__all__"


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

class TrainingPartnerSubmissionSerializer(SoftDeleteModelSerializer):
    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.TrainingPartnerSubmission
        fields = "__all__"


class TrainingPartnerCentreDetailSerializer(SoftDeleteModelSerializer):
    """
    DETAIL serializer for centre including nested rooms.
    """
    rooms = TrainingPartnerCentreRoomsSerializer(many=True, read_only=True)
    submissions = TrainingPartnerSubmissionSerializer(many=True, read_only=True)

    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.TrainingPartnerCentre
        fields = "__all__"
        depth = 1


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

class TrainingPartnerTargetsSerializer(SoftDeleteModelSerializer):
    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.TrainingPartnerTargets
        fields = "__all__"


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
    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.TrainingRequest
        fields = "__all__"


class TRBeneficiarySerializer(SoftDeleteModelSerializer):
    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.TRBeneficiary
        fields = "__all__"


class TRBeneficiaryDetailSerializer(SoftDeleteModelSerializer):
    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.TRBeneficiary
        fields = "__all__"
        depth = 1


class TRTrainerSerializer(SoftDeleteModelSerializer):
    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.TRTrainer
        fields = "__all__"


class TRTrainerDetailSerializer(SoftDeleteModelSerializer):
    """
    DETAIL serializer for TRTrainer – includes nested trainer + training.
    """
    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.TRTrainer
        fields = "__all__"
        depth = 1


class TrainingRequestDetailSerializer(SoftDeleteModelSerializer):
    beneficiary_registrations = TRBeneficiarySerializer(many=True, read_only=True)
    trainer_registrations = TRTrainerSerializer(many=True, read_only=True)
    batches = serializers.PrimaryKeyRelatedField(many=True, read_only=True)

    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.TrainingRequest
        fields = "__all__"
        depth = 1


# ----------------------------
# Batch + participants/trainers
# ----------------------------

class BatchSerializer(SoftDeleteModelSerializer):
    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.Batch
        fields = "__all__"

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


class BatchDetailSerializer(SoftDeleteModelSerializer):
    master_trainer_participations = BatchMasterTrainerSerializer(many=True, read_only=True)
    trainer_participations = BatchTrainerSerializer(many=True, read_only=True)
    beneficiary_participations = BatchBeneficiarySerializer(many=True, read_only=True)
    ekyc_verifications = BatchEkycVerificationSerializer(many=True, read_only=True)
    attendances = BatchAttendanceDetailSerializer(many=True, read_only=True)

    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.Batch
        fields = "__all__"
        depth = 1


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
    batch_expenses = TPBatchCostBreakupSerializer(read_only=True)
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


class TRClosureSerializer(SoftDeleteModelSerializer):
    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.TRClosure
        fields = "__all__"


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
    request = BatchTRSerializer()
    centre = BatchCentreSerializer()

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
            'request',
            'centre'
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
            'centre_cost',
            'hostel_cost',
            'fooding_cost',
            'dresses_cost',
            'study_material_cost',
            'total_cost',
            'batch',
        ]


class BatchCostReportSerializer(SoftDeleteModelSerializer):
    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.BatchCost
        fields = ['id', 'trainer_part_cost', 'tp_part_cost', 'batch']


class BatchMediaReportSerializer(SoftDeleteModelSerializer):
    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.BatchMedia
        fields = ['id', 'date', 'category', 'file', 'notes', 'batch']


class TRClosureReportSerializer(SoftDeleteModelSerializer):
    class Meta(SoftDeleteModelSerializer.Meta):
        model = tms_models.TRClosure
        fields = ['id', 'hra', 'ta_da']
        
class BatchCertificateSerializer(SoftDeleteModelSerializer):
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
    closure_docs = TRClosureReportSerializer(
        source='TR_closure',
        many=True,
        read_only=True
    )

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
            'closure_docs',
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