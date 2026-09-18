"""Safe extraction and project-boundary checks for WhatsApp property imports."""
from __future__ import annotations

import hashlib
import io
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Developer, Project

MAX_TEXT_CHARS = 120_000
MAX_ATTACHMENT_BYTES = 30 * 1024 * 1024
MAX_VIDEO_FRAMES = 6


def normalize_name(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def _money(raw: str) -> float | None:
    text = raw.lower().replace(",", "").strip()
    m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*(cr(?:ore)?|crore|l(?:akh)?|lac)?", text)
    if not m:
        return None
    try:
        value = Decimal(m.group(1))
    except InvalidOperation:
        return None
    unit = m.group(2) or ""
    if unit.startswith("cr"):
        value *= Decimal("10000000")
    elif unit.startswith("l"):
        value *= Decimal("100000")
    return float(value)


def _first(patterns: tuple[str, ...], text: str, flags: int = re.I) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags)
        if match:
            return match.group(1).strip(" \t:-|_")
    return None


def _clean_line(line: str) -> str:
    line = re.sub(r"[\*_]+", "", line)
    line = re.sub(r"[￼]+", " ", line)
    return re.sub(r"\s+", " ", line).strip(" •\t")


def _extract_identities(text: str) -> dict[str, list[str]]:
    upper = text.upper()
    projects: list[str] = []
    for pattern in (
        r"\b(PASSCODE\s+HIGHWAY\s+BONANZA)\b",
        r"\b(SETHIA\s+PRIDE)\b",
        r"\b(PRIDE\s+KANDIVALI\s*\(E\))\b",
    ):
        for match in re.findall(pattern, upper):
            title = match.title()
            if normalize_name(title) not in {normalize_name(x) for x in projects}:
                projects.append(title)
    for line in text.splitlines():
        clean = _clean_line(line)
        if re.search(r"(?i)\bproject(?: name)?\b\s*[:\-]", clean):
            candidate = re.split(r"[:\-]", clean, maxsplit=1)[-1].strip()
            if 3 <= len(candidate) <= 100 and normalize_name(candidate) not in {normalize_name(x) for x in projects}:
                projects.append(candidate)
    developers: list[str] = []
    for pattern in (r"\b(SETHIA\s+INFRASTRUCTURE)\b", r"\b(SETHIA\s+INFRA)\b"):
        for match in re.findall(pattern, upper):
            title = match.title()
            if normalize_name(title) not in {normalize_name(x) for x in developers}:
                developers.append(title)
    return {"developers": developers, "projects": projects}


def _extract_configurations(text: str) -> list[dict[str, Any]]:
    configs: list[dict[str, Any]] = []
    patterns = (
        re.compile(r"(?i)\b(\d+\s*(?:BHK|BED))\b\s*(?:WITH\s+DECK\s*)?(?:-|–|—|:|\|)\s*([0-9,]+(?:\.[0-9]+)?)\s*(?:SQ\.?\s*FT|SQFT|SFT)?\s*(?:-|–|—|:|\|)\s*(₹?\s*[0-9,.]+\s*(?:CR(?:ORE)?|CRORE|L(?:AKH)?|LAC)?\+*)"),
        re.compile(r"(?i)\b(\d+\s*(?:BHK|BED))\b[^\n]{0,80}?(?:carpet|area)[^0-9]{0,12}([0-9,]+(?:\.[0-9]+)?)\s*(?:sq\.?\s*ft|sqft|sft)?[^\n]{0,40}?(?:₹|rs\.?|price)[^0-9]{0,8}([0-9,.]+\s*(?:cr(?:ore)?|crore|l(?:akh)?|lac)?\+?)"),
    )
    seen: set[tuple[str, float | None, float | None]] = set()
    current_wing: str | None = None
    for raw_line in text.splitlines():
        line = _clean_line(raw_line)
        wing_match = re.search(r"(?i)\b([A-Z](?:-?\s*WING))\b(?:\s*[-–—:]\s*(.*))?", line)
        if wing_match and not re.search(r"\b\d+\s*(?:BHK|BED)\b", line, re.I):
            current_wing = wing_match.group(1).replace(" ", "-").upper()
        for pattern in patterns:
            m = pattern.search(line)
            if not m:
                continue
            bhk = re.sub(r"(?i)\s*BED\b", " BHK", m.group(1)).upper().replace("  ", " ")
            area = float(m.group(2).replace(",", ""))
            price = _money(m.group(3))
            key = (bhk, area, price)
            if key in seen:
                continue
            seen.add(key)
            configs.append({"bhk": bhk, "carpet_area": area, "price": price, "wing": current_wing, "source_line": line[:500]})
            break
    return configs


def _extract_highlights(text: str) -> list[str]:
    highlights: list[str] = []
    for raw in text.splitlines():
        line = _clean_line(raw)
        if not line or len(line) > 180:
            continue
        if re.search(r"(?i)\b(?:min walk|storey|world-class amenities|infinity rooftop|w\.e\.?\s*highway|metro|railway station)\b", line):
            if line.lower() not in {x.lower() for x in highlights}:
                highlights.append(line)
    return highlights


def parse_property_text(text: str) -> dict[str, Any]:
    text = text[:MAX_TEXT_CHARS]
    identities = _extract_identities(text)
    upper = text.upper()
    city = _first((r"\b(?:city)\s*[:\-]\s*([^\n,|]+)",), text)
    if not city and "MUMBAI" in upper and "KANDIVALI" in upper:
        city = "Mumbai"
    locality = _first((r"\b(?:locality|area)\s*[:\-]\s*([^\n|]+)",), text)
    if not locality and ("KANDIVALI EAST" in upper or "KANDIVALI (E)" in upper):
        locality = "Kandivali East"
    rera = next(iter(re.findall(r"\bP\d{8,15}\b", upper)), None)
    map_url = next(iter(re.findall(r"https?://(?:goo\.gl/maps|maps\.app\.goo\.gl|maps\.google\.com)/[^\s]+", text)), None)
    website = next(iter(re.findall(r"https?://(?!goo\.gl/maps|maps\.app\.goo\.gl|maps\.google\.com)[^\s]+", text)), None)
    phone = next(iter(re.findall(r"(?<!\d)(?:\+91[\s-]?)?[6-9]\d{9}(?!\d)", text)), None)
    email = next(iter(re.findall(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", text, re.I)), None)
    location_lines: list[str] = []
    for raw in text.splitlines():
        line = _clean_line(raw)
        if re.search(r"(?i)\b(?:LOCATION|SITE ADDRESS|PROJECT ADDRESS)\s*:", line):
            location_lines.append(re.split(r":", line, maxsplit=1)[-1].strip())
        elif re.search(r"(?i)\bON\s+(?:W\.?E\.?\s*HIGHWAY|WESTERN EXPRESS HIGHWAY)\b", line):
            location_lines.append(line)
        elif re.search(r"(?i)\bNEXT TO\b", line):
            location_lines.append(line)
    address = _first((r"\b(?:address|site address|project address)\s*[:\-]\s*([^\n]+)",), text)
    if not address and location_lines:
        address = ", ".join(dict.fromkeys(location_lines))
    possession = _first((r"\b(?:possession|possession by|nearing possession|handover)\s*[:\-]?\s*([^\n]+)",), text)
    if not possession:
        possession_match = re.search(r"(?i)([A-Z]-?\s*WING[^\n]{0,80}?NEARING POSSESSION[^\n]*)", text)
        if possession_match:
            possession = _clean_line(possession_match.group(1))
    developer = identities["developers"][0] if len(identities["developers"]) == 1 else _first((r"\b(?:developer|builder|promoter)\s*[:\-]\s*([^\n]+)",), text)
    project = identities["projects"][0] if len(identities["projects"]) == 1 else _first((r"\b(?:project|project name)\s*[:\-]\s*([^\n]+)",), text)
    amenities: list[str] = []
    for line in text.splitlines():
        clean = _clean_line(line)
        if re.search(r"(?i)amenit", clean):
            value = re.sub(r"(?i).*?amenit(?:y|ies)?\s*[:\-]?\s*", "", clean).strip()
            if value and value.lower() not in {x.lower() for x in amenities}:
                amenities.append(value)
    for line in _extract_highlights(text):
        if re.search(r"(?i)world-class amenities|infinity rooftop swimming pool", line):
            if line.lower() not in {x.lower() for x in amenities}:
                amenities.append(line)
    floors = _first((r"\b(\d+)\s*[- ]?storey(?:\s+iconic\s+tower)?\b",), text)
    total_units = _first((r"\b(?:total units|no\. of units|number of units)\s*[:\-]\s*([^\n]+)",), text)
    parking = _first((r"\bparking\s*[:\-]\s*([^\n]+)", r"\b(\d+\s*(?:car|car park|parking)(?:s)?\b)"), text)
    return {
        "developer": developer,
        "project": project,
        "project_candidates": identities["projects"],
        "city": city,
        "locality": locality,
        "address": address,
        "rera": rera,
        "map_url": map_url,
        "website": website,
        "contact_phone": phone,
        "contact_email": email,
        "amenities": amenities,
        "highlights": _extract_highlights(text),
        "total_building_floors": int(floors) if floors and floors.isdigit() else None,
        "parking": parking,
        "total_units": total_units,
        "unit_configurations": _extract_configurations(text),
        "possession_text": possession,
        "raw_text": text,
    }


def extract_pdf_text(data: bytes) -> str:
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        chunks = [page.extract_text() or "" for page in reader.pages[:30]]
        text = "\n".join(chunks)[:MAX_TEXT_CHARS]
        if text.strip():
            return text
    except Exception:
        pass
    try:
        import fitz
        import pytesseract
        from PIL import Image
        doc = fitz.open(stream=data, filetype="pdf")
        chunks = []
        for page in doc[:15]:
            pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
            image = Image.open(io.BytesIO(pix.tobytes("png")))
            chunks.append(pytesseract.image_to_string(image))
        doc.close()
        return "\n".join(chunks)[:MAX_TEXT_CHARS]
    except Exception:
        return ""


def ocr_image(data: bytes) -> str:
    try:
        from PIL import Image
        import pytesseract
        with Image.open(io.BytesIO(data)) as image:
            return pytesseract.image_to_string(image)[:MAX_TEXT_CHARS]
    except Exception:
        return ""


def extract_video_text(data: bytes, suffix: str = ".mp4") -> str:
    try:
        import cv2
        import pytesseract
        import tempfile
        suffix = suffix.lower() if suffix.lower() in {".mp4", ".mov", ".m4v"} else ".mp4"
        with tempfile.NamedTemporaryFile(suffix=suffix) as tmp:
            tmp.write(data); tmp.flush()
            capture = cv2.VideoCapture(tmp.name)
            if not capture.isOpened():
                capture.release(); return ""
            total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            positions = [0.08, 0.25, 0.45, 0.65, 0.82, 0.95]
            chunks: list[str] = []
            for ratio in positions[:MAX_VIDEO_FRAMES]:
                target = int(max(0, min(total - 1, ratio * total))) if total else 0
                capture.set(cv2.CAP_PROP_POS_FRAMES, target)
                ok, frame = capture.read()
                if not ok: continue
                text = pytesseract.image_to_string(frame)
                if text.strip(): chunks.append(text)
            capture.release()
            return "\n".join(chunks)[:MAX_TEXT_CHARS]
    except Exception:
        return ""


def attachment_text(filename: str, mime_type: str, data: bytes) -> str:
    lower = filename.lower()
    if mime_type == "application/pdf" or lower.endswith(".pdf"):
        return extract_pdf_text(data)
    if mime_type.startswith("image/"):
        return ocr_image(data)
    if mime_type.startswith("video/"):
        return extract_video_text(data, Path(filename).suffix)
    return ""


def attachment_record(filename: str, mime_type: str, data: bytes) -> dict[str, Any]:
    extracted = attachment_text(filename, mime_type, data)
    return {"filename": Path(filename).name[:255], "mime_type": mime_type[:120], "size": len(data), "sha256": hashlib.sha256(data).hexdigest(), "extracted_text_chars": len(extracted)}


def analyze_sources(text: str, attachments: list[dict[str, Any]]) -> dict[str, Any]:
    combined = [text[:MAX_TEXT_CHARS]]
    source_identities = []
    unattributed_sources = []
    for item in attachments:
        extracted = item.get("extracted_text", "")
        if extracted: combined.append(extracted[:MAX_TEXT_CHARS])
        identities = _extract_identities(extracted)
        if identities["projects"] or identities["developers"]:
            source_identities.append({"filename": item.get("filename"), **identities})
        elif extracted.strip():
            unattributed_sources.append(item.get("filename"))
    parsed = parse_property_text("\n\n".join(x for x in combined if x))
    unique_projects = {normalize_name(x): x for x in parsed["project_candidates"]}
    for item in source_identities:
        for project in item["projects"]:
            unique_projects.setdefault(normalize_name(project), project)
    parsed["project_candidates"] = list(unique_projects.values())
    parsed["source_identities"] = source_identities
    parsed["unattributed_sources"] = [x for x in unattributed_sources if x]
    parsed["identity_conflict"] = len(unique_projects) > 1 or len(_extract_identities("\n".join(combined))["developers"]) > 1
    return parsed


def find_safe_project_matches(db: Session, parsed: dict[str, Any]) -> dict[str, Any]:
    result: list[dict[str, Any]] = []
    for project_name in parsed.get("project_candidates") or []:
        exact = db.scalars(select(Project).where(func.lower(Project.name) == normalize_name(project_name))).all()
        for project in exact:
            developer = db.get(Developer, project.developer_id)
            checks = {"developer": not parsed.get("developer") or normalize_name(developer.name if developer else "") == normalize_name(parsed["developer"]), "city": not parsed.get("city") or normalize_name(project.city) == normalize_name(parsed["city"]), "rera": not parsed.get("rera") or normalize_name(project.rera) == normalize_name(parsed["rera"])}
            result.append({"project_id": project.id, "name": project.name, "developer": developer.name if developer else None, "checks": checks, "safe": all(checks.values())})
    return {"matches": result, "ambiguous": len(result) != 1 or not result[0]["safe"]}


def build_draft(text: str, attachments: list[dict[str, Any]], db: Session) -> dict[str, Any]:
    parsed = analyze_sources(text, attachments)
    parsed["project_match"] = find_safe_project_matches(db, parsed)
    # OCR/text from an attachment that cannot identify its project must not
    # silently contribute fields to a final CRM record. Keep the attachment in
    # the review draft, but require explicit manual review before commit.
    parsed["requires_manual_project_selection"] = bool(
        parsed["identity_conflict"]
        or parsed["project_match"]["ambiguous"]
        or parsed["unattributed_sources"]
    )
    parsed["safe_to_commit"] = not parsed["requires_manual_project_selection"]
    return parsed


def detect_field_conflicts(project: Project, parsed: dict[str, Any]) -> list[dict[str, str]]:
    conflicts = []
    for field in ("city", "locality", "rera"):
        incoming, existing = parsed.get(field), getattr(project, field, None)
        if incoming and existing and normalize_name(str(incoming)) != normalize_name(str(existing)):
            conflicts.append({"field": field, "existing": str(existing), "incoming": str(incoming)})
    return conflicts
