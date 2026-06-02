from epSakhi.models import DistMOUTarget
from core.models import MasterDistrict
from django.utils import timezone

targets = [
    ("AGRA", 992),
    ("ALIGARH", 744),
    ("AMBEDKAR NAGAR", 558),
    ("AMETHI", 806),
    ("AMROHA", 372),
    ("AURAIYA", 434),
    ("AYODHYA (FAIZABAD)", 682),
    ("AZAMGARH", 1426),
    ("BAGHPAT", 372),
    ("BAHRAICH", 868),
    ("BALLIA", 1054),
    ("BALRAMPUR", 558),
    ("BANDA", 496),
    ("BARABANKI", 930),
    ("BAREILLY", 930),
    ("BASTI", 868),
    ("BIJNOR", 682),
    ("BUDAUN", 1116),
    ("BULANDSHAHR", 992),
    ("CHANDAULI", 558),
    ("CHITRAKOOT", 310),
    ("DEORIA", 992),
    ("ETAH", 496),
    ("ETAWAH", 496),
    ("FARRUKHABAD", 434),
    ("FATEHPUR", 806),
    ("FIROZABAD", 310),
    ("GAUTAM BUDDHA NAGAR", 248),
    ("GHAZIABAD", 248),
    ("GHAZIPUR", 992),
    ("GONDA", 992),
    ("GORAKHPUR", 1240),
    ("HAMIRPUR", 434),
    ("HAPUR", 248),
    ("HARDOI", 1240),
    ("HATHRAS", 434),
    ("JALAUN", 558),
    ("JAUNPUR", 1364),
    ("JHANSI", 496),
    ("KANNAUJ", 496),
    ("KANPUR DEHAT", 620),
    ("KANPUR NAGAR", 620),
    ("KASGANJ", 434),
    ("KAUSHAMBI", 496),
    ("KHERI", 930),
    ("KUSHI NAGAR", 868),
    ("LALITPUR", 372),
    ("LUCKNOW", 496),
    ("MAHARAJGANJ", 744),
    ("MAHOBA", 248),
    ("MAINPURI", 558),
    ("MATHURA", 620),
    ("MAU", 558),
    ("MEERUT", 744),
    ("MIRZAPUR", 744),
    ("MORADABAD", 496),
    ("MUZAFFARNAGAR", 558),
    ("PILIBHIT", 434),
    ("PRATAPGARH", 1054),
    ("PRAYAGRAJ (ALLAHABAD)", 1302),
    ("RAE BARELI", 1116),
    ("RAMPUR", 372),
    ("SAHARANPUR", 682),
    ("SAMBHAL", 496),
    ("SANT KABEER NAGAR", 558),
    ("SANT RAVIDAS NAGAR", 310),
    ("SHAHJAHANPUR", 930),
    ("SHAMLI", 310),
    ("SHRAVASTI", 310),
    ("SIDDHARTH NAGAR", 868),
    ("SITAPUR", 1240),
    ("SONBHADRA", 496),
    ("SULTANPUR", 868),
    ("UNNAO", 992),
    ("VARANASI", 496),
]

financial_year = "2026-27"

for district_name, target in targets:

    # handle special district name mappings
    search_name = district_name

    if district_name == "AYODHYA (FAIZABAD)":
        search_name = "AYODHYA"

    elif district_name == "PRAYAGRAJ (ALLAHABAD)":
        search_name = "PRAYAGRAJ"

    district = MasterDistrict.objects.filter(
        district_name_en__iexact=search_name
    ).first()

    if not district:
        print(f"District NOT FOUND: {district_name}")
        continue

    obj, created = DistMOUTarget.objects.update_or_create(
        district=district,
        financial_year=financial_year,
        defaults={
            "mou_target": target,
            "achieved_mou": 0,
        }
    )

    action = "CREATED" if created else "UPDATED"

    print(
        f"{action} -> "
        f"{district.district_name_en} | "
        f"Target: {target}"
    )

print("Done")