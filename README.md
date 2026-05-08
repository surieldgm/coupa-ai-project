# Coupa AI Engineering Evaluation

A procurement agent coding project. You're given a working mock API with pre-seeded data — your job is to build an agent on top of it.

## Quick Start

### Prerequisites

- Python 3.11+
- An OpenAI API key

### Setup

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your OpenAI API key
```

### Run the API

```bash
uvicorn api.main:app --reload
```

The API runs at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

## Project Structure

```
├── api/                  # Mock Procurement API (FastAPI)
│   ├── main.py           # App entry point
│   ├── models.py         # Pydantic data models
│   ├── data.py           # Pre-seeded mock data
│   └── routers/          # Route handlers
│       ├── suppliers.py
│       ├── purchase_orders.py
│       ├── invoices.py
│       ├── contracts.py
│       ├── catalog.py
│       └── analytics.py
├── docs/
│   └── DATA_MODEL.md     # Entity reference
├── .env.example
├── requirements.txt
└── pyproject.toml
```

## API Reference

The API serves pre-seeded procurement data (resets on restart). Key endpoints:

| Endpoint | Description |
|----------|-------------|
| `GET /suppliers` | List/filter suppliers |
| `GET /suppliers/{id}` | Get supplier details |
| `GET /purchase-orders` | List/filter purchase orders |
| `GET /purchase-orders/{id}` | Get PO details |
| `POST /purchase-orders` | Create a new PO |
| `PATCH /purchase-orders/{id}` | Update PO status |
| `GET /invoices` | List/filter invoices |
| `GET /invoices/{id}` | Get invoice details |
| `GET /contracts` | List/filter contracts |
| `GET /contracts/{id}` | Get contract details |
| `GET /catalog` | Search catalog items |
| `GET /catalog/{id}` | Get catalog item details |
| `GET /analytics/spend-by-supplier` | Spend breakdown |
| `GET /analytics/overdue-summary` | Overdue aging analysis |

Full interactive docs available at `/docs` when the API is running.

## Data

See [docs/DATA_MODEL.md](docs/DATA_MODEL.md) for the full entity reference. The mock data includes:

- 10 suppliers across 6 categories
- 20 purchase orders in various states
- 30 invoices (paid, pending, and overdue)
- 8 contracts (active, expired, pending renewal)
- 40 catalog items
