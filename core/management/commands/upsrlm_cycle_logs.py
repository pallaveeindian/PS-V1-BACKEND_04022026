# core/management/commands/upsrlm_cycle_logs.py

import logging
import os
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from core.models import MasterBlock  # uses master_block.block_id :contentReference[oaicite:0]{index=0}

logger = logging.getLogger(__name__)


def get_log_dir() -> Path:
    """
    Directory where UPSRLM import progress logs are written.

    You can override via:
        UPSRLM_IMPORT_LOG_DIR = BASE_DIR / "upsrlm_logs"
    in settings.py.
    """
    base = getattr(settings, "UPSRLM_IMPORT_LOG_DIR", None)
    if base is None:
        base = Path(settings.BASE_DIR) / "upsrlm_logs"
    return Path(base)


class Command(BaseCommand):
    help = (
        "Check UPSRLM import coverage based on log files, and when ALL blocks "
        "have completed SHG/CLF list+detail imports, wipe the log directory "
        "so the next full cycle can start cleanly."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Only report status; do not delete any files.",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Print details of missing logs.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        verbose = options["verbose"]

        log_dir = get_log_dir()
        if not log_dir.exists():
            self.stdout.write(
                self.style.WARNING(
                    f"UPSrlm log dir {log_dir} does not exist yet. Nothing to cycle."
                )
            )
            return

        # Get all block_ids from MasterBlock
        block_ids = list(MasterBlock.objects.values_list("block_id", flat=True))
        total_blocks = len(block_ids)

        if not block_ids:
            self.stdout.write(
                self.style.WARNING("No MasterBlock rows found. Nothing to check.")
            )
            return

        # Naming convention MUST match whatever you use in the import code:
        #   - list imports:
        #        {block_id}_shg_list.log
        #        {block_id}_clf_list.log
        #   - detail imports:
        #        {block_id}_shg_detail.log
        #        {block_id}_clf_detail.log
        #
        # Each file contains only newly CREATED codes for that block.
        patterns = [
            "{block_id}_shg_list.log",
            "{block_id}_clf_list.log",
            "{block_id}_shg_detail.log",
            "{block_id}_clf_detail.log",
        ]

        missing = []
        for bid in block_ids:
            for template in patterns:
                fname = template.format(block_id=bid)
                fpath = log_dir / fname
                if not fpath.exists() or fpath.stat().st_size == 0:
                    missing.append((bid, fname))

        if missing:
            msg = (
                f"Coverage incomplete: {len(missing)} missing/empty log files "
                f"out of {total_blocks} blocks * {len(patterns)} patterns."
            )
            self.stdout.write(self.style.WARNING(msg))
            if verbose:
                for bid, fname in missing[:50]:  # limit output
                    self.stdout.write(f"  - Block {bid} missing/empty: {fname}")
                if len(missing) > 50:
                    self.stdout.write(
                        f"  ...and {len(missing) - 50} more missing entries."
                    )
            return

        # If we reached here, all required log files exist and are non-empty.
        msg = (
            f"All UPSRLM import logs present for {total_blocks} blocks "
            f"({len(patterns)} files per block)."
        )
        self.stdout.write(self.style.SUCCESS(msg))

        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f"[DRY-RUN] Would delete all *.log under {log_dir}, "
                    f"but not doing it because --dry-run is set."
                )
            )
            return

        # Actually delete all log files in the directory.
        deleted = 0
        for path in log_dir.glob("*.log"):
            try:
                path.unlink()
                deleted += 1
            except Exception as exc:
                logger.exception("Failed to delete %s: %s", path, exc)

        self.stdout.write(
            self.style.SUCCESS(
                f"Deleted {deleted} log files under {log_dir}. New import cycle can start."
            )
        )
