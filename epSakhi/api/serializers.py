# epSakhi/api/serializers.py

from django.db import transaction
from rest_framework import serializers
from epSakhi.utils.file_security import validate_and_rename

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

    # -------- READ IDs (for response) --------
    district_id = serializers.SerializerMethodField()
    block_id = serializers.SerializerMethodField()
    panchayat_id = serializers.SerializerMethodField()

    # -------- WRITE IDs (for create/update) --------
    district_write = serializers.PrimaryKeyRelatedField(
        queryset=MasterDistrict.objects.all(),
        source="district",
        write_only=True
    )

    block_write = serializers.PrimaryKeyRelatedField(
        queryset=MasterBlock.objects.all(),
        source="block",
        write_only=True
    )

    panchayat_write = serializers.PrimaryKeyRelatedField(
        queryset=MasterPanchayat.objects.all(),
        source="panchayat",
        write_only=True
    )

    master_user = MasterUserNestedSerializer(read_only=True)
    master_user_id = serializers.PrimaryKeyRelatedField(
        queryset=MasterUser.objects.all(),
        source="master_user",
        write_only=True
    )

    def get_district_id(self, obj):
        return obj.district_id

    def get_block_id(self, obj):
        return obj.block_id

    def get_panchayat_id(self, obj):
        return obj.panchayat_id

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
            
            'district_write',
            'block_write',
            'panchayat_write',            

            'lokos_shg_code',
            'lokos_member_code',
            'nodal_clf',
            
            'master_user_id',

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
        ]

    # -------------------------
    # VALIDATIONS
    # -------------------------

    def validate_mobile_number(self, value):

        if value and not value.isdigit():
            raise serializers.ValidationError(
                "Mobile number must contain only digits."
            )

        if value and len(value) != 10:
            raise serializers.ValidationError(
                "Mobile number must be 10 digits."
            )

        return value

    def validate_marks_obtained(self, value):

        if value is not None and value < 0:
            raise serializers.ValidationError(
                "Marks obtained cannot be negative."
            )

        return value

    def validate_lokos_member_code(self, value):

        qs = CRPEP.objects.filter(lokos_member_code=value)

        if self.instance:
            qs = qs.exclude(id=self.instance.id)

        if qs.exists():
            raise serializers.ValidationError(
                "CRP with this LokOS member code already exists."
            )

        return value

    # -------------------------
    # CREATE / UPDATE SAFETY
    # -------------------------

    def create(self, validated_data):

        try:
            return super().create(validated_data)

        except IntegrityError:
            raise serializers.ValidationError({
                "detail": "Duplicate or invalid CRP data."
            })

    def update(self, instance, validated_data):

        try:
            return super().update(instance, validated_data)

        except IntegrityError:
            raise serializers.ValidationError({
                "detail": "Duplicate or invalid CRP data."
            })        

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

    # VUN - 4 Fixes: File Upload Security Enhancements for License Files 
    def validate(self, attrs):
        attrs['license_file'] = validate_and_rename(attrs.get('license_file'))
        return attrs        

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

    # VUN-4 Fixes: File Upload Security Enhancements
    def validate(self, attrs):
        attrs['open_box_photo'] = validate_and_rename(attrs.get('open_box_photo'))
        attrs['close_box_photo'] = validate_and_rename(attrs.get('close_box_photo'))
        attrs['others'] = validate_and_rename(attrs.get('others'))
        return attrs

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

# CRP-Panchayat mapping Form Serializers
class CRPPanchayatBulkSerializer(serializers.Serializer):
    crp_id = serializers.IntegerField()
    allocated_panchayats = serializers.ListField(
        child=serializers.IntegerField(),
        allow_empty=False
    )

    def validate_crp_id(self, value):
        """
        Validate CRP exists
        """
        try:
            CRPEP.objects.get(master_user_id=value)
        except CRPEP.DoesNotExist:
            raise serializers.ValidationError("Invalid CRP ID")

        return value

    def validate_allocated_panchayats(self, value):
        """
        Remove duplicates in payload
        """
        unique_ids = list(set(value))

        if len(unique_ids) != len(value):
            raise serializers.ValidationError(
                "Duplicate Panchayat IDs in request"
            )

        return unique_ids

    def create(self, validated_data):
        crp_id = validated_data["crp_id"]
        panchayats = validated_data["allocated_panchayats"]
        user = self.context["request"].user

        master_user = MasterUser.objects.get(username=user.username)

        existing = set(
            CRPEPToPanchayat.objects.filter(
                crp_id=crp_id,
                allocated_panchayat_id__in=panchayats,
                is_active=True
            ).values_list("allocated_panchayat_id", flat=True)
        )

        created_rows = []

        with transaction.atomic():

            for panchayat_id in panchayats:

                if panchayat_id in existing:
                    continue

                obj = CRPEPToPanchayat.objects.create(
                    crp_id=crp_id,
                    allocated_panchayat_id=panchayat_id,
                    created_by=master_user,
                    updated_by=master_user,
                    is_active=True
                )

                created_rows.append(obj)

        return created_rows 
    
# CRP view with panchayat
class PanchayatSerializer(serializers.ModelSerializer):
    panchayat_name_en = serializers.CharField()
    
    class Meta:
        model = MasterPanchayat
        fields = ["panchayat_id", "panchayat_name_en"]
        
class CRPListSerializer(serializers.ModelSerializer):

    district_name_en = serializers.CharField(source="district.district_name_en", read_only=True)
    block_name_en = serializers.CharField(source="block.block_name_en", read_only=True)
    panchayat_name_en = serializers.CharField(source="panchayat.panchayat_name_en", read_only=True)

    allocated_panchayats = serializers.SerializerMethodField()

    class Meta:
        model = CRPEP
        fields = [
            "id",
            "name",
            "mobile_number",
            "lokos_shg_code",
            "lokos_member_code",

            "district",
            "district_name_en",

            "block",
            "block_name_en",

            "panchayat",
            "panchayat_name_en",

            "allocated_panchayats"
        ]

    def get_allocated_panchayats(self, obj):

        allocations = CRPEPToPanchayat.objects.filter(
            crp=obj.master_user_id
        ).values_list("allocated_panchayat_id", flat=True)

        panchayats = MasterPanchayat.objects.filter(panchayat_id__in=allocations)

        return PanchayatSerializer(panchayats, many=True).data


# EPSMS Serializers
class RemoveCRPPanchayatSerializer(serializers.Serializer):
    crpep_id = serializers.IntegerField()
    panchayat_ids = serializers.CharField()

    def validate_panchayat_ids(self, value):
        try:
            ids = [
                int(x.strip())
                for x in value.split(",")
                if x.strip()
            ]
        except ValueError:
            raise serializers.ValidationError(
                "Panchayat IDs must be comma separated integers."
            )

        if not ids:
            raise serializers.ValidationError(
                "At least one Panchayat ID is required."
            )

        return ids