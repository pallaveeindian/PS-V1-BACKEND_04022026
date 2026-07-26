import csv
import os
from django.core.management.base import BaseCommand
from django.db import transaction
from TMS.models import Bank, BankBranch, BankIFSC

class Command(BaseCommand):
    help = 'Extremely verbose command to load bank details from a CSV file.'

    def add_arguments(self, parser):
        parser.add_argument(
            'csv_file', 
            type=str, 
            help='The absolute or relative path to the bank.csv file'
        )

    def handle(self, *args, **kwargs):
        csv_file_path = kwargs['csv_file']

        # Check if the file exists
        if not os.path.exists(csv_file_path):
            self.stdout.write(self.style.ERROR(f"❌ ERROR: File not found at path: {csv_file_path}"))
            return

        self.stdout.write(self.style.SUCCESS(f"🚀 Starting to process CSV file: {csv_file_path}\n"))

        # Open and read the CSV
        with open(csv_file_path, mode='r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            
            # Using a transaction ensures that if something crashes drastically, we don't end up with partial junk
            with transaction.atomic():
                for row_number, row in enumerate(reader, start=1):
                    self.stdout.write(self.style.NOTICE(f"\n{'='*50}"))
                    self.stdout.write(self.style.NOTICE(f"📄 READING ROW {row_number}: {row}"))
                    self.stdout.write(self.style.NOTICE(f"{'='*50}"))

                    # Extract and cleanly format the data (Strip whitespaces and uppercase to prevent duplicates)
                    raw_bank_name = row.get('Bank Name', '').strip()
                    raw_branch_name = row.get('Branch Name', '').strip()
                    raw_ifsc_code = row.get('IFSC Code', '').strip()

                    # Skip if the bank name is totally empty
                    if not raw_bank_name:
                        self.stdout.write(self.style.ERROR(f"⚠️  Row {row_number}: Bank Name is empty. Skipping entire row."))
                        continue

                    bank_name = raw_bank_name.upper()
                    branch_name = raw_branch_name.upper()
                    ifsc_code = raw_ifsc_code.upper()

                    # ---------------------------------------------------------
                    # 1. PROCESS BANK
                    # ---------------------------------------------------------
                    self.stdout.write(f"🔍 [1/3] Evaluating Bank: '{bank_name}'...")
                    bank_obj, bank_created = Bank.objects.get_or_create(bank_name=bank_name)
                    
                    if bank_created:
                        self.stdout.write(self.style.SUCCESS(f"   ✅ CREATED: New Bank saved to database -> '{bank_name}' (ID: {bank_obj.id})"))
                    else:
                        self.stdout.write(self.style.WARNING(f"   ⏭️  SKIPPED: Bank '{bank_name}' already exists (ID: {bank_obj.id})."))

                    # ---------------------------------------------------------
                    # 2. PROCESS BANK BRANCH
                    # ---------------------------------------------------------
                    if branch_name:
                        self.stdout.write(f"🔍 [2/3] Evaluating Branch: '{branch_name}' for Bank '{bank_name}'...")
                        branch_obj, branch_created = BankBranch.objects.get_or_create(
                            branch_name=branch_name,
                            bank=bank_obj
                        )
                        
                        if branch_created:
                            self.stdout.write(self.style.SUCCESS(f"   ✅ CREATED: New Branch saved to database -> '{branch_name}' (ID: {branch_obj.id})"))
                        else:
                            self.stdout.write(self.style.WARNING(f"   ⏭️  SKIPPED: Branch '{branch_name}' already exists for this Bank."))
                    else:
                        self.stdout.write(self.style.ERROR(f"   ⚠️  [2/3] No Branch Name provided in row {row_number}. Skipping branch creation."))

                    # ---------------------------------------------------------
                    # 3. PROCESS BANK IFSC
                    # ---------------------------------------------------------
                    if ifsc_code:
                        self.stdout.write(f"🔍 [3/3] Evaluating IFSC Code: '{ifsc_code}' for Bank '{bank_name}'...")
                        ifsc_obj, ifsc_created = BankIFSC.objects.get_or_create(
                            ifsc_code=ifsc_code,
                            bank=bank_obj
                        )
                        
                        if ifsc_created:
                            self.stdout.write(self.style.SUCCESS(f"   ✅ CREATED: New IFSC saved to database -> '{ifsc_code}' (ID: {ifsc_obj.id})"))
                        else:
                            self.stdout.write(self.style.WARNING(f"   ⏭️  SKIPPED: IFSC '{ifsc_code}' already exists for this Bank."))
                    else:
                        self.stdout.write(self.style.ERROR(f"   ⚠️  [3/3] No IFSC Code provided in row {row_number}. Skipping IFSC creation."))

        self.stdout.write(self.style.SUCCESS(f"\n🎉 SUCCESS: Finished processing the CSV file completely!"))