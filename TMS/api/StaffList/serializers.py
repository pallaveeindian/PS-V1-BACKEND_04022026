# TMS/api/StaffList/serializers.py

from rest_framework import serializers
from TMS.models import StaffProfile, TrainingTheme, Bank, BankBranch, BankIFSC
from core.models import MasterDistrict, MasterBlock

# ==========================================
# NESTED SERIALIZERS (For Detail View)
# ==========================================

class NestedTrainingThemeSerializer(serializers.ModelSerializer):
    class Meta:
        model = TrainingTheme
        fields = ['id', 'theme_name']

class NestedMasterDistrictSerializer(serializers.ModelSerializer):
    class Meta:
        model = MasterDistrict
        fields = ['district_id', 'district_name_en', 'district_code']

class NestedMasterBlockSerializer(serializers.ModelSerializer):
    class Meta:
        model = MasterBlock
        fields = ['block_id', 'block_name_en', 'block_code']

class NestedBankSerializer(serializers.ModelSerializer):
    class Meta:
        model = Bank
        fields = ['id', 'bank_name']

class NestedBankBranchSerializer(serializers.ModelSerializer):
    class Meta:
        model = BankBranch
        fields = ['id', 'branch_name']

class NestedBankIFSCSerializer(serializers.ModelSerializer):
    class Meta:
        model = BankIFSC
        fields = ['id', 'ifsc_code']


# ==========================================
# MAIN SERIALIZERS
# ==========================================

class StaffListSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for the List API. 
    Returns basic info to keep the list fast and efficient.
    """
    district_name = serializers.CharField(source='district.district_name_en', read_only=True)
    block_name = serializers.CharField(source='block.block_name_en', read_only=True)
    theme_name = serializers.CharField(source='theme.theme_name', read_only=True)

    class Meta:
        model = StaffProfile
        fields = [
            'id', 
            'employee_id', 
            'full_name', 
            'mobile', 
            'email', 
            'designation', 
            'employment_type', 
            'gender', 
            'social_category',
            'theme', 'theme_name',
            'district', 'district_name',
            'block', 'block_name',
            'is_active'
        ]

class StaffDetailSerializer(serializers.ModelSerializer):
    """
    Heavy serializer for the Detail API. 
    Returns WHOLE nested objects for all Foreign Keys.
    """
    # Replacing the ID fields with fully nested objects
    theme = NestedTrainingThemeSerializer(read_only=True)
    district = NestedMasterDistrictSerializer(read_only=True)
    block = NestedMasterBlockSerializer(read_only=True)
    bank = NestedBankSerializer(read_only=True)
    bank_branch = NestedBankBranchSerializer(read_only=True)
    bank_ifsc = NestedBankIFSCSerializer(read_only=True)

    class Meta:
        model = StaffProfile
        # '__all__' will grab every column from the model, and the nested serializers 
        # above will override the foreign keys to show full dictionaries.
        fields = '__all__'
        