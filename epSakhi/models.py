# epSakhi/models.py
import uuid
import random
import string
from django.db import models
from django.utils import timezone
from core.models import MasterUser


def generate_custom_th_urid():
    # Example generator for format like: TH_1AN33KN221 (prefix TH_ + 11 alnum)
    body = ''.join(random.choices(string.ascii_uppercase + string.digits, k=11))
    return f"TH_{body}"


class SoftDeleteMixin(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_column='created_at')
    updated_at = models.DateTimeField(auto_now=True, db_column='updated_at')
    deleted_at = models.DateTimeField(null=True, blank=True, db_column='deleted_at')
    created_by = models.ForeignKey(
        'core.MasterUser', null=True, blank=True, on_delete=models.SET_NULL,
        db_column='created_by', related_name='+', db_constraint=False)
    updated_by = models.ForeignKey(
        'core.MasterUser', null=True, blank=True, on_delete=models.SET_NULL,
        db_column='updated_by', related_name='+', db_constraint=False)
    deleted_by = models.ForeignKey(
        'core.MasterUser', null=True, blank=True, on_delete=models.SET_NULL,
        db_column='deleted_by', related_name='+', db_constraint=False)
    is_active = models.BooleanField(default=True, db_column='is_active')

    TH_urid = models.CharField(max_length=36, default=generate_custom_th_urid, editable=False, db_column='TH_urid')

    class Meta:
        abstract = True

    def delete(self, using=None, keep_parents=False, by_user: MasterUser = None):
        self.deleted_at = timezone.now()
        self.is_active = False
        if by_user is not None:
            try:
                if isinstance(by_user, MasterUser):
                    self.deleted_by = by_user
                else:
                    self.deleted_by_id = int(by_user)
            except Exception:
                pass
        self.save()

    def hard_delete(self):
        super().delete()


# -------------------------
# CRP Data
# -------------------------
class CRPEP(SoftDeleteMixin):
    id = models.BigAutoField(primary_key=True)

    district_id = models.BigIntegerField(null=True, blank=True, db_column='district_id', db_index=True)
    block_id = models.BigIntegerField(null=True, blank=True, db_column='block_id', db_index=True)
    panchayat_id = models.BigIntegerField(null=True, blank=True, db_column='panchayat_id', db_index=True)

    master_user = models.ForeignKey(
        'core.MasterUser', on_delete=models.PROTECT, db_column='user_id',
        related_name='crpep_account', null=True, blank=True, db_constraint=False)

    name = models.CharField(max_length=255)

    lokos_shg_code = models.CharField(max_length=100, null=True, blank=True, db_column='lokos_shg_code')
    nodal_clf = models.BigIntegerField(null=True, blank=True, db_column='nodal_clf')
    lokos_member_code = models.CharField(max_length=100, null=True, blank=True, db_column='lokos_member_code')

    category = models.CharField(max_length=255, null=True, blank=True)
    subcategory = models.CharField(max_length=100, null=True, blank=True)
    marks_obtained = models.IntegerField(null=True, blank=True)
    mobile_number = models.CharField(max_length=20, null=True, blank=True)

    class Meta:
        db_table = 'epSakhi_crpep'

    def __str__(self):
        return f"{self.id} - {self.name}"


class CRPEPToPanchayat(SoftDeleteMixin):
    id = models.BigAutoField(primary_key=True)
    crp = models.ForeignKey(CRPEP, on_delete=models.CASCADE, db_column='crp_id', db_constraint=False)
    allocated_panchayat_id = models.BigIntegerField()

    class Meta:
        db_table = 'epSakhi_crpep_panchayat'

    def __str__(self):
        return f"{self.crp_id} -> {self.allocated_panchayat_id}"


# -------------------------
# BeneficiaryRecorded (epSakhi_recorBenefs)
# -------------------------
class BeneficiaryRecorded(SoftDeleteMixin):
    class Meta:
        db_table = 'epSakhi_recorBenefs'

    TH_urid = models.CharField(
        max_length=36,
        primary_key=True,
        default=generate_custom_th_urid,
        editable=False,
        db_column='TH_urid',
    )

    lokos_member_code = models.CharField(max_length=100, db_column='lokos_member_code')
    applicant_name = models.CharField(max_length=255)
    age = models.PositiveIntegerField(null=True, blank=True)
    gender = models.CharField(max_length=50, null=True, blank=True)
    marital_status = models.CharField(max_length=50, null=True, blank=True)
    father_husband_name = models.CharField(max_length=255, null=True, blank=True)
    category = models.CharField(max_length=255, null=True, blank=True)
    pld_status = models.CharField(max_length=255, null=True, blank=True)

    enterprise_type = models.CharField(max_length=255, null=True, blank=True)
    special_category = models.CharField(max_length=255, null=True, blank=True)

    education = models.CharField(max_length=255, null=True, blank=True)
    address = models.TextField(null=True, blank=True)

    district_id = models.BigIntegerField(db_index=True, null=True, blank=True)
    block_id = models.BigIntegerField(db_index=True, null=True, blank=True)
    panchayat_id = models.BigIntegerField(db_index=True, null=True, blank=True)
    village_id = models.BigIntegerField(db_index=True, null=True, blank=True)

    mobile = models.CharField(max_length=20, null=True, blank=True)
    email = models.EmailField(null=True, blank=True)
    lokos_shg_code = models.CharField(max_length=100, null=True, blank=True)

    enterprise_id = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text='TH_urid of enterprise form (existing or new)',
    )

    def __str__(self):
        return f"{self.lokos_member_code} - {self.applicant_name}"


# -------------------------
# ExistingEnterprise + related tables
# -------------------------
class ExistingEnterprise(SoftDeleteMixin):
    """
    epSakhi_existingEpForm
    """
    TH_urid = models.CharField(
        max_length=36,
        primary_key=True,
        default=generate_custom_th_urid,
        editable=False,
        db_column='TH_urid',
    )
    recorded_benef_id = models.CharField(max_length=36, db_column='recorded_benef_id')

    enterprise_name = models.CharField(max_length=255)
    uddyam_aadhar = models.CharField(max_length=255, null=True, blank=True)
    ownership_type = models.CharField(max_length=255, null=True, blank=True)
    owner_special_category = models.CharField(max_length=255, null=True, blank=True)
    year_of_establishment = models.IntegerField(null=True, blank=True)
    total_emp = models.IntegerField(null=True, blank=True)
    number_of_shg_emp = models.IntegerField(null=True, blank=True)

    workplace_type = models.CharField(max_length=255, null=True, blank=True)
    electricity_available = models.CharField(max_length=255, null=True, blank=True)
    water_available = models.CharField(max_length=255, null=True, blank=True)
    transportation_availability = models.CharField(max_length=255, null=True, blank=True)
    can_send_to_bijnor = models.BooleanField(default=False)
    need_transport_help = models.CharField(max_length=255, null=True, blank=True)

    monthly_income_estimate = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    annual_turnover = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    gross_profit = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    working_capital_monthly = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    has_shg_cif = models.BooleanField(default=False)
    cif_fund_amt = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    initial_investment = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    source_of_investment = models.CharField(max_length=255, null=True, blank=True)
    has_taken_loan = models.BooleanField(default=False)
    has_receieved_subsidy = models.BooleanField(default=False)

    is_training_received = models.BooleanField(default=False)
    expansion_plan = models.TextField(null=True, blank=True)
    info_abt_gov_scheme = models.TextField(null=True, blank=True)

    is_training_required = models.BooleanField(default=False)
    nearest_skill_centre = models.CharField(max_length=255, null=True, blank=True)
    skill_centre_loc = models.CharField(max_length=255, null=True, blank=True)
    nearest_industry = models.CharField(max_length=255, null=True, blank=True)
    industry_loc = models.CharField(max_length=255, null=True, blank=True)
    mentorship_support = models.CharField(max_length=255, null=True, blank=True)
    market_branding_support = models.CharField(max_length=255, null=True, blank=True)
    infrastructure_support = models.CharField(max_length=255, null=True, blank=True)
    digital_emarket_support = models.CharField(max_length=255, null=True, blank=True)
    is_promo_ad_req = models.CharField(max_length=255, null=True, blank=True)
    is_equip_req = models.CharField(max_length=255, null=True, blank=True)
    other_support = models.TextField(null=True, blank=True)

    declaration_confirmed = models.BooleanField(default=False)
    declaration_date = models.DateField(null=True, blank=True)
    verifier_name = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        db_table = 'epSakhi_existingEpForm'

    def __str__(self):
        return f"{self.enterprise_name} ({self.TH_urid})"


class EnterpriseLoanDetail(SoftDeleteMixin):
    """
    epSakhi_epLoanDeets
    """
    TH_urid = models.CharField(
        max_length=36,
        primary_key=True,
        default=generate_custom_th_urid,
        editable=False,
        db_column='TH_urid',
    )
    enterprise_id = models.CharField(
        max_length=36,
        db_column='enterprise_id',
        help_text='TH_urid of enterprise form (existing/new)',
    )

    # NEW: to distinguish existing vs new etc.
    form_type = models.CharField(max_length=20, null=True, blank=True, help_text='existing/new/other')

    institution_name = models.CharField(max_length=255, null=True, blank=True)
    loan_amount = models.CharField(max_length=255, null=True, blank=True)
    date_taken = models.DateField(null=True, blank=True)
    repayment_status = models.CharField(max_length=100, null=True, blank=True)

    class Meta:
        db_table = 'epSakhi_epLoanDeets'


class EnterpriseSubsidyDetail(SoftDeleteMixin):    
    TH_urid = models.CharField(
        max_length=36,
        primary_key=True,
        default=generate_custom_th_urid,
        editable=False,
        db_column='TH_urid',
    )
    enterprise_id = models.CharField(
        max_length=36,
        db_column='enterprise_id',
        help_text='TH_urid of enterprise form (existing/new)',
    )
    
    subsidy_type = models.CharField(max_length=255, null=True, blank=True)
    subsidy_name = models.CharField(max_length=255, null=True, blank=True)
    subsidy_detail = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'epSakhi_exEpSubsidy'


class EnterpriseTrainingReq(SoftDeleteMixin):

    TH_urid = models.CharField(
        max_length=36,
        primary_key=True,
        default=generate_custom_th_urid,
        editable=False,
        db_column='TH_urid',
    )
    enterprise_id = models.CharField(
        max_length=36,
        db_column='enterprise_id',
        help_text='TH_urid of enterprise form (existing/new)',
    )

    form_type = models.CharField(max_length=20, null=True, blank=True, help_text='existing/new/other')
    training_module_name = models.TextField(null=True, blank=True, help_text='Parent: Child for sectors')
    sector = models.CharField(max_length=255, null=True, blank=True)
    department = models.CharField(max_length=255, null=True, blank=True)
    duration = models.CharField(max_length=100, null=True, blank=True)
    location = models.CharField(max_length=255, null=True, blank=True)
    expected_income = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        db_table = 'epSakhi_epTraining'


class EnterpriseMedia(SoftDeleteMixin):
    TH_urid = models.CharField(
        max_length=36,
        primary_key=True,
        default=generate_custom_th_urid,
        editable=False,
        db_column='TH_urid',
    )
    enterprise_id = models.CharField(
        max_length=36,
        db_column='enterprise_id',
        help_text='TH_urid of enterprise form (existing/new)',
    )

    # NEW: to distinguish existing vs new etc.
    form_type = models.CharField(max_length=20, null=True, blank=True, help_text='existing/new/other')

    photo_entrepreneur = models.ImageField(upload_to='epSakhi/media/%Y/%m/', null=True, blank=True)
    photo_enterprise = models.ImageField(upload_to='epSakhi/media/%Y/%m/', null=True, blank=True)
    open_box_photo = models.ImageField(upload_to='epSakhi/media/%Y/%m/', null=True, blank=True)
    close_box_photo = models.ImageField(upload_to='epSakhi/media/%Y/%m/', null=True, blank=True)
    others = models.ImageField(upload_to='epSakhi/media/%Y/%m/', null=True, blank=True)
    certificates = models.FileField(upload_to='epSakhi/media/%Y/%m/', null=True, blank=True)

    class Meta:
        db_table = 'epSakhi_epMedia'


# -------------------------
# NewEnterprise (epSakhi_newEpForm)
# -------------------------
class NewEnterprise(SoftDeleteMixin):
    TH_urid = models.CharField(
        max_length=36,
        primary_key=True,
        default=generate_custom_th_urid,
        editable=False,
        db_column='TH_urid',
    )
    recorded_benef_id = models.CharField(max_length=36, db_column='recorded_benef_id')

    applicant_special_category = models.CharField(max_length=255, null=True, blank=True)
    prefered_location = models.CharField(max_length=255, null=True, blank=True)
    has_shg_cif = models.BooleanField(default=False)
    cif_fund_amt = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)

    is_training_received = models.BooleanField(default=False)
    is_training_required = models.BooleanField(default=False)

    nearest_skill_centre = models.CharField(max_length=255, null=True, blank=True)
    skill_centre_loc = models.CharField(max_length=255, null=True, blank=True)
    nearest_industry = models.CharField(max_length=255, null=True, blank=True)
    industry_loc = models.CharField(max_length=255, null=True, blank=True)

    mentorship_support = models.CharField(max_length=255, null=True, blank=True)
    financial_support = models.CharField(max_length=255, null=True, blank=True)
    loan_amount = models.CharField(max_length=255, null=True, blank=True)

    market_linkage_type = models.CharField(max_length=255, null=True, blank=True)
    market_linkage_detail = models.TextField(null=True, blank=True)

    is_promo_ad_req_type = models.CharField(max_length=255, null=True, blank=True)
    is_promo_ad_req_detail = models.TextField(null=True, blank=True)

    infrastructure_support_type = models.CharField(max_length=255, null=True, blank=True)
    infrastructure_support_detail = models.TextField(null=True, blank=True)

    digital_emarket_support = models.BooleanField(default=False)
    other_support = models.TextField(null=True, blank=True)

    declaration_confirmed = models.BooleanField(default=False)
    declaration_date = models.DateField(null=True, blank=True)
    applicant_signature = models.ImageField(upload_to='epSakhi/new_enterprise/%Y/%m/', null=True, blank=True)

    class Meta:
        db_table = 'epSakhi_newEpForm'

    def __str__(self):
        return f"NewEnterprise {self.TH_urid}"


# -------------------------
# NEW: Existing Enterprise Product table (epSakhi_exEpProduct)
# -------------------------
class EnterpriseProduct(SoftDeleteMixin):
    """
    epSakhi_exEpProduct
    Stores product/market details for an enterprise (Existing/New).
    enterprise_id holds the TH_urid of the Enterprise form (no FK).
    """
    TH_urid = models.CharField(
        max_length=36,
        primary_key=True,
        default=generate_custom_th_urid,
        editable=False,
        db_column='TH_urid',
    )
    enterprise_id = models.CharField(
        max_length=36,
        db_column='enterprise_id',
        help_text='TH_urid of enterprise form (existing/new)',
    )

    main_product_name = models.CharField(max_length=255, null=True, blank=True)
    activity_or_product_type = models.CharField(max_length=255, null=True, blank=True)
    product_features = models.TextField(null=True, blank=True)
    production_capacity = models.CharField(max_length=255, null=True, blank=True)
    raw_material = models.TextField(null=True, blank=True)
    machinery_equipment = models.TextField(null=True, blank=True)

    sales_area = models.CharField(max_length=255, null=True, blank=True)
    target_customers = models.TextField(null=True, blank=True)
    packaging_branding_status = models.CharField(max_length=255, null=True, blank=True)

    marketing_strategy = models.TextField(null=True, blank=True)
    marketing_channels = models.TextField(null=True, blank=True)
    marketing_challenges = models.TextField(null=True, blank=True)
    market_linkage = models.TextField(null=True, blank=True)

    accept_digital_payment = models.BooleanField(default=False)
    avg_monthly_sales = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)

    class Meta:
        db_table = 'epSakhi_exEpProduct'


# -------------------------
# NEW: Enterprise Type categorisation (epSakhi_epType)
# -------------------------
class EnterpriseTypeCategory(SoftDeleteMixin):
    """
    epSakhi_epType
    Stores parent/sub category for an enterprise.
    """
    TH_urid = models.CharField(
        max_length=36,
        primary_key=True,
        default=generate_custom_th_urid,
        editable=False,
        db_column='TH_urid',
    )
    form_type = models.CharField(max_length=20, null=True, blank=True, help_text='existing/new/none')
    enterprise_id = models.CharField(
        max_length=36,
        db_column='enterprise_id',
        help_text='TH_urid of enterprise form (existing/new)',
    )
    parent_category = models.TextField(null=True, blank=True)
    sub_category = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'epSakhi_epType'


# -------------------------
# NEW: No Enterprise Form table (epSakhi_noEpForm)
# -------------------------
class NoEnterpriseForm(SoftDeleteMixin):
    """
    epSakhi_noEpForm
    For beneficiaries not interested in opening an enterprise.
    """
    TH_urid = models.CharField(
        max_length=36,
        primary_key=True,
        default=generate_custom_th_urid,
        editable=False,
        db_column='TH_urid',
    )
    recorded_benef_id = models.CharField(max_length=36, db_column='recorded_benef_id')

    if_shg_member_inv = models.TextField(null=True, blank=True, help_text='Is SHG member involved in any EP/wage activity')
    no_int_reason = models.TextField(null=True, blank=True)
    is_training_required = models.BooleanField(default=False)
    future_willing = models.BooleanField(default=False)

    has_shg_cif = models.BooleanField(default=False)
    cif_fund_amt = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)

    class Meta:
        db_table = 'epSakhi_noEpForm'


# -------------------------
# NEW: No Enterprise Wage/placement table (epSakhi_noEpWage)
# -------------------------
class NoEnterpriseWage(SoftDeleteMixin):
    """
    epSakhi_noEpWage
    Wage / placement preferences when not opening an enterprise.
    """
    TH_urid = models.CharField(
        max_length=36,
        primary_key=True,
        default=generate_custom_th_urid,
        editable=False,
        db_column='TH_urid',
    )
    enterprise_id = models.CharField(
        max_length=36,
        db_column='enterprise_id',
        help_text='Link to TH_urid (could be NoEnterpriseForm / other form as per design)',
    )

    placement_sector = models.CharField(max_length=255, null=True, blank=True)
    type_of_emp = models.CharField(max_length=255, null=True, blank=True)
    exp_salary = models.CharField(max_length=255, null=True, blank=True)
    location_scope = models.CharField(max_length=255, null=True, blank=True)
    location = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        db_table = 'epSakhi_noEpWage'
