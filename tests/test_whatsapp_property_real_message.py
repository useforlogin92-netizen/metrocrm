from app.services.whatsapp_property_import import parse_property_text


REAL_WHATSAPP_PROPERTY = """_💎 SETHIA INFRASTRUCTURE 💎_
_PRESENTS THE CROWN OF KANDIVALI

_🏢 SETHIA PRIDE 🏢_
_ON WESTERN EXPRESS HIGHWAY, KANDIVALI EAST_

_🔥 KANDIVALI'S MOST DESIRED LOCATION 🔥_
✨ On W.E. Highway - The Heartbeat of Mumbai
✨ 2 Min Walk - Poisar Metro
✨ 5 Min Walk - Kandivali Railway Station
✨ 40 Storey Iconic Tower
✨ 30+ World-Class Amenities
✨ Infinity Rooftop Swimming Pool

_🏗️ A-WING NEARING POSSESSION IN 6 TO 7 MONTHS 🏗️_

_A - WING_
🏠 1 BHK - 365 Sq.ft - 1.13 Cr++ - Only 1 Left!
🏠 1 BHK - 395 Sq.ft - 1.22 Cr++ - Only 2 Left!
🏠 2 BHK - 520 Sq.ft - 1.60 Cr++
_B - WING - DECK RESIDENCES_
🏠 2 BHK - 590 Sq.ft - 1.56 Cr++
🏠 2 BHK - 620 Sq.ft - 1.64 Cr++
📍 LOCATION: NEXT TO MAHINDRA GATE, W.E.H, KANDIVALI EAST
https://goo.gl/maps/f9zJatKz3WNvhA7j8
_FOR BEST DEAL & SITE VISIT:_
_ALTAMAS_
_Sourcing Manager - Sethia_
📞 9920854306"""


def test_real_whatsapp_message_extracts_only_source_stated_property_data():
    parsed = parse_property_text(REAL_WHATSAPP_PROPERTY)
    assert parsed["developer"] == "Sethia Infrastructure"
    assert "Sethia Pride" in parsed["project_candidates"]
    assert parsed["city"] == "Mumbai"
    assert parsed["locality"] == "Kandivali East"
    assert "NEXT TO MAHINDRA GATE" in parsed["address"]
    assert parsed["map_url"].startswith("https://goo.gl/maps/")
    assert parsed["contact_phone"] == "9920854306"
    assert parsed["possession_text"]
    assert parsed["total_building_floors"] == 40
    assert len(parsed["unit_configurations"]) == 5
    assert [x["carpet_area"] for x in parsed["unit_configurations"]] == [365, 395, 520, 590, 620]
    assert [x["price"] for x in parsed["unit_configurations"]] == [11300000.0, 12200000.0, 16000000.0, 15600000.0, 16400000.0]
    assert any("30+ World-Class Amenities" in item for item in parsed["amenities"])
    assert any("Infinity Rooftop Swimming Pool" in item for item in parsed["amenities"])
    assert parsed["contact_email"] is None
    assert parsed["rera"] is None


def test_missing_fields_are_not_invented():
    parsed = parse_property_text("SETHIA PRIDE\nKANDIVALI EAST\n1 BHK - 365 Sq.ft - 1.13 Cr++")
    assert parsed["rera"] is None
    assert parsed["contact_email"] is None
    assert parsed["website"] is None
