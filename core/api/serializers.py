from rest_framework import serializers
from core import models
from django.utils import timezone
from django.db import IntegrityError

# -------------------------
# Lightweight list serializers (return FK ids only)
# -------------------------

class MasterDistrictListSerializer(serializers.ModelSerializer):
    # list endpoints must return FK ids only for speed
    state_id = serializers.IntegerField(read_only=True)
    mandal_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = models.MasterDistrict
        # choose fields that are useful in lists; include ids and names
        fields = [
            'district_id', 'district_name_en', 'district_short_name_en', 'district_name_local',
            'district_code', 'lgd_code', 'language_id', 'created_at', 'updated_at',
            'state_id', 'mandal_id'
        ]


class MasterBlockListSerializer(serializers.ModelSerializer):
    state_id = serializers.IntegerField(read_only=True)
    district_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = models.MasterBlock
        fields = [
            'block_id', 'block_name_en', 'block_name_local', 'block_code',
            'rural_urban_area', 'is_aspirational', 'created_at', 'updated_at',
            'state_id', 'district_id'
        ]


class MasterPanchayatListSerializer(serializers.ModelSerializer):
    state_id = serializers.IntegerField(read_only=True)
    district_id = serializers.IntegerField(read_only=True)
    block_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = models.MasterPanchayat
        fields = [
            'panchayat_id', 'panchayat_name_en', 'panchayat_name_local', 'panchayat_code',
            'rural_urban_area', 'created_at', 'updated_at',
            'state_id', 'district_id', 'block_id'
        ]


class MasterVillageListSerializer(serializers.ModelSerializer):
    state_id = serializers.IntegerField(read_only=True)
    district_id = serializers.IntegerField(read_only=True)
    block_id = serializers.IntegerField(read_only=True)
    panchayat_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = models.MasterVillage
        fields = [
            'village_id', 'village_name_english', 'village_name_local', 'village_code',
            'is_active', 'created_at', 'updated_at',
            'state_id', 'district_id', 'block_id', 'panchayat_id'
        ]


class MasterShgListSerializer(serializers.ModelSerializer):
    # list returns FK ids only
    block_id = serializers.IntegerField(read_only=True)
    district_id = serializers.IntegerField(read_only=True)
    panchayat_id = serializers.IntegerField(read_only=True)
    village_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = models.MasterShgList
        fields = [
            'id', 'shg_code', 'name', 'formation_date', 'is_active',
            'block_id', 'district_id', 'panchayat_id', 'village_id'
        ]


class MasterBeneficiaryListSerializer(serializers.ModelSerializer):
    shg_code = serializers.CharField(read_only=True)
    state_id = serializers.IntegerField(read_only=True)
    district_id = serializers.IntegerField(read_only=True)
    block_id = serializers.IntegerField(read_only=True)
    panchayat_id = serializers.IntegerField(read_only=True)
    village_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = models.MasterBeneficiary
        fields = [
            'member_code', 'member_name', 'dob', 'gender', 'joining_date',
            'shg_code', 'state_id', 'district_id', 'block_id', 'panchayat_id', 'village_id',
            'marital_status', 'religion', 'social_category'
        ]


class MasterClfListSerializer(serializers.ModelSerializer):
    state_id = serializers.IntegerField(read_only=True)
    district_id = serializers.IntegerField(read_only=True)
    block_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = models.MasterClfList
        fields = ['id', 'clf_code', 'name', 'nic_code', 'formation_date', 'is_complete', 'pfms_verified', 'state_id', 'district_id', 'block_id']


class MasterMembersUnderClfListSerializer(serializers.ModelSerializer):
    clf_code = serializers.CharField(read_only=True)

    class Meta:
        model = models.MasterMembersUnderClf
        fields = ['id', 'clf_code', 'member_code', 'member_name', 'designation', 'is_signatory']


class MasterPanchayatsUnderClfListSerializer(serializers.ModelSerializer):
    clf_code = serializers.CharField(read_only=True)
    panchayat_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = models.MasterPanchayatsUnderClf
        # return panchayat_id (fk id) rather than nested object in list
        fields = ['id', 'clf_code', 'panchayat_id', 'panchayat_code', 'panchayat_name', 'lgd_gp']


class MasterVillagesUnderClfListSerializer(serializers.ModelSerializer):
    clf_code = serializers.CharField(read_only=True)
    panchayat_id = serializers.IntegerField(read_only=True)
    village_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = models.MasterVillagesUnderClf
        # list shows ids for speed
        fields = ['id', 'clf_code', 'panchayat_id', 'village_id', 'village_code', 'village_name', 'lgd_village']


# -------------------------
# Detail serializers (return everything, nested objects included)
# -------------------------

class MasterStateSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.MasterState
        fields = '__all__'


class MasterMandalSerializer(serializers.ModelSerializer):

    class Meta:
        model = models.MasterMandal
        fields = '__all__'

class MasterDistrictCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = models.MasterDistrictCategory
        fields = '__all__'

class MasterDistrictDetailSerializer(serializers.ModelSerializer):
    # nested state & mandal fully for detail endpoint
    state = MasterStateSerializer(read_only=True)
    mandal = MasterMandalSerializer(read_only=True)

    class Meta:
        model = models.MasterDistrict
        fields = '__all__'

class MasterDistrictCategoryMappingSerializer(serializers.ModelSerializer):
    district = MasterDistrictListSerializer(read_only=True)
    category = MasterDistrictCategorySerializer(read_only=True)

    class Meta:
        model = models.MasterDistrictCategoryMapping
        fields = '__all__'

class MasterBlockDetailSerializer(serializers.ModelSerializer):
    state = MasterStateSerializer(read_only=True)
    district = MasterDistrictDetailSerializer(read_only=True)

    class Meta:
        model = models.MasterBlock
        fields = '__all__'


class MasterPanchayatDetailSerializer(serializers.ModelSerializer):
    state = MasterStateSerializer(read_only=True)
    district = MasterDistrictDetailSerializer(read_only=True)
    block = MasterBlockDetailSerializer(read_only=True)

    class Meta:
        model = models.MasterPanchayat
        fields = '__all__'


class MasterVillageDetailSerializer(serializers.ModelSerializer):
    state = MasterStateSerializer(read_only=True)
    district = MasterDistrictDetailSerializer(read_only=True)
    block = MasterBlockDetailSerializer(read_only=True)
    panchayat = MasterPanchayatDetailSerializer(read_only=True)

    class Meta:
        model = models.MasterVillage
        fields = '__all__'


class MasterShgDetailSerializer(serializers.ModelSerializer):
    state = MasterStateSerializer(read_only=True)
    district = MasterDistrictDetailSerializer(read_only=True)
    block = MasterBlockDetailSerializer(read_only=True)
    panchayat = MasterPanchayatDetailSerializer(read_only=True)
    village = MasterVillageDetailSerializer(read_only=True)

    class Meta:
        model = models.MasterShgList
        fields = '__all__'


class MasterBeneficiaryDetailSerializer(serializers.ModelSerializer):
    state = MasterStateSerializer(read_only=True)
    district = MasterDistrictDetailSerializer(read_only=True)
    block = MasterBlockDetailSerializer(read_only=True)
    panchayat = MasterPanchayatDetailSerializer(read_only=True)
    village = MasterVillageDetailSerializer(read_only=True)

    class Meta:
        model = models.MasterBeneficiary
        fields = '__all__'


class MasterClfAddressesSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.MasterClfAddresses
        fields = '__all__'


class MasterClfBanksSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.MasterClfBanks
        fields = '__all__'


class MasterClfPhonesSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.MasterClfPhones
        fields = '__all__'


class MasterClfVoDetailsSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.MasterClfVoDetails
        fields = '__all__'


class MasterClfDetailSerializer(serializers.Serializer):
    clf = MasterClfListSerializer()
    addresses = MasterClfAddressesSerializer(many=True)
    banks = MasterClfBanksSerializer(many=True)
    phones = MasterClfPhonesSerializer(many=True)
    vo_details = MasterClfVoDetailsSerializer(many=True)


# Roles & Users (detail)
class MasterRolesSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.MasterRoles
        fields = '__all__'


class MasterUserSerializer(serializers.ModelSerializer):
    role_id = serializers.IntegerField(source="role.id", read_only=True)
    role_name = serializers.CharField(source="role.name", read_only=True)

    class Meta:
        model = models.MasterUser
        read_only_fields = (
            'id',
            'created_at',
            'updated_at',
            'deleted_at',
        )
        exclude = (
            "password",
            "pass_attempt_no",
            "pass_updated_at",
            "pass_updated_by",
            "locked_on",
            "suspended_on",
            "recovery_email",
            "recovery_mobile",            
        )        

class MasterUserCUDSerializer(serializers.ModelSerializer):
    role_id = serializers.IntegerField(source="role.id", read_only=True)
    role_name = serializers.CharField(source="role.name", read_only=True)

    class Meta:
        model = models.MasterUser
        read_only_fields = (
            "id",
            "created_at",
            "updated_at",
            "deleted_at",
        )
        fields = "__all__"

    # Username uniqueness validation
    def validate_username(self, value):
        qs = models.MasterUser.objects.filter(username=value)

        # same username allowed when updating same record
        if self.instance:
            qs = qs.exclude(id=self.instance.id)

        if qs.exists():
            raise serializers.ValidationError("Username already exists.")

        return value

    def create(self, validated_data):
        validated_data['created_at'] = timezone.now()

        try:
            return super().create(validated_data)

        # Race-condition protection
        except IntegrityError:
            raise serializers.ValidationError({
                "username": "Username already exists."
            })

    def update(self, instance, validated_data):
        validated_data['updated_at'] = timezone.now()

        try:
            return super().update(instance, validated_data)

        except IntegrityError:
            raise serializers.ValidationError({
                "username": "Username already exists."
            })
    
class MasterUserListSerializer(serializers.ModelSerializer):
    role_name = serializers.SerializerMethodField()
    created_by_username = serializers.CharField(
        source="created_by.username",
        read_only=True
    )

    class Meta:
        model = models.MasterUser
        fields = [
            "id",
            "username",
            "password",
            "role",
            "role_name",
            "is_active",
            "created_at",
            "created_by",
            "created_by_username",
        ]

    def get_role_name(self, obj):
        return obj.get_role_name()    