from django.core.management.base import BaseCommand
from django.utils.timezone import now

import logging
logger = logging.getLogger(__name__)

from core.models import MasterDistrict, MasterBlock
from LDMS.models import (
    Block_Analytics,
    District_Analytics,
    State_Analytics,
)
from LDMS.api.analytics_views import build_block_analytics


class Command(BaseCommand):
    help = "Rebuild analytics in DB (blocks → districts → state)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--districts",
            action="store_true",
            help="Rebuild ONLY district analytics",
        )
        parser.add_argument(
            "--blocks",
            action="store_true",
            help="Rebuild ONLY block analytics",
        )

    def handle(self, *args, **options):
        run_started_at = now()
        self.stdout.write("🔥 COMMAND STARTED")
        self.stdout.write(f"⏱ Run started at {run_started_at}")

        run_blocks = options["blocks"]
        run_districts = options["districts"]

        if not run_blocks and not run_districts:
            run_blocks = True
            run_districts = True

        blocks_cached = 0
        districts_cached = 0
        failed_blocks = []

        # =====================================================
        # 1️⃣ BLOCK ANALYTICS (SOURCE OF TRUTH)
        # =====================================================
        if run_blocks:
            self.stdout.write("📦 Rebuilding BLOCK analytics...")

            for block_id in MasterBlock.objects.values_list("block_id", flat=True):
                try:
                    data = build_block_analytics(block_id)

                    Block_Analytics.objects.update_or_create(
                        block_id=block_id,
                        defaults={
                            "total_vos": data["totals"]["total_vos"],
                            "total_clfs": data["totals"]["total_clfs"],
                            "total_shgs": data["totals"]["total_shgs"],
                            "updated_at": now(),
                        },
                    )

                    blocks_cached += 1
                    self.stdout.write(f"✔ Block stored {block_id}")

                except Exception:
                    failed_blocks.append(block_id)
                    logger.exception("Block failed %s", block_id)
                    self.stderr.write(f"✖ Block {block_id} failed")

        # =====================================================
        # 2️⃣ DISTRICT ANALYTICS (SUM OF BLOCKS)
        # =====================================================
        if run_districts:
            self.stdout.write("🏙 Rebuilding DISTRICT analytics...")

            for district in MasterDistrict.objects.all():
                try:
                    blocks = Block_Analytics.objects.filter(
                        block__district_id=district.district_id,
                        is_active=True,
                    )

                    if not blocks.exists():
                        self.stderr.write(
                            f"⚠ District {district.district_id} has no block analytics"
                        )
                        continue

                    total_vos = sum(int(b.total_vos or 0) for b in blocks)
                    total_clfs = sum(int(b.total_clfs or 0) for b in blocks)
                    total_shgs = sum(int(b.total_shgs or 0) for b in blocks)

                    District_Analytics.objects.update_or_create(
                        district=district,
                        defaults={
                            "total_vos": total_vos,
                            "total_clfs": total_clfs,
                            "total_shgs": total_shgs,
                            "updated_at": now(),
                        },
                    )

                    districts_cached += 1
                    self.stdout.write(f"✔ District stored {district.district_id}")

                except Exception:
                    logger.exception("District failed %s", district.district_id)
                    self.stderr.write(f"✖ District {district.district_id} failed")

        # =====================================================
        # 3️⃣ STATE ANALYTICS (SUM OF DISTRICTS)
        # =====================================================
        self.stdout.write("🌍 Rebuilding STATE analytics...")

        districts = District_Analytics.objects.filter(is_active=True)

        state_total_vos = sum(int(d.total_vos or 0) for d in districts)
        state_total_clfs = sum(int(d.total_clfs or 0) for d in districts)
        state_total_shgs = sum(int(d.total_shgs or 0) for d in districts)

        State_Analytics.objects.update_or_create(
            id=1,
            defaults={
                "total_vos": state_total_vos,
                "total_clfs": state_total_clfs,
                "total_shgs": state_total_shgs,
                "updated_at": now(),
            },
        )

        self.stdout.write("✔ State analytics stored")

        # =====================================================
        # 4️⃣ RETRY FAILED BLOCKS (ONE TIME ONLY)
        # =====================================================
        if failed_blocks:
            self.stdout.write(
                f"🔁 Retrying failed blocks ({len(failed_blocks)})..."
            )

            recovered_blocks = []

            for block_id in failed_blocks:
                try:
                    data = build_block_analytics(block_id)

                    Block_Analytics.objects.update_or_create(
                        block_id=block_id,
                        defaults={
                            "total_vos": data["totals"]["total_vos"],
                            "total_clfs": data["totals"]["total_clfs"],
                            "total_shgs": data["totals"]["total_shgs"],
                            "updated_at": now(),
                        },
                    )

                    recovered_blocks.append(block_id)
                    self.stdout.write(f"✔ Block recovered {block_id}")

                except Exception:
                    logger.exception("Retry failed %s", block_id)
                    self.stderr.write(f"✖ Retry failed for block {block_id}")

            # =================================================
            # 5️⃣ REBUILD DISTRICT + STATE IF ANY RECOVERED
            # =================================================
            if recovered_blocks:
                self.stdout.write("🔄 Rebuilding DISTRICT + STATE after retry...")

                affected_districts = set(
                    MasterBlock.objects.filter(
                        block_id__in=recovered_blocks
                    ).values_list("district_id", flat=True)
                )

                for district_id in affected_districts:
                    blocks = Block_Analytics.objects.filter(
                        block__district_id=district_id,
                        is_active=True,
                    )

                    total_vos = sum(int(b.total_vos or 0) for b in blocks)
                    total_clfs = sum(int(b.total_clfs or 0) for b in blocks)
                    total_shgs = sum(int(b.total_shgs or 0) for b in blocks)

                    District_Analytics.objects.update_or_create(
                        district_id=district_id,
                        defaults={
                            "total_vos": total_vos,
                            "total_clfs": total_clfs,
                            "total_shgs": total_shgs,
                            "updated_at": now(),
                        },
                    )

                districts = District_Analytics.objects.filter(is_active=True)
                state_total_vos = sum(int(d.total_vos or 0) for d in districts)
                state_total_clfs = sum(int(d.total_clfs or 0) for d in districts)
                state_total_shgs = sum(int(d.total_shgs or 0) for d in districts)

                State_Analytics.objects.update_or_create(
                    id=1,
                    defaults={
                        "total_vos": state_total_vos,
                        "total_clfs": state_total_clfs,
                        "total_shgs": state_total_shgs,
                        "updated_at": now(),
                    },
                )

                self.stdout.write("✔ District & State refreshed after retry")

        # =====================================================
        # 6️⃣ FINAL SUMMARY
        # =====================================================
        run_finished_at = now()

        self.stdout.write("✅ ANALYTICS REBUILD COMPLETE")
        self.stdout.write(f"📦 Blocks stored: {blocks_cached}")
        self.stdout.write(f"🏙 Districts stored: {districts_cached}")
        self.stdout.write(f"❌ Blocks failed initially: {len(failed_blocks)}")
        self.stdout.write(
            f"⏱ Duration: {(run_finished_at - run_started_at).total_seconds() / 60:.2f} min"
        )
