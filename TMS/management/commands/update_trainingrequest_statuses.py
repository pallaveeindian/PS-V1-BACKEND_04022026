from django.core.management.base import BaseCommand
from django.db.models import Count, Q, F

from TMS import models as tmsmodels


class Command(BaseCommand):
    help = (
        "If all batches of a TrainingRequest are COMPLETED, "
        "auto-update TrainingRequest.status to REVIEW."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Do not save changes, only show what would be updated.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        # Status constants
        TR_STATUS_REVIEW = 'REVIEW'
        TR_STATUS_COMPLETED = 'COMPLETED'
        TR_STATUS_REJECTED = 'REJECTED'
        BATCH_STATUS_COMPLETED = 'COMPLETED'

        # Base queryset: TRs not in REVIEW / COMPLETED / REJECTED
        candidate_tr_qs = (
            tmsmodels.TrainingRequest.objects
            .filter(~Q(status__in=[TR_STATUS_REVIEW, TR_STATUS_COMPLETED, TR_STATUS_REJECTED]))
            .annotate(
                total_batches=Count('batches'),
                completed_batches=Count(
                    'batches',
                    filter=Q(batches__status=BATCH_STATUS_COMPLETED),
                ),
            )
        )

        # All batches completed (and at least one batch)
        eligible_tr_qs = candidate_tr_qs.filter(
            total_batches__gt=0,
            total_batches=F('completed_batches'),
        )

        total_candidates = candidate_tr_qs.count()
        eligible_count = eligible_tr_qs.count()

        self.stdout.write(
            f"Candidate TrainingRequests (non-final status): {total_candidates}"
        )
        self.stdout.write(
            f"Eligible for REVIEW (all batches COMPLETED): {eligible_count}"
        )

        if eligible_count == 0:
            self.stdout.write(self.style.SUCCESS("No TrainingRequests to update."))
            return

        updated = 0

        # NOTE: correct field name is training_plan (with underscore)[file:1]
        for tr in eligible_tr_qs.select_related('training_plan').order_by('id'):
            old_status = tr.status

            if dry_run:
                self.stdout.write(
                    self.style.WARNING(
                        f"[DRY-RUN] Would update TR #{tr.id} "
                        f"(status {old_status} → {TR_STATUS_REVIEW})"
                    )
                )
                continue

            tr.status = TR_STATUS_REVIEW
            tr.save(update_fields=['status'])
            updated += 1
            self.stdout.write(
                self.style.SUCCESS(
                    f"Updated TR #{tr.id} (status {old_status} → {TR_STATUS_REVIEW})"
                )
            )

        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f"DRY-RUN complete. TrainingRequests that would be updated: {eligible_count}"
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f"Total TrainingRequests updated: {updated}")
            )
