import csv
from django.core.management.base import BaseCommand
from LDMS.models import Department, Scheme
from django.db import transaction

class Command(BaseCommand):
    help = "Import Departments and Schemes from CSV"

    def add_arguments(self, parser):
        parser.add_argument(
            '--file',
            type=str,
            required=True,
            help='Path to CSV file'
        )

    @transaction.atomic
    def handle(self, *args, **options):
        file_path = options['file']

        self.stdout.write(self.style.WARNING(f"Reading file: {file_path}"))

        with open(file_path, newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)

            for row in reader:
                department_name = row.get('Department', '').strip()
                scheme_name = row.get('Scheme Name', '').strip()

                if not department_name or not scheme_name:
                    continue  # skip invalid rows

                # ---- Department ----
                department, _ = Department.objects.get_or_create(
                    name=department_name
                )

                # ---- Scheme ----
                Scheme.objects.get_or_create(
                    department=department,
                    name=scheme_name,
                    defaults={
                        'code': row.get('Scheme Code', '').strip() or None,
                        'assistance': row.get('Assistance', '').strip() or None,
                        'elligibility': row.get('Eligibility', '').strip() or None,
                        'scope': row.get('Scope', '').strip() or None,
                        'funding': row.get('Funding', '').strip() or None,
                        'contact_point': row.get('Contact Point', '').strip() or None,
                    }
                )

        self.stdout.write(self.style.SUCCESS("✅ Departments & Schemes imported successfully"))
