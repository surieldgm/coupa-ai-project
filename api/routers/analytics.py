from datetime import date

from fastapi import APIRouter

from api.data import INVOICES, SUPPLIERS
from api.filtering import filter_by_supplier
from api.models import InvoiceStatus

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/spend-by-supplier")
def spend_by_supplier(supplier_id: int | None = None):
    """Total invoiced amount per supplier (paid + pending + overdue)."""
    invoices = filter_by_supplier(INVOICES, supplier_id)

    spend: dict[int, dict] = {}
    for inv in invoices:
        if inv.supplier_id not in spend:
            supplier = next((s for s in SUPPLIERS if s.id == inv.supplier_id), None)
            spend[inv.supplier_id] = {
                "supplier_id": inv.supplier_id,
                "supplier_name": supplier.name if supplier else "Unknown",
                "total_invoiced": 0.0,
                "total_paid": 0.0,
                "total_outstanding": 0.0,
                "invoice_count": 0,
            }
        entry = spend[inv.supplier_id]
        entry["total_invoiced"] += inv.amount
        entry["invoice_count"] += 1
        if inv.status == InvoiceStatus.PAID:
            entry["total_paid"] += inv.amount
        else:
            entry["total_outstanding"] += inv.amount

    results = sorted(spend.values(), key=lambda x: x["total_invoiced"], reverse=True)
    return {"data": results, "currency": "USD"}


@router.get("/overdue-summary")
def overdue_summary(supplier_id: int | None = None):
    """Summary of overdue invoices with aging buckets."""
    today = date.today()
    invoices = filter_by_supplier(INVOICES, supplier_id)
    overdue_invoices = [
        inv for inv in invoices
        if inv.status == InvoiceStatus.OVERDUE
        or (inv.status == InvoiceStatus.PENDING and inv.due_date < today)
    ]

    buckets: dict[str, list[dict]] = {"1-30_days": [], "31-60_days": [], "61-90_days": [], "90+_days": []}
    total_overdue = 0.0

    for inv in overdue_invoices:
        days_overdue = (today - inv.due_date).days
        total_overdue += inv.amount
        entry = {
            "invoice_id": inv.id,
            "supplier_id": inv.supplier_id,
            "amount": inv.amount,
            "days_overdue": days_overdue,
            "due_date": inv.due_date.isoformat(),
        }
        if days_overdue <= 30:
            buckets["1-30_days"].append(entry)
        elif days_overdue <= 60:
            buckets["31-60_days"].append(entry)
        elif days_overdue <= 90:
            buckets["61-90_days"].append(entry)
        else:
            buckets["90+_days"].append(entry)

    return {
        "total_overdue_amount": total_overdue,
        "total_overdue_count": len(overdue_invoices),
        "currency": "USD",
        "aging_buckets": {
            bucket: {"count": len(items), "total": sum(i["amount"] for i in items), "invoices": items}
            for bucket, items in buckets.items()
        },
    }
