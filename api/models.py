from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel


class SupplierCategory(str, Enum):
    IT = "IT"
    OFFICE_SUPPLIES = "office_supplies"
    RAW_MATERIALS = "raw_materials"
    LOGISTICS = "logistics"
    PROFESSIONAL_SERVICES = "professional_services"
    FACILITIES = "facilities"


class SupplierStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    PENDING = "pending"


class POStatus(str, Enum):
    SUBMITTED = "submitted"
    ACKNOWLEDGED = "acknowledged"


class InvoiceStatus(str, Enum):
    PENDING = "pending"
    PAID = "paid"
    OVERDUE = "overdue"


class ContractStatus(str, Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    PENDING_RENEWAL = "pending_renewal"


class Supplier(BaseModel):
    id: int
    name: str
    contact_email: str
    category: SupplierCategory
    rating: float
    location: str
    status: SupplierStatus
    onboarded_date: date
    payment_terms_days: int


class LineItem(BaseModel):
    description: str
    quantity: int
    unit_price: float


class PurchaseOrder(BaseModel):
    id: int
    supplier_id: int
    line_items: list[LineItem]
    total_amount: float
    currency: str
    status: POStatus
    created_date: date
    delivery_date: date | None


class Invoice(BaseModel):
    id: int
    po_id: int | None
    supplier_id: int
    amount: float
    currency: str
    status: InvoiceStatus
    issued_date: date
    due_date: date
    paid_date: date | None


class Contract(BaseModel):
    id: int
    supplier_id: int
    title: str
    start_date: date
    end_date: date
    annual_value: float
    currency: str
    terms: str
    auto_renew: bool
    status: ContractStatus


class CatalogItem(BaseModel):
    id: int
    supplier_id: int
    name: str
    description: str
    category: str
    unit_price: float
    currency: str
    lead_time_days: int
    in_stock: bool
