# core/management/commands/unlock_locked_users.py

from django.core.management.base import BaseCommand
from django.utils import timezone
from core.models import MasterUser
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Unlock all locked users every 12 hours"

    def handle(self, *args, **kwargs):

        now = timezone.localtime()

        locked_users = MasterUser.objects.filter(is_locked=1)

        count = locked_users.update(
            is_locked=0,
            locked_on=None,
            pass_attempt_no=0,
            updated_at=now
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully unlocked {count} users at {now}"
            )
        )

        logger.info(f"Unlocked {count} users at {now}")