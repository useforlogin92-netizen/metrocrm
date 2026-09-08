from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.accounting_models import AccountCategory, AccountingEntry, JournalEntry, JournalLine


def dec(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"))


def post_transaction(db: Session, entry: AccountingEntry, user_id: int, entry_no: str) -> JournalEntry:
    """Post a register transaction into the double-entry ledger.

    Expense: Dr expense + eligible input GST, Cr cash/bank/payable, with TDS payable.
    Income: Dr cash/bank/receivable, Cr income + output GST.
    """
    if entry.amount < 0 or entry.gst_amount < 0 or entry.tds_amount < 0:
        raise ValueError("Amounts cannot be negative")
    if entry_type := entry.entry_type not in {"EXPENSE", "INCOME"}:
        raise ValueError("Unsupported transaction type")
    if db.scalar(select(JournalEntry.id).where(JournalEntry.entry_no == entry_no)):
        raise ValueError("Duplicate journal entry number")

    gross_tax = dec(entry.amount) + dec(entry.gst_amount)
    net_cash = gross_tax - dec(entry.tds_amount)
    if net_cash < 0:
        raise ValueError("TDS cannot exceed gross transaction value")

    lines: list[tuple[str, Decimal, Decimal, str | None]] = []
    if entry.entry_type == "EXPENSE":
        lines.append((entry.category_code, dec(entry.amount), Decimal("0"), entry.party_name))
        if entry.gst_amount:
            # Default to CGST input for a management ledger; CA can reclassify via journal.
            lines.append(("INPUT_CGST", dec(entry.gst_amount), Decimal("0"), entry.party_name))
        if entry.tds_amount:
            lines.append(("TDS_PAYABLE", Decimal("0"), dec(entry.tds_amount), entry.party_name))
        credit_account = "CASH" if (entry.payment_mode or "").lower() == "cash" else "BANK"
        if entry.payment_mode and entry.payment_mode.lower() == "credit":
            credit_account = "LOAN_LIABILITY"
        lines.append((credit_account, Decimal("0"), net_cash, entry.party_name))
    else:
        debit_account = "CASH" if (entry.payment_mode or "").lower() == "cash" else "BANK"
        if entry.payment_mode and entry.payment_mode.lower() == "credit":
            debit_account = "BANK"
        lines.append((debit_account, gross_tax, Decimal("0"), entry.party_name))
        lines.append((entry.category_code, Decimal("0"), dec(entry.amount), entry.party_name))
        if entry.gst_amount:
            lines.append(("OUTPUT_CGST", Decimal("0"), dec(entry.gst_amount), entry.party_name))

    debit_total = sum((x[1] for x in lines), Decimal("0"))
    credit_total = sum((x[2] for x in lines), Decimal("0"))
    if debit_total != credit_total:
        raise ValueError("Journal is not balanced")

    je = JournalEntry(
        entry_no=entry_no,
        entry_date=entry.entry_date,
        narration=entry.description,
        reference_no=entry.reference_no,
        created_by_id=user_id,
        status="POSTED",
    )
    db.add(je)
    db.flush()
    for account_code, debit, credit, party in lines:
        db.add(JournalLine(journal_entry_id=je.id, account_code=account_code, debit=debit, credit=credit, party_name=party))
    return je
