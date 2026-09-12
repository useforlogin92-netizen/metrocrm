"""Idempotently seed a Godrej Nest test inventory into a configured MetroCRM database.

Run manually against a test/staging database only, or call seed_godrej_nest_test(db)
from an explicitly authorized admin workflow.
Prices are indicative test values and are deliberately marked in descriptions.
"""
from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog_models import PropertyMedia
from app.database import SessionLocal
from app.models import Developer, Project, Tower, Unit

AMENITIES = [
    "7-Tier Security", "RFID-enabled campus", "Swimming Pool", "Kids' Pool",
    "Gym/Fitness Centre", "Outdoor Gym", "Jogging Track", "Kids Play Area",
    "Basketball/Multipurpose Court", "Amphitheatre with Pergola", "Senior Citizen Area",
    "Outdoor Creche Area", "Multipurpose Lawn", "Yoga/Zumba Studio", "Meditation Room",
    "Acupressure Path", "Fitness Centre", "Kids Activity Centre",
]

OFFICIAL_GALLERY = [
    ("Godrej Nest Location AV", "https://gplwebsitecdn.blob.core.windows.net/godrej-cdn/Images/Godrej-Nest-Location-AV1d270baa-8bdb-4974-b5d3-87be44a88f22.jpg", "LOCATION_MAP"),
    ("Godrej Nest Concept AV", "https://gplwebsitecdn.blob.core.windows.net/godrej-cdn/Images/Godrej-Nest-Concept-AV3eaa4a00-728e-4978-be49-f8adf033993a.jpg", "EXTERIOR"),
    ("Godrej Nest Project Walkthrough AV", "https://gplwebsitecdn.blob.core.windows.net/godrej-cdn/Images/Godrej-Nest-Concept-AV255599ab-540f-4f65-835b-c22f3f17309a.jpg", "EXTERIOR"),
    ("Godrej Nest Sample Flat AV", "https://gplwebsitecdn.blob.core.windows.net/godrej-cdn/Images/Godrej-Nest-Sample-flat-AVcbf7be22-6425-4397-b481-4d03500ce27.jpg", "INTERIOR"),
]

UNITS = [
    ("A-TEST-2BHK-606", "Wing A", "2 BHK", 606, 20_000_000, 33_003),
    ("A-TEST-3BHK-860", "Wing A", "3 BHK", 860, 28_300_000, 32_907),
    ("C-TEST-1BHK-428", "Wing C", "1 BHK", 428, 14_100_000, 32_944),
    ("C-TEST-2BHK-680", "Wing C", "2 BHK", 680, 22_400_000, 32_941),
]


def seed_godrej_nest_test(db: Session) -> tuple[int, int, int]:
    """Create/update the Godrej Nest test project, four units and four gallery items."""
    developer = db.scalar(select(Developer).where(Developer.name == "Godrej Properties Limited"))
    if not developer:
        developer = Developer(name="Godrej Properties Limited", contact="https://www.godrejproperties.com", details="Test data: project brochure identifies Shivam Megastructures Private Limited as developer and Godrej Properties Limited as Development Manager.")
        db.add(developer)
        db.flush()

    project = db.scalar(select(Project).where(Project.name == "Godrej Nest", Project.city == "Mumbai", Project.locality == "Kandivali East"))
    if not project:
        project = Project(developer_id=developer.id, name="Godrej Nest", state="Maharashtra", district="Mumbai Suburban", city="Mumbai", locality="Kandivali East", sector="Akurli Road", address="Godrej Nest Sales Pavilion, Near Lokhandwala Circle, Opp. Living Essence Building, Off Akurli Road, Kandivali East, Mumbai", pincode="400101", rera="P51800022159", possession_date=datetime(2024, 6, 30), construction_status="READY_TO_MOVE", amenities_json=json.dumps(AMENITIES), brochure="https://www.godrejproperties.com/mumbai/residential/godrej-nest/landingpage/landingpage", description="TEST DATA — Godrej Nest. Prices are indicative test values compiled from current online market listings; verify against the latest developer cost sheet before client use.")
        db.add(project)
        db.flush()
    else:
        project.developer_id = developer.id
        project.state = "Maharashtra"
        project.district = "Mumbai Suburban"
        project.address = "Godrej Nest Sales Pavilion, Near Lokhandwala Circle, Opp. Living Essence Building, Off Akurli Road, Kandivali East, Mumbai"
        project.pincode = "400101"
        project.rera = "P51800022159"
        project.construction_status = "READY_TO_MOVE"
        project.possession_date = datetime(2024, 6, 30)
        project.amenities_json = json.dumps(AMENITIES)
        project.brochure = "https://www.godrejproperties.com/mumbai/residential/godrej-nest/landingpage/landingpage"
        project.description = "TEST DATA — Godrej Nest. Prices are indicative test values compiled from current online market listings; verify against the latest developer cost sheet before client use."

    towers = {}
    for name, floors in (("Wing A", 32), ("Wing B", 32), ("Wing C", 48), ("Wing D", 48)):
        tower = db.scalar(select(Tower).where(Tower.project_id == project.id, Tower.name == name))
        if not tower:
            tower = Tower(project_id=project.id, name=name, floors=floors, possession_date=datetime(2024, 6, 30), details="TEST DATA — verify exact live inventory before client use.")
            db.add(tower)
            db.flush()
        else:
            tower.floors = floors
            tower.possession_date = datetime(2024, 6, 30)
            tower.details = "TEST DATA — verify exact live inventory before client use."
        towers[name] = tower

    for unit_number, tower_name, bhk, carpet, price, rate in UNITS:
        unit = db.scalar(select(Unit).where(Unit.project_id == project.id, Unit.unit_number == unit_number))
        values = dict(project_id=project.id, tower_id=towers[tower_name].id, unit_number=unit_number, bhk=bhk, property_type="APARTMENT", carpet_area=carpet, price=price, price_per_sqft=rate, parking="As per inventory", possession="Ready to Move", rera="P51800022159", availability="AVAILABLE", status="ACTIVE", amenities_json="[]", photos_json="[]", description=f"{bhk} test configuration for Godrej Nest. Indicative test price only: ₹{price:,}. Verify current cost sheet.", other_details="TEST DATA — DO NOT USE AS A LIVE QUOTE.")
        if not unit:
            db.add(Unit(**values))
        else:
            for key, value in values.items():
                setattr(unit, key, value)

    for order, (title, url, media_type) in enumerate(OFFICIAL_GALLERY):
        media = db.scalar(select(PropertyMedia).where(PropertyMedia.project_id == project.id, PropertyMedia.unit_id.is_(None), PropertyMedia.title == title))
        if not media:
            db.add(PropertyMedia(project_id=project.id, unit_id=None, media_type=media_type, title=title, file_url=url, storage_key=None, mime_type="image/jpeg", sort_order=order, is_shareable=True))
        else:
            media.file_url = url
            media.sort_order = order
            media.is_shareable = True

    db.flush()
    return project.id, len(UNITS), len(OFFICIAL_GALLERY)


def main() -> None:
    db = SessionLocal()
    try:
        project_id, unit_count, gallery_count = seed_godrej_nest_test(db)
        db.commit()
        print(f"Seeded Godrej Nest test inventory: project_id={project_id}, units={unit_count}, gallery_images={gallery_count}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
