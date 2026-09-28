import os
import csv
from django.core.management.base import BaseCommand
from django.db import transaction
from TMS.models import StaffProfile, TrainingTheme

class RollbackTransactionException(Exception):
    """Custom exception used strictly to force a graceful transaction rollback."""
    pass

class Command(BaseCommand):
    help = 'Extremely verbose interactive script to map and update StaffProfile themes from STAFFtheme_push.csv.'

    def handle(self, *args, **options):
        # 1. Resolve dynamic path to CSV in the exact same directory as this script
        current_dir = os.path.dirname(os.path.abspath(__file__))
        csv_path = os.path.join(current_dir, 'STAFFtheme_push.csv')

        if not os.path.exists(csv_path):
            self.stdout.write(self.style.ERROR(f"CRITICAL ERROR: CSV file not found at expected path: {csv_path}"))
            return

        self.stdout.write(self.style.WARNING(f"\n[INIT] Starting verbose execution using file: {csv_path}"))

        # 2. Database Caching (Performance Optimization)
        self.stdout.write("[INIT] Querying active TrainingThemes into memory cache...")
        # Dictionary mapping lowercase theme names to actual model instances
        themes_cache = {
            t.theme_name.strip().lower(): t 
            for t in TrainingTheme.objects.filter(is_active=True) 
            if t.theme_name
        }
        self.stdout.write(self.style.SUCCESS(f"       -> Cached {len(themes_cache)} Training Themes."))

        self.stdout.write("[INIT] Querying active StaffProfiles into memory cache...")
        # Dictionary mapping exact employee_id to actual model instances
        staff_cache = {
            s.employee_id.strip(): s 
            for s in StaffProfile.objects.filter(is_active=True, employee_id__isnull=False)
        }
        self.stdout.write(self.style.SUCCESS(f"       -> Cached {len(staff_cache)} Staff Profiles.\n"))

        success_count = 0
        errors = []

        try:
            # 3. Enter the absolute Atomic Transaction block
            with transaction.atomic():
                self.stdout.write(self.style.WARNING("=========================================================="))
                self.stdout.write(self.style.WARNING(">>> ENTERED ATOMIC TRANSACTION DATABASE LOCK ZONE <<<"))
                self.stdout.write(self.style.WARNING("=========================================================="))

                with open(csv_path, mode='r', encoding='utf-8-sig') as file:
                    # Smart CSV Reader: Handles both comma separated and tab separated (Excel copy-paste)
                    header_check = file.readline()
                    file.seek(0)
                    delimiter = '\t' if '\t' in header_check else ','
                    
                    reader = csv.DictReader(file, delimiter=delimiter)
                    
                    # Clean up header names to ensure exact matches
                    headers = [h.strip() for h in reader.fieldnames if h]
                    
                    if 'Employee ID' not in headers or 'THEME' not in headers:
                        raise Exception(
                            f"CSV must strictly contain 'Employee ID' and 'THEME' column headers. "
                            f"Detected headers: {headers}"
                        )

                    # 4. Process CSV line by line
                    for row_number, row in enumerate(reader, start=2): # start=2 accounts for header row
                        emp_id_raw = row.get('Employee ID', '')
                        theme_raw = row.get('THEME', '')

                        # Validation A: Empty Employee ID
                        if not emp_id_raw:
                            err = f"Row {row_number} | FAILED | Empty Employee ID column."
                            self.stdout.write(self.style.ERROR(err))
                            errors.append(err)
                            continue

                        # Validation B: Empty Theme
                        if not theme_raw:
                            err = f"Row {row_number} | FAILED | Empty THEME column for Employee ID '{emp_id_raw}'."
                            self.stdout.write(self.style.ERROR(err))
                            errors.append(err)
                            continue

                        emp_id = emp_id_raw.strip()
                        theme_name_clean = theme_raw.strip().lower()

                        # Validation C: Staff Profile Existence
                        staff = staff_cache.get(emp_id)
                        if not staff:
                            err = f"Row {row_number} | FAILED | StaffProfile with Employee ID '{emp_id}' DOES NOT EXIST in database."
                            self.stdout.write(self.style.ERROR(err))
                            errors.append(err)
                            continue

                        # Validation D: Theme Existence
                        theme = themes_cache.get(theme_name_clean)
                        if not theme:
                            err = f"Row {row_number} | FAILED | TrainingTheme with name '{theme_raw}' DOES NOT EXIST in database."
                            self.stdout.write(self.style.ERROR(err))
                            errors.append(err)
                            continue

                        # Core Update Action
                        old_theme_name = staff.theme.theme_name if staff.theme else "None"
                        
                        if staff.theme == theme:
                            self.stdout.write(f"Row {row_number} | SKIPPED | Employee '{emp_id}' already has theme '{theme.theme_name}' assigned.")
                            continue

                        # Apply changes to the object in memory and save it to the DB (within the transaction)
                        staff.theme = theme
                        staff.save(update_fields=['theme', 'updated_at'])
                        success_count += 1

                        self.stdout.write(self.style.SUCCESS(
                            f"Row {row_number} | SUCCESS | Employee: {emp_id} | Theme Override: [{old_theme_name}] -> [{theme.theme_name}]"
                        ))

                # 5. Post-Processing Logging & Diagnostics
                self.stdout.write("\n" + "="*60)
                self.stdout.write(self.style.WARNING("                 TRANSACTION DIAGNOSTICS & SUMMARY"))
                self.stdout.write("="*60)
                
                self.stdout.write(self.style.SUCCESS(f"🟢 Total Successful Database Updates Pending Commit: {success_count}"))
                
                if errors:
                    self.stdout.write(self.style.ERROR(f"🔴 Total Corrupt/Failed Rows Detected: {len(errors)}"))
                    self.stdout.write("\n--- EXHAUSTIVE ERROR LOG ---")
                    for e in errors:
                        self.stdout.write(self.style.ERROR(f"  * {e}"))
                else:
                    self.stdout.write(self.style.SUCCESS(f"🟢 Total Corrupt/Failed Rows Detected: {len(errors)}"))
                    self.stdout.write(self.style.SUCCESS("\n--- EXHAUSTIVE ERROR LOG ---"))
                    self.stdout.write(self.style.SUCCESS("  * No errors encountered. 100% clean mapping run."))
                
                self.stdout.write("="*60)

                # 6. Interactive Database Gateway (Commit or Abort)
                self.stdout.write(self.style.WARNING("\nWARNING: You are currently holding an active database lock."))
                user_input = input("Do you want to permanently COMMIT these changes to the database? Type 'yes' to proceed, or anything else to abort: ").strip().lower()

                if user_input == 'yes':
                    self.stdout.write(self.style.SUCCESS("\n[+] Authorized. Committing transaction to database... Done!"))
                    # Exiting the 'with transaction.atomic():' block normally automatically issues the SQL COMMIT.
                else:
                    self.stdout.write(self.style.ERROR("\n[-] Abort instruction received. Triggering manual rollback..."))
                    # Raising a specific exception forces Django to discard the atomic block and issue an SQL ROLLBACK.
                    raise RollbackTransactionException("User consciously rejected the pending database changes.")

        except RollbackTransactionException as e:
            self.stdout.write(self.style.WARNING(f"\n<<< TRANSACTION COMPLETELY REVERTED: {str(e)} >>>"))
            self.stdout.write(self.style.WARNING("Zero changes were written to the database. Exiting cleanly.\n"))
            
        except Exception as e:
            # Catches Python errors (like FileIO or KeyErrors) and safely rolls back the DB before crashing out.
            self.stdout.write(self.style.ERROR(f"\n<<< FATAL SYSTEM ERROR DURING TRANSACTION: {str(e)} >>>"))
            self.stdout.write(self.style.ERROR("Transaction failed and was reverted automatically for safety.\n"))