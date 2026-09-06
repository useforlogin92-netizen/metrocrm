"""India location catalogue and real-estate search priorities.

The catalogue is deliberately seed-oriented: it contains every current Indian
state/UT plus a curated set of major cities and the Mumbai/Pune target belt.
The database location master can later be populated with a complete city,
locality and PIN dataset without changing the matching contract.
"""

COUNTRY = "India"

INDIA_STATES_AND_UTS = [
    "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh",
    "Goa", "Gujarat", "Haryana", "Himachal Pradesh", "Jharkhand",
    "Karnataka", "Kerala", "Madhya Pradesh", "Maharashtra", "Manipur",
    "Meghalaya", "Mizoram", "Nagaland", "Odisha", "Punjab", "Rajasthan",
    "Sikkim", "Tamil Nadu", "Telangana", "Tripura", "Uttar Pradesh",
    "Uttarakhand", "West Bengal",
    "Andaman and Nicobar Islands", "Chandigarh", "Dadra and Nagar Haveli and Daman and Diu",
    "Delhi", "Jammu and Kashmir", "Ladakh", "Lakshadweep", "Puducherry",
]

# Major-city seed set. The location master is designed to accept the complete
# India city/locality/PIN dataset later.
MAJOR_CITIES = [
    ("Maharashtra", "Mumbai", 100),
    ("Maharashtra", "Pune", 95),
    ("Maharashtra", "Thane", 95),
    ("Maharashtra", "Navi Mumbai", 95),
    ("Maharashtra", "Kalyan-Dombivli", 90),
    ("Maharashtra", "Vasai-Virar", 90),
    ("Maharashtra", "Panvel", 88),
    ("Maharashtra", "Mira-Bhayandar", 88),
    ("Maharashtra", "Bhiwandi", 85),
    ("Maharashtra", "Palghar", 82),
    ("Maharashtra", "Nashik", 75),
    ("Maharashtra", "Nagpur", 75),
    ("Gujarat", "Ahmedabad", 80),
    ("Gujarat", "Surat", 75),
    ("Karnataka", "Bengaluru", 80),
    ("Telangana", "Hyderabad", 80),
    ("Tamil Nadu", "Chennai", 80),
    ("Delhi", "New Delhi", 80),
    ("West Bengal", "Kolkata", 75),
    ("Rajasthan", "Jaipur", 70),
    ("Uttar Pradesh", "Noida", 75),
    ("Uttar Pradesh", "Lucknow", 70),
    ("Uttar Pradesh", "Ghaziabad", 72),
    ("Haryana", "Gurugram", 78),
    ("Kerala", "Kochi", 70),
]

# Higher-priority Mumbai/Pune catchment. This is a ranking preference, not a
# hard filter: an exact customer PIN/city match still wins over a priority area.
MUMBAI_PRIORITY_DISTRICTS = {"Mumbai City", "Mumbai Suburban", "Thane", "Palghar", "Raigad"}
PUNE_PRIORITY_DISTRICTS = {"Pune", "Raigad", "Satara", "Ahmednagar", "Nashik"}

REGIONAL_PRIORITY = {
    "Mumbai": 100,
    "Navi Mumbai": 98,
    "Thane": 96,
    "Mira-Bhayandar": 94,
    "Kalyan-Dombivli": 92,
    "Bhiwandi": 90,
    "Vasai-Virar": 90,
    "Panvel": 88,
    "Palghar": 82,
    "Pune": 100,
    "Pimpri-Chinchwad": 96,
    "Lonavala": 88,
}


def location_priority(*, city: str | None = None, district: str | None = None, state: str | None = None) -> int:
    """Return a deterministic ranking priority for property search."""
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
