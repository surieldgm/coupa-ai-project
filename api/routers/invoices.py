from datetime import date

from fastapi import APIRouter, HTTPException, Query

from api.data import INVOICES
from api.models import Invoice, InvoiceStatus

router = APIRouter(prefix="/invoices", tags=["invoices"])


@router.get("", response_model=list[Invoice])
def list_invoices(
    supplier_id: int | None = None,
    status: InvoiceStatus | None = None,
    overdue: bool | None = Query(None, description="Filter to currently overdue invoices"),
    min_amount: float | None = Query(None, ge=0),
    max_amount: float | None = Query(None, ge=0),
):
    results = INVOICES
    if supplier_id is not None:
        results = [inv for inv in results if inv.supplier_id == supplier_id]
    if status:
        results = [inv for inv in results if inv.status == status]
    if overdue is True:
        today = date.today()
        results = [
            inv for inv in results
            if inv.status == InvoiceStatus.OVERDUE
            or (inv.status == InvoiceStatus.PENDING and inv.due_date < today)
        ]
    if min_amount is not None:
        results = [inv for inv in results if inv.amount >= min_amount]
    if max_amount is not None:
        results = [inv for inv in results if inv.amount <= max_amount]
    return results


@router.get("/{invoice_id}", response_model=Invoice)
def get_invoice(invoice_id: int):
    for inv in INVOICES:
        if inv.id == invoice_id:
            return inv
    raise HTTPException(status_code=404, detail=f"Invoice {invoice_id} not found")
