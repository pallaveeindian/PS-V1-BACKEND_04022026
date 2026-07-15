import os
import csv
import random
from django.core.management.base import BaseCommand
from django.db import transaction
from core.models import MasterUser, MasterDistrict
from TMS.models import MasterTrainer, TrainingTheme

class Command(BaseCommand):
    help = "Extremely verbose and atomic import of Master Trainers. Aggressively sanitizes data to prevent length errors."

    def add_arguments(self, parser):
        parser.add_argument(
            'csv_filename', 
            nargs='?', 
            type=str, 
            default='trainers.csv', 
            help='The name of the CSV file in the same folder as this script (default: trainers.csv).'
        )

    def get_unique_username(self):
        """Generates a strictly unique username in the format drpXXXX."""
        while True:
            # Generate a random 4-digit number padded with zeros (e.g., 0042)
            num_str = f"{random.randint(1, 9999):04d}"
            username = f"drp{num_str}"
            
            # STRICTLY ensure uniqueness
            if not MasterUser.objects.filter(username=username).exists():
                return username

    def generate_th_urid(self):
        """Helper to generate TH_urid for new MasterUser rows."""
        chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        body = ''.join(random.choices(chars, k=11))
        return f"TH_{body}"

    def handle(self, *args, **options):
        # Automatically locate the CSV in the exact same folder as this script file
        script_dir = os.path.dirname(os.path.abspath(__file__))
        csv_filename = options['csv_filename']
        csv_file_path = os.path.join(script_dir, csv_filename)
        
        # Output Log File Path
        log_file_path = os.path.join(script_dir, 'import_errors_log.txt')
        
        updated_count = 0
        created_count = 0
        skipped_count = 0
        
        # Keep track of skipped rows for final summary and log file
        skipped_rows_log = []

        self.stdout.write(self.style.WARNING(f"\n=================================================="))
        self.stdout.write(self.style.WARNING(f"🚀 STARTING MASTER TRAINER IMPORT SCRIPT"))
        self.stdout.write(self.style.WARNING(f"📁 CSV FILE PATH: {csv_file_path}"))
        self.stdout.write(self.style.WARNING(f"📝 LOG FILE PATH: {log_file_path}"))
        self.stdout.write(self.style.WARNING(f"🛡️ MODE: ATOMIC TRANSACTION (Safe to cancel anytime)"))
        self.stdout.write(self.style.WARNING(f"==================================================\n"))

        if not os.path.exists(csv_file_path):
            self.stdout.write(self.style.ERROR(f"\n❌ FATAL ERROR: The file '{csv_filename}' was not found in {script_dir}."))
            return

        try:
            with open(csv_file_path, mode='r', encoding='utf-8-sig') as file:
                reader = csv.DictReader(file)
                
                # Sanitize headers (strip leading/trailing whitespaces from column names)
                reader.fieldnames = [header.strip() for header in reader.fieldnames]

                # ALL DATABASE OPERATIONS WRAPPED IN ONE ATOMIC BLOCK
                with transaction.atomic():
                    for row_idx, row in enumerate(reader, start=1):
                        self.stdout.write(f"\n--- Processing Row {row_idx} ---")
                        
                        # ==========================================
                        # AGGRESSIVE DATA SANITIZATION
                        # ==========================================
                        
                        # 1. Clean Mobile Number (Remove .0 from excel floats, keep only digits/+, slice to 20)
                        raw_mobile = str(row.get('MOBILE NUMBER', '')).strip()
                        if raw_mobile.endswith('.0'):
                            raw_mobile = raw_mobile[:-2]
                        mobile_no = ''.join(c for c in raw_mobile if c.isdigit() or c == '+')[:20]

                        # 2. Clean District
                        district_name = str(row.get('DISTRICT', '')).strip()
                        
                        if not mobile_no or not district_name:
                            error_msg = f"Missing Mobile No ('{mobile_no}') or District ('{district_name}')"
                            self.stdout.write(self.style.ERROR(f"[ROW {row_idx} SKIPPED] {error_msg}"))
                            skipped_rows_log.append(f"Row {row_idx} | REASON: {error_msg} | RAW DATA: {row}")
                            skipped_count += 1
                            continue

                        # 1. District Matching
                        self.stdout.write(f"🔍 Looking up District: '{district_name}'")
                        district_obj = MasterDistrict.objects.filter(district_name_en__iexact=district_name).first()
                        if not district_obj:
                            error_msg = f"District '{district_name}' not found in DB"
                            self.stdout.write(self.style.ERROR(f"[ROW {row_idx} SKIPPED] {error_msg}"))
                            skipped_rows_log.append(f"Row {row_idx} | REASON: {error_msg} | RAW DATA: {row}")
                            skipped_count += 1
                            continue
                        self.stdout.write(self.style.SUCCESS(f"   ✓ District matched: {district_obj.district_name_en} (ID: {district_obj.district_id})"))

                        # 2. Strict Theme Matching
                        theme_name = str(row.get('Theme', '')).strip()
                        if not theme_name:
                            error_msg = "Theme cell is empty in CSV"
                            self.stdout.write(self.style.ERROR(f"[ROW {row_idx} SKIPPED] {error_msg}"))
                            skipped_rows_log.append(f"Row {row_idx} | REASON: {error_msg} | RAW DATA: {row}")
                            skipped_count += 1
                            continue

                        self.stdout.write(f"🔍 Looking up Theme: '{theme_name}'")
                        theme_obj = TrainingTheme.objects.filter(theme_name__iexact=theme_name).first()
                        if not theme_obj:
                            error_msg = f"Theme '{theme_name}' not found in DB"
                            self.stdout.write(self.style.ERROR(f"[ROW {row_idx} SKIPPED] {error_msg}"))
                            skipped_rows_log.append(f"Row {row_idx} | REASON: {error_msg} | RAW DATA: {row}")
                            skipped_count += 1
                            continue
                            
                        self.stdout.write(self.style.SUCCESS(f"   ✓ Theme matched: {theme_obj.theme_name} (ID: {theme_obj.id})"))

                        # Extract & truncate string details to match database schema exactly
                        name = str(row.get('NAME OF DRP', '')).strip()[:200]
                        father_name = str(row.get('FATHERS NAME/', '')).strip()[:200]
                        
                        # Designation strictly limited to 3 characters (e.g., 'DRP')
                        designation = str(row.get('DESIGNATION', '')).strip()[:3].upper()
                        
                        # Safe Aadhaar extraction (Strip .0 and non-digits, limit to 20)
                        raw_aadhaar = str(row.get('AADHAR NUMBER', '')).strip()
                        if raw_aadhaar.endswith('.0'):
                            raw_aadhaar = raw_aadhaar[:-2]
                            
                        if raw_aadhaar.upper() in ['N/A', 'NA', '']:
                            aadhaar_clean = None
                        else:
                            aadhaar_clean = ''.join(filter(str.isdigit, raw_aadhaar))[:20]

                        # Boolean Extractions
                        def parse_bool(col_name):
                            return str(row.get(col_name, '')).strip().upper() == 'YES'

                        induction = parse_bool('Inducttion (YES/NO)')
                        tot_smcb = parse_bool('TOT SMCB (YES/NO)')
                        tot_mffi = parse_bool('TOT MFFI (YES/NO)')
                        tot_sisd = parse_bool('TOT SISD (YES/NO)')
                        tot_farm_lh = parse_bool('TOT FARM LH (YES/NO)')
                        tot_non_farm_lh = parse_bool('TOT NON FARM LH (YES/NO)')
                        tot_model_clf = parse_bool('TOT MODEL CLF (YES/NO)')
                        tot_lokos = parse_bool('TOT LOKOS (YES/NO)')

                        # 3. Check if Trainer Exists
                        self.stdout.write(f"🔍 Checking existence by Mobile: {mobile_no} + District: {district_obj.district_id}")
                        trainer = MasterTrainer.objects.filter(
                            mobile_no=mobile_no, 
                            empanel_district=district_obj
                        ).first()

                        if trainer:
                            # ==========================================
                            # UPDATE EXISTING TRAINER
                            # ==========================================
                            self.stdout.write(self.style.NOTICE(f"   📝 TRAINER FOUND! Updating records for {trainer.full_name}..."))
                            
                            trainer.full_name = name
                            trainer.parent_or_spouse_name = father_name
                            trainer.designation = designation
                            trainer.theme = theme_obj
                            trainer.aadhaar_no = aadhaar_clean
                            
                            # Update booleans
                            trainer.induction = induction
                            trainer.tot_smcb = tot_smcb
                            trainer.tot_mffi = tot_mffi
                            trainer.tot_sisd = tot_sisd
                            trainer.tot_farm_lh = tot_farm_lh
                            trainer.tot_non_farm_lh = tot_non_farm_lh
                            trainer.tot_model_clf = tot_model_clf
                            trainer.tot_lokos = tot_lokos

                            trainer.save()
                            
                            self.stdout.write(self.style.SUCCESS(
                                f"   ✅ UPDATED -> Name: {name} | Theme: {theme_obj.theme_name} | "
                                f"Desig: {designation} | Aadhaar: {'[Aadhaar Redacted]' if aadhaar_clean else 'N/A'} | "
                                f"Mobile: {mobile_no}"
                            ))
                            updated_count += 1

                        else:
                            # ==========================================
                            # CREATE NEW TRAINER & MASTER USER
                            # ==========================================
                            self.stdout.write(self.style.WARNING(f"   ✨ TRAINER NOT FOUND. Initiating creation protocol..."))
                            
                            # Generate unique username
                            new_username = self.get_unique_username()
                            self.stdout.write(f"   -> Generated strictly unique username: {new_username}")
                            
                            # Create Master User
                            new_master_user = MasterUser(
                                username=new_username,
                                is_active=1,
                                is_suspended=0,
                                is_locked=0,
                                TH_urid=self.generate_th_urid()
                            )
                            # Assign default password securely in CLEARTEXT
                            new_master_user.password = "mt@tms"
                            new_master_user.save()
                            self.stdout.write(self.style.SUCCESS(f"   ✓ MasterUser Created in cleartext (ID: {new_master_user.id})"))

                            # Create Master Trainer
                            new_trainer = MasterTrainer.objects.create(
                                master_user=new_master_user,
                                full_name=name,
                                parent_or_spouse_name=father_name,
                                mobile_no=mobile_no,
                                empanel_district=district_obj,
                                designation=designation,
                                theme=theme_obj,
                                aadhaar_no=aadhaar_clean,
                                induction=induction,
                                tot_smcb=tot_smcb,
                                tot_mffi=tot_mffi,
                                tot_sisd=tot_sisd,
                                tot_farm_lh=tot_farm_lh,
                                tot_non_farm_lh=tot_non_farm_lh,
                                tot_model_clf=tot_model_clf,
                                tot_lokos=tot_lokos
                            )
                            self.stdout.write(self.style.SUCCESS(f"   ✅ CREATED -> Trainer {name} mapped to {new_username} successfully!"))
                            created_count += 1

            # End of File Processing
            self.stdout.write(self.style.SUCCESS(f"\n=================================================="))
            self.stdout.write(self.style.SUCCESS(f"🎉 IMPORT COMPLETED SUCCESSFULLY!"))
            self.stdout.write(self.style.SUCCESS(f"=================================================="))
            self.stdout.write(self.style.SUCCESS(f"   Total Rows Processed : {updated_count + created_count + skipped_count}"))
            self.stdout.write(self.style.SUCCESS(f"   Newly Created        : {created_count}"))
            self.stdout.write(self.style.SUCCESS(f"   Successfully Updated : {updated_count}"))
            self.stdout.write(self.style.ERROR(f"   Skipped / Errors     : {skipped_count}"))
            
            # Print Console Summary of Skipped
            if skipped_rows_log:
                self.stdout.write(self.style.ERROR(f"\n--- SKIPPED ROWS SUMMARY ---"))
                self.stdout.write(self.style.ERROR(f"⚠️ {len(skipped_rows_log)} rows failed to import. Checking log.txt is highly recommended."))
            
            self.stdout.write(self.style.SUCCESS(f"==================================================\n"))

        except Exception as e:
            # Because we are in an atomic transaction block, any crash here automatically reverses all DB creations/updates.
            self.stdout.write(self.style.ERROR(f"\n❌ FATAL ERROR ENCOUNTERED: {str(e)}"))
            self.stdout.write(self.style.ERROR(f"🛑 ATOMIC TRANSACTION TRIGGERED: ALL DATABASE CHANGES HAVE BEEN ROLLED BACK."))
            skipped_rows_log.append(f"\nFATAL TRANSACTION ABORT ERROR: {str(e)}")

        finally:
            # Always export the log file if there were any errors/skips, even if the transaction crashed
            if skipped_rows_log:
                try:
                    with open(log_file_path, mode='w', encoding='utf-8') as log_file:
                        log_file.write("=========================================================\n")
                        log_file.write("           MASTER TRAINER IMPORT - ERROR LOG             \n")
                        log_file.write("=========================================================\n\n")
                        
                        for entry in skipped_rows_log:
                            log_file.write(f"{entry}\n\n")
                            
                    self.stdout.write(self.style.WARNING(f"📄 Detailed error log saved to: {log_file_path}\n"))
                except Exception as log_err:
                    self.stdout.write(self.style.ERROR(f"Failed to write log file: {str(log_err)}"))