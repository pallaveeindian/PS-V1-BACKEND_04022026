import pytz
from django.core.management.base import BaseCommand
from django.utils import timezone
from TMS.models import Batch

class Command(BaseCommand):
    help = 'Update SCHEDULED batches to ONGOING when start_date == today (IST)'

    def handle(self, *args, **options):
        india_tz = pytz.timezone('Asia/Kolkata')
        today_ist = timezone.now().astimezone(india_tz).date()
        
        scheduled_today = Batch.objects.filter(
            status='SCHEDULED',
            start_date=today_ist
        ).select_related('request', 'centre')
        
        count = scheduled_today.count()
        if count == 0:
            self.stdout.write(self.style.SUCCESS(f'No batches for {today_ist}'))
            return
        
        updated = 0
        for batch in scheduled_today:
            batch.status = 'ONGOING'
            batch.save(update_fields=['status'])
            updated += 1
            self.stdout.write(
                self.style.SUCCESS(f'Batch {batch.code or batch.id} → ONGOING')
            )
        
        self.stdout.write(self.style.SUCCESS(f'Updated {updated}/{count} batches'))
