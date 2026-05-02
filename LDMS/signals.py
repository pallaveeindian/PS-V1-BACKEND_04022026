# LDMS/signals.py

from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from django.db.models import Count
from core.models import MasterGeoUserScope, MasterUser
from .models import Bucket_Approval, Notification

@receiver(pre_save, sender=Bucket_Approval)
def capture_previous_approval_status(sender, instance, **kwargs):
    """
    Captures the old approval status before the object is saved to the database.
    This allows us to detect exact state transitions (e.g., DRAFT -> PENDING).
    """
    if instance.pk:
        try:
            old_instance = Bucket_Approval.objects.get(pk=instance.pk)
            instance._old_status = old_instance.approval_status
        except Bucket_Approval.DoesNotExist:
            instance._old_status = None
    else:
        instance._old_status = None


@receiver(post_save, sender=Bucket_Approval)
def handle_bucket_approval_notifications(sender, instance, created, **kwargs):
    old_status = getattr(instance, '_old_status', None)

    # ---------------------------------------------------------
    # TRIGGER 1: REJECTED NOTIFICATION (Sent to the BMMU Creator)
    # ---------------------------------------------------------
    # Check old_status to prevent spamming if a rejected row is just updated
    if instance.approval_status == 'REJECTED' and old_status != 'REJECTED':
        if instance.created_by:
            Notification.objects.create(
                recipient=instance.created_by,
                title="Support Request Rejected",
                message=f"Your support request for bucket ID {instance.support_bucket.id} was rejected.\nReason: {instance.rejection_reason or 'No reason provided.'}",
                priority='HIGH',
                notification_type='APPROVAL_REJECTED'
            )

    # ---------------------------------------------------------
    # TRIGGER 2: PENDING NOTIFICATIONS (Sent to DMMU)
    # ---------------------------------------------------------
    elif instance.approval_status == 'PENDING':
        
        # Check if this is newly created OR transitioned from DRAFT/REJECTED
        is_new_submission = created or (old_status in ['DRAFT', 'REJECTED'])

        # If it's just a regular edit/update to an already PENDING row, ignore it
        if not is_new_submission:
            return

        if not instance.block_id:
            return
            
        district_id = instance.block_id.district_id
        
        # Find the DMMU user(s) responsible for this district
        dmmu_scopes = MasterGeoUserScope.objects.filter(
            district_id=district_id,
            is_active=1
        ).values_list('user_id', flat=True)
        
        dmmu_users = MasterUser.objects.filter(
            id__in=dmmu_scopes, 
            role_id=2, 
            is_active=1
        )

        # 1. SEND IMMEDIATE NOTIFICATION FOR THIS SPECIFIC SUBMISSION
        for dmmu in dmmu_users:
            Notification.objects.create(
                recipient=dmmu,
                title="New Support Request Submitted",
                message=f"A support request (Bucket ID {instance.support_bucket.id}) was just submitted and is awaiting your approval.",
                priority='MEDIUM',
                notification_type='APPROVAL_PENDING'
            )

        # 2. SEND THE AGGREGATE "STACKING" NOTIFICATION (Every 10 rows)
        pending_count = Bucket_Approval.objects.filter(
            block_id__district_id=district_id,
            approval_status='PENDING',
            is_active=True
        ).count()

        if pending_count > 0 and pending_count % 10 == 0:
            for dmmu in dmmu_users:
                Notification.objects.create(
                    recipient=dmmu,
                    title="Action Required: Pending Approvals Stack",
                    message=f"You currently have {pending_count} Support Bucket requests stacked up and pending approval for your district.",
                    priority='CRITICAL' if pending_count >= 20 else 'HIGH',
                    notification_type='APPROVAL_PENDING'
                )