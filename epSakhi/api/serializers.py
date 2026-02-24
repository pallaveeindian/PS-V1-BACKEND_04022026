# epSakhi/api/serializers.py

from django.db import transaction
from rest_framework import serializers

from epSakhi.models import *

from core.api.serializers import (
    MasterPanchayatListSerializer,
    MasterBlockListSerializer,
    MasterDistrictListSerializer,
)

class MasterUserNestedSerializer(serializers.ModelSerializer):
    role_name = serializers.SerializerMethodField()

    class Meta:
        model = MasterUser
        fields = [
            "id",
            "username",
            "recovery_email",
            "recovery_mobile",
            "is_active",
            "is_suspended",
            "is_locked",
            "TH_urid",
            "created_at",
            "role_name",
        ]
        read_only_fields = fields

    def get_role_name(self, obj):
        return obj.get_role_name()

class CRPEPSerializer(serializers.ModelSerializer):
    # Nested relations
    district = MasterDistrictListSerializer(read_only=True)
    block = MasterBlockListSerializer(read_only=True)
    panchayat = MasterPanchayatListSerializer(read_only=True)

    master_user = MasterUserNestedSerializer(read_only=True)

    class Meta:
        model = CRPEP
        fields = [
            'id',
            'name',
            'mobile_number',
            'category',
            'subcategory',
            'marks_obtained',
            'TH_urid',

            'district_id',
            'block_id',
            'panchayat_id',

            'lokos_shg_code',
            'lokos_member_code',
            'nodal_clf',

            # Nested
            'district',
            'block',
            'panchayat',
            'master_user',

            'created_by',
            'updated_by',
            'deleted_by',
            
            'created_at',
            'updated_at',
            'deleted_at',
        ]

        read_only_fields = [
            'created_at',
            'updated_at',
            'deleted_at',
            'TH_urid',
            'district',
            'block',
            'panchayat',
            'master_user',
        ]

class CRPEPToPanchayatCRUDSerializer(serializers.ModelSerializer):
    class Meta:
        model = CRPEPToPanchayat
        fields = '__all__'

class BeneficiaryRecordedSerializer(serializers.ModelSerializer):

    district_name_en = serializers.SerializerMethodField()
    block_name_en = serializers.SerializerMethodField()
    panchayat_name_en = serializers.SerializerMethodField()
    village_name_english = serializers.SerializerMethodField()

    class Meta:
        model = BeneficiaryRecorded
        fields = '__all__'   # keeps ALL previous fields
        read_only_fields = [
            'created_at',
            'updated_at',
            'deleted_at',
            'TH_urid',
            'id'
        ]

    def get_district_name_en(self, obj):
        return obj.district_id.district_name_en if obj.district_id else None

    def get_block_name_en(self, obj):
        return obj.block_id.block_name_en if obj.block_id else None

    def get_panchayat_name_en(self, obj):
        return obj.panchayat_id.panchayat_name_en if obj.panchayat_id else None

    def get_village_name_english(self, obj):
        return obj.village_id.village_name_english if obj.village_id else None
    
# ============= EXISTING / NEW ENTERPRISE =============

class ExistingEnterpriseSerializer(serializers.ModelSerializer):
    """
    CRUD for epSakhi_existingEpForm ONLY.
    No nested writes.
    """

    class Meta:
        model = ExistingEnterprise
        fields = '__all__'
        read_only_fields = (
            'id',
            'TH_urid',
            'created_at',
            'updated_at',
            'deleted_at',
        )

class NewEnterpriseSerializer(serializers.ModelSerializer):
    class Meta:
        model = NewEnterprise
        fields = '__all__'
        read_only_fields = ['id', 'TH_urid', 'created_at', 'updated_at', 'deleted_at']

# ============= NEW DETAIL MODELS =============
class EnterpriseLicensesSerializer(serializers.ModelSerializer):
    class Meta:
        model = EnterpriseLicenses
        fields = '__all__'
        read_only_fields = ['id', 'TH_urid', 'created_at', 'updated_at', 'deleted_at']

class EnterpriseLoanDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = EnterpriseLoanDetail
        fields = '__all__'
        read_only_fields = ['id', 'TH_urid', 'created_at', 'updated_at', 'deleted_at']

class EnterpriseSubsidyDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = EnterpriseSubsidyDetail
        fields = '__all__'
        read_only_fields = ['id', 'TH_urid', 'created_at', 'updated_at', 'deleted_at']

class EnterpriseShopSerializer(serializers.ModelSerializer):
    class Meta:
        model = EnterpriseShop
        fields = '__all__'
        read_only_fields = ['id', 'TH_urid', 'created_at', 'updated_at', 'deleted_at']

class ShopMediaSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShopMedia
        fields = '__all__'
        read_only_fields = ['id', 'TH_urid', 'created_at', 'updated_at', 'deleted_at']

class EnterpriseProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = EnterpriseProduct
        fields = '__all__'
        read_only_fields = ['id', 'TH_urid', 'created_at', 'updated_at', 'deleted_at']

class ProductMediaSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductMedia
        fields = '__all__'
        read_only_fields = ['id', 'TH_urid', 'created_at', 'updated_at', 'deleted_at']

class EnterpriseMediaSerializer(serializers.ModelSerializer):
    class Meta:
        model = EnterpriseMedia
        fields = '__all__'
        read_only_fields = ['id', 'TH_urid', 'created_at', 'updated_at', 'deleted_at']

class EnterpriseTypeCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = EnterpriseTypeCategory
        fields = '__all__'
        read_only_fields = ['id', 'TH_urid', 'created_at', 'updated_at', 'deleted_at']

class EnterpriseSupportSerializer(serializers.ModelSerializer):
    class Meta:
        model = EnterpriseSupport
        fields = '__all__'
        read_only_fields = ['id', 'TH_urid', 'created_at', 'updated_at', 'deleted_at']

class EnterpriseMandatoryFundSerializer(serializers.ModelSerializer):
    class Meta:
        model = EnterpriseMandatoryFund
        fields = '__all__'
        read_only_fields = ['id', 'TH_urid', 'created_at', 'updated_at', 'deleted_at']

class EnterpriseTrainingReqSerializer(serializers.ModelSerializer):
    class Meta:
        model = EnterpriseTrainingReq
        fields = '__all__'
        read_only_fields = ['id', 'TH_urid', 'created_at', 'updated_at', 'deleted_at']

class TrainingCertificatesSerializer(serializers.ModelSerializer):
    class Meta:
        model = TrainingCertificates
        fields = '__all__'
        read_only_fields = ['id', 'TH_urid', 'created_at', 'updated_at', 'deleted_at']

class NoEnterpriseFormSerializer(serializers.ModelSerializer):
    """
    CRUD for epSakhi_noEpForm
    """
    class Meta:
        model = NoEnterpriseForm
        fields = '__all__'

class NoEnterpriseWageSerializer(serializers.ModelSerializer):
    """
    CRUD for epSakhi_noEpWage
    """
    class Meta:
        model = NoEnterpriseWage
        fields = '__all__'

# Analytics Views
class CRPEPAnalyticsSerializer(serializers.ModelSerializer):
    total_beneficiaries = serializers.IntegerField(read_only=True)
    district_name = serializers.CharField(read_only=True)
    block_name = serializers.CharField(read_only=True)
    panchayat_name = serializers.CharField(read_only=True)

    class Meta:
        model = CRPEP
        fields = [
            "id",
            "name",
            "master_user",
            "district_id",
            "district_name",
            "block_id",
            "block_name",
            "panchayat_id",
            "panchayat_name",
            "nodal_clf",
            "lokos_shg_code",
            "lokos_member_code",
            "category",
            "subcategory",
            "mobile_number",
            "total_beneficiaries",
        ]