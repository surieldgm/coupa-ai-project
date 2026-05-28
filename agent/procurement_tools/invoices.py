"""Invoice tools — fully implemented as a reference example.

Available API endpoints:
  GET  /invoices            — List/filter invoices (params: supplier_id, status, overdue, min_amount, max_amount)
  GET  /invoices/{id}       — Get a single invoice by ID (params: supplier_id)
  POST /invoices            — Create a new invoice (query: supplier_id required, body: po_id, amount, due_date, currency)
"""

import os
import httpx

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

# TEMPLATE: Update accordingly
GET_INVOICES_SCHEMA = {
    "type": "function",
    "name": "get_invoices",
    "description": "Retrieve invoices. Use this to check payment statuses, find overdue invoices, or review invoice history.",
    "parameters": {
        "type": "object",
        "properties": {
            "print_string": {
                "type": "string",
                "description": "This parameter will be printed to the console.",
            },
        },
        "required": [],
    },
}

# TEMPLATE: Update accordingly
def get_invoices(print_string: str) -> str: 
    """Fetch invoices from the procurement API, optionally filtered."""
    
    # TEMPLATE: Update accordingly
    print(f"Printing: {print_string}")

    ## NOT SAFE: RETURNS INVOICES FOR ALL SUPPLIERS. 
    response = httpx.get(f"{API_BASE_URL}/invoices", params={}) # This must be updated
    response.raise_for_status()
    return response.text
