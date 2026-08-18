from rest_framework import serializers
from core.models import MasterUser, MasterDistrict
from TMS.models import *

# ---------------------------------------------------------
# 1) List Serializer
# ---------------------------------------------------------
class MasterTrainerListSerializer(serializers.ModelSerializer):
    district_name_en = serializers.CharField(source='empanel_district.district_name_en', read_only=True)
    theme_name = serializers.CharField(source='theme.theme_name', read_only=True)

    class Meta:
        model = MasterTrainer
        fields = [
            'id', 'full_name', 'mobile_no', 'designation', 'induction', 'tot_smcb', 'tot_mffi', 
            'tot_sisd', 'tot_farm_lh', 'tot_non_farm_lh', 'tot_model_clf', 'tot_lokos',
            'district_name_en', 'theme_name', 'social_category', 'gender', 
            'thematic_expert_recommendation'
        ]

# ---------------------------------------------------------
# 2) Detail Serializers (Nested)
# ---------------------------------------------------------
class MasterUserNestedSerializer(serializers.ModelSerializer):
    class Meta:
        model = MasterUser
        # Exclude 'password' explicitly
        exclude = ['password']

class TrainingThemeNestedSerializer(serializers.ModelSerializer):
    class Meta:
        model = TrainingTheme
        fields = '__all__'

class TrainingPlanNestedSerializer(serializers.ModelSerializer):
    class Meta:
        model = TrainingPlan
        fields = '__all__'

class MasterDistrictNestedSerializer(serializers.ModelSerializer):
    class Meta:
        model = MasterDistrict
        fields = '__all__'

class MasterTrainerCertificateSerializer(serializers.ModelSerializer):
    theme = TrainingThemeNestedSerializer(read_only=True)
    training_plan= TrainingPlanNestedSerializer(read_only=True)

    class Meta:
        model = MasterTrainerCertificate
        fields = '__all__'

class MasterTrainerDetailSerializer(serializers.ModelSerializer):
    master_user = MasterUserNestedSerializer(read_only=True)
    theme = TrainingThemeNestedSerializer(read_only=True)
    empanel_district = MasterDistrictNestedSerializer(read_only=True)
    certificates = MasterTrainerCertificateSerializer(many=True, read_only=True)

    class Meta:
        model = MasterTrainer
        fields = '__all__'

# ---------------------------------------------------------
# Create / Update Serializers
# ---------------------------------------------------------
class MasterTrainerWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = MasterTrainer
        # master_user will be handled manually in the view
        exclude = ['master_user']

# ---------------------------------------------------------
# Approve / Reject MT Profile Serializers
# ---------------------------------------------------------

class NestedMasterTrainerSerializer(serializers.ModelSerializer):
    """
    Nested serializer for Master Trainer with depth=1 to expand 
    foreign keys like theme, empanel_district, and empanel_block.
    """
    class Meta:
        model = MasterTrainer
        fields = '__all__'
        depth = 1

class MasterTrainerProfileStatusSerializer(serializers.ModelSerializer):
    """
    Serializer for the Profile Status Tracker, embedding the full Master Trainer object.
    """
    trainer = NestedMasterTrainerSerializer(read_only=True)

    class Meta:
        model = MasterTrainerProfileStatus
        fields = '__all__'
        depth = 1     