# support/models.py
import random
import string
from django.db import models, transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from core.models import MasterUser, MasterDistrict, MasterBlock

# ==========================================
# HELPER FUNCTIONS & MIXINS
# ==========================================

def generate_custom_th_urid():
    # Example generator for format like: TH_1AN33KN221 (prefix TH_ + 11 alnum)
    body = ''.join(random.choices(string.ascii_uppercase + string.digits, k=11))
    return f"TH_{body}"

def generate_ticket_code():
    # Example generator for ticket codes like: TKT_X89F2A
    body = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    return f"TKT_{body}"

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


# ==========================================
# SUPPORT APP MODELS
# ==========================================

class Ticket(SoftDeleteMixin):
    ticket_code = models.CharField(
        max_length=20, 
        default=generate_ticket_code, 
        unique=True, 
        editable=False,
        verbose_name="Ticket Code"
    )
    is_solved = models.BooleanField(default=False, verbose_name="Is Solved?")
    master_user = models.ForeignKey(
        MasterUser, on_delete=models.PROTECT, db_column='user_id',
        related_name='grievance_user', null=True, blank=True, db_constraint=False
    )    
    pmu_response = models.TextField(verbose_name="PMU IT Resposne")

    def __str__(self):
        return f"{self.ticket_code} - {'Solved' if self.is_solved else 'Pending'}"


class TicketBody(SoftDeleteMixin):
    ticket = models.OneToOneField(
        Ticket, 
        on_delete=models.CASCADE, 
        related_name='ticket_body',
        verbose_name="Ticket"
    )
    district = models.ForeignKey(
        MasterDistrict, 
        on_delete=models.PROTECT, 
        verbose_name="District"
    )
    block = models.ForeignKey(
        MasterBlock, 
        on_delete=models.PROTECT, 
        verbose_name="Block",
        null=True,
        blank=True
    )
    username = models.CharField(max_length=150, verbose_name="Username")

    problem_message = models.TextField(verbose_name="Problem Message")
    mobile_no = models.CharField(max_length=15, verbose_name="Mobile Number")

    def __str__(self):
        return f"Body for {self.ticket.ticket_code}"


class TicketMedia(SoftDeleteMixin):
    ticket = models.ForeignKey(
        Ticket, 
        on_delete=models.CASCADE, 
        related_name='ticket_media',
        verbose_name="Ticket"
    )
    screenshot = models.ImageField(
        upload_to='support_tickets/screenshots/', 
        verbose_name="Screenshot"
    )

    def clean(self):
        # Validate that a single ticket cannot have more than 3 screenshots
        # self.pk is None implies we are creating a new instance
        if self.pk is None and self.ticket_id:
            existing_media_count = TicketMedia.objects.filter(
                ticket=self.ticket, 
                is_active=True
            ).count()
            
            if existing_media_count >= 3:
                raise ValidationError("A maximum of 3 screenshots are allowed per ticket.")
                
        super().clean()

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Media for {self.ticket.ticket_code}"