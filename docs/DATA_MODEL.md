# Data Model Reference

## Entities

### Suppliers

| Field | Type | Description |
|-------|------|-------------|
| id | int | Unique identifier |
| name | string | Company name |
| contact_email | string | Primary contact email |
| category | enum | IT, office_supplies, raw_materials, logistics, professional_services, facilities |
| rating | float | Performance rating (1.0 - 5.0) |
| location | string | City, State |
| status | enum | active, inactive, pending |
| onboarded_date | date | When the supplier was onboarded |
| payment_terms_days | int | Standard payment terms in days |

### Purchase Orders

| Field | Type | Description |
|-------|------|-------------|
| id | int | Unique identifier (1001+) |
| supplier_id | int | FK → Supplier |
| line_items | array | List of {description, quantity, unit_price} |
| total_amount | float | Computed total |
| currency | string | ISO currency code |
| status | enum | submitted, acknowledged |
| created_date | date | When the PO was created |
| delivery_date | date/null | Expected or actual delivery date |

### Invoices

| Field | Type | Description |
|-------|------|-------------|
| id | int | Unique identifier (2001+) |
| po_id | int/null | FK → PurchaseOrder (null for non-PO invoices) |
| supplier_id | int | FK → Supplier |
| amount | float | Invoice amount |
| currency | string | ISO currency code |
| status | enum | pending, paid, overdue |
| issued_date | date | When the invoice was issued |
| due_date | date | Payment due date |
| paid_date | date/null | When payment was made |

### Contracts

| Field | Type | Description |
|-------|------|-------------|
| id | int | Unique identifier (3001+) |
| supplier_id | int | FK → Supplier |
| title | string | Contract title |
| start_date | date | Contract start |
| end_date | date | Contract end |
| annual_value | float | Annual contract value |
| currency | string | ISO currency code |
| terms | string | Key terms summary |
| auto_renew | bool | Whether the contract auto-renews |
| status | enum | active, expired, pending_renewal |

### Catalog Items

| Field | Type | Description |
|-------|------|-------------|
| id | int | Unique identifier (4001+) |
| supplier_id | int | FK → Supplier |
| name | string | Product/service name |
| description | string | Detailed description |
| category | string | Product category (freeform) |
| unit_price | float | Price per unit |
| currency | string | ISO currency code |
| lead_time_days | int | Days from order to delivery |
| in_stock | bool | Current availability |

## Relationships

```
Supplier (1) ──→ (many) Purchase Orders
Supplier (1) ──→ (many) Invoices
Supplier (1) ──→ (many) Contracts
Supplier (1) ──→ (many) Catalog Items
Purchase Order (1) ──→ (many) Invoices
```

## Pre-seeded Data Volume

| Entity | Count | Notes |
|--------|-------|-------|
| Suppliers | 10 | Across all 6 categories |
| Purchase Orders | 20 | Mix of all statuses |
| Invoices | 30 | ~40% paid, ~40% pending, ~20% overdue |
| Contracts | 8 | 1 expired, 1 pending renewal, 6 active |
| Catalog Items | 40 | 3-6 items per supplier |
