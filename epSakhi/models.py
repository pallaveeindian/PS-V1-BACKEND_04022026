# epSakhi/models.py
import uuid
import random
import string
from django.db import models
from django.utils import timezone
from core.models import MasterUser, MasterDistrict, MasterBlock, MasterPanchayat, MasterVillage

def generate_custom_th_urid():
    return f"TH_{uuid.uuid4().hex[:12].upper()}"

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

    TH_urid = models.CharField(
        max_length=36,
        unique=True,
        db_index=True,
        default=generate_custom_th_urid,
        editable=False,
        db_column='TH_urid'
    )

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

    district = models.ForeignKey(
        MasterDistrict,
        on_delete=models.PROTECT,
        db_column='district_id',
        db_constraint=False,
        null=True,
        blank=True,
    )
    
    block = models.ForeignKey(
        MasterBlock,
        on_delete=models.PROTECT,
        db_column='block_id',
        db_constraint=False,
        null=True,
        blank=True,
    )

    panchayat = models.ForeignKey(
        MasterPanchayat,
        on_delete=models.PROTECT,
        db_column='panchayat_id',
        db_constraint=False,
        null=True,
        blank=True,
    )

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
        managed = False

    def __str__(self):
        return f"{self.id} - {self.name}"

class CRPEPToPanchayat(SoftDeleteMixin):
    id = models.BigAutoField(primary_key=True)
    crp = models.ForeignKey(
        MasterUser,
        on_delete=models.CASCADE,
        db_column='crp_id',
        db_constraint=False
    )
    allocated_panchayat_id = models.BigIntegerField()

    class Meta:
        db_table = 'epSakhi_crpep_panchayat'
        managed = False

    def __str__(self):
        return f"{self.crp_id} -> {self.allocated_panchayat_id}"

# ---------------------------------------------
# BeneficiaryRecorded (epSakhi_recorBenefs)
# ---------------------------------------------
class BeneficiaryRecorded(SoftDeleteMixin):
    class Meta:
        db_table = 'epSakhi_recorBenefs'
            
    id = models.BigAutoField(primary_key=True)

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

    district_id = models.ForeignKey(
        MasterDistrict,
        on_delete=models.PROTECT,
        db_column='district_id',
        db_constraint=False,
        null=True,
        blank=True,
        related_name='beneficiaries'
    )

    block_id= models.ForeignKey(
        MasterBlock,
        on_delete=models.PROTECT,
        db_column='block_id',
        db_constraint=False,
        null=True,
        blank=True,
        related_name='beneficiaries'
    )

    panchayat_id = models.ForeignKey(
        MasterPanchayat,
        on_delete=models.PROTECT,
        db_column='panchayat_id',
        db_constraint=False,
        null=True,
        blank=True,
        related_name='beneficiaries'
    )

    village_id = models.ForeignKey(
        MasterVillage,
        on_delete=models.PROTECT,
        db_column='village_id',
        db_constraint=False,
        null=True,
        blank=True,
        related_name='beneficiaries'
    )

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

# --------------------------------------
# ExistingEnterprise + related tables
# --------------------------------------
class ExistingEnterprise(SoftDeleteMixin):
    """
    epSakhi_existingEpForm
    """
    id = models.BigAutoField(primary_key=True)
    recorded_benef_id = models.ForeignKey(
        BeneficiaryRecorded,
        on_delete=models.CASCADE,
        related_name='exep_recorded_benef',
        blank=True,
        null=True,
    ) 
    
    # 1) Basic Information Section
    enterprise_name = models.CharField(max_length=255)
    ownership_type = models.CharField(max_length=255, null=True, blank=True)
    owner_cadre = models.CharField(max_length=255, null=True, blank=True)
    owner_designation = models.CharField(max_length=255, null=True, blank=True)
    owner_special_category = models.CharField(max_length=255, null=True, blank=True)
    
    # 2) Enterprise Details Section
    year_of_establishment = models.IntegerField(null=True, blank=True)
    total_emp = models.IntegerField(null=True, blank=True)
    number_of_shg_emp = models.IntegerField(null=True, blank=True)
    workplace_type = models.CharField(max_length=255, null=True, blank=True)
    electricity_available = models.CharField(max_length=255, null=True, blank=True)
    water_available = models.CharField(max_length=255, null=True, blank=True)
    transportation_availability = models.CharField(max_length=255, null=True, blank=True)
    can_send_to_bijnor = models.BooleanField(default=False)
    need_transport_help = models.CharField(max_length=255, null=True, blank=True)

    # 3) Product Section
    have_shop_based_prod = models.BooleanField(default=False)

    # 4) Investment Section
    monthly_income_estimate = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    annual_turnover = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    gross_profit = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    working_capital_monthly = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    initial_investment = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    source_of_investment = models.TextField(null=True, blank=True)
    
    # 5) Loan/Subsidy Section
    has_taken_loan = models.BooleanField(default=False)
    has_receieved_subsidy = models.BooleanField(default=False)
    has_shg_receieved_man_fund = models.BooleanField(default=False)

    # 6) Training Section
    is_training_received = models.BooleanField(default=False)
    expansion_plan = models.TextField(null=True, blank=True)
    info_abt_gov_scheme = models.TextField(null=True, blank=True)
    is_training_required = models.BooleanField(default=False)
    nearest_skill_centre = models.CharField(max_length=255, null=True, blank=True)
    skill_centre_loc = models.CharField(max_length=255, null=True, blank=True)
    nearest_industry = models.CharField(max_length=255, null=True, blank=True)
    industry_loc = models.CharField(max_length=255, null=True, blank=True)
    
    # 7) Support Section
    is_support_required = models.CharField(max_length=255, null=True, blank=True)

    # 8) Enterprise Media

    # 9) Declaration Section
    declaration_confirmed = models.BooleanField(default=False)
    declaration_date = models.DateField(null=True, blank=True)
    verifier_name = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        db_table = 'epSakhi_existingEpForm'

    def __str__(self):
        return f"{self.enterprise_name} ({self.id})"

class EnterpriseLicenses(SoftDeleteMixin):
    """
    epSakhi_epLicenses
    """    
    id = models.BigAutoField(primary_key=True)
    
    enterprise_id = models.ForeignKey(
        ExistingEnterprise,
        on_delete=models.CASCADE,
        related_name='exep_licenses',
        blank=True,
        null=True,
    )  
    license_category = models.CharField(max_length=255, null=True, blank=True)
    license_name = models.CharField(max_length=255, null=True, blank=True)
    license_no = models.CharField(max_length=255, null=True, blank=True)
    license_file = models.FileField(upload_to='epSakhi/media/licenses/%Y/%m/', null=True, blank=True)
    
    class Meta:
        db_table = 'epSakhi_epLicenses'    

class EnterpriseLoanDetail(SoftDeleteMixin):
    """
    epSakhi_epLoanDeets
    """
    id = models.BigAutoField(primary_key=True)
    
    enterprise_id = models.ForeignKey(
        ExistingEnterprise,
        on_delete=models.CASCADE,
        related_name='exep_loan',
        blank=True,
        null=True,
    )  

    form_type = models.CharField(max_length=20, null=True, blank=True, help_text='existing/new/other')
    department = models.CharField(max_length=255, null=True, blank=True)
    institution_name = models.CharField(max_length=255, null=True, blank=True)
    bank_name = models.CharField(max_length=255, null=True, blank=True)
    bank_branch = models.CharField(max_length=255, null=True, blank=True)
    loan_amount = models.CharField(max_length=255, null=True, blank=True)
    repaid_amount = models.CharField(max_length=255, null=True, blank=True)
    date_taken = models.DateField(null=True, blank=True)
    repayment_status = models.CharField(max_length=100, null=True, blank=True)

    class Meta:
        db_table = 'epSakhi_epLoanDeets'

class EnterpriseSubsidyDetail(SoftDeleteMixin):    
    id = models.BigAutoField(primary_key=True)
    
    enterprise_id = models.ForeignKey(
        ExistingEnterprise,
        on_delete=models.CASCADE,
        related_name='exep_subsidy',
        blank=True,
        null=True,
    )  
    
    subsidy_type = models.CharField(max_length=255, null=True, blank=True)
    subsidy_name = models.CharField(max_length=255, null=True, blank=True)
    subsidy_detail = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'epSakhi_exEpSubsidy'

# Shop Based 'YES': Existing Enterprise Shop table
class EnterpriseShop(SoftDeleteMixin):
    """
    epSakhi_exEpShop
    Stores shop details for an enterprise (Existing).
    enterprise_id holds the TH_urid of the Enterprise form (no FK).
    """
    id = models.BigAutoField(primary_key=True)
    
    enterprise_id = models.ForeignKey(
        ExistingEnterprise,
        on_delete=models.CASCADE,
        related_name='exep_shop_media',
        blank=True,
        null=True,
    )  
    shop_category = models.CharField(max_length=255, null=True, blank=True)
    shop_type = models.CharField(max_length=255, null=True, blank=True)
    source_of_inventory = models.CharField(max_length=255, null=True, blank=True)
    
    # Migrate from EnterpriseProduct
    target_customers = models.TextField(null=True, blank=True)
    sales_area = models.CharField(max_length=255, null=True, blank=True)
    marketing_strategy = models.TextField(null=True, blank=True)
    marketing_channels = models.TextField(null=True, blank=True)
    marketing_challenges = models.TextField(null=True, blank=True)
    market_linkage = models.TextField(null=True, blank=True)

    accept_digital_payment = models.BooleanField(default=False)
    
    avg_monthly_sales = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    avg_annual_sales = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)  

    class Meta:
        db_table = 'epSakhi_exEpShop'    
    
class ShopMedia(SoftDeleteMixin):
    id = models.BigAutoField(primary_key=True)

    product_id = models.ForeignKey(
        EnterpriseShop,
        on_delete=models.CASCADE,
        related_name='shop_media',
        blank=True,
        null=True,
    )   
    front_photo = models.ImageField(upload_to='epSakhi/media/shop/%Y/%m/', null=True, blank=True)
    inside_photo = models.ImageField(upload_to='epSakhi/media/shop/%Y/%m/', null=True, blank=True)
    others = models.ImageField(upload_to='epSakhi/media/shop/%Y/%m/', null=True, blank=True)    

    class Meta:
        db_table = 'epSakhi_epShopMedia'        
    
# Shop Based 'NO': Existing Enterprise Product table
class EnterpriseProduct(SoftDeleteMixin):
    """
    epSakhi_exEpProduct
    Stores product/market details for an enterprise (Existing/New).
    enterprise_id holds the TH_urid of the Enterprise form (no FK).
    """
    id = models.BigAutoField(primary_key=True)
    
    enterprise_id = models.ForeignKey(
        ExistingEnterprise,
        on_delete=models.CASCADE,
        related_name='exep_prod_media',
        blank=True,
        null=True,
    )  

    main_product_name = models.CharField(max_length=255, null=True, blank=True)
    activity_or_product_type = models.CharField(max_length=255, null=True, blank=True)
    product_features = models.TextField(null=True, blank=True)
    production_capacity = models.CharField(max_length=255, null=True, blank=True)
    raw_material = models.TextField(null=True, blank=True)
    raw_material_source = models.TextField(null=True, blank=True)
    machinery_equipment = models.TextField(null=True, blank=True)
    source_machinery = models.TextField(null=True, blank=True)
    product_mrp = models.CharField(max_length=255, null=True, blank=True)

    sales_area = models.CharField(max_length=255, null=True, blank=True)
    target_customers = models.TextField(null=True, blank=True)
    packaging_branding_status = models.CharField(max_length=255, null=True, blank=True)

    marketing_strategy = models.TextField(null=True, blank=True)
    marketing_channels = models.TextField(null=True, blank=True)
    marketing_challenges = models.TextField(null=True, blank=True)
    market_linkage = models.TextField(null=True, blank=True)

    accept_digital_payment = models.BooleanField(default=False)
    
    avg_monthly_sales = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    avg_annual_sales = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)

    class Meta:
        db_table = 'epSakhi_exEpProduct'

class ProductMedia(SoftDeleteMixin):
    id = models.BigAutoField(primary_key=True)

    product_id = models.ForeignKey(
        EnterpriseProduct,
        on_delete=models.CASCADE,
        related_name='prod_media',
        blank=True,
        null=True,
    )   
    open_box_photo = models.ImageField(upload_to='epSakhi/media/products/%Y/%m/', null=True, blank=True)
    close_box_photo = models.ImageField(upload_to='epSakhi/media/products/%Y/%m/', null=True, blank=True)
    others = models.ImageField(upload_to='epSakhi/media/product/%Y/%m/', null=True, blank=True)    

    class Meta:
        db_table = 'epSakhi_epProdMedia'

# Existing Enterprise Media
class EnterpriseMedia(SoftDeleteMixin):
    id = models.BigAutoField(primary_key=True)
    
    enterprise_id = models.ForeignKey(
        ExistingEnterprise,
        on_delete=models.CASCADE,
        related_name='exep_media',
        blank=True,
        null=True,
    )  

    photo_entrepreneur = models.ImageField(upload_to='epSakhi/media/exep/entrepreneur/%Y/%m/', null=True, blank=True)
    photo_enterprise = models.ImageField(upload_to='epSakhi/media/exep/enterprise/%Y/%m/', null=True, blank=True)
    others = models.ImageField(upload_to='epSakhi/media/exep/others/%Y/%m/', null=True, blank=True)
    
    class Meta:
        db_table = 'epSakhi_exepMedia'

# Shared classes (exep + newep)
class EnterpriseTypeCategory(SoftDeleteMixin):
    """
    epSakhi_epType
    Stores parent/sub category for an enterprise.
    """
    id = models.BigAutoField(primary_key=True)
    
    form_type = models.CharField(max_length=20, null=True, blank=True, help_text='existing/new')
    enterprise_id = models.CharField(
        max_length=36,
        db_column='enterprise_id',
        help_text='TH_urid of enterprise form (existing/new)',
    )
    parent_category = models.TextField(null=True, blank=True)
    sub_category = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'epSakhi_epType'

class EnterpriseSupport(SoftDeleteMixin):
    """
    epSakhi_epSupport
    """    
    id = models.BigAutoField(primary_key=True)
    
    enterprise_id = models.CharField(
        max_length=36,
        db_column='enterprise_id',
        help_text='TH_urid of enterprise form (existing/new)',
    )     
    form_type = models.CharField(max_length=20, null=True, blank=True, help_text='existing/new')
    support_category = models.CharField(max_length=255, null=True, blank=True)
    support_sub_category = models.CharField(max_length=255, null=True, blank=True)
    support_description = models.CharField(max_length=255, null=True, blank=True)
    other_support = models.CharField(max_length=255, null=True, blank=True)
    
    class Meta:
        db_table = 'epSakhi_epSupport'
        
class EnterpriseMandatoryFund(SoftDeleteMixin):
    """
    epSakhi_epManFund
    """    
    id = models.BigAutoField(primary_key=True)
    
    enterprise_id = models.CharField(
        max_length=36,
        db_column='enterprise_id',
        help_text='TH_urid of enterprise form (existing/new)',
    )            
    form_type = models.CharField(max_length=20, null=True, blank=True, help_text='existing/new')
    fund_type = models.CharField(max_length=255, null=True, blank=True)
    have_received_part = models.BooleanField(default=False)
    amount_received = models.CharField(max_length=255, null=True, blank=True)
    amount_repaid = models.CharField(max_length=255, null=True, blank=True)
    CHOICES = [
        ("PAID", "Paid in Full"),
        ("PARTIALLY PAID", "Partially Paid"),
        ("NOT PAID", "Not paid"),
    ]    
    repayment_status = models.CharField(
        "Repayment Status",
        max_length=20,
        choices=CHOICES,
        default="NOT PAID",
    )
    
    class Meta:
        db_table = 'epSakhi_epManFund'    

# Training Section
class EnterpriseTrainingReq(SoftDeleteMixin):
    id = models.BigAutoField(primary_key=True)

    enterprise_id = models.CharField(
        max_length=36,
        db_column='enterprise_id',
        help_text='TH_urid of enterprise form (existing/new)',
    )

    form_type = models.CharField(max_length=20, null=True, blank=True, help_text='rec/req')
    
    sector_type = models.CharField(max_length=255, null=True, blank=True)
    sector = models.CharField(max_length=255, null=True, blank=True)
    department = models.CharField(max_length=255, null=True, blank=True)
    training_type = models.CharField(max_length=255, null=True, blank=True) 
    duration = models.CharField(max_length=100, null=True, blank=True)
    location = models.CharField(max_length=255, null=True, blank=True)
    expected_income = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        db_table = 'epSakhi_epTraining'

class TrainingCertificates(SoftDeleteMixin):
    id = models.BigAutoField(primary_key=True)

    enterprise_id = models.CharField(
        max_length=36,
        db_column='enterprise_id',
        help_text='TH_urid of enterprise form (existing/new)',
    )
    training_id = models.ForeignKey(
        EnterpriseTrainingReq,
        on_delete=models.CASCADE,
        related_name='training_certificate',
        blank=True,
        null=True,
    )  
    certificates = models.FileField(upload_to='epSakhi/media/training/certificates/%Y/%m/', null=True, blank=True)
    
    class Meta:
        db_table = 'epSakhi_epTrainingCert'

# ----------------------------------
# NewEnterprise (epSakhi_newEpForm)
# ----------------------------------
class NewEnterprise(SoftDeleteMixin):
    id = models.BigAutoField(primary_key=True)

    recorded_benef_id = models.ForeignKey(
        BeneficiaryRecorded,
        on_delete=models.CASCADE,
        related_name='newep_recorded_benef',
        blank=True,
        null=True,
    ) 
    
    # Basic Info Section
    applicant_special_category = models.CharField(max_length=255, null=True, blank=True)
    applicant_cadre = models.CharField(max_length=255, null=True, blank=True)
    applicant_designation = models.CharField(max_length=255, null=True, blank=True)    
    prefered_location = models.CharField(max_length=255, null=True, blank=True)

    # Fund Section
    has_shg_receieved_man_fund = models.BooleanField(default=False)

    # Training Section
    is_training_received = models.BooleanField(default=False)
    is_training_required = models.BooleanField(default=False)

    nearest_skill_centre = models.CharField(max_length=255, null=True, blank=True)
    skill_centre_loc = models.CharField(max_length=255, null=True, blank=True)
    nearest_industry = models.CharField(max_length=255, null=True, blank=True)
    industry_loc = models.CharField(max_length=255, null=True, blank=True)

    # Support Section
    is_support_required = models.CharField(max_length=255, null=True, blank=True)

    # Declaration Section
    declaration_confirmed = models.BooleanField(default=False)
    declaration_date = models.DateField(null=True, blank=True)
    applicant_signature = models.ImageField(upload_to='epSakhi/new_enterprise/applicant_sign/%Y/%m/', null=True, blank=True)

    class Meta:
        db_table = 'epSakhi_newEpForm'

    def __str__(self):
        return f"NewEnterprise {self.TH_urid}"

# CANCELLED

# --------------------------------------------
# No Enterprise Form table (epSakhi_noEpForm)
# --------------------------------------------
class NoEnterpriseForm(SoftDeleteMixin):
    """
    epSakhi_noEpForm
    For beneficiaries not interested in opening an enterprise.
    """
    id = models.BigAutoField(primary_key=True)

    recorded_benef_id = models.ForeignKey(
        BeneficiaryRecorded,
        on_delete=models.CASCADE,
        related_name='noep_recorded_benef',
        blank=True,
        null=True,
    ) 

    if_shg_member_inv = models.TextField(null=True, blank=True, help_text='Is SHG member involved in any EP/wage activity')
    no_int_reason = models.TextField(null=True, blank=True)
    is_training_required = models.BooleanField(default=False)
    future_willing = models.BooleanField(default=False)

    has_shg_cif = models.BooleanField(default=False)
    cif_fund_amt = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)

    class Meta:
        db_table = 'epSakhi_noEpForm'

# No Enterprise Wage/placement table
class NoEnterpriseWage(SoftDeleteMixin):
    """
    epSakhi_noEpWage
    Wage / placement preferences when not opening an enterprise.
    """
    id = models.BigAutoField(primary_key=True)

    enterprise_id = models.ForeignKey(
        NoEnterpriseForm,
        on_delete=models.CASCADE,
        related_name='noep_wage',
        blank=True,
        null=True,
    )  

    placement_sector = models.CharField(max_length=255, null=True, blank=True)
    type_of_emp = models.CharField(max_length=255, null=True, blank=True)
    exp_salary = models.CharField(max_length=255, null=True, blank=True)
    location_scope = models.CharField(max_length=255, null=True, blank=True)
    location = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        db_table = 'epSakhi_noEpWage'
