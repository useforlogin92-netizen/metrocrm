from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.accounting_models import AccountCategory, AccountingEntry, JournalEntry, JournalLine


def dec(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"))


def post_transaction(db: Session, entry: AccountingEntry, user_id: int, entry_no: str) -> JournalEntry:
    """Convert a register transaction into a balanced double-entry journal."""
    if entry.entry_type not in {"EXPENSE", "INCOME"}:
        raise ValueError("Unsupported transaction type")
    if any(dec(x) < 0 for x in (entry.amount, entry.gst_amount, entry.tds_amount)):
        raise ValueError("Amounts cannot be negative")
    if db.scalar(select(JournalEntry.id).where(JournalEntry.entry_no == entry_no)):
        raise ValueError("Duplicate journal entry number")

    amount = dec(entry.amount)
    gst = dec(entry.gst_amount)
    tds = dec(entry.tds_amount)
    gross = amount + gst
    if tds > gross:
        raise ValueError("TDS cannot exceed gross transaction value")

    # Verify all ledger accounts used by the posting actually exist. This keeps
    # the helper safe even when called outside the HTTP route.
    mode = (entry.payment_mode or "").strip().lower()
    if entry.entry_type == "EXPENSE" and mode == "credit":
        settlement_account = "VENDOR_PAYABLE"
    elif entry.entry_type == "INCOME" and mode == "credit":
        settlement_account = "CUSTOMER_RECEIVABLE"
    elif mode == "cash":
        settlement_account = "CASH"
    else:
        settlement_account = "BANK"

    required = {entry.category_code, settlement_account}
    if entry.entry_type == "EXPENSE" and gst:
        required.add("INPUT_CGST")
    if entry.entry_type == "EXPENSE" and tds:
        required.add("TDS_PAYABLE")
    if entry.entry_type == "INCOME" and gst:
        required.add("OUTPUT_CGST")
    existing = set(db.scalars(select(AccountCategory.code).where(AccountCategory.code.in_(required))).all())
    missing = required - existing
    if missing:
        raise ValueError("Missing accounting account: " + ", ".join(sorted(missing)))

    lines: list[tuple[str, Decimal, Decimal, str | None]] = []
    if entry.entry_type == "EXPENSE":
        lines.append((entry.category_code, amount, Decimal("0"), entry.party_name))
        if gst:
            lines.append(("INPUT_CGST", gst, Decimal("0"), entry.party_name))
        if tds:
            lines.append(("TDS_PAYABLE", Decimal("0"), tds, entry.party_name))
        lines.append((settlement_account, Decimal("0"), gross - tds, entry.party_name))
    else:
        lines.append((settlement_account, gross, Decimal("0"), entry.party_name))
        lines.append((entry.category_code, Decimal("0"), amount, entry.party_name))
        if gst:
            lines.append(("OUTPUT_CGST", Decimal("0"), gst, entry.party_name))

    debit_total = sum((x[1] for x in lines), Decimal("0"))
    credit_total = sum((x[2] for x in lines), Decimal("0"))
    if debit_total != credit_total:
        raise ValueError("Journal is not balanced")

    je = JournalEntry(entry_no=entry_no, entry_date=entry.entry_date, narration=entry.description, reference_no=entry.reference_no, created_by_id=user_id, status="POSTED")
    db.add(je)
    db.flush()
    for account_code, debit, credit, party in lines:
        db.add(JournalLine(journal_entry_id=je.id, account_code=account_code, debit=debit, credit=credit, party_name=party))
    return je
