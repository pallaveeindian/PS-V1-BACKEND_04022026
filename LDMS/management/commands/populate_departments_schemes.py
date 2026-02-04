from django.core.management.base import BaseCommand
from LDMS.models import Department, Scheme


class Command(BaseCommand):
    help = "Populate predefined Departments and their Schemes"

    def handle(self, *args, **options):
        # Define departments and linked schemes (FULL DATA)
        data = {
            "AGRICULTURE": [
                {
                    "code": "AGR-PM-KISAN",
                    "name": "PRADHAN MANTRI KISAN SAMMAN NIDHI",
                    "assistance": (
                        "₹6,000 per year per eligible farmer family, paid as "
                        "3 equal instalments of ₹2,000 through DBT."
                    ),
                    "elligibility": (
                        "Landholding farmers. Serving/retired officers and employees "
                        "of Central/State Government (except Class IV) are excluded."
                    ),
                    "scope": "CENTRAL",
                    "funding": "100% GOI",
                    "contact_point": "District Agriculture Officer (DAO)",
                },
                {
                    "code": "AGR-PM-KMY",
                    "name": "PRADHAN MANTRI KISAN MAANDHAN YOJANA",
                    "assistance": (
                        "Monthly pension of ₹3,000 after age 60. Farmer contributes "
                        "monthly amount to LIC-managed pension fund with equal GOI contribution."
                    ),
                    "elligibility": (
                        "Age 18–40 years, landholders up to 2 HA, not a member of "
                        "EPFO/ESIC/NPS and not an income tax payer."
                    ),
                    "scope": "CENTRAL",
                    "funding": "100% GOI",
                    "contact_point": "District Agriculture Officer (DAO)",
                },
                {
                    "code": "AGR-PM-FBY",
                    "name": "PRADHAN MANTRI FASAL BIMA YOJANA",
                    "assistance": (
                        "Crop insurance for Kharif and Rabi seasons with subsidised premium: "
                        "2% for Kharif crops, 1.5% for Rabi crops; remaining premium shared "
                        "50:50 between Centre and State."
                    ),
                    "elligibility": (
                        "KYC-verified bank account, crop insurance linked to KCC, "
                        "enrolment before cut-off date."
                    ),
                    "scope": "CENTRAL",
                    "funding": "50% GOI, 50% UPGOV",
                    "contact_point": "District Agriculture Officer (DAO)",
                },
                {
                    "code": "AGR-NFSM",
                    "name": "NATIONAL FOOD SECURITY MISSION",
                    "assistance": (
                        "Seed minikits, subsidy for certified seeds, plant protection, "
                        "nutrient management, farm implements and capacity building."
                    ),
                    "elligibility": "All farmers can apply.",
                    "scope": "CENTRAL",
                    "funding": "100% GOI",
                    "contact_point": "District Agriculture Officer (DAO)",
                },
                {
                    "code": "AGR-PM-RKVY",
                    "name": "RASHTRIYA KRISHI VIKAS YOJANA",
                    "assistance": "Funding support for state-designed agricultural projects.",
                    "elligibility": (
                        "Farmers, FPOs, SHGs, Cooperatives, Agri-Startups and other beneficiaries."
                    ),
                    "scope": "CENTRAL",
                    "funding": "100% GOI",
                    "contact_point": "Deputy Director Agriculture (DDA)",
                },
                {
                    "code": "AGR-SMAM",
                    "name": "SUB-MISSION ON AGRICULTURAL MECHANISATION",
                    "assistance": (
                        "Capital subsidy on tractors, power tillers, harvesters, seed drills, "
                        "planters, weeders and plant protection equipment."
                    ),
                    "elligibility": (
                        "Individual farmers, FPOs, SHGs, cooperative societies, "
                        "panchayats and agri-entrepreneurs."
                    ),
                    "scope": "CENTRAL",
                    "funding": "100% GOI",
                    "contact_point": "District Agriculture Officer (DAO)",
                },
                {
                    "code": "AGR-KTY-UP",
                    "name": "KHET TALAB YOJANA (FARM POND SCHEME – UP)",
                    "assistance": (
                        "Subsidy for construction of standard-size farm pond with additional "
                        "support for micro-irrigation and pump sets as per government orders."
                    ),
                    "elligibility": (
                        "Pond must follow prescribed dimensions and be GPS-tagged. "
                        "Preference to SC/ST, women, marginal and small farmers."
                    ),
                    "scope": "STATE",
                    "funding": "100% UPGOV",
                    "contact_point": "District Agriculture Officer (DAO)",
                },
                {
                    "code": "AGR-MFS-UP",
                    "name": "KISAN PATHSHALA / MILLION FARMER SCHOOL",
                    "assistance": (
                        "Large-scale farmer training programmes conducted twice a year "
                        "at Panchayat/GP level."
                    ),
                    "elligibility": (
                        "Any farmer can attend; priority to small & marginal farmers, "
                        "women and youth."
                    ),
                    "scope": "STATE",
                    "funding": "100% UPGOV",
                    "contact_point": "Deputy Director Agriculture (DDA)",
                },
                {
                    "code": "AGR-PKUSY-UP",
                    "name": "PRASHIKSHIT KRISHI UDYAMI SWAVALAMBAN (AGRI-JUNCTION) YOJANA",
                    "assistance": (
                        "Entrepreneurship training, financial assistance and facilitation "
                        "for agricultural input centres."
                    ),
                    "elligibility": (
                        "Agriculture graduates/postgraduates from recognised universities; "
                        "preference to unemployed rural youth."
                    ),
                    "scope": "STATE",
                    "funding": "100% UPGOV",
                    "contact_point": "Deputy Director Agriculture (DDA)",
                },
            ],
        }

        self.stdout.write("Seeding departments and schemes…")

        for dept_name, schemes in data.items():
            dept_obj, _ = Department.objects.get_or_create(name=dept_name)
            self.stdout.write(f"Department ready: {dept_name}")

            for scheme in schemes:
                scheme_obj, created = Scheme.objects.get_or_create(
                    department=dept_obj,
                    code=scheme["code"],
                    defaults={
                        "name": scheme["name"],
                        "assistance": scheme.get("assistance"),
                        "elligibility": scheme.get("elligibility"),
                        "scope": scheme.get("scope"),
                        "funding": scheme.get("funding"),
                        "contact_point": scheme.get("contact_point"),
                    },
                )

                if created:
                    self.stdout.write(f"  → Added scheme: {scheme['name']}")
                else:
                    self.stdout.write(f"  → Scheme already exists: {scheme['name']}")

        self.stdout.write(
            self.style.SUCCESS("Departments & Schemes populated successfully!")
        )
