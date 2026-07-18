from rest_framework import serializers
from TMS.models import *
from core.models import MasterBlock, MasterDistrict

# ---------------------------------------------------------
# 1. Base / Configuration Serializers
# ---------------------------------------------------------
class TrainingThemeSerializer(serializers.ModelSerializer):
    class Meta:
        model = TrainingTheme
        fields = '__all__'

class TrainingPlanSerializer(serializers.ModelSerializer):
    theme = TrainingThemeSerializer(read_only=True)
    
    class Meta:
        model = TrainingPlan
        fields = '__all__'

class TrainingPartnerSerializer(serializers.ModelSerializer):
    class Meta:
        model = TrainingPartner
        fields = '__all__'

class MasterBlockSerializer(serializers.ModelSerializer):
    class Meta:
        model = MasterBlock
        fields = '__all__'

# --- Centre Nested Serializers ---
class TrainingPartnerCentreRoomSerializer(serializers.ModelSerializer):
    class Meta:
        model = TrainingPartnerCentreRooms
        fields = '__all__'

class TPCPToCentreSerializer(serializers.ModelSerializer):
    contact_person_name = serializers.CharField(source='contact_person.name', read_only=True)
    contact_person_mobile = serializers.CharField(source='contact_person.mobile_number', read_only=True)
    contact_person_email = serializers.CharField(source='contact_person.email', read_only=True)

    class Meta:
        model = TPCPToCentre
        fields = '__all__'

class TrainingPartnerCentreSerializer(serializers.ModelSerializer):
    rooms = TrainingPartnerCentreRoomSerializer(many=True, read_only=True)
    contact_persons = serializers.SerializerMethodField()

    class Meta:
        model = TrainingPartnerCentre
        fields = '__all__'

    def get_contact_persons(self, obj):
        # Fetch associated contact persons natively using the reverse relation
        if hasattr(obj, 'tpcptocentre_set'):
            return TPCPToCentreSerializer(obj.tpcptocentre_set.all(), many=True).data
        return []

# ---------------------------------------------------------
# 2. Base Participant Serializers
# ---------------------------------------------------------
class MasterTrainerSerializer(serializers.ModelSerializer):
    theme = TrainingThemeSerializer(read_only=True)
    
    class Meta:
        model = MasterTrainer
        fields = '__all__'


class TRBeneficiarySerializer(serializers.ModelSerializer):
    district_name_en = serializers.CharField(
        source="district.district_name_en",
        read_only=True
    )
    block_name_en = serializers.CharField(
        source="block.block_name_en",
        read_only=True
    )

    class Meta:
        model = TRBeneficiary
        fields = '__all__'


class TRTrainerSerializer(serializers.ModelSerializer):
    district_name_en = serializers.CharField(
        source="district.district_name_en",
        read_only=True
    )
    block_name_en = serializers.CharField(
        source="block.block_name_en",
        read_only=True
    )
    trainer = MasterTrainerSerializer(read_only=True)

    class Meta:
        model = TRTrainer
        fields = '__all__'

# ---------------------------------------------------------
# 3. Batch Participation & Attendance Aggregation
# ---------------------------------------------------------
class BeneficiaryAttendanceSummarySerializer(serializers.ModelSerializer):
    attendance_fraction = serializers.SerializerMethodField()

    class Meta:
        model = BeneficiaryAttendanceSummary
        fields = '__all__'

    def get_attendance_fraction(self, obj):
        # Returns format: "<x days present>/total batch days"
        return f"{obj.days_present}/{obj.total_training_days}"

class BatchBeneficiarySerializer(serializers.ModelSerializer):
    beneficiary = TRBeneficiarySerializer(read_only=True)
    attendance_summary = BeneficiaryAttendanceSummarySerializer(read_only=True)

    class Meta:
        model = BatchBeneficiary
        fields = '__all__'

class BatchTrainerSerializer(serializers.ModelSerializer):
    trainer = TRTrainerSerializer(read_only=True)
    attendance_summary = BeneficiaryAttendanceSummarySerializer(read_only=True)

    class Meta:
        model = BatchTrainer
        fields = '__all__'

class BatchMasterTrainerSerializer(serializers.ModelSerializer):
    master_trainer = MasterTrainerSerializer(read_only=True)

    class Meta:
        model = BatchMasterTrainer
        fields = '__all__'

# ---------------------------------------------------------
# 4. Batch Operations (Schedules, EKYC, Daily Attendance)
# ---------------------------------------------------------
class BatchScheduleSerializer(serializers.ModelSerializer):
    class Meta:
        model = BatchSchedule
        fields = '__all__'

class BatchEkycVerificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = BatchEkycVerification
        fields = '__all__'

class ParticipantAttendanceSerializer(serializers.ModelSerializer):
    class Meta:
        model = ParticipantAttendance
        fields = '__all__'

class BatchAttendanceSerializer(serializers.ModelSerializer):
    # Nests the specific participant present/absent markers under each day
    participant_records = ParticipantAttendanceSerializer(many=True, read_only=True)
    
    class Meta:
        model = BatchAttendance
        fields = '__all__'

# ---------------------------------------------------------
# 5. Costs, Media, and Certificates
# ---------------------------------------------------------
class TPBatchCostBreakupSerializer(serializers.ModelSerializer):
    class Meta:
        model = TPBatchCostBreakup
        fields = '__all__'

class BatchClosingSerializer(serializers.ModelSerializer):
    class Meta:
        model = BatchClosureRequest
        fields = '__all__'

class BatchCostSerializer(serializers.ModelSerializer):
    class Meta:
        model = BatchCost
        fields = '__all__'

class BatchMediaSerializer(serializers.ModelSerializer):
    class Meta:
        model = BatchMedia
        fields = '__all__'

class BatchParticipantCertificateSerializer(serializers.ModelSerializer):
    tr_beneficiary = TRBeneficiarySerializer(read_only=True)
    tr_trainer = TRTrainerSerializer(read_only=True)

    class Meta:
        model = BatchParticipantCertificate
        fields = '__all__'

# ---------------------------------------------------------
# 6. MASTER COMPREHENSIVE BATCH SERIALIZER
# ---------------------------------------------------------
class ComprehensiveBatchDetailSerializer(serializers.ModelSerializer):
    # Top-level lookups
    training_plan = TrainingPlanSerializer(read_only=True)
    partner = TrainingPartnerSerializer(read_only=True)
    centre = TrainingPartnerCentreSerializer(read_only=True)

    # All Participants (Trainees + Master Trainers)
    beneficiary_participations = BatchBeneficiarySerializer(many=True, read_only=True)
    trainer_participations = BatchTrainerSerializer(many=True, read_only=True)
    master_trainer_participations = BatchMasterTrainerSerializer(many=True, read_only=True)

    # Dynamic Block-wise grouping for Combined Batches
    combined_batch_details = serializers.SerializerMethodField()

    # Timetables, EKYC, and Daily Attendance
    schedules = BatchScheduleSerializer(many=True, read_only=True)
    ekyc_verifications = BatchEkycVerificationSerializer(many=True, read_only=True)
    attendances = BatchAttendanceSerializer(many=True, read_only=True)
    
    # Financials
    batch_costing = BatchCostSerializer(read_only=True)
    participant_costs = TPBatchCostBreakupSerializer(many=True, read_only=True)
    
    # Files & Closure
    batch_closing = BatchClosingSerializer(read_only=True)
    batch_pictures = BatchMediaSerializer(many=True, read_only=True)
    batch_certificates = BatchParticipantCertificateSerializer(many=True, read_only=True)

    class Meta:
        model = Batch
        fields = '__all__'

    def get_combined_batch_details(self, obj):
        """
        Iterates over all participants mapping them under their corresponding MasterBlock.
        Returns a list of dicts: [{"block": <MasterBlockData>, "participants": [...]}]
        """
        blocks_map = {}

        # Process Beneficiaries
        for bp in obj.beneficiary_participations.all():
            if bp.beneficiary and bp.beneficiary.block:
                b_id = bp.beneficiary.block.block_id
                if b_id not in blocks_map:
                    blocks_map[b_id] = {
                        "block": MasterBlockSerializer(bp.beneficiary.block).data,
                        "participants": []
                    }
                blocks_map[b_id]["participants"].append(BatchBeneficiarySerializer(bp).data)

        # Process Trainers
        for bt in obj.trainer_participations.all():
            if bt.trainer and bt.trainer.block:
                b_id = bt.trainer.block.block_id
                if b_id not in blocks_map:
                    blocks_map[b_id] = {
                        "block": MasterBlockSerializer(bt.trainer.block).data,
                        "participants": []
                    }
                blocks_map[b_id]["participants"].append(BatchTrainerSerializer(bt).data)

        return list(blocks_map.values())