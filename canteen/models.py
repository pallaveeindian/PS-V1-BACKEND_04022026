# prernaCanteen/models.py
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
# 1) Canteen Home
# -------------------------
class CanteenHome(SoftDeleteMixin):
    id = models.BigAutoField(primary_key=True)
    canteen_type = models.TextField(null=True, blank=True)

    district = models.ForeignKey(
        MasterDistrict,
        on_delete=models.PROTECT,
        db_column='district_id',
        db_constraint=False,
        null=True,
        blank=True,
        related_name='canteen_homes'
    )
    block = models.ForeignKey(
        MasterBlock,
        on_delete=models.PROTECT,
        db_column='block_id',
        db_constraint=False,
        null=True,
        blank=True,
        related_name='canteen_homes'
    )
    panchayat = models.ForeignKey(
        MasterPanchayat,
        on_delete=models.PROTECT,
        db_column='panchayat_id',
        db_constraint=False,
        null=True,
        blank=True,
        related_name='canteen_homes'
    )
    village = models.ForeignKey(
        MasterVillage,
        on_delete=models.PROTECT,
        db_column='village_id',
        db_constraint=False,
        null=True,
        blank=True,
        related_name='canteen_homes'
    )

    class Meta:
        db_table = 'prernaCanteen_home'

    def __str__(self):
        return f"CanteenHome ({self.id}) - {self.canteen_type}"

# -------------------------
# 2) Canteen Members
# -------------------------
class CanteenMember(SoftDeleteMixin):
    id = models.BigAutoField(primary_key=True)
    canteen_home = models.ForeignKey(
        CanteenHome,
        on_delete=models.CASCADE,
        related_name='members',
        blank=True,
        null=True,
        db_column='canteen_home_id'
    )

    lokos_shg_code = models.CharField(max_length=100, null=True, blank=True)
    lokos_shg_name = models.TextField(null=True, blank=True)
    lokos_clf_code = models.CharField(max_length=100, null=True, blank=True)
    lokos_clf_name = models.TextField(null=True, blank=True)
    lokos_member_code = models.CharField(max_length=100, db_column='lokos_member_code')
    
    applicant_name = models.CharField(max_length=255)
    age = models.PositiveIntegerField(null=True, blank=True)
    gender = models.CharField(max_length=50, null=True, blank=True)
    marital_status = models.CharField(max_length=50, null=True, blank=True)
    father_husband_name = models.CharField(max_length=255, null=True, blank=True)
    category = models.CharField(max_length=255, null=True, blank=True)
    pld_status = models.CharField(max_length=255, null=True, blank=True)
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
        related_name='canteen_members'
    )
    block_id = models.ForeignKey(
        MasterBlock,
        on_delete=models.PROTECT,
        db_column='block_id',
        db_constraint=False,
        null=True,
        blank=True,
        related_name='canteen_members'
    )
    panchayat_id = models.ForeignKey(
        MasterPanchayat,
        on_delete=models.PROTECT,
        db_column='panchayat_id',
        db_constraint=False,
        null=True,
        blank=True,
        related_name='canteen_members'
    )
    village_id = models.ForeignKey(
        MasterVillage,
        on_delete=models.PROTECT,
        db_column='village_id',
        db_constraint=False,
        null=True,
        blank=True,
        related_name='canteen_members'
    )

    mobile = models.CharField(max_length=20, null=True, blank=True)
    email = models.EmailField(null=True, blank=True)

    class Meta:
        db_table = 'prernaCanteen_members'

    def __str__(self):
        return f"{self.lokos_member_code} - {self.applicant_name}"

# -------------------------
# 3) Canteen Details
# -------------------------
class CanteenDetail(SoftDeleteMixin):
    id = models.BigAutoField(primary_key=True)
    canteen_home = models.ForeignKey(
        CanteenHome,
        on_delete=models.CASCADE,
        related_name='details',
        blank=True,
        null=True,
        db_column='canteen_home_id'
    )

    canteen_name = models.CharField(max_length=255, null=True, blank=True)
    food_type = models.CharField(max_length=255, null=True, blank=True)
    date_of_establishment = models.DateField(null=True, blank=True)
    
    # Questions
    sells_other_shg_packaged_food = models.CharField(
        max_length=255, null=True, blank=True,
        help_text="Are any other packaged food products manufactured by SHGs also being sold at the canteen?"
    )
    packaged_products_list = models.TextField(null=True, blank=True, help_text="If yes, please list the products.")
    has_canteen_management_training = models.CharField(
        max_length=255, null=True, blank=True,
        help_text="Have you received any training related to operating or managing the canteen?"
    )
    training_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    training_source = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        db_table = 'prernaCanteen_details'

# -------------------------
# 4) Canteen Finances
# -------------------------
class CanteenFinance(SoftDeleteMixin):
    id = models.BigAutoField(primary_key=True)
    canteen_home = models.ForeignKey(
        CanteenHome,
        on_delete=models.CASCADE,
        related_name='finances',
        blank=True,
        null=True,
        db_column='canteen_home_id'
    )

    total_investment = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    monthly_sale = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    rent = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    salary = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    electricity = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    miscellaneous = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    other_expense = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    total_income = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    total_expense = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    profit_loss = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)

    class Meta:
        db_table = 'prernaCanteen_finances'

# -------------------------
# 5) Canteen Licenses
# -------------------------
class CanteenLicense(SoftDeleteMixin):
    id = models.BigAutoField(primary_key=True)
    canteen_home = models.ForeignKey(
        CanteenHome,
        on_delete=models.CASCADE,
        related_name='licenses',
        blank=True,
        null=True,
        db_column='canteen_home_id'
    )
    
    license_name = models.CharField(max_length=255, null=True, blank=True)
    license_file = models.FileField(upload_to='prernaCanteen/media/licenses/%Y/%m/', null=True, blank=True)

    class Meta:
        db_table = 'prernaCanteen_licenses'

# -------------------------
# 6) Canteen Model PC
# -------------------------
class CanteenModelPC(SoftDeleteMixin):
    id = models.BigAutoField(primary_key=True)
    canteen_home = models.ForeignKey(
        CanteenHome,
        on_delete=models.CASCADE,
        related_name='model_pc',
        blank=True,
        null=True,
        db_column='canteen_home_id'
    )

    aop_name = models.CharField(max_length=255, null=True, blank=True)
    aop_members = models.TextField(null=True, blank=True)
    account_no = models.CharField(max_length=100, null=True, blank=True)
    ifsc = models.CharField(max_length=20, null=True, blank=True)
    branch = models.CharField(max_length=255, null=True, blank=True)
    bank_name = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        db_table = 'prernaCanteen_modelPC'