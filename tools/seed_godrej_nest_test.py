"""Idempotently seed a Godrej Nest test inventory into the configured MetroCRM database.

Run manually against a test/staging database only:
    python tools/seed_godrej_nest_test.py

Prices are indicative test values and are deliberately marked in descriptions.
"""
from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import select

from app.database import SessionLocal
from app.models import Developer, Project, Tower, Unit

AMENITIES = [
    "7-Tier Security", "RFID-enabled campus", "Swimming Pool", "Kids' Pool",
    "Gym/Fitness Centre", "Outdoor Gym", "Jogging Track", "Kids Play Area",
    "Basketball/Multipurpose Court", "Amphitheatre with Pergola", "Senior Citizen Area",
    "Outdoor Creche Area", "Multipurpose Lawn", "Yoga/Zumba Studio", "Meditation Room",
    "Acupressure Path", "Fitness Centre", "Kids Activity Centre",
]

UNITS = [
    ("A-TEST-2BHK-606", "Wing A", "2 BHK", 606, 20_000_000, 33_003),
    ("A-TEST-3BHK-860", "Wing A", "3 BHK", 860, 28_300_000, 32_907),
    ("C-TEST-1BHK-428", "Wing C", "1 BHK", 428, 14_100_000, 32_944),
    ("C-TEST-2BHK-680", "Wing C", "2 BHK", 680, 22_400_000, 32_941),
]


def main() -> None:
    db = SessionLocal()
    try:
        developer = db.scalar(select(Developer).where(Developer.name == "Godrej Properties Limited"))
        if not developer:
            developer = Developer(name="Godrej Properties Limited", contact="https://www.godrejproperties.com", details="Test data: project brochure identifies Shivam Megastructures Private Limited as developer and Godrej Properties Limited as Development Manager.")
            db.add(developer)
            db.flush()

        project = db.scalar(select(Project).where(Project.name == "Godrej Nest", Project.city == "Mumbai", Project.locality == "Kandivali East"))
        if not project:
            project = Project(developer_id=developer.id, name="Godrej Nest", state="Maharashtra", district="Mumbai Suburban", city="Mumbai", locality="Kandivali East", sector="Akurli Road", address="Godrej Nest Sales Pavilion, Near Lokhandwala Circle, Opp. Living Essence Building, Off Akurli Road, Kandivali East, Mumbai", pincode="400101", rera="P51800022159", possession_date=datetime(2024, 6, 30), construction_status="READY_TO_MOVE", amenities_json=json.dumps(AMENITIES), brochure="https://www.godrejproperties.com/mumbai/residential/godrej-nest/landingpage/landingpage", description="Test inventory for Godrej Nest. Prices are indicative test values compiled from current online market listings; verify against the latest developer cost sheet before client use.")
            db.add(project)
            db.flush()
        else:
            project.developer_id = developer.id
            project.rera = "P51800022159"
            project.construction_status = "READY_TO_MOVE"
            project.possession_date = datetime(2024, 6, 30)
            project.amenities_json = json.dumps(AMENITIES)

        towers = {}
        for name, floors in (("Wing A", 32), ("Wing B", 32), ("Wing C", 48), ("Wing D", 48)):
            tower = db.scalar(select(Tower).where(Tower.project_id == project.id, Tower.name == name))
            if not tower:
                tower = Tower(project_id=project.id, name=name, floors=floors, possession_date=datetime(2024, 6, 30), details="Test tower record; verify exact live inventory before client use.")
                db.add(tower)
                db.flush()
            towers[name] = tower

        for unit_number, tower_name, bhk, carpet, price, rate in UNITS:
            unit = db.scalar(select(Unit).where(Unit.project_id == project.id, Unit.unit_number == unit_number))
            values = dict(project_id=project.id, tower_id=towers[tower_name].id, unit_number=unit_number, bhk=bhk, property_type="APARTMENT", carpet_area=carpet, price=price, price_per_sqft=rate, parking="As per inventory", possession="Ready to Move", rera="P51800022159", availability="AVAILABLE", status="ACTIVE", amenities_json="[]", photos_json="[]", description=f"{bhk} test configuration for Godrej Nest. Indicative test price only: ₹{price:,}. Verify current cost sheet.", other_details="TEST DATA — DO NOT USE AS A LIVE QUOTE.")
            if not unit:
                db.add(Unit(**values))
            else:
                for key, value in values.items():
                    setattr(unit, key, value)

        db.commit()
        print(f"Seeded Godrej Nest test inventory: project_id={project.id}, units={len(UNITS)}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
