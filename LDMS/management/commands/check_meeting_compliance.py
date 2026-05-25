# LDMS/management/commands/check_meeting_compliance.py

import datetime
from django.core.management.base import BaseCommand
from django.utils import timezone
from core.models import MasterUser, MasterGeoUserScope
from LDMS.models import DLCC_Meeting, BLCC_Meeting, Notification

class Command(BaseCommand):
    help = 'Checks for missing MoM uploads for DMMUs and BMMUs and sends notifications.'

    def handle(self, *args, **kwargs):
        now = timezone.now()
        current_month = now.month
        current_year = now.year

        self.stdout.write(f"Running compliance check for {current_month}/{current_year}...")

        # ---------------------------------------------------------
        # CHECK 1: DMMU COMPLIANCE (Role ID = 2)
        # ---------------------------------------------------------
        active_dmmus = MasterUser.objects.filter(role_id=2, is_active=1)
        
        for dmmu in active_dmmus:
            # Find their assigned district
            scope = MasterGeoUserScope.objects.filter(user_id=dmmu.id, is_active=1).first()
            if not scope or not scope.district_id:
                continue
                
            # Check if they have AT LEAST 1 uploaded DLCC meeting this month
            has_meeting = DLCC_Meeting.objects.filter(
                district_id=scope.district_id,
                meeting_date__month=current_month,
                meeting_date__year=current_year,
                is_uploaded=True,
                is_active=True
            ).exists()

            if not has_meeting:
                Notification.objects.create(
                    recipient=dmmu,
                    title="URGENT: Monthly DLCC MoM Missing",
                    message=f"You have not scheduled or uploaded the Minutes of Meeting (MoM) for {current_month}/{current_year} DLCC Meeting. Please complete this immediately to ensure compliance.",
                    priority='CRITICAL',
                    notification_type='MEETING_COMPLIANCE'
                )
                self.stdout.write(self.style.WARNING(f"Notified DMMU: {dmmu.username}"))

        # ---------------------------------------------------------
        # CHECK 2: BMMU COMPLIANCE (Role ID = 1)
        # ---------------------------------------------------------
        active_bmmus = MasterUser.objects.filter(role_id=1, is_active=1)

        for bmmu in active_bmmus:
            # Find their assigned block
            scope = MasterGeoUserScope.objects.filter(user_id=bmmu.id, is_active=1).first()
            if not scope or not scope.block_id:
                continue

            # Check if they have AT LEAST 1 uploaded BLCC meeting this month
            has_meeting = BLCC_Meeting.objects.filter(
                block_id=scope.block_id,
                meeting_date__month=current_month,
                meeting_date__year=current_year,
                is_uploaded=True,
                is_active=True
            ).exists()

            if not has_meeting:
                Notification.objects.create(
                    recipient=bmmu,
                    title="URGENT: Monthly BLCC MoM Missing",
                    message=f"You have not scheduled or uploaded the Minutes of Meeting (MoM) for {current_month}/{current_year} BLCC Meeting. Please complete this immediately to ensure compliance.",
                    priority='CRITICAL',
                    notification_type='MEETING_COMPLIANCE'
                )
                self.stdout.write(self.style.WARNING(f"Notified BMMU: {bmmu.username}"))

        self.stdout.write(self.style.SUCCESS("Compliance check completed successfully."))