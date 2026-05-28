from datetime import date

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from api.data import INVOICES, PURCHASE_ORDERS, SUPPLIERS
from api.filtering import filter_by_supplier
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
    """List all invoices, optionally filtered by supplier, status, overdue flag, or amount range."""
    results = filter_by_supplier(INVOICES, supplier_id)
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
def get_invoice(invoice_id: int, supplier_id: int | None = None):
    """Get a single invoice by ID. Returns 404 if not found or doesn't belong to the given supplier."""
    results = filter_by_supplier(INVOICES, supplier_id)
    invoice = next((inv for inv in results if inv.id == invoice_id), None)
    if invoice is None:
        raise HTTPException(status_code=404, detail=f"Invoice {invoice_id} not found")
    return invoice


class CreateInvoiceRequest(BaseModel):
    po_id: int | None = None
    amount: float
    due_date: date
    currency: str = "USD"


@router.post("", response_model=Invoice, status_code=201)
def create_invoice(req: CreateInvoiceRequest, supplier_id: int = Query(...)):
    """Create a new invoice. Supplier ID is required."""
    if not any(s.id == supplier_id for s in SUPPLIERS):
        raise HTTPException(status_code=400, detail=f"Supplier {supplier_id} not found")

    if req.po_id is not None:
        po = next((p for p in PURCHASE_ORDERS if p.id == req.po_id), None)
        if po is None or po.supplier_id != supplier_id:
            raise HTTPException(status_code=400, detail=f"Purchase order {req.po_id} not found")

    new_id = max(inv.id for inv in INVOICES) + 1
    invoice = Invoice(
        id=new_id,
        po_id=req.po_id,
        supplier_id=supplier_id,
        amount=req.amount,
        currency=req.currency,
        status=InvoiceStatus.PENDING,
        issued_date=date.today(),
        due_date=req.due_date,
        paid_date=None,
    )
    INVOICES.append(invoice)
    return invoice
