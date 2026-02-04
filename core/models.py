# core/models.py
"""
Comprehensive master_* models for upsrlm database.

All models have Meta.managed = False to avoid Django managing schema changes.
Adjust field types, nullability and on_delete behavior as needed for your use-case.
"""

from django.db import models
from django.utils import timezone

# ---------- Role & User (used by auth backend) ----------

class MasterRoles(models.Model):
    id = models.BigAutoField(primary_key=True)
    name = models.CharField(unique=True, max_length=100)
    role_type = models.CharField(max_length=3)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'master_roles'

    def __str__(self):
        return self.name


class MasterUser(models.Model):
    """
    master_user table representation. 
    Note: role modeled as FK to MasterRoles to reflect your schema.
    """
    id = models.BigAutoField(primary_key=True)
    username = models.CharField(unique=True, max_length=150)
    password = models.CharField(max_length=255)
    recovery_email = models.CharField(max_length=255, blank=True, null=True)
    recovery_mobile = models.CharField(max_length=20, blank=True, null=True)
    pass_attempt_no = models.IntegerField(blank=True, null=True)
    role = models.ForeignKey(MasterRoles,models.DO_NOTHING,db_column='role_id',blank=True,null=True)
    is_active = models.IntegerField(blank=True, null=True)
    last_active_on = models.DateTimeField(blank=True, null=True)
    is_suspended = models.IntegerField(blank=True, null=True)
    suspended_on = models.DateTimeField(blank=True, null=True)
    is_locked = models.IntegerField(blank=True, null=True)
    locked_on = models.DateTimeField(blank=True, null=True)
    pass_updated_at = models.DateTimeField(blank=True, null=True)
    pass_updated_by = models.ForeignKey('self', models.DO_NOTHING, db_column='pass_updated_by', blank=True, null=True)
    TH_urid = models.CharField(db_column='TH_urid', unique=True, max_length=36)  # Field name kept as in DB
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)
    deleted_at = models.DateTimeField(blank=True, null=True)
    created_by = models.ForeignKey('self', models.DO_NOTHING, db_column='created_by', related_name='masteruser_created_by_set', blank=True, null=True)
    updated_by = models.ForeignKey('self', models.DO_NOTHING, db_column='updated_by', related_name='masteruser_updated_by_set', blank=True, null=True)
    deleted_by = models.ForeignKey('self', models.DO_NOTHING, db_column='deleted_by', related_name='masteruser_deleted_by_set', blank=True, null=True)

    class Meta:
        managed = True
        db_table = 'master_user'

    def __str__(self):
        return self.username

    def get_role_name(self):
        """
        Return the role name string for compatibility with the authentication backend.
        """
        try:
            if self.role:
                return self.role.name
        except Exception:
            pass
        return None


# ---------- Geographical / admin units ----------

class MasterState(models.Model):
    state_id = models.IntegerField(primary_key=True)
    state_name_en = models.CharField(max_length=255)
    state_name_hi = models.CharField(max_length=255, blank=True, null=True)
    state_name_local = models.CharField(max_length=255, blank=True, null=True)
    state_short_name_en = models.CharField(max_length=10, blank=True, null=True)
    category = models.PositiveIntegerField(blank=True, null=True)
    lgd_code = models.IntegerField(blank=True, null=True)
    state_code = models.IntegerField(blank=True, null=True)
    kyc_flag = models.IntegerField(blank=True, null=True)
    is_active = models.IntegerField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'master_state'

    def __str__(self):
        return self.state_name_en


class MasterMandal(models.Model):
    id = models.BigAutoField(primary_key=True)
    name = models.CharField(unique=True, max_length=255)
    th_urid = models.CharField(db_column='TH_urid', unique=True, max_length=36)

    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)
    deleted_at = models.DateTimeField(blank=True, null=True)

    created_by = models.ForeignKey(
        MasterUser,
        models.DO_NOTHING,
        db_column='created_by',
        blank=True,
        null=True
    )
    updated_by = models.ForeignKey(
        MasterUser,
        models.DO_NOTHING,
        db_column='updated_by',
        related_name='mastermandal_updated_by_set',
        blank=True,
        null=True
    )
    deleted_by = models.ForeignKey(
        MasterUser,
        models.DO_NOTHING,
        db_column='deleted_by',
        related_name='mastermandal_deleted_by_set',
        blank=True,
        null=True
    )

    class Meta:
        managed = False
        db_table = 'master_mandal'

    def __str__(self):
        return self.name

class MasterDistrictCategory(models.Model):
    id = models.BigAutoField(primary_key=True)
    name = models.CharField(unique=True, max_length=255)
    th_urid = models.CharField(db_column='TH_urid', unique=True, max_length=36)

    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)
    deleted_at = models.DateTimeField(blank=True, null=True)

    created_by = models.ForeignKey(
        MasterUser,
        models.DO_NOTHING,
        db_column='created_by',
        blank=True,
        null=True
    )
    updated_by = models.ForeignKey(
        MasterUser,
        models.DO_NOTHING,
        db_column='updated_by',
        related_name='masterdistrictcategory_updated_by_set',
        blank=True,
        null=True
    )
    deleted_by = models.ForeignKey(
        MasterUser,
        models.DO_NOTHING,
        db_column='deleted_by',
        related_name='masterdistrictcategory_deleted_by_set',
        blank=True,
        null=True
    )

    class Meta:
        managed = False
        db_table = 'master_district_category'

    def __str__(self):
        return self.name

class MasterDistrict(models.Model):
    district_id = models.BigIntegerField(primary_key=True)
    district_code = models.CharField(max_length=50, blank=True, null=True)
    state = models.ForeignKey(MasterState, on_delete=models.DO_NOTHING)
    mandal = models.ForeignKey(
        MasterMandal,
        models.DO_NOTHING,
        db_column='mandal_id',
        blank=True,
        null=True
    )
    district_name_en = models.CharField(max_length=255)
    district_short_name_en = models.CharField(max_length=50, blank=True, null=True)
    district_name_local = models.CharField(max_length=255, blank=True, null=True)
    lgd_code = models.CharField(max_length=50, blank=True, null=True)
    language_id = models.CharField(max_length=20, blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'master_district'

    def __str__(self):
        return self.district_name_en

class MasterDistrictCategoryMapping(models.Model):
    id = models.BigAutoField(primary_key=True)

    district = models.ForeignKey(
        MasterDistrict,
        models.DO_NOTHING,
        db_column='district_id'
    )

    category = models.ForeignKey(
        MasterDistrictCategory,
        models.DO_NOTHING,
        db_column='category_id'
    )

    th_urid = models.CharField(db_column='TH_urid', unique=True, max_length=36)

    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)
    deleted_at = models.DateTimeField(blank=True, null=True)

    created_by = models.ForeignKey(
        MasterUser,
        models.DO_NOTHING,
        db_column='created_by',
        blank=True,
        null=True
    )
    updated_by = models.ForeignKey(
        MasterUser,
        models.DO_NOTHING,
        db_column='updated_by',
        related_name='masterdistrictcategorymapping_updated_by_set',
        blank=True,
        null=True
    )
    deleted_by = models.ForeignKey(
        MasterUser,
        models.DO_NOTHING,
        db_column='deleted_by',
        related_name='masterdistrictcategorymapping_deleted_by_set',
        blank=True,
        null=True
    )

    class Meta:
        managed = False
        db_table = 'master_district_category_mapping'

class MasterBlock(models.Model):
    block_id = models.BigIntegerField(primary_key=True)
    state = models.ForeignKey(MasterState, on_delete=models.DO_NOTHING)
    district = models.ForeignKey(MasterDistrict, on_delete=models.DO_NOTHING)
    block_code = models.CharField(max_length=50, blank=True, null=True)
    block_name_en = models.CharField(max_length=255, blank=True, null=True)
    block_name_local = models.CharField(max_length=255, blank=True, null=True)
    rural_urban_area = models.CharField(max_length=1, blank=True, null=True)
    lgd_code = models.CharField(max_length=50, blank=True, null=True)
    language_id = models.CharField(max_length=20, blank=True, null=True)
    is_aspirational = models.IntegerField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'master_block'

    def __str__(self):
        return self.block_name_en or str(self.block_id)


class MasterPanchayat(models.Model):
    panchayat_id = models.BigIntegerField(primary_key=True)
    state = models.ForeignKey(MasterState, on_delete=models.DO_NOTHING)
    district = models.ForeignKey(MasterDistrict, on_delete=models.DO_NOTHING)
    block = models.ForeignKey(MasterBlock, on_delete=models.DO_NOTHING)
    panchayat_code = models.CharField(max_length=100, blank=True, null=True)
    panchayat_name_en = models.CharField(max_length=255, blank=True, null=True)
    panchayat_name_local = models.CharField(max_length=255, blank=True, null=True)
    rural_urban_area = models.CharField(max_length=1, blank=True, null=True)
    language_id = models.CharField(max_length=20, blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'master_panchayat'

    def __str__(self):
        return self.panchayat_name_en or str(self.panchayat_id)


class MasterVillage(models.Model):
    village_id = models.BigIntegerField(primary_key=True)
    state = models.ForeignKey(MasterState, on_delete=models.DO_NOTHING)
    district = models.ForeignKey(MasterDistrict, on_delete=models.DO_NOTHING)
    block = models.ForeignKey(MasterBlock, on_delete=models.DO_NOTHING)
    panchayat = models.ForeignKey(MasterPanchayat, on_delete=models.DO_NOTHING)
    village_code = models.CharField(max_length=100, blank=True, null=True)
    village_name_english = models.CharField(max_length=255, blank=True, null=True)
    village_name_local = models.CharField(max_length=255, blank=True, null=True)
    rural_urban_area = models.CharField(max_length=1, blank=True, null=True)
    is_active = models.IntegerField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'master_village'

    def __str__(self):
        return self.village_name_english or str(self.village_id)


# ---------- SHG / CLF related ----------

class MasterClfList(models.Model):
    id = models.BigAutoField(primary_key=True)
    clf_code = models.CharField(unique=True, max_length=100)
    code = models.CharField(max_length=100, blank=True, null=True)
    name = models.CharField(max_length=255, blank=True, null=True)
    nic_code = models.CharField(max_length=100, blank=True, null=True)
    block = models.ForeignKey(MasterBlock, on_delete=models.DO_NOTHING, blank=True, null=True)
    district = models.ForeignKey(MasterDistrict, on_delete=models.DO_NOTHING, blank=True, null=True)
    state = models.ForeignKey(MasterState, on_delete=models.DO_NOTHING, blank=True, null=True)
    formation_date = models.DateField(blank=True, null=True)
    is_complete = models.IntegerField(blank=True, null=True)
    pfms_verified = models.IntegerField(blank=True, null=True)
    meeting_frequency = models.CharField(max_length=50, blank=True, null=True)
    registration_act_name = models.CharField(max_length=255, blank=True, null=True)
    registration_date = models.DateField(blank=True, null=True)
    created_by = models.CharField(max_length=100, blank=True, null=True)
    created_date = models.DateTimeField(blank=True, null=True)
    updated_by = models.CharField(max_length=100, blank=True, null=True)
    updated_date = models.DateTimeField(blank=True, null=True)
    guid = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'master_clf_list'

    def __str__(self):
        return self.name or self.clf_code


class MasterClfAddresses(models.Model):
    id = models.BigAutoField(primary_key=True)
    clf_code = models.ForeignKey(MasterClfList, on_delete=models.DO_NOTHING, db_column='clf_code', to_field='clf_code')
    address_line1 = models.CharField(max_length=255, blank=True, null=True)
    address_line2 = models.CharField(max_length=255, blank=True, null=True)
    city_town = models.CharField(max_length=100, blank=True, null=True)
    landmark = models.CharField(max_length=255, blank=True, null=True)
    postal_code = models.CharField(max_length=20, blank=True, null=True)
    state = models.ForeignKey(MasterState, on_delete=models.DO_NOTHING, blank=True, null=True)
    district = models.ForeignKey(MasterDistrict, on_delete=models.DO_NOTHING, blank=True, null=True)
    block = models.ForeignKey(MasterBlock, on_delete=models.DO_NOTHING, blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'master_clf_addresses'


class MasterClfBanks(models.Model):
    id = models.BigAutoField(primary_key=True)
    clf_code = models.ForeignKey(MasterClfList, on_delete=models.DO_NOTHING, db_column='clf_code', to_field='clf_code')
    account_no = models.CharField(max_length=64, blank=True, null=True)
    account_opening_date = models.DateField(blank=True, null=True)
    account_type = models.CharField(max_length=20, blank=True, null=True)
    bank_branch_code = models.CharField(max_length=50, blank=True, null=True)
    bank_branch_name = models.CharField(max_length=255, blank=True, null=True)
    bank_code = models.CharField(max_length=50, blank=True, null=True)
    bank_name = models.CharField(max_length=255, blank=True, null=True)
    ifsc_code = models.CharField(max_length=50, blank=True, null=True)
    is_default = models.IntegerField(blank=True, null=True)
    lokos_account_holder_name = models.CharField(max_length=255, blank=True, null=True)
    pfms_account_holder_name = models.CharField(max_length=255, blank=True, null=True)
    pfms_ifsc_code = models.CharField(max_length=50, blank=True, null=True)
    pfms_vendor_code = models.CharField(max_length=100, blank=True, null=True)
    pfms_verification = models.IntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'master_clf_banks'


class MasterClfPhones(models.Model):
    id = models.BigAutoField(primary_key=True)
    clf_code = models.ForeignKey(MasterClfList, on_delete=models.DO_NOTHING, db_column='clf_code', to_field='clf_code')
    phone_no = models.CharField(max_length=20, blank=True, null=True)
    is_default = models.IntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'master_clf_phones'


class MasterClfVoDetails(models.Model):
    id = models.BigAutoField(primary_key=True)
    clf_code = models.ForeignKey(MasterClfList, on_delete=models.DO_NOTHING, db_column='clf_code', to_field='clf_code')
    vo_code = models.CharField(max_length=100, blank=True, null=True)
    vo_id = models.BigIntegerField(blank=True, null=True)
    vo_name = models.CharField(max_length=255, blank=True, null=True)
    vo_formation_date = models.DateField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'master_clf_vo_details'


# ---------- SHG ----------

class MasterShgList(models.Model):
    id = models.BigAutoField(primary_key=True)
    shg_code = models.CharField(unique=True, max_length=100)
    block = models.ForeignKey(MasterBlock, on_delete=models.DO_NOTHING, blank=True, null=True)
    district = models.ForeignKey(MasterDistrict, on_delete=models.DO_NOTHING, blank=True, null=True)
    panchayat = models.ForeignKey(MasterPanchayat, on_delete=models.DO_NOTHING, blank=True, null=True)
    village = models.ForeignKey(MasterVillage, on_delete=models.DO_NOTHING, blank=True, null=True)
    state = models.ForeignKey(MasterState, on_delete=models.DO_NOTHING, blank=True, null=True)
    name = models.CharField(max_length=255, blank=True, null=True)
    nic_code = models.CharField(max_length=100, blank=True, null=True)
    formation_date = models.DateField(blank=True, null=True)
    is_complete = models.IntegerField(blank=True, null=True)
    pfms_verified = models.IntegerField(blank=True, null=True)
    meeting_frequency = models.CharField(max_length=50, blank=True, null=True)
    latitude = models.DecimalField(max_digits=10, decimal_places=7, blank=True, null=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, blank=True, null=True)
    created_by = models.CharField(max_length=100, blank=True, null=True)
    created_date = models.DateTimeField(blank=True, null=True)
    updated_by = models.CharField(max_length=100, blank=True, null=True)
    updated_date = models.DateTimeField(blank=True, null=True)
    is_active = models.IntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'master_shg_list'

    def __str__(self):
        return self.name or self.shg_code

    @property
    def code(self):
        """
        Backwards-compatible attribute so `obj.code` works even though DB column is `shg_code`.
        """
        return self.shg_code


class MasterShgAddresses(models.Model):
    id = models.BigAutoField(primary_key=True)
    shg_code = models.ForeignKey(MasterShgList, on_delete=models.DO_NOTHING, db_column='shg_code', to_field='shg_code')
    address_line1 = models.CharField(max_length=255, blank=True, null=True)
    address_line2 = models.CharField(max_length=255, blank=True, null=True)
    city_town = models.CharField(max_length=100, blank=True, null=True)
    landmark = models.CharField(max_length=255, blank=True, null=True)
    pincode = models.CharField(max_length=20, blank=True, null=True)
    state_name = models.CharField(max_length=255, blank=True, null=True)
    state = models.ForeignKey(MasterState, on_delete=models.DO_NOTHING, blank=True, null=True)
    district = models.ForeignKey(MasterDistrict, on_delete=models.DO_NOTHING, blank=True, null=True)
    block = models.ForeignKey(MasterBlock, on_delete=models.DO_NOTHING, blank=True, null=True)
    panchayat = models.ForeignKey(MasterPanchayat, on_delete=models.DO_NOTHING, blank=True, null=True)
    village = models.ForeignKey(MasterVillage, on_delete=models.DO_NOTHING, blank=True, null=True)
    village_code = models.CharField(max_length=100, blank=True, null=True)
    lgd_village = models.CharField(max_length=100, blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'master_shg_addresses'


class MasterShgBanks(models.Model):
    id = models.BigAutoField(primary_key=True)
    shg_code = models.ForeignKey(MasterShgList, on_delete=models.DO_NOTHING, db_column='shg_code', to_field='shg_code')
    account_no = models.CharField(max_length=64, blank=True, null=True)
    account_opening_date = models.DateField(blank=True, null=True)
    account_type = models.CharField(max_length=20, blank=True, null=True)
    bank_branch_code = models.CharField(max_length=50, blank=True, null=True)
    bank_branch_name = models.CharField(max_length=255, blank=True, null=True)
    bank_code = models.CharField(max_length=50, blank=True, null=True)
    bank_name = models.CharField(max_length=255, blank=True, null=True)
    ifsc_code = models.CharField(max_length=50, blank=True, null=True)
    is_default = models.IntegerField(blank=True, null=True)
    lokos_account_holder_name = models.CharField(max_length=255, blank=True, null=True)
    pfms_account_holder_name = models.CharField(max_length=255, blank=True, null=True)
    pfms_ifsc_code = models.CharField(max_length=50, blank=True, null=True)
    pfms_vendor_code = models.CharField(max_length=100, blank=True, null=True)
    pfms_verification = models.IntegerField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'master_shg_banks'


class MasterShgPhone(models.Model):
    id = models.BigAutoField(primary_key=True)
    shg_code = models.ForeignKey(MasterShgList, on_delete=models.DO_NOTHING, db_column='shg_code', to_field='shg_code')
    phone_no = models.CharField(max_length=20, blank=True, null=True)
    is_default = models.IntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'master_shg_phone'


# ---------- Beneficiary (members) ----------

class MasterBeneficiary(models.Model):
    member_code = models.CharField(primary_key=True, max_length=100)
    member_id = models.BigIntegerField(unique=True, blank=True, null=True)
    shg_code = models.ForeignKey(MasterShgList, on_delete=models.DO_NOTHING, db_column='shg_code', to_field='shg_code', blank=True, null=True)
    member_guid = models.CharField(max_length=100, blank=True, null=True)
    member_name = models.CharField(max_length=255, blank=True, null=True)
    dob = models.DateField(blank=True, null=True)
    gender = models.CharField(max_length=50, blank=True, null=True)
    joining_date = models.DateField(blank=True, null=True)
    marital_status = models.CharField(max_length=50, blank=True, null=True)
    education = models.CharField(max_length=255, blank=True, null=True)
    father_husband = models.CharField(max_length=255, blank=True, null=True)
    relation_name = models.CharField(max_length=255, blank=True, null=True)
    religion = models.CharField(max_length=100, blank=True, null=True)
    social_category = models.CharField(max_length=50, blank=True, null=True)
    nic_member_code = models.CharField(max_length=100, blank=True, null=True)
    aadhar_verified = models.IntegerField(blank=True, null=True)
    created_by = models.CharField(max_length=100, blank=True, null=True)
    created_date = models.DateTimeField(blank=True, null=True)
    updated_by = models.CharField(max_length=100, blank=True, null=True)
    updated_date = models.DateTimeField(blank=True, null=True)
    token = models.CharField(max_length=255, blank=True, null=True)
    state = models.ForeignKey(MasterState, on_delete=models.DO_NOTHING, blank=True, null=True)
    district = models.ForeignKey(MasterDistrict, on_delete=models.DO_NOTHING, blank=True, null=True)
    block = models.ForeignKey(MasterBlock, on_delete=models.DO_NOTHING, blank=True, null=True)
    panchayat = models.ForeignKey(MasterPanchayat, on_delete=models.DO_NOTHING, blank=True, null=True)
    village = models.ForeignKey(MasterVillage, on_delete=models.DO_NOTHING, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'master_beneficiary'

    def __str__(self):
        return self.member_name or self.member_code


class MasterBeneficiaryAddress(models.Model):
    id = models.BigAutoField(primary_key=True)
    member_code = models.ForeignKey(MasterBeneficiary, on_delete=models.DO_NOTHING, db_column='member_code')
    address_line1 = models.CharField(max_length=255, blank=True, null=True)
    address_line2 = models.CharField(max_length=255, blank=True, null=True)
    address_type = models.CharField(max_length=100, blank=True, null=True)
    city_town = models.CharField(max_length=100, blank=True, null=True)
    landmark = models.CharField(max_length=255, blank=True, null=True)
    postal_code = models.CharField(max_length=20, blank=True, null=True)
    state = models.ForeignKey(MasterState, on_delete=models.DO_NOTHING, blank=True, null=True)
    state_code = models.CharField(max_length=50, blank=True, null=True)
    district = models.ForeignKey(MasterDistrict, on_delete=models.DO_NOTHING, blank=True, null=True)
    block = models.ForeignKey(MasterBlock, on_delete=models.DO_NOTHING, blank=True, null=True)
    panchayat = models.ForeignKey(MasterPanchayat, on_delete=models.DO_NOTHING, blank=True, null=True)
    village = models.ForeignKey(MasterVillage, on_delete=models.DO_NOTHING, blank=True, null=True)
    village_code = models.CharField(max_length=100, blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'master_beneficiary_address'


class MasterBeneficiaryBank(models.Model):
    id = models.BigAutoField(primary_key=True)
    member_code = models.ForeignKey(MasterBeneficiary, on_delete=models.DO_NOTHING, db_column='member_code')
    account_no = models.CharField(max_length=64, blank=True, null=True)
    ifsc_code = models.CharField(max_length=50, blank=True, null=True)
    account_type = models.CharField(max_length=20, blank=True, null=True)
    bank_name = models.CharField(max_length=255, blank=True, null=True)
    is_default = models.IntegerField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'master_beneficiary_bank'


class MasterBeneficiaryDesignation(models.Model):
    id = models.BigAutoField(primary_key=True)
    member_code = models.ForeignKey(MasterBeneficiary, on_delete=models.DO_NOTHING, db_column='member_code')
    designation = models.CharField(max_length=255, blank=True, null=True)
    is_signatory = models.IntegerField(blank=True, null=True)
    member_name = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'master_beneficiary_designation'


class MasterBeneficiaryPhone(models.Model):
    id = models.BigAutoField(primary_key=True)
    member_code = models.ForeignKey(MasterBeneficiary, on_delete=models.DO_NOTHING, db_column='member_code')
    phone_no = models.CharField(max_length=20, blank=True, null=True)
    is_default = models.IntegerField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'master_beneficiary_phone'


class MasterMembersUnderClf(models.Model):
    id = models.BigAutoField(primary_key=True)
    clf_code = models.ForeignKey(MasterClfList, on_delete=models.DO_NOTHING, db_column='clf_code', to_field='clf_code')
    member_code = models.CharField(max_length=100, blank=True, null=True)
    member_name = models.CharField(max_length=255, blank=True, null=True)
    designation = models.CharField(max_length=255, blank=True, null=True)
    is_signatory = models.IntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'master_members_under_clf'


class MasterPanchayatsUnderClf(models.Model):
    id = models.BigAutoField(primary_key=True)
    clf_code = models.ForeignKey(MasterClfList, on_delete=models.DO_NOTHING, db_column='clf_code', to_field='clf_code')
    panchayat = models.ForeignKey(MasterPanchayat, on_delete=models.DO_NOTHING, blank=True, null=True)
    panchayat_code = models.CharField(max_length=100, blank=True, null=True)
    panchayat_name = models.CharField(max_length=255, blank=True, null=True)
    lgd_gp = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'master_panchayats_under_clf'


class MasterVillagesUnderClf(models.Model):
    id = models.BigAutoField(primary_key=True)
    clf_code = models.ForeignKey(MasterClfList, on_delete=models.DO_NOTHING, db_column='clf_code', to_field='clf_code')
    panchayat = models.ForeignKey(MasterPanchayat, on_delete=models.DO_NOTHING, blank=True, null=True)
    village = models.ForeignKey(MasterVillage, on_delete=models.DO_NOTHING, blank=True, null=True)
    village_code = models.CharField(max_length=100, blank=True, null=True)
    village_name = models.CharField(max_length=255, blank=True, null=True)
    lgd_village = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'master_villages_under_clf'


# ---------- NEW: Geo user scope mapping table ----------
class MasterGeoUserScope(models.Model):
    """
    Maps master_user.id to block_id and/or district_id.
    - user_id: FK to master_user.id (but keep as BigIntegerField to keep read-only/mapping simple)
    - block_id, district_id reference master_block.master_block_id and master_district.district_id respectively.
    """
    id = models.BigAutoField(primary_key=True)
    user_id = models.BigIntegerField(db_index=True)
    block_id = models.BigIntegerField(blank=True, null=True, db_index=True)
    district_id = models.BigIntegerField(blank=True, null=True, db_index=True)
    is_active = models.IntegerField(blank=True, null=True)
    created_by = models.BigIntegerField(blank=True, null=True)
    updated_by = models.BigIntegerField(blank=True, null=True)
    deleted_by = models.BigIntegerField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)
    deleted_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'master_geouserscope'

    def __str__(self):
        return f'GeoScope(user_id={self.user_id}, block={self.block_id}, district={self.district_id})'
