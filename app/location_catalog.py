"""India location catalogue and real-estate search priorities.

The Mumbai catalogue covers the main suburban corridors used for caller-led
property searches. Station records keep corridor and city metadata so future
inventory imports can map properties deterministically.
"""

COUNTRY = "India"
INDIA_STATES_AND_UTS = [
    "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh", "Goa",
    "Gujarat", "Haryana", "Himachal Pradesh", "Jharkhand", "Karnataka", "Kerala",
    "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya", "Mizoram", "Nagaland",
    "Odisha", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana", "Tripura",
    "Uttar Pradesh", "Uttarakhand", "West Bengal", "Andaman and Nicobar Islands",
    "Chandigarh", "Dadra and Nagar Haveli and Daman and Diu", "Delhi", "Jammu and Kashmir",
    "Ladakh", "Lakshadweep", "Puducherry",
]

MAJOR_CITIES = [
    ("Maharashtra", "Mumbai", 100), ("Maharashtra", "Pune", 95), ("Maharashtra", "Thane", 95),
    ("Maharashtra", "Navi Mumbai", 95), ("Maharashtra", "Kalyan-Dombivli", 90),
    ("Maharashtra", "Vasai-Virar", 90), ("Maharashtra", "Panvel", 88),
    ("Maharashtra", "Mira-Bhayandar", 88), ("Maharashtra", "Bhiwandi", 85),
    ("Maharashtra", "Palghar", 82), ("Maharashtra", "Nashik", 75), ("Maharashtra", "Nagpur", 75),
    ("Gujarat", "Ahmedabad", 80), ("Gujarat", "Surat", 75), ("Karnataka", "Bengaluru", 80),
    ("Telangana", "Hyderabad", 80), ("Tamil Nadu", "Chennai", 80), ("Delhi", "New Delhi", 80),
    ("West Bengal", "Kolkata", 75), ("Rajasthan", "Jaipur", 70), ("Uttar Pradesh", "Noida", 75),
    ("Uttar Pradesh", "Lucknow", 70), ("Uttar Pradesh", "Ghaziabad", 72), ("Haryana", "Gurugram", 78),
    ("Kerala", "Kochi", 70),
]


def _stations(names: list[str], corridor: str, city: str = "Mumbai") -> list[dict[str, str]]:
    return [{"name": name, "corridor": corridor, "city": city} for name in names]


# Main Mumbai suburban corridors. The order within each list is the travel
# order used for From -> To range matching.
MUMBAI_LOCAL_STATIONS = (
    _stations([
        "Churchgate", "Marine Lines", "Charni Road", "Grant Road", "Mumbai Central", "Mahalaxmi",
        "Lower Parel", "Prabhadevi", "Dadar", "Matunga Road", "Mahim Junction", "Bandra", "Khar Road",
        "Santacruz", "Vile Parle", "Andheri", "Jogeshwari", "Ram Mandir", "Goregaon", "Malad",
        "Kandivali", "Borivali", "Dahisar", "Mira Road", "Bhayandar", "Naigaon", "Vasai Road",
        "Nalasopara", "Virar", "Vaitarna", "Saphale", "Kelva Road", "Palghar", "Umroli", "Boisar",
        "Vangaon", "Dahanu Road",
    ], "Western")
    + _stations([
        "Chhatrapati Shivaji Maharaj Terminus", "Masjid", "Sandhurst Road", "Byculla", "Chinchpokli",
        "Currey Road", "Parel", "Dadar", "Matunga", "Sion", "Kurla", "Vidyavihar", "Ghatkopar",
        "Vikhroli", "Kanjurmarg", "Bhandup", "Nahur", "Mulund", "Thane", "Kalwa", "Mumbra",
        "Diva", "Kopar", "Dombivli", "Thakurli", "Kalyan", "Vithalwadi", "Ulhasnagar", "Ambernath",
        "Chikhloli", "Badlapur", "Vangani", "Shelu", "Neral", "Bhivpuri Road", "Karjat", "Palasdhari",
        "Kelavli", "Dolavli", "Lowjee", "Khopoli", "Shahad", "Ambivli", "Titwala", "Khadavli", "Vasind",
        "Asangaon", "Atgaon", "Tanshet", "Khardi", "Umbermali", "Kasara",
    ], "Central")
    + _stations([
        "Chhatrapati Shivaji Maharaj Terminus", "Masjid", "Sandhurst Road", "Dockyard Road", "Reay Road",
        "Cotton Green", "Sewri", "Wadala Road", "Guru Tegh Bahadur Nagar", "Chunabhatti", "Kurla",
        "Tilak Nagar", "Chembur", "Govandi", "Mankhurd", "Vashi", "Sanpada", "Juinagar", "Nerul",
        "Seawoods-Darave", "CBD Belapur", "Kharghar", "Mansarovar", "Khandeshwar", "Panvel", "Goregaon",
        "Jogeshwari",
    ], "Harbour")
    + _stations([
        "Thane", "Digha Gaon", "Airoli", "Rabale", "Ghansoli", "Koparkhairane", "Turbhe", "Sanpada",
        "Vashi", "Juinagar", "Nerul", "Seawoods-Darave", "CBD Belapur", "Kharghar", "Mansarovar",
        "Khandeshwar", "Panvel",
    ], "Trans-Harbour")
    + _stations([
        "Nerul", "Seawoods-Darave", "Belapur CBD", "Bamandongri", "Kharkopar", "Uran",
    ], "Nerul-Uran", city="Navi Mumbai")
    + _stations([
        "Vasai Road", "Juchandra", "Kaman Road", "Kharbao", "Bhiwandi Road", "Kopar", "Diva",
        "Nilaje", "Taloja Panchnand", "Navade Road", "Kalamboli", "Panvel", "Apta", "Rasayani",
        "Sev", "Nagothane", "Roha",
    ], "Vasai-Roha")
)

# A simple canonical lookup remains useful for station-only property records.
MUMBAI_STATION_ORDER = {}
for station in MUMBAI_LOCAL_STATIONS:
    MUMBAI_STATION_ORDER.setdefault(station["name"].casefold(), len(MUMBAI_STATION_ORDER))

MUMBAI_PRIORITY_DISTRICTS = {"Mumbai City", "Mumbai Suburban", "Thane", "Palghar", "Raigad"}
PUNE_PRIORITY_DISTRICTS = {"Pune", "Raigad", "Satara", "Ahmednagar", "Nashik"}
REGIONAL_PRIORITY = {
    "Mumbai": 100, "Navi Mumbai": 98, "Thane": 96, "Mira-Bhayandar": 94,
    "Kalyan-Dombivli": 92, "Bhiwandi": 90, "Vasai-Virar": 90, "Panvel": 88,
    "Palghar": 82, "Pune": 100, "Pimpri-Chinchwad": 96, "Lonavala": 88,
}


def location_priority(*, city: str | None = None, district: str | None = None, state: str | None = None) -> int:
    if city:
        key = city.strip().casefold()
        for name, score in REGIONAL_PRIORITY.items():
            if name.casefold() == key:
                return score
    if district in MUMBAI_PRIORITY_DISTRICTS or district in PUNE_PRIORITY_DISTRICTS:
        return 80
    if state == "Maharashtra":
        return 60
    return 0


def mumbai_station_index(name: str | None) -> int | None:
    return MUMBAI_STATION_ORDER.get(str(name or "").strip().casefold())


def mumbai_station_range_matches(*, property_station: str | None, from_station: str | None,
                                 to_station: str | None, side: str = "Both",
                                 property_side: str = "Both", corridor: str | None = None) -> bool:
    """Match a property to a Mumbai station range and optional East/West side."""
    if not from_station and not to_station:
        return True

    wanted_from = str(from_station or "").strip().casefold()
    wanted_to = str(to_station or "").strip().casefold()
    wanted_corridor = str(corridor or "").strip().casefold()

    matching_corridors = []
    for item in MUMBAI_LOCAL_STATIONS:
        name = item["name"].casefold()
        if (not wanted_from or name == wanted_from) and (not wanted_to or name == wanted_to):
            if not wanted_corridor or item["corridor"].casefold() == wanted_corridor:
                matching_corridors.append(item["corridor"])
    if not matching_corridors:
        # Try corridor from the first endpoint when the two names are on the
        # same corridor; otherwise a missing corridor is treated as invalid.
        matching_corridors = [item["corridor"] for item in MUMBAI_LOCAL_STATIONS
                              if item["name"].casefold() in {wanted_from, wanted_to}
                              and (not wanted_corridor or item["corridor"].casefold() == wanted_corridor)]
    if not matching_corridors:
        return False

    property_name = str(property_station or "").strip().casefold()
    actual_side = str(property_side or "Both").strip().casefold()
    requested_side = str(side or "Both").strip().casefold()

    for selected_corridor in dict.fromkeys(matching_corridors):
        ordered = [item["name"].casefold() for item in MUMBAI_LOCAL_STATIONS if item["corridor"] == selected_corridor]
        if wanted_from and wanted_from not in ordered:
            continue
        if wanted_to and wanted_to not in ordered:
            continue
        if property_name not in ordered:
            continue
        start = ordered.index(wanted_from) if wanted_from else ordered.index(property_name)
        end = ordered.index(wanted_to) if wanted_to else ordered.index(property_name)
        if start <= ordered.index(property_name) <= end or end <= ordered.index(property_name) <= start:
            if requested_side == "both" or actual_side == "both" or actual_side == requested_side:
                return True
    return False
