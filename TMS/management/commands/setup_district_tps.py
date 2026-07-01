# pragati_setu/TMS/management/commands/setup_district_tps.py
import uuid
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

# Adjust imports based on your app structure
from core.models import MasterUser, MasterDistrict, MasterGeoUserScope
from TMS.models import TrainingPartner, DistrictTP

class Command(BaseCommand):
    help = 'Creates DistrictTP records, MasterUser accounts, and GeoUserScopes for all Training Partners across all Districts.'

    def handle(self, *args, **kwargs):
        partners = TrainingPartner.objects.filter(is_active=True)
        districts = MasterDistrict.objects.all()

        if not partners.exists():
            self.stdout.write(self.style.ERROR("No active Training Partners found. Aborting."))
            return

        if not districts.exists():
            self.stdout.write(self.style.ERROR("No Districts found in MasterDistrict. Aborting."))
            return

        total_created_users = 0
        total_created_dtps = 0
        total_created_scopes = 0

        self.stdout.write(self.style.NOTICE(f"Found {partners.count()} TPs and {districts.count()} Districts."))
        self.stdout.write(self.style.NOTICE("Starting processing..."))

        for tp in partners:
            # Fallback to ID if short name is missing to ensure unique usernames
            tp_short = tp.tp_short_name.strip().lower().replace(" ", "") if tp.tp_short_name else f"tp{tp.id}"
            
            for district in districts:
                dist_short = district.district_short_name_en.strip().lower().replace(" ", "") if district.district_short_name_en else f"dist{district.district_id}"
                
                # Format: <district_short_name_en>-<tp_short_name>
                raw_username = f"{dist_short}-{tp_short}"
                # Format: <username>@dtp
                raw_password = f"{raw_username}@dtp"

                with transaction.atomic():
                    # ---------------------------------------------------------
                    # 1. Create or Get MasterUser
                    # ---------------------------------------------------------
                    user, user_created = MasterUser.objects.get_or_create(
                        username=raw_username,
                        defaults={
                            'password': raw_password, # Cleartext password as requested
                            'role_id': 13,
                            'is_active': 1,
                            'created_at': timezone.now(),
                            'TH_urid': str(uuid.uuid4()), # Generates a unique 36-char string
                        }
                    )
                    
                    if user_created:
                        total_created_users += 1

                    # ---------------------------------------------------------
                    # 2. Create or Get DistrictTP
                    # ---------------------------------------------------------
                    dtp, dtp_created = DistrictTP.objects.get_or_create(
                        partner=tp,
                        district=district,
                        defaults={
                            'master_user': user,
                            'is_active_dtp': True,
                        }
                    )
                    
                    # If the DistrictTP existed but didn't have a user attached, attach it now
                    if not dtp_created and dtp.master_user is None:
                        dtp.master_user = user
                        dtp.save(update_fields=['master_user'])

                    if dtp_created:
                        total_created_dtps += 1

                    # ---------------------------------------------------------
                    # 3. Create or Get MasterGeoUserScope
                    # ---------------------------------------------------------
                    scope, scope_created = MasterGeoUserScope.objects.get_or_create(
                        user_id=user.id,
                        district_id=district.district_id,
                        defaults={
                            'is_active': 1,
                            'created_at': timezone.now()
                        }
                    )
                    
                    if scope_created:
                        total_created_scopes += 1

            self.stdout.write(self.style.SUCCESS(f"Processed District TPs for Partner: {tp.name}"))

        self.stdout.write(self.style.SUCCESS(
            f"\nFinished Execution:\n"
            f"- MasterUsers Created: {total_created_users}\n"
            f"- DistrictTPs Created: {total_created_dtps}\n"
            f"- GeoScopes Created: {total_created_scopes}"
        ))