"""India location catalogue and real-estate search priorities.

The catalogue is seed-oriented but includes a detailed Mumbai local-station
search index so callers can select a station-to-station range, East/West side,
or both sides. Matching uses these values as a deterministic location filter.
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

# Mumbai suburban/local search index, in railway-corridor order.
MUMBAI_LOCAL_STATIONS = [
    {"name": "Churchgate", "corridor": "Western", "city": "Mumbai"},
    {"name": "Marine Lines", "corridor": "Western", "city": "Mumbai"},
    {"name": "Charni Road", "corridor": "Western", "city": "Mumbai"},
    {"name": "Grant Road", "corridor": "Western", "city": "Mumbai"},
    {"name": "Mumbai Central", "corridor": "Western", "city": "Mumbai"},
    {"name": "Mahalaxmi", "corridor": "Western", "city": "Mumbai"},
    {"name": "Lower Parel", "corridor": "Western", "city": "Mumbai"},
    {"name": "Prabhadevi", "corridor": "Western", "city": "Mumbai"},
    {"name": "Dadar", "corridor": "Western", "city": "Mumbai"},
    {"name": "Matunga Road", "corridor": "Western", "city": "Mumbai"},
    {"name": "Mahim Junction", "corridor": "Western", "city": "Mumbai"},
    {"name": "Bandra", "corridor": "Western", "city": "Mumbai"},
    {"name": "Khar Road", "corridor": "Western", "city": "Mumbai"},
    {"name": "Santacruz", "corridor": "Western", "city": "Mumbai"},
    {"name": "Vile Parle", "corridor": "Western", "city": "Mumbai"},
    {"name": "Andheri", "corridor": "Western", "city": "Mumbai"},
    {"name": "Jogeshwari", "corridor": "Western", "city": "Mumbai"},
    {"name": "Ram Mandir", "corridor": "Western", "city": "Mumbai"},
    {"name": "Goregaon", "corridor": "Western", "city": "Mumbai"},
    {"name": "Malad", "corridor": "Western", "city": "Mumbai"},
    {"name": "Kandivali", "corridor": "Western", "city": "Mumbai"},
    {"name": "Borivali", "corridor": "Western", "city": "Mumbai"},
    {"name": "Dahisar", "corridor": "Western", "city": "Mumbai"},
    {"name": "Mira Road", "corridor": "Western", "city": "Thane"},
    {"name": "Bhayandar", "corridor": "Western", "city": "Thane"},
    {"name": "Naigaon", "corridor": "Western", "city": "Palghar"},
    {"name": "Vasai Road", "corridor": "Western", "city": "Palghar"},
    {"name": "Nalasopara", "corridor": "Western", "city": "Palghar"},
    {"name": "Virar", "corridor": "Western", "city": "Palghar"},
]
MUMBAI_STATION_ORDER = {station["name"].casefold(): index for index, station in enumerate(MUMBAI_LOCAL_STATIONS)}

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
                                 property_side: str = "Both") -> bool:
    """Match a property to a Mumbai station range and East/West/Both side."""
    if not from_station and not to_station:
        return True
    property_index = mumbai_station_index(property_station)
    if property_index is None:
        return False
    start = mumbai_station_index(from_station) if from_station else property_index
    end = mumbai_station_index(to_station) if to_station else property_index
    if start is None or end is None:
        return False
    low, high = sorted((start, end))
    if not low <= property_index <= high:
        return False
    requested = str(side or "Both").strip().casefold()
    actual = str(property_side or "Both").strip().casefold()
    if requested == "both" or actual == "both":
        return True
    return actual == requested
