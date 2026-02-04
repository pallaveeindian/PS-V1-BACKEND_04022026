# pragati_setu/LDMS/models.py
import uuid
import random
import string
from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError
from core.models import MasterUser, MasterDistrict, MasterBlock, MasterPanchayat, MasterVillage
from TMS.models import TrainingTheme, TrainingPlan

def generate_custom_th_urid():
    # Example generator for format like: TH_1AN33KN221 (prefix TH_ + 11 alnum)
    body = ''.join(random.choices(string.ascii_uppercase + string.digits, k=11))
    return f"TH_{body}"

class SoftDeleteMixin(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_column='created_at')
    updated_at = models.DateTimeField(auto_now=True, db_column='updated_at')
    deleted_at = models.DateTimeField(null=True, blank=True, db_column='deleted_at')
    created_by = models.ForeignKey(
        MasterUser, null=True, blank=True, on_delete=models.SET_NULL,
        db_column='created_by', related_name='+', db_constraint=False
    )
    updated_by = models.ForeignKey(
        MasterUser, null=True, blank=True, on_delete=models.SET_NULL,
        db_column='updated_by', related_name='+', db_constraint=False
    )
    deleted_by = models.ForeignKey(
        MasterUser, null=True, blank=True, on_delete=models.SET_NULL,
        db_column='deleted_by', related_name='+', db_constraint=False
    )
    is_active = models.BooleanField(default=True, db_column='is_active')

    TH_urid = models.CharField(
        max_length=36,
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

# Global Analytics Models
class State_Analytics(SoftDeleteMixin):
    id = models.AutoField(primary_key=True, db_column='state_analytics_id')
    total_vos = models.CharField(max_length=255, db_column='total_vos', null=True, blank=True)
    total_clfs = models.TextField(db_column='total_clfs', null=True, blank=True)
    total_shgs = models.TextField(db_column='total_shgs', null=True, blank=True)
    total_rural_hh = models.TextField(db_column='total_rural_hh', null=True, blank=True)
    total_hh_under_shgs = models.TextField(db_column='total_hh_under_shgs', null=True, blank=True)

    class Meta:
        db_table = 'ldms_state_analytics'
        verbose_name = 'State Analytics'
        verbose_name_plural = 'State Analytics Records'

class District_Analytics(SoftDeleteMixin):
    id = models.AutoField(primary_key=True, db_column='dist_analytics_id')
    district = models.ForeignKey(
        MasterDistrict, on_delete=models.PROTECT,
        db_column='district_id', db_constraint=False
    )
    total_vos = models.CharField(max_length=255, db_column='total_vos', null=True, blank=True)
    total_clfs = models.TextField(db_column='total_clfs', null=True, blank=True)
    total_shgs = models.TextField(db_column='total_shgs', null=True, blank=True)
    total_rural_hh = models.TextField(db_column='total_rural_hh', null=True, blank=True)
    total_hh_under_shgs = models.TextField(db_column='total_hh_under_shgs', null=True, blank=True)

    class Meta:
        db_table = 'ldms_district_analytics'
        verbose_name = 'District Analytics'
        verbose_name_plural = 'District Analytics Records'

class Block_Analytics(SoftDeleteMixin):
    id = models.AutoField(primary_key=True, db_column='block_analytics_id')
    block = models.ForeignKey(
        MasterBlock, on_delete=models.PROTECT,
        db_column='block_id', db_constraint=False
    )   
    total_vos = models.CharField(max_length=255, db_column='total_vos', null=True, blank=True)
    total_clfs = models.TextField(db_column='total_clfs', null=True, blank=True)
    total_shgs = models.TextField(db_column='total_shgs', null=True, blank=True)
    total_rural_hh = models.TextField(db_column='total_rural_hh', null=True, blank=True)
    total_hh_under_shgs = models.TextField(db_column='total_hh_under_shgs', null=True, blank=True)

    class Meta:
        db_table = 'ldms_block_analytics'
        verbose_name = 'Block Analytics'
        verbose_name_plural = 'Block Analytics Records'        

# DLCC and BLCC Meeting Models
class DLCC_Meeting_List(SoftDeleteMixin):
    id = models.AutoField(primary_key=True, db_column='dlcc_meeting_list_id')
    # Data Recieved from Google Sheet
    notif_date = models.TextField(db_column='meeting_notification_date')
    district = models.ForeignKey(
        MasterDistrict, on_delete=models.PROTECT,
        db_column='district_id', db_constraint=False
    )
    # Month format (YYYY-MM)
    meeting_month = models.TextField(db_column='meeting_month')
    no_of_meetings = models.IntegerField(db_column='number_of_meetings')

    class Meta:
        db_table = 'ldms_dlcc_meeting_list'
        verbose_name = 'DLCC Meeting List'
        verbose_name_plural = 'DLCC Meeting Lists'
        
class DLCC_Meeting(SoftDeleteMixin):
    id = models.AutoField(primary_key=True, db_column='dlcc_meeting_id')
    dlcc_meeting_list = models.ForeignKey(
        DLCC_Meeting_List, on_delete=models.CASCADE,
        db_column='dlcc_meeting_list_id', db_constraint=False
    )
    meeting_date = models.DateField(db_column='meeting_date', blank=True, null=True)
    mom = models.FileField(
        upload_to='dlcc_meetings/mom/',
        null=True, blank=True, db_column='mom'
    )
    is_uploaded = models.BooleanField(default=False, db_column='is_uploaded')

    class Meta:
        db_table = 'ldms_dlcc_meeting'
        verbose_name = 'DLCC Meeting'
        verbose_name_plural = 'DLCC Meetings'

    def clean(self):
        if self.meeting_date > timezone.now().date():
            raise ValidationError("Meeting date cannot be in the future.")        

class BLCC_Meeting_List(SoftDeleteMixin):
    id = models.AutoField(primary_key=True, db_column='blcc_meeting_list_id')
    # Data Recieved from Google Sheet
    notif_date = models.TextField(db_column='meeting_notification_date')
    district = models.ForeignKey(
        MasterDistrict, on_delete=models.PROTECT,
        db_column='district_id', db_constraint=False, blank=True, null=True
    )
    blocks_notif_issued = models.IntegerField(
        db_column='blocks_notified', blank=True, null=True
    )    
    meeting_month = models.TextField(db_column='meeting_month')
    no_of_meetings = models.IntegerField(db_column='number_of_meetings')
    
    class Meta:
        db_table = 'ldms_blcc_meeting_list'
        verbose_name = 'BLCC Meeting List'
        verbose_name_plural = 'BLCC Meeting Lists'

class BLCC_Meeting(SoftDeleteMixin):
    id = models.AutoField(primary_key=True, db_column='blcc_meeting_id')
    blcc_meeting_list = models.ForeignKey(
        BLCC_Meeting_List, on_delete=models.CASCADE,
        db_column='blcc_meeting_list_id', db_constraint=False
    )
    block = models.ForeignKey(
        MasterBlock, on_delete=models.PROTECT,
        db_column='block_id', db_constraint=False, blank=True, null=True
    )    
    meeting_date = models.DateField(db_column='meeting_date', blank=True, null=True)
    mom = models.FileField(
        upload_to='blcc_meetings/mom/',
        null=True, blank=True, db_column='mom'
    )
    is_uploaded = models.BooleanField(default=False, db_column='is_uploaded')

    class Meta:
        db_table = 'ldms_blcc_meeting'
        verbose_name = 'BLCC Meeting'
        verbose_name_plural = 'BLCC Meetings'

    def clean(self):
        if self.meeting_date > timezone.now().date():
            raise ValidationError("Meeting date cannot be in the future.")      

# Department and Scheme Models
class Department(SoftDeleteMixin):
    id = models.AutoField(primary_key=True, db_column='department_id')
    name = models.CharField(max_length=255, db_column='name')

    class Meta:
        db_table = 'ldms_department'
        verbose_name = 'Department'
        verbose_name_plural = 'Departments'
        
class Scheme(SoftDeleteMixin):
    id = models.AutoField(primary_key=True, db_column='scheme_id')
    department = models.ForeignKey(
        Department, on_delete=models.PROTECT,
        db_column='department_id', db_constraint=False
    )
    name = models.CharField(max_length=255, db_column='name')
    code = models.CharField(max_length=100, db_column='code', null=True, blank=True)
    assistance = models.TextField(db_column='assistance', null=True, blank=True)
    elligibility = models.TextField(db_column='elligibility', null=True, blank=True)
    scope = models.TextField(db_column='scope', null=True, blank=True)
    funding = models.TextField(db_column='funding', null=True, blank=True)
    contact_point = models.TextField(db_column='contact_point', null=True, blank=True)
    
    class Meta:
        db_table = 'ldms_scheme'
        verbose_name = 'Scheme'
        verbose_name_plural = 'Schemes'        
        
# Support Bucket Models
class recorded_benefs(SoftDeleteMixin):
    id = models.AutoField(primary_key=True, db_column='recorded_benefs_id')
    
    # LokOS API Data
    lokos_shg_code = models.CharField(max_length=100, null=True, blank=True)
    lokos_member_code = models.CharField(max_length=100, db_column='lokos_member_code')
    pld_status = models.CharField(max_length=100, null=True, blank=True)
    member_name = models.CharField(max_length=255)
    designation = models.CharField(max_length=255, null=True, blank=True)
    gender = models.CharField(max_length=50, null=True, blank=True)
    religion = models.CharField(max_length=100, null=True, blank=True)
    marital_status = models.CharField(max_length=50, null=True, blank=True)
    father_husband_name = models.CharField(max_length=255, null=True, blank=True)
    social_category = models.CharField(max_length=255, null=True, blank=True)
    education = models.CharField(max_length=255, null=True, blank=True)
    address = models.TextField(null=True, blank=True)

    district_id = models.ForeignKey(
        MasterDistrict, on_delete=models.PROTECT,
        db_column='district_id', db_constraint=False
    )
    block_id = models.ForeignKey(
        MasterBlock, on_delete=models.PROTECT,
        db_column='block_id', db_constraint=False
    )
    panchayat_id = models.ForeignKey(
        MasterPanchayat, on_delete=models.PROTECT,
        db_column='panchayat_id', db_constraint=False
    )
    village_id = models.ForeignKey(
        MasterVillage, on_delete=models.PROTECT,
        db_column='village_id', db_constraint=False
    )

    mobile = models.CharField(max_length=20, null=True, blank=True)
    # Calculate from LokOS DOB
    age = models.PositiveIntegerField(null=True, blank=True)    

    support_bucket = models.ForeignKey(
        'SupportBucket', on_delete=models.PROTECT,
        db_column='support_bucket_id', db_constraint=False
    )    
    
    class Meta:
        db_table = 'ldms_recorded_benefs'
        verbose_name = 'Recorded Beneficiary'
        verbose_name_plural = 'Recorded Beneficiaries'

class SBtypes(SoftDeleteMixin):
    id = models.AutoField(primary_key=True, db_column='sbtypes_id')
    bucket_type = models.CharField(max_length=255, db_column='bucket_type')

    class Meta:
        db_table = 'ldms_sbtypes'
        verbose_name = 'Support Bucket Type'
        verbose_name_plural = 'Support Bucket Types'
        
class SupportBucket(SoftDeleteMixin):
    id = models.AutoField(primary_key=True, db_column='support_bucket_id')
    department = models.ForeignKey(
        Department, on_delete=models.PROTECT,
        db_column='department_id', db_constraint=False
    )
    scheme = models.ForeignKey(
        Scheme, on_delete=models.PROTECT,
        db_column='scheme_id', db_constraint=False
    )
    bucket_type = models.ForeignKey(
        SBtypes, on_delete=models.PROTECT,
        db_column='bucket_type_id', db_constraint=False,
        null=True, blank=True
    )
    benefit_name = models.CharField(max_length=255, db_column='benefit_name', null=True, blank=True)
    benefit_amount = models.DecimalField(max_digits=10, decimal_places=2, db_column='benefit_amount', null=True, blank=True)
    benefit_description = models.TextField(db_column='benefit_description', null=True, blank=True)
    
    class Meta:
        db_table = 'ldms_support_bucket'
        verbose_name = 'Support Bucket'
        verbose_name_plural = 'Support Buckets'
        
class TrainingSupport(SoftDeleteMixin):
    id = models.AutoField(primary_key=True, db_column='training_support_id')
    training_theme = models.ForeignKey(
        TrainingTheme, on_delete=models.PROTECT,
        db_column='training_theme_id', db_constraint=False
    )
    training_plan = models.ForeignKey(
        TrainingPlan, on_delete=models.PROTECT,
        db_column='training_plan_id', db_constraint=False
    )
    support_bucket = models.ForeignKey(
        SupportBucket, on_delete=models.PROTECT,
        db_column='support_bucket_id', db_constraint=False
    )

    class Meta:
        db_table = 'ldms_training_support'
        verbose_name = 'Training Support'
        verbose_name_plural = 'Training Supports'        

# Bucket Approval
class Bucket_Approval(SoftDeleteMixin):
    id = models.AutoField(primary_key=True, db_column='bucket_approval_id')
    support_bucket = models.ForeignKey(
        SupportBucket, on_delete=models.PROTECT,
        db_column='support_bucket_id', db_constraint=False
    )
    STATUS = [
        ('DRAFT', 'Draft'),
        ('PENDING', 'Pending Approval'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
    ]
    approval_status = models.CharField(max_length=50, choices=STATUS, default='DRAFT', db_column='approval_status')
    rejection_reason = models.TextField(db_column='rejection_reason', null=True, blank=True)
    
    block_id = models.ForeignKey(
        MasterBlock, on_delete=models.PROTECT,
        db_column='block_id', db_constraint=False, null=True, blank=True
    )
    panchayat_id = models.ForeignKey(
        MasterPanchayat, on_delete=models.PROTECT,
        db_column='panchayat_id', db_constraint=False, null=True, blank=True
    )    
    
    approved_by = models.ForeignKey(
        MasterUser, null=True, blank=True, on_delete=models.SET_NULL,
        db_column='approved_by', related_name='+', db_constraint=False
    )
    approval_date = models.DateField(db_column='approval_date', null=True, blank=True)

    class Meta:
        db_table = 'ldms_bucket_approval'
        verbose_name = 'Bucket Approval'
        verbose_name_plural = 'Bucket Approvals'
            
# Plans and Activities Models
class AEP_Plan(SoftDeleteMixin):
    id = models.AutoField(primary_key=True, db_column='aep_plan_id')
    plan_name = models.CharField(max_length=255, db_column='plan_name')
    plan_description = models.TextField(db_column='plan_description', null=True, blank=True)
    start_date = models.DateField(db_column='start_date')
    end_date = models.DateField(db_column='end_date')

    class Meta:
        db_table = 'ldms_aep_plan'
        verbose_name = 'AEP Plan'
        verbose_name_plural = 'AEP Plans'

class VPRP_Plan(SoftDeleteMixin):
    id = models.AutoField(primary_key=True, db_column='vprp_plan_id')
    
    # Fields from (Corrupt code)VPRP Excel Sheet
    lokos_shg_code = models.CharField(max_length=100, null=True, blank=True)
    lokos_state_id = models.CharField(max_length=100, null=True, blank=True)
    lokos_district_id = models.CharField(max_length=100, null=True, blank=True)
    lokos_block_id = models.CharField(max_length=100, null=True, blank=True)
    lokos_vo_id = models.CharField(max_length=100, null=True, blank=True)
    lokos_clf_id = models.CharField(max_length=100, null=True, blank=True)
    lokos_panchayat_id = models.CharField(max_length=100, null=True, blank=True)
    lokos_member_name = models.CharField(max_length=255, null=True, blank=True)
    survey_year = models.CharField(max_length=4, db_column='survey_year', null=True, blank=True)
    lokos_member_code = models.CharField(max_length=100, db_column='lokos_member_code')
    hh_rank = models.CharField(max_length=50, db_column='hh_rank', null=True, blank=True)
    scale = models.CharField(max_length=50, db_column='scale', null=True, blank=True)
    sub_activity = models.CharField(max_length=255, db_column='sub_activity', null=True, blank=True)
    lh_activity = models.CharField(max_length=255, db_column='lh_activity', null=True, blank=True)
    lokos_shg_name = models.CharField(max_length=255, null=True, blank=True)
    support_category = models.CharField(max_length=255, db_column='support_category', null=True, blank=True)
    support_type = models.CharField(max_length=255, db_column='support_type', null=True, blank=True)
    head_of_hh = models.CharField(max_length=255, db_column='head_of_hh', null=True, blank=True)
    scheme_name = models.CharField(max_length=255, db_column='scheme_name', null=True, blank=True)
    department_name = models.CharField(max_length=255, db_column='department_name', null=True, blank=True)
    lokos_vo_name = models.CharField(max_length=255, db_column='lokos_vo_name', null=True, blank=True)
    panchayat_name = models.CharField(max_length=255, db_column='panchayat_name', null=True, blank=True)
    block_name = models.CharField(max_length=255, db_column='block_name', null=True, blank=True)
    district_name = models.CharField(max_length=255, db_column='district_name', null=True, blank=True)
    state_name = models.CharField(max_length=255, db_column='state_name', null=True, blank=True)

    class Meta:
        db_table = 'ldms_vprp_plan'
        verbose_name = 'VPRP Plan'
        verbose_name_plural = 'VPRP Plans'        
        
