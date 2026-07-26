import csv
import os
import re
from datetime import datetime, timedelta
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from TMS.models import StaffProfile, TrainingTheme, Bank, BankBranch, BankIFSC
from core.models import MasterDistrict, MasterBlock

class Command(BaseCommand):
    help = 'Extremely verbose command to load staff from CSV with intelligent lookups, detailed logging, and a manual rollback failsafe.'

    def add_arguments(self, parser):
        parser.add_argument('csv_file', type=str, help='Path to the StaffList.csv file')

    def parse_excel_date(self, date_str):
        """Converts Excel serial dates (e.g., 44197) or standard date strings into aware datetimes."""
        if not date_str or str(date_str).strip() in ['NA', '', 'None']:
            return None
        
        date_str = str(date_str).strip()
        try:
            # Excel uses days since Dec 30, 1899
            serial = float(date_str)
            base_date = datetime(1899, 12, 30)
            return timezone.make_aware(base_date + timedelta(days=serial))
        except ValueError:
            # Fallback if it's already a standard string date (YYYY-MM-DD)
            from dateutil import parser
            try:
                return timezone.make_aware(parser.parse(date_str))
            except:
                return None

    def handle(self, *args, **kwargs):
        csv_file_path = kwargs['csv_file']
        log_file_path = 'LOG.csv'

        if not os.path.exists(csv_file_path):
            self.stdout.write(self.style.ERROR(f"❌ ERROR: File not found at {csv_file_path}"))
            return

        self.stdout.write(self.style.SUCCESS(f"🚀 Initializing Staff Upload from: {csv_file_path}\n"))

        rows_processed = 0
        success_count = 0
        failed_count = 0
        log_records = []

        try:
            # The entire process is wrapped in one massive transaction
            with transaction.atomic():
                with open(csv_file_path, mode='r', encoding='utf-8-sig') as file:
                    reader = csv.DictReader(file)
                    
                    # Capture exact original headers and add our auditing headers
                    original_headers = reader.fieldnames
                    log_headers = original_headers + ['Status', 'Reason']

                    for row in reader:
                        rows_processed += 1
                        sno = row.get('S.N.', str(rows_processed)).strip()
                        emp_id = row.get('Employee ID', '').strip()
                        emp_name = row.get('Name', '').strip()
                        
                        self.stdout.write(self.style.NOTICE(f"\n{'='*60}"))
                        self.stdout.write(self.style.NOTICE(f"📄 PROCESSING ROW {sno}: {emp_name} ({emp_id})"))
                        self.stdout.write(self.style.NOTICE(f"{'='*60}"))

                        row_status = "Failed"
                        failure_reason = ""

                        try:
                            # ---------------------------------------------------------
                            # 1. SCIENTIFIC NOTATION CHECK (Data Protection)
                            # ---------------------------------------------------------
                            aadhar_val = row.get('Aadhar', '').strip()
                            account_val = row.get('Account No ', '').strip() # Notice trailing space in your CSV header
                            
                            if 'E+' in str(aadhar_val).upper() or 'E+' in str(account_val).upper():
                                raise ValueError("Scientific notation (E+) detected. Format column as 'Number' in Excel before exporting to prevent data loss.")

                            # ---------------------------------------------------------
                            # 2. THEME LOOKUP (Intelligent Bracket Parsing)
                            # ---------------------------------------------------------
                            theme_str = row.get('Theme', '').strip()
                            theme_obj = None
                            if theme_str:
                                self.stdout.write(f"  🔍 Searching Theme: '{theme_str}'...")
                                # Attempt 1: Exact Match
                                theme_obj = TrainingTheme.objects.filter(theme_name__iexact=theme_str).first()
                                
                                # Attempt 2: Match content inside brackets
                                if not theme_obj:
                                    bracket_match = re.search(r'\((.*?)\)', theme_str)
                                    if bracket_match:
                                        inner_text = bracket_match.group(1).strip()
                                        theme_obj = TrainingTheme.objects.filter(theme_name__icontains=inner_text).first()
                                
                                # Attempt 3: Fallback to loose partial match
                                if not theme_obj:
                                    theme_obj = TrainingTheme.objects.filter(theme_name__icontains=theme_str).first()

                                if theme_obj:
                                    self.stdout.write(self.style.SUCCESS(f"     ✅ Found Theme: {theme_obj.theme_name}"))
                                else:
                                    self.stdout.write(self.style.WARNING(f"     ⚠️ Theme not found. Leaving blank."))

                            # ---------------------------------------------------------
                            # 3. DISTRICT & BLOCK LOOKUP (Strict Hierarchy)
                            # ---------------------------------------------------------
                            district_str = row.get('District', '').strip()
                            block_str = row.get('Block', '').strip()
                            district_obj = None
                            block_obj = None

                            if district_str:
                                self.stdout.write(f"  🔍 Searching District: '{district_str}'...")
                                district_obj = MasterDistrict.objects.filter(district_name_en__iexact=district_str).first()
                                if district_obj:
                                    self.stdout.write(self.style.SUCCESS(f"     ✅ Found District: {district_obj.district_name_en}"))
                                    
                                    if block_str:
                                        self.stdout.write(f"  🔍 Searching Block: '{block_str}' inside {district_obj.district_name_en}...")
                                        block_obj = MasterBlock.objects.filter(
                                            district=district_obj, 
                                            block_name_en__iexact=block_str
                                        ).first()
                                        
                                        if block_obj:
                                            self.stdout.write(self.style.SUCCESS(f"     ✅ Found Block: {block_obj.block_name_en}"))
                                        else:
                                            self.stdout.write(self.style.WARNING(f"     ⚠️ Block not found. Leaving blank."))
                                else:
                                    self.stdout.write(self.style.ERROR(f"     ❌ District '{district_str}' not found!"))
                                    raise ValueError(f"District '{district_str}' does not exist in MasterDistrict.")

                            # ---------------------------------------------------------
                            # 4. BANK, BRANCH & IFSC LOOKUP (Strict Hierarchy)
                            # ---------------------------------------------------------
                            bank_str = row.get('Bank Name', '').strip()
                            branch_str = row.get('Branch Name', '').strip()
                            ifsc_str = row.get('IFSC Code', '').strip()
                            
                            bank_obj = None
                            branch_obj = None
                            ifsc_obj = None

                            if bank_str and bank_str.upper() != 'NA':
                                self.stdout.write(f"  🔍 Searching Bank: '{bank_str}'...")
                                bank_obj = Bank.objects.filter(bank_name__iexact=bank_str).first()
                                
                                if bank_obj:
                                    self.stdout.write(self.style.SUCCESS(f"     ✅ Found Bank: {bank_obj.bank_name}"))
                                    
                                    if branch_str and branch_str.upper() != 'NA':
                                        branch_obj = BankBranch.objects.filter(bank=bank_obj, branch_name__iexact=branch_str).first()
                                        if branch_obj: self.stdout.write(self.style.SUCCESS(f"     ✅ Found Branch: {branch_obj.branch_name}"))
                                        
                                    if ifsc_str and ifsc_str.upper() != 'NA':
                                        ifsc_obj = BankIFSC.objects.filter(bank=bank_obj, ifsc_code__iexact=ifsc_str).first()
                                        if ifsc_obj: self.stdout.write(self.style.SUCCESS(f"     ✅ Found IFSC: {ifsc_obj.ifsc_code}"))
                                else:
                                    self.stdout.write(self.style.WARNING(f"     ⚠️ Bank '{bank_str}' not found in DB."))

                            # ---------------------------------------------------------
                            # 5. ASSEMBLE AND CREATE STAFF PROFILE
                            # ---------------------------------------------------------
                            self.stdout.write(f"  ⚙️  Parsing Dates & creating record...")
                            
                            # Clean numeric strings of 'NA'
                            def clean_val(v): return '' if v.strip().upper() == 'NA' else v.strip()

                            # Create the profile
                            staff, created = StaffProfile.objects.update_or_create(
                                employee_id=emp_id,
                                defaults={
                                    'mobile': clean_val(row.get('Mobile', '')),
                                    'email': clean_val(row.get('Email', '')),
                                    'full_name': emp_name,
                                    'designation': clean_val(row.get('Designation ', '')), # Note trailing space in your header
                                    'employment_type': clean_val(row.get('Employment Type', '')),
                                    'theme': theme_obj,
                                    'doj': self.parse_excel_date(row.get('DoJ', '')),
                                    'dob': self.parse_excel_date(row.get('DoB', '')),
                                    'gender': clean_val(row.get('Gender', '')),
                                    'marital_status': clean_val(row.get('Marital Status', '')),
                                    'district': district_obj,
                                    'block': block_obj,
                                    'perma_address': clean_val(row.get('Permanent Address', '')),
                                    'current_address': clean_val(row.get('Current Address', '')),
                                    'program': clean_val(row.get('Program', '')),
                                    'social_category': clean_val(row.get('Social Category', '')),
                                    'aadhar': int(float(aadhar_val)) if clean_val(aadhar_val) else 0, # Validator requires integer
                                    'pan': clean_val(row.get('Pan', '')),
                                    'uan': clean_val(row.get('UAN', '')),
                                    'epf': clean_val(row.get('EPF', '')),
                                    'esic': clean_val(row.get('ESIC', '')),
                                    'bank': bank_obj,
                                    'bank_branch': branch_obj,
                                    'bank_ifsc': ifsc_obj,
                                    'bank_account_no': clean_val(account_val),
                                }
                            )

                            if created:
                                self.stdout.write(self.style.SUCCESS(f"  🎉 SUCCESS: Created new Staff Profile (ID: {staff.id})"))
                            else:
                                self.stdout.write(self.style.SUCCESS(f"  🔄 SUCCESS: Updated existing Staff Profile (ID: {staff.id})"))
                            
                            row_status = "Success"
                            success_count += 1

                        except Exception as e:
                            failed_count += 1
                            failure_reason = str(e)
                            self.stdout.write(self.style.ERROR(f"  ❌ FAILED: {failure_reason}"))

                        # Log row outcome
                        log_row = row.copy()
                        log_row['Status'] = row_status
                        log_row['Reason'] = failure_reason
                        log_records.append(log_row)

                # ---------------------------------------------------------
                # 6. WRITE LOG & TRIGGER FAILSAFE PROMPT
                # ---------------------------------------------------------
                # Write to LOG.csv before deciding on commit, so you have the report either way
                with open(log_file_path, mode='w', encoding='utf-8', newline='') as logfile:
                    writer = csv.DictWriter(logfile, fieldnames=log_headers)
                    writer.writeheader()
                    writer.writerows(log_records)

                self.stdout.write(self.style.NOTICE(f"\n{'*'*60}"))
                self.stdout.write(self.style.NOTICE(f"📊 SUMMARY REPORT"))
                self.stdout.write(self.style.NOTICE(f"{'*'*60}"))
                self.stdout.write(f"Total Rows Processed: {rows_processed}")
                self.stdout.write(self.style.SUCCESS(f"Ready to Insert/Update: {success_count}"))
                self.stdout.write(self.style.ERROR(f"Failed Rows: {failed_count}"))
                self.stdout.write(f"Detailed log written to: {os.path.abspath(log_file_path)}")
                
                self.stdout.write(self.style.WARNING(f"\n⚠️  THE DATABASE IS CURRENTLY LOCKED IN A TRANSACTION."))
                user_input = input("Are you absolutely sure you want to commit these changes? Type 'yes' to save, or press any other key to ROLLBACK: ")

                if user_input.strip().lower() != 'yes':
                    raise Exception("MANUAL_ROLLBACK_INITIATED")

        except Exception as e:
            if str(e) == "MANUAL_ROLLBACK_INITIATED":
                self.stdout.write(self.style.ERROR(f"\n🛑 ROLLBACK EXECUTED. No data was saved to the database."))
            else:
                self.stdout.write(self.style.ERROR(f"\n💥 CRITICAL ERROR: Transaction aborted due to unexpected failure: {str(e)}"))
        else:
            self.stdout.write(self.style.SUCCESS(f"\n✅ COMMIT EXECUTED. Data has been permanently saved to the database."))