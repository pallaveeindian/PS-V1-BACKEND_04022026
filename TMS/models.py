# pragati_setu/TMS/models.py
import uuid
import random
import string
from django.db import models, transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from core.models import MasterUser, MasterDistrict, MasterBlock, MasterPanchayat, MasterVillage
from django.db.models import Max
from django.db.models.signals import post_save
from django.dispatch import receiver

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

    theme = models.ForeignKey(
        TrainingTheme, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='master_trainers'
    )
    induction = models.BooleanField("Induction (YES/NO)", default=False)
    tot_smcb = models.BooleanField("TOT SMCB (YES/NO)", default=False)
    tot_mffi = models.BooleanField("TOT MFFI (YES/NO)", default=False)
    tot_sisd = models.BooleanField("TOT SISD (YES/NO)", default=False)
    tot_farm_lh = models.BooleanField("TOT FARM LH (YES/NO)", default=False)
    tot_non_farm_lh = models.BooleanField("TOT NON FARM LH (YES/NO)", default=False)
    tot_model_clf = models.BooleanField("TOT MODEL CLF (YES/NO)", default=False)
    tot_lokos = models.BooleanField("TOT LOKOS (YES/NO)", default=False)
    # ------------------------------------------------------------

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

    tp_short_name = models.CharField("Short Name", max_length=100, blank=True, null=True)

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

# ----------------------------
# TC Module - New District TP
# ----------------------------

class DistrictTP(SoftDeleteMixin):
    id = models.BigAutoField(primary_key=True)
    
    partner = models.ForeignKey(
        TrainingPartner, 
        on_delete=models.CASCADE, 
        related_name='district_nodes'
    )
    
    master_user = models.ForeignKey(
        MasterUser, 
        on_delete=models.PROTECT, 
        db_column='user_id',
        related_name='dtp_account', 
        null=True, 
        blank=True, 
        db_constraint=False
    )

    district = models.ForeignKey(
        MasterDistrict,
        on_delete=models.RESTRICT,
        related_name='district_tp_assignments'
    )

    is_active_dtp = models.BooleanField("Is Active District TP", default=True)

    class Meta:
        db_table = 'tms_districttp'
        managed = True
        unique_together = ('partner', 'district')
        indexes = [
            models.Index(fields=['partner']),
            models.Index(fields=['district']),
            models.Index(fields=['master_user']),
        ]

    def __str__(self):
        tp_name = self.partner.tp_short_name or self.partner.name
        district_name = getattr(self.district, 'district_name_en', f"District-{self.district_id}")
        return f"{tp_name} - {district_name}"

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
        unique_together = ('contact_person', 'allocated_centre')
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
        if self.target_count < 0:
            raise ValidationError("target_count cannot be negative.")

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
        # Check if this is a brand new record being inserted
        is_new = self.pk is None        
        super().save(*args, **kwargs)
        # --- NEW SURGICAL ADDITION: Auto-populate Achievement ---
        if is_new:
            TrainingPartnerAchievement.objects.create(
                partner=self.partner,
                assigned_target=self,
                batches_completed=0,
                financial_year=self.financial_year,
                training_plan=self.training_plan,
                district=self.district,
            )        

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

    financial_year = models.CharField("Financial year", max_length=9, null=True, blank=True)
    remarks = models.TextField(blank=True, null=True)

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

    CB_selected = models.BooleanField(default=False)

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

    CB_selected = models.BooleanField(default=False)

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

    training_plan = models.ForeignKey(
        TrainingPlan, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='plan_batches'
    )

    district = models.ForeignKey(
        MasterDistrict, on_delete=models.DO_NOTHING, blank=True, null=True
    )
    block = models.ForeignKey(
        MasterBlock, on_delete=models.DO_NOTHING, blank=True, null=True
    )    

    partner = models.ForeignKey(
        TrainingPartner, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='partner_batches'
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

    PARTICIPANT_TYPE_CHOICES = [
        ('BENEFICIARY', 'Beneficiary'),
        ('TRAINER', 'Master Trainer'),
    ]
    participant_type = models.CharField(
        "Applicable For", max_length=20, choices=PARTICIPANT_TYPE_CHOICES, null=True, blank=True
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
        ('REVIEW', 'Under Review'),
        ('CLOSED', 'Closed'),
        ('REJECTED', 'Rejected'),
    ]
    status = models.CharField(
        max_length=30, choices=STATUS, default='DRAFT'
    )

    rejection_reason = models.CharField(max_length=500, blank=True, null=True)
    start_date = models.DateField(blank=True, null=True)
    end_date = models.DateField(blank=True, null=True)
    time_of_training = models.CharField(max_length=255, blank=True, null=True)
    is_achievement_counted = models.BooleanField(default=False)
    financial_year = models.CharField("Financial year", max_length=9, null=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.code:
            # Extract names or fallback to "XXX"
            district = "XXX"
            if self.district:
                district = self.district.district_short_name_en or "XXX"

            block = "XXX"
            if self.block:
                block = self.block.block_name_local or "XXX"
                
            tp = "XXX"
            if self.partner:
                tp = self.partner.tp_short_name or "XXX"
                
            plan_id = 0
            if self.training_plan:
                plan_id = self.training_plan.id or 0

            # 2. Construct the prefix
            prefix = f"{district}-{block}-{tp}-{plan_id}"

            # 3. Sequence Generation with Race-Condition Protection
            with transaction.atomic():
                # select_for_update() locks these rows until the save is complete
                last_batch = Batch.objects.select_for_update().filter(
                    code__startswith=prefix
                ).aggregate(max_seq=Max("code"))

                last_code = last_batch["max_seq"]

                if last_code:
                    try:
                        # Split by hyphen and take the last part (the sequence)
                        parts = last_code.split("-")
                        last_seq = int(parts[-1])
                    except (ValueError, IndexError):
                        last_seq = 0
                else:
                    last_seq = 0

                new_seq = str(last_seq + 1).zfill(4)
                self.code = f"{prefix}-{new_seq}"

        super(Batch, self).save(*args, **kwargs)

    class Meta:
        db_table = 'tms_batch'
        managed = True
        indexes = [
            models.Index(fields=['training_plan']),
            models.Index(fields=['partner']),
            models.Index(fields=['centre']),
            models.Index(fields=['status']),
            models.Index(fields=['start_date']),
            models.Index(fields=['end_date']),
        ]

    def __str__(self):
        return self.code or str(self.id)

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
    
    training_request = models.ForeignKey(
        TrainingRequest, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='batch_beneficiary_mappings'
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
            models.Index(fields=['training_request']),
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
    
    training_request = models.ForeignKey(
        TrainingRequest, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='batch_trainer_mappings'
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
            models.Index(fields=['training_request']),
        ]

    def __str__(self):
        return f"BatchTrainer({self.trainer_id}) in Batch {self.batch_id}"


# ----------------------------
# Batch Block Coverage Tracker
# ----------------------------

class BatchBlockCoverage(SoftDeleteMixin):
    """
    Tracks how many participants from specific blocks are inside a Batch.
    If a Batch has >1 records here, it is automatically a 'COMBINED' batch.
    """
    id = models.BigAutoField(primary_key=True)
    batch = models.ForeignKey(
        Batch, on_delete=models.CASCADE, related_name='block_coverages'
    )
    block = models.ForeignKey(
        MasterBlock, on_delete=models.CASCADE, related_name='covered_batches'
    )
    participant_count = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'tms_batchblockcoverage'
        managed = True
        unique_together = ('batch', 'block')
        indexes = [
            models.Index(fields=['batch']),
            models.Index(fields=['block']),
        ]

    def __str__(self):
        return f"Batch {self.batch_id} covers Block {self.block_id} ({self.participant_count} pax)"

# ----------------------------
# Batch eKYC verification & attendance
# ----------------------------

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
    """
    Line-item cost for a SINGLE participant in a batch.
    Only participants with is_successful=True will have this row created.
    """
    id = models.BigAutoField(primary_key=True)
    batch = models.ForeignKey(
        Batch, on_delete=models.CASCADE, 
        related_name='participant_costs'
    )

    # Directly link to the specific participant (only one will be populated per row)
    batch_beneficiary = models.ForeignKey(
        'BatchBeneficiary', on_delete=models.CASCADE,
        null=True, blank=True, related_name='cost_breakup'
    )
    batch_trainer = models.ForeignKey(
        'BatchTrainer', on_delete=models.CASCADE,
        null=True, blank=True, related_name='cost_breakup'
    )

    participant_type = models.CharField(
        max_length=20,
        choices=[('BENEFICIARY', 'Beneficiary'), ('TRAINER', 'Trainer')]
    )

    hra = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    ta_da = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0) # hra + ta_da

    class Meta:
        db_table = 'tms_tpbatchcostbreakup'
        managed = True
        indexes = [
            models.Index(fields=['batch']),
            models.Index(fields=['batch_beneficiary']),
            models.Index(fields=['batch_trainer']),
        ]

    def __str__(self):
        return f"CostBreakup(Batch {self.batch_id} - Part: {self.batch_beneficiary_id or self.batch_trainer_id})"

class BatchCost(SoftDeleteMixin):
    """
    The master invoice for the entire Batch.
    """
    id = models.BigAutoField(primary_key=True)
    training = models.ForeignKey(
        TrainingRequest, on_delete=models.SET_NULL, null=True,
        related_name='TR_of_batch'
    )
    
    # Changed to OneToOne because a Batch should only have ONE total cost summary
    batch = models.OneToOneField(
        Batch, on_delete=models.CASCADE, 
        related_name='batch_costing'
    )

    is_exposure_visit = models.BooleanField(default=False)
    exposure_visit_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    is_field_visit = models.BooleanField(default=False)
    field_visit_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    # The sum of ALL TPBatchCostBreakup rows + the visit costs above
    grand_total_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        db_table = 'tms_batchcost'
        managed = True

    def __str__(self):
        return f"BatchCost(Batch {self.batch_id} - Total: {self.grand_total_cost})"

class BatchClosureRequest(SoftDeleteMixin):
    id = models.BigAutoField(primary_key=True)
    
    # Changed to OneToOne because a Batch only gets closed once
    batch = models.OneToOneField(
        Batch, on_delete=models.CASCADE, 
        related_name='batch_closing'
    )
    
    # Point this to the Master Invoice (BatchCost), NOT the line items
    batch_costing = models.ForeignKey(
        BatchCost, on_delete=models.SET_NULL, null=True,
        related_name='closure_requests'
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

        # must be consistent with batch.participant_type if possible
        if self.batch and self.batch.participant_type:
            t_type = self.batch.participant_type
            if t_type == 'BENEFICIARY' and self.tr_trainer:
                raise ValidationError("For BENEFICIARY participant_type, use tr_beneficiary, not tr_trainer.")
            if t_type == 'TRAINER' and self.tr_beneficiary:
                raise ValidationError("For TRAINER participant_type, use tr_trainer, not tr_beneficiary.")

    def save(self, *args, **kwargs):
        from django.utils import timezone

        if not self.issued_on:
            self.issued_on = timezone.now()

        # Auto-generate issue_code if missing
        if not self.issue_code and self.batch:
            training_plan_id = self.batch.training_plan_id or 0

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

class BeneficiaryAttendanceSummary(SoftDeleteMixin):
    id = models.BigAutoField(primary_key=True)
    
    # Traceability Foreign Keys
    batch_beneficiary = models.OneToOneField(
        'BatchBeneficiary', on_delete=models.CASCADE, related_name='attendance_summary',
        null=True, blank=True
    )
    # NEW: Added batch_trainer
    batch_trainer = models.OneToOneField(
        'BatchTrainer', on_delete=models.CASCADE, related_name='attendance_summary',
        null=True, blank=True
    )
    batch = models.ForeignKey(
        'Batch', on_delete=models.CASCADE, related_name='beneficiary_summaries'
    )
    training_request = models.ForeignKey(
        'TrainingRequest', on_delete=models.CASCADE, related_name='all_attendance_summaries'
    )

    # Calculated Metrics
    total_training_days = models.PositiveIntegerField(default=0)
    days_present = models.PositiveIntegerField(default=0)
    attendance_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    
    # Flags
    is_dropout = models.BooleanField(default=False)
    is_successful = models.BooleanField(
        default=False, 
        help_text="True if attendance is >= 80% and participant is NOT a dropout."
    )

    class Meta:
        db_table = 'tms_beneficiaryattendancesummary'
        managed = True
        indexes = [
            models.Index(fields=['batch']),
            models.Index(fields=['training_request']),
            models.Index(fields=['is_dropout']),
            models.Index(fields=['is_successful']),
        ]

    def clean(self):
        # Validation to ensure exactly ONE participant type is linked
        if self.batch_beneficiary and self.batch_trainer:
            raise ValidationError("Only one of batch_beneficiary or batch_trainer can be set.")
        if not self.batch_beneficiary and not self.batch_trainer:
            raise ValidationError("Either batch_beneficiary or batch_trainer must be set.")

    def __str__(self):
        # Safely fetch the name depending on which participant is linked
        if self.batch_beneficiary:
            name = getattr(self.batch_beneficiary.beneficiary, 'member_name', 'Unknown')
        elif self.batch_trainer:
            name = getattr(self.batch_trainer.trainer, 'full_name', getattr(self.batch_trainer.trainer, 'member_name', 'Unknown'))
        else:
            name = "Unknown"
            
        return f"Summary: {name} - {self.attendance_percentage}%"

class TrainingPartnerAchievement(SoftDeleteMixin):
    id = models.BigAutoField(primary_key=True)
    partner = models.ForeignKey(
        TrainingPartner, on_delete=models.CASCADE, related_name='achievements'
    )
    assigned_target = models.ForeignKey(
        TrainingPartnerTargets, on_delete=models.SET_NULL, null=True, blank=True, related_name='achievements'
    )
    batches_completed = models.PositiveIntegerField(default=0)
    financial_year = models.CharField("Financial year", max_length=9, null=True, blank=True)
    training_plan = models.ForeignKey(
        TrainingPlan, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='achievements'
    )
    district = models.ForeignKey(
        MasterDistrict, on_delete=models.SET_NULL, null=True, blank=True
    )
    date_achieved = models.DateField(blank=True, null=True)

    class Meta:
        db_table = 'tms_trainingpartnerachievement'
        managed = True
        indexes = [
            models.Index(fields=['partner']),
            models.Index(fields=['assigned_target']),
            models.Index(fields=['date_achieved']),
        ]

    def __str__(self):
        return f"{self.partner.name} - {self.title}"


class TMSFirstLoginTracker(models.Model):
    master_user = models.OneToOneField(
        MasterUser, 
        on_delete=models.CASCADE, 
        related_name='tms_first_login'
    )
    first_login_at = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    must_change_password = models.BooleanField(default=True)

    class Meta:
        managed = True
        db_table = 'tms_first_login_tracker'

    def __str__(self):
        return f"{self.master_user.username} - First TMS Login"

# ----------------------------
# Batch History Tracker
# ----------------------------

class BatchHistory(SoftDeleteMixin):
    """
    Automatically tracks date and timestamps of a Batch's status changes.
    Records every transition (DRAFT, PENDING, SCHEDULED, REJECTED, etc.)
    """
    id = models.BigAutoField(primary_key=True)
    batch = models.ForeignKey(
        Batch, 
        on_delete=models.CASCADE, 
        related_name='status_history'
    )
    status = models.CharField(
        max_length=30, 
        choices=Batch.STATUS
    )
    remarks = models.TextField(
        blank=True, 
        null=True, 
        help_text="Stores rejection reasons or automated system tracking remarks."
    )

    class Meta:
        db_table = 'tms_batchhistory'
        managed = True
        ordering = ['-created_at']  # Newest history appears first
        indexes = [
            models.Index(fields=['batch']),
            models.Index(fields=['status']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        batch_identifier = self.batch.code or f"ID-{self.batch.id}"
        return f"Batch {batch_identifier} -> {self.status} on {self.created_at.strftime('%Y-%m-%d %H:%M')}"

# =====================================================================
# SIGNAL: The Engine that makes BatchHistory "Self-Populating"
# =====================================================================

@receiver(post_save, sender=Batch)
def track_batch_status_history(sender, instance, created, **kwargs):
    """
    Automatically creates a BatchHistory record whenever a Batch is created 
    or its status is updated. It compares the current status against the 
    last recorded status to prevent duplicate log entries.
    """
    if created:
        # 1. Triggered when the Batch is first created (e.g., DRAFT)
        BatchHistory.objects.create(
            batch=instance,
            status=instance.status,
            remarks=f"Batch Initialized as {instance.status}.",
            created_by=instance.created_by
        )
    else:
        # 2. Triggered on subsequent updates
        # Fetch the most recent history record for this batch
        last_history = BatchHistory.objects.filter(batch=instance).order_by('-created_at').first()
        
        # Only create a new history row if the status has actually changed
        if not last_history or last_history.status != instance.status:
            
            # Safely capture who made the change
            user = instance.updated_by if instance.updated_by else instance.created_by
            
            # Auto-capture rejection reasons if applicable
            remarks = None
            if instance.status == 'REJECTED' and instance.rejection_reason:
                remarks = f"Rejected Reason: {instance.rejection_reason}"
            else:
                remarks = f"Status automatically transitioned to {instance.status}"
            
            BatchHistory.objects.create(
                batch=instance,
                status=instance.status,
                remarks=remarks,
                created_by=user
            )