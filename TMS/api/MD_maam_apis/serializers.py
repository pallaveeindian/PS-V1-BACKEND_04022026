from rest_framework import serializers
from TMS.models import TrainingPartnerCentre, TrainingPartnerSubmission

class MasterProgressReportSerializer(serializers.Serializer):
    district_id = serializers.IntegerField(required=False, allow_null=True)
    district_name = serializers.CharField(required=False, allow_null=True)
    group_id = serializers.IntegerField(required=False, allow_null=True)
    group_name = serializers.CharField(required=False, allow_null=True)
    target = serializers.IntegerField(default=0)
    total_onboarded = serializers.IntegerField(default=0)
    total_batches = serializers.IntegerField(default=0)
    dmmu_approved_batches = serializers.IntegerField(default=0)
    ongoing_batches = serializers.IntegerField(default=0)
    completed_batches = serializers.IntegerField(default=0)
    total_participants_trained = serializers.IntegerField(default=0)
    percentage = serializers.FloatField(default=0.0)

class CentreSummarySerializer(serializers.ModelSerializer):
    partner_name = serializers.CharField(source='partner.name', read_only=True)
    district_name = serializers.CharField(source='district.district_name_en', read_only=True)
    
    # Annotated Fields
    tpcp_count = serializers.IntegerField(read_only=True)
    batch_count = serializers.IntegerField(read_only=True)
    asset_count = serializers.IntegerField(read_only=True)
    
    # Python-mapped Field
    allocated_target = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = TrainingPartnerCentre
        fields = [
            'id', 
            'partner_id', 'partner_name', 
            'district_id', 'district_name', 
            'venue_name', 
            'allocated_target', 
            'tpcp_count', 
            'batch_count', 
            'asset_count'
        ]

class CentreSubmissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = TrainingPartnerSubmission
        fields = ['id', 'category', 'file', 'notes', 'created_at']

class CertificatePendencySerializer(serializers.Serializer):
    district_id = serializers.IntegerField(source='district__district_id')
    district_name = serializers.CharField(source='district__district_name_en')
    total_closed_batches = serializers.IntegerField()
    certificates_uploaded = serializers.IntegerField()
    pending_backlog = serializers.IntegerField()
    oldest_uncertified_batch_date = serializers.DateTimeField(source='oldest_uncertified_date', format="%Y-%m-%d %I:%M %p")        

class BeneficiaryEligibilitySerializer(serializers.Serializer):
    district_id = serializers.IntegerField(source='district__district_id')
    district_name = serializers.CharField(source='district__district_name_en')
    block_id = serializers.IntegerField(source='block__block_id', allow_null=True)
    block_name = serializers.CharField(source='block__block_name_en', allow_null=True)
    
    total_participants = serializers.IntegerField()
    successful_participants = serializers.IntegerField()
    unsuccessful_participants = serializers.IntegerField()
    attendance_ratio = serializers.FloatField()    

class HomeDashboardStatsSerializer(serializers.Serializer):
    # TMS Stats
    tms_total_batches = serializers.IntegerField(default=0)
    tms_completed = serializers.IntegerField(default=0)
    tms_pending = serializers.IntegerField(default=0)
    tms_ongoing = serializers.IntegerField(default=0)

    # EPSMS Stats
    epsms_total_forms = serializers.IntegerField(default=0)
    epsms_existing = serializers.IntegerField(default=0)
    epsms_new = serializers.IntegerField(default=0)
    epsms_non_ep = serializers.IntegerField(default=0)

    # LDMS Stats
    ldms_total_support = serializers.IntegerField(default=0)
    ldms_pld = serializers.IntegerField(default=0)
    ldms_non_pld = serializers.IntegerField(default=0)

    # MOU Stats
    mou_state = serializers.IntegerField(default=0)
    mou_district = serializers.IntegerField(default=0)
    mou_block = serializers.IntegerField(default=0)
    mou_clf = serializers.IntegerField(default=0)
    mou_vo = serializers.IntegerField(default=0)
    mou_shg = serializers.IntegerField(default=0)