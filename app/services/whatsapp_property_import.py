"""Safe extraction and project-boundary checks for WhatsApp property imports."""
from __future__ import annotations

import hashlib
import io
import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Developer, Project

MAX_TEXT_CHARS = 120_000
MAX_ATTACHMENT_BYTES = 30 * 1024 * 1024


def normalize_name(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def _money(raw: str) -> float | None:
    text = raw.lower().replace(",", "").strip()
    m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*(cr(?:ore)?|crore|l(?:akh)?|lac)?", text)
    if not m: return None
    try: value = Decimal(m.group(1))
    except InvalidOperation: return None
    unit = m.group(2) or ""
    if unit.startswith("cr"): value *= Decimal("10000000")
    elif unit.startswith("l"): value *= Decimal("100000")
    return float(value)


def _extract_identities(text: str) -> dict[str, list[str]]:
    upper = text.upper(); projects: list[str] = []
    for pattern in (r"\b(PASSCODE\s+HIGHWAY\s+BONANZA)\b", r"\b(SETHIA\s+PRIDE)\b", r"\b(PRIDE\s+KANDIVALI\s*\(E\))\b"):
        for match in re.findall(pattern, upper):
            title = match.title()
            if normalize_name(title) not in {normalize_name(x) for x in projects}: projects.append(title)
    for line in text.splitlines():
        clean = re.sub(r"[^A-Za-z0-9&'(). -]", " ", line).strip()
        if re.search(r"(?i)\bproject(?: name)?\b\s*[:\-]", clean):
            candidate = re.split(r"[:\-]", clean, maxsplit=1)[-1].strip()
            if 3 <= len(candidate) <= 100 and normalize_name(candidate) not in {normalize_name(x) for x in projects}: projects.append(candidate)
    developers: list[str] = []
    for pattern in (r"\b(SETHIA\s+INFRASTRUCTURE)\b", r"\b(SETHIA\s+INFRA)\b"):
        for match in re.findall(pattern, upper):
            title = match.title()
            if normalize_name(title) not in {normalize_name(x) for x in developers}: developers.append(title)
    return {"developers": developers, "projects": projects}


def parse_property_text(text: str) -> dict[str, Any]:
    text = text[:MAX_TEXT_CHARS]; identities = _extract_identities(text); upper = text.upper()
    city = "Kandivali" if "KANDIVALI" in upper else None
    locality = "Kandivali East" if "KANDIVALI EAST" in upper or "KANDIVALI (E)" in upper else None
    rera = next(iter(re.findall(r"\bP\d{8,15}\b", upper)), None)
    map_url = next(iter(re.findall(r"https?://(?:goo\.gl/maps|maps\.app\.goo\.gl)/[^\s]+", text)), None)
    amenities: list[str] = []
    for line in text.splitlines():
        clean = line.strip(" •*-\t")
        if re.search(r"(?i)amenit", clean):
            value = re.sub(r"(?i).*?amenit(?:y|ies)?\s*[:\-]?\s*", "", clean).strip()
            if value and value.lower() not in {x.lower() for x in amenities}: amenities.append(value)
    configs: list[dict[str, Any]] = []
    line_pattern = re.compile(r"(?i)\b(\d+\s*BHK|\d+\s*BED)\b\s*(?:WITH\s+DECK\s*)?(?:-|–|—|:)\s*([0-9,]+(?:\.[0-9]+)?)\s*(?:SQ\.?\s*FT|SQFT|SFT)?\s*(?:-|–|—|:)\s*(₹?\s*[0-9,.]+\s*(?:CR(?:ORE)?|CRORE|L(?:AKH)?|LAC)?\+*)")
    for line in text.splitlines():
        m = line_pattern.search(line)
        if not m: continue
        configs.append({"bhk": re.sub(r"(?i)\s*BED\b", " BHK", m.group(1)).upper().replace("  ", " "), "carpet_area": float(m.group(2).replace(",", "")), "price": _money(m.group(3)), "source_line": line[:500]})
    possession = None
    m = re.search(r"(?i)(?:possession|nearing possession)[^\n]{0,80}", text)
    if m: possession = m.group(0).strip()
    return {"developer": identities["developers"][0] if len(identities["developers"]) == 1 else None, "project_candidates": identities["projects"], "city": city, "locality": locality, "rera": rera, "map_url": map_url, "amenities": amenities, "unit_configurations": configs, "possession_text": possession, "raw_text": text}


def extract_pdf_text(data: bytes) -> str:
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data)); chunks = [page.extract_text() or "" for page in reader.pages[:30]]
        text = "\n".join(chunks)[:MAX_TEXT_CHARS]
        if text.strip(): return text
    except Exception: pass
    try:
        import fitz
        import pytesseract
        from PIL import Image
        doc = fitz.open(stream=data, filetype="pdf"); chunks = []
        for page in doc[:15]:
            pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
            image = Image.open(io.BytesIO(pix.tobytes("png")))
            chunks.append(pytesseract.image_to_string(image))
        doc.close(); return "\n".join(chunks)[:MAX_TEXT_CHARS]
    except Exception:
        return ""


def ocr_image(data: bytes) -> str:
    try:
        from PIL import Image
        import pytesseract
        with Image.open(io.BytesIO(data)) as image: return pytesseract.image_to_string(image)[:MAX_TEXT_CHARS]
    except Exception: return ""


def attachment_text(filename: str, mime_type: str, data: bytes) -> str:
    lower = filename.lower()
    if mime_type == "application/pdf" or lower.endswith(".pdf"): return extract_pdf_text(data)
    if mime_type.startswith("image/"): return ocr_image(data)
    return ""


def attachment_record(filename: str, mime_type: str, data: bytes) -> dict[str, Any]:
    return {"filename": Path(filename).name[:255], "mime_type": mime_type[:120], "size": len(data), "sha256": hashlib.sha256(data).hexdigest(), "extracted_text_chars": len(attachment_text(filename, mime_type, data))}


def analyze_sources(text: str, attachments: list[dict[str, Any]]) -> dict[str, Any]:
    combined = [text[:MAX_TEXT_CHARS]]; source_identities = []
    for item in attachments:
        extracted = item.get("extracted_text", "")
        if extracted: combined.append(extracted[:MAX_TEXT_CHARS])
        identities = _extract_identities(extracted)
        if identities["projects"] or identities["developers"]: source_identities.append({"filename": item.get("filename"), **identities})
    parsed = parse_property_text("\n\n".join(x for x in combined if x))
    unique_projects = {normalize_name(x): x for x in parsed["project_candidates"]}
    for item in source_identities:
        for project in item["projects"]: unique_projects.setdefault(normalize_name(project), project)
    parsed["project_candidates"] = list(unique_projects.values()); parsed["source_identities"] = source_identities
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
    parsed = analyze_sources(text, attachments); parsed["project_match"] = find_safe_project_matches(db, parsed)
    parsed["requires_manual_project_selection"] = bool(parsed["identity_conflict"] or parsed["project_match"]["ambiguous"]); parsed["safe_to_commit"] = not parsed["requires_manual_project_selection"]
    return parsed


def detect_field_conflicts(project: Project, parsed: dict[str, Any]) -> list[dict[str, str]]:
    conflicts = []
    for field in ("city", "locality", "rera"):
        incoming, existing = parsed.get(field), getattr(project, field, None)
        if incoming and existing and normalize_name(str(incoming)) != normalize_name(str(existing)): conflicts.append({"field": field, "existing": str(existing), "incoming": str(incoming)})
    return conflicts
