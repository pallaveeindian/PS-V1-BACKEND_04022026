# pragati_setu/TMS/models.py
import uuid
import random
import string
from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError
from core.models import MasterUser, MasterDistrict, MasterBlock, MasterPanchayat, MasterVillage

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

# ----------------------------
# TrainingPlan Related
# ----------------------------

class TrainingTheme(SoftDeleteMixin):
    id = models.BigAutoField(primary_key=True)
    theme_name = models.CharField(max_length=200, blank=True, null=True)
    expert = models.ForeignKey(MasterUser, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        db_table = 'tms_trainingtheme'
        managed = True
        indexes = [
            models.Index(fields=['theme_name']),
            models.Index(fields=['expert']),
        ]

    def __str__(self):
        return self.theme_name or f"Theme-{self.id}"

class TrainingPlan(SoftDeleteMixin):
    id = models.BigAutoField(primary_key=True)
    training_name = models.CharField("Training name", max_length=255)
    theme = models.ForeignKey(
        TrainingTheme,
        on_delete=models.SET_NULL,
        null=True,
        related_name='THEME'
    )

    TYPE_CHOICES = [
        ("RES", "Residential"),
        ("NON RES", "Non-residential"),
        ("OTHER", "Other"),
    ]
    type_of_training = models.CharField(
        "Type of Training",
        max_length=20,
        choices=TYPE_CHOICES,
        default="OTHER",
    )

    LEVEL_CHOICES = [
        ("VILLAGE", "Village"),
        ("SHG", "SHG"),
        ("CLF", "CLF"),
        ("BLOCK", "Block"),
        ("BLOCK_DISTRICT", "Block/District"),
        ("CMTC/BLOCK", "CMTC/Block"),
        ("DISTRICT", "District"),
        ("STATE", "State"),
        ("WITHIN_STATE", "Within State"),
        ("OUTSIDE_STATE", "Outside State"),
    ]
    level_of_training = models.CharField(
        "Level of training",
        max_length=32,
        choices=LEVEL_CHOICES,
        blank=True,
        null=True,
    )

    no_of_days = models.PositiveIntegerField("No of Days", blank=True, null=True)

    APPROVAL_CHOICES = [
        ("SANCTIONED", "Sanctioned"),
        ("PENDING", "Pending"),
        ("DENIED", "Denied"),
    ]
    approval_status = models.CharField(
        "Approval of Training Plan",
        max_length=20,
        choices=APPROVAL_CHOICES,
        blank=True,
        null=True,
    )

    class Meta:
        db_table = 'tms_trainingplan'
        managed = True
        indexes = [
            models.Index(fields=['training_name']),
            models.Index(fields=['approval_status']),
            models.Index(fields=['level_of_training']),
            models.Index(fields=['type_of_training']),
            models.Index(fields=['theme']),
        ]

    def __str__(self):
        return self.training_name or str(self.id)

# ----------------------------
# MasterTrainer & Certificates
# ----------------------------

class MasterTrainer(SoftDeleteMixin):
    id = models.AutoField(primary_key=True)
    master_user = models.ForeignKey(
        MasterUser, on_delete=models.PROTECT, db_column='user_id',
        related_name='master_trainer', null=True, blank=True, db_constraint=False
    )

    full_name = models.CharField(max_length=200)
    profile_picture = models.ImageField(upload_to='trainer_pfps/', blank=True, null=True)
    date_of_birth = models.DateField(blank=True, null=True)
    mobile_no = models.CharField(
        "Mobile No.", max_length=20, blank=True, null=True, db_index=True
    )
    aadhaar_no = models.CharField("Aadhaar No", max_length=20, blank=True, null=True)

    empanel_district = models.ForeignKey(
        MasterDistrict, on_delete=models.DO_NOTHING, blank=True, null=True
    )
    empanel_block = models.ForeignKey(
        MasterBlock, on_delete=models.DO_NOTHING, blank=True, null=True
    )

    social_category = models.CharField("Social Category", max_length=50, blank=True, null=True)
    gender = models.CharField(max_length=20, blank=True, null=True)
    education = models.CharField(max_length=200, blank=True, null=True)
    marital_status = models.CharField(max_length=50, blank=True, null=True)
    parent_or_spouse_name = models.CharField(
        "Father/Mother/Spouse Name", max_length=200, blank=True, null=True
    )

    skills = models.TextField("Skills / Thematic Sectors", blank=True, null=True)
    thematic_expert_recommendation = models.CharField(max_length=255, blank=True, null=True)
    success_rate = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    any_other_tots = models.TextField(blank=True, null=True)
    other_achievements = models.TextField(blank=True, null=True)
    recommended_tots_by_dmmu = models.TextField(blank=True, null=True)
    success_story_publications = models.TextField(blank=True, null=True)

    bank_account_number = models.CharField("Account Number", max_length=64, blank=True, null=True)
    ifsc = models.CharField("IFSC", max_length=32, blank=True, null=True)
    branch_name = models.CharField("Branch Name", max_length=200, blank=True, null=True)
    bank_name = models.CharField("Bank Name", max_length=200, blank=True, null=True)

    DESIGNATION_CHOICES = [
        ('BRP', 'BRP'),
        ('DRP', 'DRP'),
        ('SRP', 'SRP'),
    ]
    designation = models.CharField(
        "Designation",
        max_length=3,
        choices=DESIGNATION_CHOICES,
        blank=True,
        null=True,
        db_index=True,
    )

    class Meta:
        db_table = 'tms_mastertrainer'
        managed = True
        indexes = [
            models.Index(fields=['mobile_no']),
            models.Index(fields=['designation']),
            models.Index(fields=['empanel_district']),
            models.Index(fields=['empanel_block']),
            models.Index(fields=['success_rate']),
        ]

    def __str__(self):
        return self.full_name

class MasterTrainerCertificate(SoftDeleteMixin):
    id = models.BigAutoField(primary_key=True)
    trainer = models.ForeignKey(
        MasterTrainer, on_delete=models.CASCADE, related_name='certificates'
    )
    training_plan = models.ForeignKey(
        TrainingPlan, on_delete=models.SET_NULL, null=True, blank=True
    )
    theme = models.ForeignKey(
        TrainingTheme, on_delete=models.SET_NULL, null=True, blank=True
    )
    certificate_no = models.CharField(max_length=255, blank=True, null=True)
    issued_on = models.DateField(blank=True, null=True)
    certificate_file = models.FileField(
        upload_to='trainer_certificates/', blank=True, null=True,
        help_text="Upload certificate image/PDF (jpeg, png, pdf)."
    )
    
    class Meta:
        db_table = 'tms_mastertrainercertificate'
        managed = True

# ----------------------------
# TrainingPartner & centres
# ----------------------------

class TrainingPartner(SoftDeleteMixin):
    id = models.AutoField(primary_key=True)

    master_user = models.ForeignKey(
        MasterUser, on_delete=models.PROTECT, db_column='user_id',
        related_name='tp_account', null=True, blank=True, db_constraint=False
    )

    name = models.CharField(max_length=255)
    email = models.EmailField(blank=True, null=True)
    address = models.TextField(blank=True, null=True)

    tpm_registration_no = models.CharField(
        "Registration No (TPM/Org)", max_length=128, blank=True, null=True
    )
    mou_form = models.FileField(
        "Signed MoU (PDF)", upload_to='partner_mous/', blank=True, null=True
    )

    class Meta:
        db_table = 'tms_trainingpartner'
        managed = True
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['tpm_registration_no']),
        ]

    def __str__(self):
        return f"{self.name} ({self.tpm_registration_no or 'N/A'})"

class TrainingPartnerBank(SoftDeleteMixin):
    id = models.AutoField(primary_key=True)

    partner = models.ForeignKey(
        TrainingPartner, on_delete=models.CASCADE, related_name='banks'
    )

    bank_name = models.CharField("Bank Name", max_length=255, blank=True, null=True)
    bank_branch = models.CharField("Branch", max_length=255, blank=True, null=True)
    bank_ifsc = models.CharField("IFSC / Routing", max_length=32, blank=True, null=True)
    bank_account_number = models.CharField("Account Number", max_length=64, blank=True, null=True)

    class Meta:
        db_table = 'tms_tpbanks'
        managed = True

    def __str__(self):
        return f"{self.partner.name} - {self.bank_account_number}"

class TrainingPartnerCP(SoftDeleteMixin):
    id = models.AutoField(primary_key=True)

    partner = models.ForeignKey(
        TrainingPartner, on_delete=models.CASCADE, related_name='contact_person'
    )
    master_user = models.ForeignKey(
        MasterUser, on_delete=models.PROTECT, db_column='user_id',
        related_name='tpcp_account', null=True, blank=True, db_constraint=False
    )

    name = models.CharField(max_length=255)
    mobile_number = models.CharField(max_length=20, null=True, blank=True)
    email = models.EmailField(blank=True, null=True)
    address = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'tms_tpcontactperson'
        managed = True

    def __str__(self):
        return f"{self.partner.name} - {self.name}"

class TrainingPartnerCentre(SoftDeleteMixin):
    id = models.BigAutoField(primary_key=True)
    partner = models.ForeignKey(
        TrainingPartner, on_delete=models.CASCADE, related_name='centres'
    )

    # Basic Details
    serial_number = models.IntegerField(blank=True, null=True)
    district = models.ForeignKey(
        MasterDistrict,
        on_delete=models.SET_NULL,
        related_name='trainingpartner_centre_district',
        null=True, blank=True,
    )
    block = models.ForeignKey(
        MasterBlock,
        on_delete=models.SET_NULL,
        related_name='trainingpartner_centre_block',
        null=True, blank=True,
    )
    panchayat = models.ForeignKey(
        MasterPanchayat,
        on_delete=models.SET_NULL,
        related_name='trainingpartner_centre_panchayat',
        null=True, blank=True,
    )
    village = models.ForeignKey(
        MasterVillage,
        on_delete=models.SET_NULL,
        related_name='trainingpartner_centre_village',
        null=True, blank=True,
    )

    venue_name = models.CharField("Venue Name", max_length=120, blank=True, null=True)
    venue_address = models.CharField("Venue Address", max_length=500, blank=True, null=True)

    # Training Hall
    training_hall_count = models.IntegerField(
        "Number of Training Halls", blank=True, null=True
    )
    training_hall_capacity = models.IntegerField(
        "Training Hall Capacity (max 35 participants/batch)", blank=True, null=True
    )

    # Facilities
    security_arrangements = models.CharField(
        "Security Arrangements", max_length=255, blank=True, null=True
    )
    toilets_bathrooms = models.IntegerField(
        "Total Toilets/Bathrooms", blank=True, null=True
    )
    power_water_facility = models.CharField(
        "Power/Water Availability", max_length=255, blank=True, null=True
    )
    medical_kit = models.BooleanField("Medical Kit Available", default=False)
    centre_type = models.CharField(
        "Centre Type (Private/Govt/Lodge/Rented)", max_length=255, blank=True, null=True
    )
    open_space = models.BooleanField("Open Space for Group Activity", default=False)
    field_visit_facility = models.BooleanField("Field Visit Facility", default=False)
    transport_facility = models.BooleanField("Transport Facility", default=False)
    dining_facility = models.BooleanField("Dining Room Facility", default=False)
    other_details = models.TextField("Other Details", blank=True, null=True)

    class Meta:
        db_table = 'tms_trainingpartnercentre'
        managed = True
        indexes = [
            models.Index(fields=['partner']),
            models.Index(fields=['district']),
            models.Index(fields=['block']),
            models.Index(fields=['panchayat']),
            models.Index(fields=['village']),
        ]

    def __str__(self):
        return f"{self.partner.name} - {self.venue_name}"

class TrainingPartnerCentreRooms(SoftDeleteMixin):
    id = models.BigAutoField(primary_key=True)
    centre = models.ForeignKey(
        TrainingPartnerCentre, on_delete=models.CASCADE, related_name='rooms'
    )
    room_name = models.CharField(max_length=200)
    room_capacity = models.IntegerField(default=0)

    class Meta:
        db_table = 'tms_trainingpartnercentrerooms'
        managed = True

    def __str__(self):
        return f"{self.centre.venue_name} - {self.room_name}"

class TPCPToCentre(SoftDeleteMixin):
    id = models.BigAutoField(primary_key=True)
    contact_person = models.ForeignKey(
        TrainingPartnerCP, on_delete=models.CASCADE, db_constraint=False
    )
    allocated_centre = models.ForeignKey(
        TrainingPartnerCentre, on_delete=models.CASCADE, db_constraint=False
    )

    class Meta:
        db_table = 'tms_tpcp_centre'
        managed = True

    def __str__(self):
        return f"{self.contact_person_id} -> {self.allocated_centre_id}"

class TrainingPartnerSubmission(SoftDeleteMixin):
    id = models.BigAutoField(primary_key=True)
    partner = models.ForeignKey(
        TrainingPartner, on_delete=models.CASCADE, related_name='submissions'
    )
    centre = models.ForeignKey(
        TrainingPartnerCentre,
        on_delete=models.CASCADE,
        related_name='submissions',
        blank=True,
        null=True,
    )

    CATEGORY_CHOICES = [
        ('FOODING', 'Fooding'),
        ('TOILET', 'Toilet'),
        ('CENTRE_FRONT', 'Centre (front)'),
        ('HOSTEL', 'Hostel'),
        ('CCTV_SECURITY', 'CCTV SECURITY'),
        ('ACTIVITY_HALL', 'Activity Hall'),
        ('OTHER', 'Other'),
    ]
    category = models.CharField(max_length=32, choices=CATEGORY_CHOICES, default='OTHER')
    file = models.FileField(
        upload_to='partner_photos_or_pdfs/', blank=True, null=True,
        help_text='Upload image (jpeg/png) or a PDF containing required photos.'
    )
    notes = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'tms_trainingpartnersubmission'
        managed = True

# ----------------------------
# TrainingPartnerTargets
# ----------------------------

class TrainingPartnerTargets(SoftDeleteMixin):
    id = models.BigAutoField(primary_key=True)
    partner = models.ForeignKey(
        TrainingPartner, on_delete=models.CASCADE, related_name='targets'
    )

    TARGET_TYPE_CHOICES = [
        ("DISTRICT", "District"),
        ("MODULE", "Module"),
        ("THEME", "Theme"),
    ]
    target_type = models.CharField(max_length=20, choices=TARGET_TYPE_CHOICES)
    training_plan = models.ForeignKey(
        TrainingPlan, on_delete=models.CASCADE,
        related_name='partner_targets', null=True, blank=True
    )
    district = models.ForeignKey(
        MasterDistrict,
        on_delete=models.SET_NULL,
        related_name='trainingpartner_district_target',
        null=True, blank=True,
    )
    theme = models.CharField(max_length=200, blank=True, null=True)

    target_count = models.PositiveIntegerField("Target count (batches)", default=0)
    notes = models.TextField("Notes / rationale", blank=True, null=True)
    financial_year = models.CharField("Financial year", max_length=9, null=True, blank=True)

    class Meta:
        db_table = 'tms_trainingpartnertargets'
        managed = True
        indexes = [
            models.Index(fields=['partner']),
            models.Index(fields=['target_type']),
            models.Index(fields=['district']),
            models.Index(fields=['training_plan']),
            models.Index(fields=['theme']),
            models.Index(fields=['financial_year']),
        ]

    def clean(self):
        if not self.partner:
            raise ValidationError("partner is required.")
        if not self.financial_year:
            raise ValidationError("financial_year is required (e.g. '2023-24').")
        if self.target_count is None:
            raise ValidationError("target_count is required.")

        if self.target_type == "DISTRICT":
            if not self.district:
                raise ValidationError("district must be set for DISTRICT targets.")
        elif self.target_type == "MODULE":
            if not self.training_plan:
                raise ValidationError("training_plan must be set for MODULE targets.")
            if not self.district:
                raise ValidationError("district must be set for MODULE targets.")
        elif self.target_type == "THEME":
            # theme must be present either explicitly or via training_plan.theme
            tp_theme_name = None
            if self.training_plan and self.training_plan.theme:
                tp_theme_name = self.training_plan.theme.theme_name
            if not (self.theme or tp_theme_name):
                raise ValidationError(
                    "theme must be present for THEME targets (inferred from logged-in SMMU or training_plan)."
                )

        if len(self.financial_year) < 5:
            raise ValidationError("financial_year looks invalid (expected e.g. '2023-24').")

    def save(self, *args, **kwargs):
        # Populate theme automatically when possible
        if not self.theme and self.training_plan and self.training_plan.theme:
            self.theme = self.training_plan.theme.theme_name
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        scope = self.target_type
        if self.target_type == "MODULE":
            scope += f" - {getattr(self.training_plan, 'training_name', self.training_plan_id)} / {getattr(self.district, 'district_name_en', self.district_id)}"
        elif self.target_type == "DISTRICT":
            scope += f" - {getattr(self.district, 'district_name_en', self.district_id)}"
        else:
            scope += f" - {self.theme or 'N/A'}"
        return f"{self.partner.name} — {scope} = {self.target_count} ({self.financial_year})"

# ---------------------------------------
# Training Request Participant Authority
# ---------------------------------------

class TRPUserScope(SoftDeleteMixin):
    """
    Maps master_user.role_id (user_role_id) to TrainingPlan.id (training_id).
    Purpose: specify participant selection authority for any training.
    """
    id = models.BigAutoField(primary_key=True)
    user_role_id = models.BigIntegerField(db_index=True)
    training_id = models.BigIntegerField(blank=True, null=True, db_index=True)

    class Meta:
        managed = True
        db_table = 'tms_trpuserscope'

    def __str__(self):
        return f'TRPScope(user_role_id={self.user_role_id}, training={self.training_id})'

# ----------------------------
# Training Request
# ----------------------------

class TrainingRequest(SoftDeleteMixin):
    id = models.BigAutoField(primary_key=True)
    training_plan = models.ForeignKey(
        TrainingPlan, on_delete=models.SET_NULL, null=True, blank=True, related_name='requests'
    )
    partner = models.ForeignKey(
        TrainingPartner, on_delete=models.SET_NULL, null=True, blank=True
    )
    TRAINING_TYPE_CHOICES = [
        ('BENEFICIARY', 'Beneficiary'),
        ('TRAINER', 'Master Trainer'),
    ]
    training_type = models.CharField(
        "Applicable For", max_length=20, choices=TRAINING_TYPE_CHOICES
    )

    LEVEL_CHOICES = [
        ('BLOCK', 'Block'),
        ('DISTRICT', 'District'),
        ('STATE', 'State'),
    ]
    level = models.CharField(
        max_length=50, choices=LEVEL_CHOICES, default='BLOCK', blank=True, null=True
    )

    STATUS_CHOICES = [
        ('BATCHING', 'Batching Phase'),
        ('PENDING', 'Pending Approval'),
        ('ONGOING', 'Ongoing'),
        ('REVIEW', 'Review Phase'),
        ('COMPLETED', 'Completed'),
        ('REJECTED', 'Rejected'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='BATCHING')
    rejection_reason = models.CharField(max_length=500, blank=True, null=True)

    district = models.ForeignKey(
        MasterDistrict, on_delete=models.DO_NOTHING, blank=True, null=True
    )
    block = models.ForeignKey(
        MasterBlock, on_delete=models.DO_NOTHING, blank=True, null=True
    )    

    class Meta:
        db_table = 'tms_trainingrequest'
        managed = True
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['level']),
            models.Index(fields=['training_type']),
            models.Index(fields=['training_plan']),
            models.Index(fields=['partner']),
        ]

    def __str__(self):
        title = getattr(self.training_plan, 'training_name', None)
        return f"{self.id} - {title or 'No plan'}"

# ----------------------------
# Training Request to Beneficiary Joint
# ----------------------------

class TRBeneficiary(SoftDeleteMixin):
    id = models.BigAutoField(primary_key=True)
    training = models.ForeignKey(
        TrainingRequest, on_delete=models.CASCADE,
        related_name='beneficiary_registrations'
    )
    lokos_shg_code = models.CharField(max_length=100, null=True, blank=True)
    lokos_member_code = models.CharField(max_length=100, db_column='lokos_member_code')

    member_name = models.CharField(max_length=255)
    age = models.PositiveIntegerField(null=True, blank=True)
    gender = models.CharField(max_length=50, null=True, blank=True)
    designation = models.CharField(max_length=255, null=True, blank=True)
    pld_status = models.CharField(max_length=50)

    social_category = models.CharField(max_length=255, null=True, blank=True)
    religion = models.CharField(max_length=255, null=True, blank=True)

    mobile = models.CharField(max_length=20, null=True, blank=True)
    email = models.EmailField(null=True, blank=True)
    education = models.CharField(max_length=255, null=True, blank=True)

    address = models.TextField(null=True, blank=True)
    district = models.ForeignKey(
        MasterDistrict, on_delete=models.DO_NOTHING, blank=True, null=True
    )
    block = models.ForeignKey(
        MasterBlock, on_delete=models.DO_NOTHING, blank=True, null=True
    )
    panchayat = models.ForeignKey(
        MasterPanchayat, on_delete=models.DO_NOTHING, blank=True, null=True
    )
    village = models.ForeignKey(
        MasterVillage, on_delete=models.DO_NOTHING, blank=True, null=True
    )

    remarks = models.TextField(blank=True, null=True)
    attended = models.BooleanField(default=False)
    is_replaced = models.BooleanField(default=False)
    registered_on = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'tms_trbeneficiary'
        managed = True
        indexes = [
            models.Index(fields=['training']),
            models.Index(fields=['lokos_shg_code']),
            models.Index(fields=['lokos_member_code']),
            models.Index(fields=['pld_status']),
            models.Index(fields=['district']),
            models.Index(fields=['block']),
        ]

    def __str__(self):
        return f"{self.member_name} ({self.lokos_member_code})"

# ----------------------------
# Training Request to Trainer Joint
# ----------------------------

class TRTrainer(SoftDeleteMixin):
    id = models.BigAutoField(primary_key=True)
    training = models.ForeignKey(
        TrainingRequest,
        on_delete=models.CASCADE,
        related_name='trainer_registrations',
    )
    trainer = models.ForeignKey(
        MasterTrainer, on_delete=models.SET_NULL, null=True, blank=True
    )

    full_name = models.CharField(max_length=200, blank=True, null=True)

    mobile_no = models.CharField(
        "Mobile No.", max_length=20, blank=True, null=True, db_index=True
    )
    aadhaar_no = models.CharField("Aadhaar No", max_length=20, blank=True, null=True)

    district = models.ForeignKey(
        MasterDistrict, on_delete=models.DO_NOTHING, blank=True, null=True
    )
    block = models.ForeignKey(
        MasterBlock, on_delete=models.DO_NOTHING, blank=True, null=True
    )

    remarks = models.TextField(blank=True, null=True)
    attended = models.BooleanField(default=False)
    is_replaced = models.BooleanField(default=False)
    registered_on = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'tms_trtrainer'
        managed = True
        indexes = [
            models.Index(fields=['training']),
            models.Index(fields=['trainer']),
        ]

    def __str__(self):
        return f"TRTrainer({self.trainer_id}) for TR {self.training_id}"

# ----------------------------
# Batch
# ----------------------------

class Batch(SoftDeleteMixin):
    id = models.BigAutoField(primary_key=True)
    request = models.ForeignKey(
        TrainingRequest, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='batches'
    )
    centre = models.ForeignKey(
        TrainingPartnerCentre, on_delete=models.SET_NULL, null=True, blank=True
    )

    master_trainers = models.ManyToManyField(
        MasterTrainer,
        blank=True,
        related_name='master_trainers_for_batch',
        through='BatchMasterTrainer',
    )
    beneficiary = models.ManyToManyField(
        TRBeneficiary,
        blank=True,
        related_name='beneficiaries_for_batch',
        through='BatchBeneficiary',
    )
    trainer = models.ManyToManyField(
        TRTrainer,
        blank=True,
        related_name='trainers_for_batch',
        through='BatchTrainer',
    )

    BATCH_TYPE = [
        ('SEPARATE', 'Separate Batch'),
        ('COMBINED', 'Combined Batch'),
    ]
    batch_type = models.CharField(
        max_length=30, choices=BATCH_TYPE,
        default='SEPARATE', blank=True, null=True
    )

    code = models.CharField(
        max_length=255, unique=True, blank=True, null=True, db_index=True
    )

    STATUS = [
        ('DRAFT', 'Draft'),
        ('PENDING', 'Pending Approval'),
        ('ONGOING', 'Ongoing'),
        ('SCHEDULED', 'Scheduled'),
        ('COMPLETED', 'Completed'),
        ('REJECTED', 'Rejected'),
    ]
    status = models.CharField(
        max_length=30, choices=STATUS, default='DRAFT'
    )

    start_date = models.DateField(blank=True, null=True)
    end_date = models.DateField(blank=True, null=True)

    time_of_training = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        db_table = 'tms_batch'
        managed = True
        indexes = [
            models.Index(fields=['request']),
            models.Index(fields=['centre']),
            models.Index(fields=['status']),
            models.Index(fields=['start_date']),
            models.Index(fields=['end_date']),
        ]

    def __str__(self):
        return self.code or str(self.id)
    
class BatchSchedule(SoftDeleteMixin):
    id = models.BigAutoField(primary_key=True)
    batch = models.ForeignKey(
        Batch, on_delete=models.CASCADE, related_name='schedules'
    )
    schedule_date = models.DateField()
    start_time = models.TimeField(blank=True, null=True)
    remarks = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'tms_batchschedule'
        managed = True
        indexes = [
            models.Index(fields=['batch']),
            models.Index(fields=['schedule_date']),
        ]

    def __str__(self):
        return f"BatchSchedule({self.batch_id}) on {self.schedule_date}"    

# ----------------------------
# Participants attached to a batch
# ----------------------------

class BatchMasterTrainer(SoftDeleteMixin):
    id = models.BigAutoField(primary_key=True)
    batch = models.ForeignKey(
        Batch, on_delete=models.CASCADE, related_name='master_trainer_participations'
    )
    master_trainer = models.ForeignKey(
        MasterTrainer, on_delete=models.SET_NULL, null=True, blank=True
    )
    participated = models.BooleanField(default=False)

    STATUS_CHOICES = [
        ('AVAILABLE', 'Available'),
        ('UNAVAILABLE', 'Unavailable'),
    ]
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='AVAILABLE',
        blank=True, null=True
    )

    remarks = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'tms_batchmastertrainer'
        managed = True
        indexes = [
            models.Index(fields=['batch']),
            models.Index(fields=['master_trainer']),
        ]

    def __str__(self):
        trainer_name = getattr(self.master_trainer, "full_name", None) or f"Trainer-{getattr(self.master_trainer, 'id', '')}"
        batch_code = ""
        try:
            if self.batch:
                batch_code = getattr(self.batch, "code", None) or (f"Batch-{getattr(self.batch, 'id', '')}" if getattr(self.batch, 'id', None) else "")
        except Exception:
            batch_code = ""
        status = self.status or ""
        return f"{trainer_name}" + (f" - {batch_code}" if batch_code else "") + (f" [{status}]" if status else "")

class BatchBeneficiary(SoftDeleteMixin):
    id = models.BigAutoField(primary_key=True)
    batch = models.ForeignKey(
        Batch, on_delete=models.CASCADE, related_name='beneficiary_participations'
    )
    beneficiary = models.ForeignKey(
        TRBeneficiary, on_delete=models.SET_NULL, null=True, blank=True
    )

    registered_on = models.DateTimeField(auto_now_add=True)
    attended = models.BooleanField(default=False)
    is_replaced = models.BooleanField(default=False)

    class Meta:
        db_table = 'tms_batchbeneficiary'
        managed = True
        indexes = [
            models.Index(fields=['batch']),
            models.Index(fields=['beneficiary']),
        ]

    def __str__(self):
        return f"BatchBeneficiary({self.beneficiary_id}) in Batch {self.batch_id}"

class BatchTrainer(SoftDeleteMixin):
    id = models.BigAutoField(primary_key=True)
    batch = models.ForeignKey(
        Batch, on_delete=models.CASCADE, related_name='trainer_participations'
    )
    trainer = models.ForeignKey(
        TRTrainer, on_delete=models.SET_NULL, null=True, blank=True
    )

    registered_on = models.DateTimeField(auto_now_add=True)
    attended = models.BooleanField(default=False)
    is_replaced = models.BooleanField(default=False)

    class Meta:
        db_table = 'tms_batchtrainer'
        managed = True
        indexes = [
            models.Index(fields=['batch']),
            models.Index(fields=['trainer']),
        ]

    def __str__(self):
        return f"BatchTrainer({self.trainer_id}) in Batch {self.batch_id}"

# ----------------------------
# Batch eKYC verification & attendance
# ----------------------------

class BatchEkycVerification(SoftDeleteMixin):
    id = models.BigAutoField(primary_key=True)
    batch = models.ForeignKey(
        Batch, on_delete=models.CASCADE, related_name='ekyc_verifications'
    )

    participant_id = models.CharField(max_length=255)
    participant_role = models.CharField(
        max_length=20,
        choices=[('trainer', 'Trainer'), ('trainee', 'Trainee')]
    )
    ekyc_status = models.CharField(
        max_length=20,
        choices=[('PENDING', 'Pending'), ('VERIFIED', 'Verified'), ('FAILED', 'Failed')],
        default='PENDING'
    )
    ekyc_document = models.FileField(upload_to='ekyc_documents/', blank=True, null=True)
    verified_on = models.DateTimeField(blank=True, null=True)
    remarks = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'tms_batchekycverification'
        managed = True
        indexes = [
            models.Index(fields=['batch']),
            models.Index(fields=['participant_id']),
            models.Index(fields=['participant_role']),
            models.Index(fields=['ekyc_status']),
            models.Index(fields=['verified_on']),
        ]

class BatchAttendance(SoftDeleteMixin):
    id = models.BigAutoField(primary_key=True)
    batch = models.ForeignKey(
        Batch, on_delete=models.CASCADE, related_name='attendances'
    )
    date = models.DateField()
    csv_upload = models.FileField(upload_to='attendance_csvs/', blank=True, null=True)

    class Meta:
        db_table = 'tms_batchattendance'
        managed = True
        unique_together = ('batch', 'date')
        indexes = [
            models.Index(fields=['batch', 'date']),
        ]

class ParticipantAttendance(SoftDeleteMixin):
    id = models.BigAutoField(primary_key=True)
    attendance = models.ForeignKey(
        BatchAttendance, on_delete=models.CASCADE, related_name='participant_records'
    )
    participant_id = models.CharField(max_length=128)
    participant_name = models.CharField(max_length=255, blank=True, null=True)
    participant_role = models.CharField(
        max_length=50, choices=[('trainer', 'Trainer'), ('trainee', 'Trainee')]
    )
    present = models.BooleanField(default=False)

    class Meta:
        db_table = 'tms_participantattendance'
        managed = True
        indexes = [
            models.Index(fields=['attendance']),
            models.Index(fields=['participant_id']),
            models.Index(fields=['participant_role']),
            models.Index(fields=['present']),
        ]

# ----------------------------
# Batch Closure, cost, media, certificates
# ----------------------------

class TPBatchCostBreakup(SoftDeleteMixin):
    id = models.BigAutoField(primary_key=True)
    batch = models.ForeignKey(
        Batch, on_delete=models.SET_NULL, null=True,
        related_name='batch_cost_breakup'
    )

    centre_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    hostel_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    fooding_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    dresses_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    study_material_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        db_table = 'tms_tpbatchcostbreakup'
        managed = True
        indexes = [
            models.Index(fields=['batch']),
        ]

    def __str__(self):
        return f"CostBreakup(Batch {self.batch_id})"

class BatchParticipantCertificate(SoftDeleteMixin):
    """
    Certificate per participant (beneficiary or trainer) in a batch.

    issue_code format:
      <TrainingPlan_ID> D <BatchEndDateYYYYMMDD> I <TRBeneficiary_or_TRTrainer_id>
    """
    id = models.BigAutoField(primary_key=True)
    batch = models.ForeignKey(
        Batch, on_delete=models.SET_NULL, null=True,
        related_name='batch_certificates'
    )

    # Link to underlying participant in TrainingRequest
    tr_beneficiary = models.ForeignKey(
        TRBeneficiary, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='certificates'
    )
    tr_trainer = models.ForeignKey(
        TRTrainer, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='certificates'
    )

    issued_on = models.DateTimeField(blank=True, null=True)
    issue_code = models.CharField(max_length=255, db_index=True, blank=True, null=True)
    attendance_rate = models.CharField(max_length=50, blank=True, null=True)

    class Meta:
        db_table = 'tms_batchparticipantcertificate'
        managed = True
        indexes = [
            models.Index(fields=['batch']),
            models.Index(fields=['issue_code']),
        ]

    def clean(self):
        # must have exactly one participant
        if self.tr_beneficiary and self.tr_trainer:
            raise ValidationError("Only one of tr_beneficiary or tr_trainer can be set.")
        if not self.tr_beneficiary and not self.tr_trainer:
            raise ValidationError("Either tr_beneficiary or tr_trainer must be set.")

        # must be consistent with batch.request.training_type if possible
        if self.batch and self.batch.request:
            t_type = self.batch.request.training_type
            if t_type == 'BENEFICIARY' and self.tr_trainer:
                raise ValidationError("For BENFICIARY training_type, use tr_beneficiary, not tr_trainer.")
            if t_type == 'TRAINER' and self.tr_beneficiary:
                raise ValidationError("For TRAINER training_type, use tr_trainer, not tr_beneficiary.")

    def save(self, *args, **kwargs):
        from datetime import datetime

        if not self.issued_on:
            self.issued_on = timezone.now()

        # Auto-generate issue_code if missing
        if not self.issue_code and self.batch and self.batch.request:
            training_plan_id = None
            if self.batch.request.training_plan_id:
                training_plan_id = self.batch.request.training_plan_id
            else:
                training_plan_id = 0

            date_part = ""
            if self.batch.end_date:
                # yyyymmdd for deterministic format
                date_part = self.batch.end_date.strftime("%Y%m%d")

            # Pick participant id from TRBeneficiary or TRTrainer
            participant_id_part = ""
            if self.tr_beneficiary_id:
                participant_id_part = str(self.tr_beneficiary_id)
            elif self.tr_trainer_id:
                participant_id_part = str(self.tr_trainer_id)

            self.issue_code = f"{training_plan_id}D{date_part}I{participant_id_part}"

        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.issue_code or f"Certificate-{self.id}"

class BatchCost(SoftDeleteMixin):
    id = models.BigAutoField(primary_key=True)
    training = models.ForeignKey(
        TrainingRequest, on_delete=models.SET_NULL, null=True,
        related_name='TR_of_batch'
    )
    
    batch = models.ForeignKey(
        Batch, on_delete=models.SET_NULL, null=True,
        related_name='batch_costing'
    )

    trainer_part_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tp_part_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    batch_expenses = models.ForeignKey(
        TPBatchCostBreakup, on_delete=models.SET_NULL,
        null=True, related_name='detailed_cost'
    )

    class Meta:
        db_table = 'tms_batchcost'
        managed = True
        indexes = [
            models.Index(fields=['batch']),
        ]

    def __str__(self):
        return f"BatchCost(Batch {self.batch_id})"

class BatchMedia(SoftDeleteMixin):
    id = models.BigAutoField(primary_key=True)
    batch = models.ForeignKey(
        Batch, on_delete=models.SET_NULL, null=True,
        related_name='batch_pictures'
    )

    date = models.CharField(max_length=100, blank=True, null=True)
    
    CATEGORY_CHOICES = [
        ('FOODING', 'Fooding'),
        ('CLASS', 'Classroom'),
        ('TRAINING', 'Pictures with Ongoing Training'),
        ('PARTICIPANTS', 'Pictures with all Participants'),
        ('ATTENDANCE', 'Pictures while Attendance'),
        ('OTHER', 'Other'),
    ]
    category = models.CharField(max_length=32, choices=CATEGORY_CHOICES, default='OTHER')
    file = models.FileField(
        upload_to='batch_photos_or_pdfs/', blank=True, null=True,
        help_text='Upload image (jpeg/png) or a PDF containing required photos.'
    )
    notes = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'tms_batchmedia'
        managed = True
        indexes = [
            models.Index(fields=['batch']),
            models.Index(fields=['category']),
        ]

    def __str__(self):
        return f"BatchMedia(Batch {self.batch_id}, {self.category})"

class BatchClosureRequest(SoftDeleteMixin):
    id = models.BigAutoField(primary_key=True)
    batch = models.ForeignKey(
        Batch, on_delete=models.SET_NULL, null=True,
        related_name='batch_closing'
    )
    batch_costing = models.ForeignKey(
        TPBatchCostBreakup, on_delete=models.SET_NULL, null=True,
        related_name='batch_cost'
    )
    certificates_issued = models.BooleanField(default=False)

    class Meta:
        db_table = 'tms_batchclosurerequest'
        managed = True
        indexes = [
            models.Index(fields=['batch']),
            models.Index(fields=['certificates_issued']),
        ]

    def __str__(self):
        return f"BatchClosureRequest(Batch {self.batch_id})"

class TRClosure(SoftDeleteMixin):
    """
    Training Request level closure, after all batches under it are completed.
    """
    id = models.BigAutoField(primary_key=True)
    training = models.ForeignKey(
        TrainingRequest, on_delete=models.SET_NULL, null=True,
        related_name='TR_closure'
    )
    hra = models.FileField(
        upload_to='batch_closure_hra/', blank=True, null=True,
        help_text='Upload HRA Document PDF containing required information.'
    )
    ta_da = models.FileField(
        upload_to='batch_closure_tada/', blank=True, null=True,
        help_text='Upload TA/DA Document PDF containing required information.'
    )

    class Meta:
        db_table = 'tms_trclosure'
        managed = True
        indexes = [
            models.Index(fields=['training']),
        ]

    def __str__(self):
        return f"TRClosure(training {self.training_id})"

class BatchReport(SoftDeleteMixin):
    id = models.BigAutoField(primary_key=True)
    batch = models.ForeignKey(
        Batch, on_delete=models.SET_NULL, null=True,
        related_name='batch_report'
    )

    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('BMM_SIGNED', 'Signed by BMMU'),
        ('DMM_SIGNED', 'Signed by DMMU'),
        ('SMM_SIGNED', 'Signed by SMMU'),
    ]
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='DRAFT'
    )
    report_file = models.FileField(
        upload_to='batch_reports/', blank=True, null=True,
        help_text='Upload Batch Report Document PDF.'
    )

    class Meta:
        db_table = 'tms_batchreport'
        managed = True
        indexes = [
            models.Index(fields=['batch']),
        ]

    def __str__(self):
        return f"BatchReport(Batch {self.batch_id})"