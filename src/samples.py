"""Canonical sample documents. Ground truth lives here so PDFs cannot drift from expected tables."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TableSpec:
    name: str
    caption: str
    headers: list[str]
    rows: list[list[str]]


@dataclass(frozen=True)
class SampleDoc:
    key: str
    title: str
    subtitle: str
    kind: str  # digital | scanned
    kv: dict[str, str] = field(default_factory=dict)
    paragraphs: list[str] = field(default_factory=list)
    tables: list[TableSpec] = field(default_factory=list)


INVOICE_TABLE = TableSpec(
    name="line_items",
    caption="Invoice line items",
    headers=["SKU", "Description", "Qty", "Unit Price", "Amount"],
    rows=[
        ["WID-100", "Industrial widget A", "12", "24.50", "294.00"],
        ["GAD-220", "Precision gadget B", "5", "119.00", "595.00"],
        ["CAB-018", "Shielded cable 2m", "20", "8.75", "175.00"],
        ["SVC-001", "Onsite installation", "1", "450.00", "450.00"],
        ["", "Subtotal", "", "", "1514.00"],
        ["", "Tax 8%", "", "", "121.12"],
        ["", "Total due", "", "", "1635.12"],
    ],
)

FINANCIAL_TABLE = TableSpec(
    name="income_statement",
    caption="Consolidated income statement (USD millions)",
    headers=["Metric", "Q1", "Q2", "Q3", "Q4", "FY2025"],
    rows=[
        ["Revenue", "12.4", "13.1", "14.8", "16.2", "56.5"],
        ["Cost of goods sold", "7.1", "7.4", "8.0", "8.6", "31.1"],
        ["Gross profit", "5.3", "5.7", "6.8", "7.6", "25.4"],
        ["Operating expenses", "3.2", "3.3", "3.5", "3.7", "13.7"],
        ["Operating income", "2.1", "2.4", "3.3", "3.9", "11.7"],
        ["Net margin %", "16.9", "18.3", "22.3", "24.1", "20.7"],
    ],
)

FORM_TABLE = TableSpec(
    name="service_account",
    caption="Service account details",
    headers=["Field", "Value"],
    rows=[
        ["Customer Name", "Jordan Hale"],
        ["Account Number", "AC-88921"],
        ["Service Address", "14 Harbor Lane, Boston MA"],
        ["Plan", "Industrial Plus"],
        ["Meter ID", "MTR-44109"],
        ["Billing Period", "Jul 2026"],
        ["Usage kWh", "14820"],
        ["Amount Due", "2376.40"],
    ],
)

SAMPLES: list[SampleDoc] = [
    SampleDoc(
        key="invoice_digital",
        title="INVOICE INV-2026-0941",
        subtitle="Northwind Industrial Supply  ·  14 August 2026",
        kind="digital",
        kv={
            "Invoice Number": "INV-2026-0941",
            "Bill To": "Acme Manufacturing",
            "Payment Terms": "Net 30",
            "PO Number": "PO-77419",
        },
        paragraphs=[
            "Please remit payment to Northwind Industrial Supply. "
            "Late invoices accrue 1.5% interest per month."
        ],
        tables=[INVOICE_TABLE],
    ),
    SampleDoc(
        key="invoice_scanned",
        title="INVOICE INV-2026-0941",
        subtitle="Northwind Industrial Supply  ·  14 August 2026",
        kind="scanned",
        kv={
            "Invoice Number": "INV-2026-0941",
            "Bill To": "Acme Manufacturing",
            "Payment Terms": "Net 30",
            "PO Number": "PO-77419",
        },
        paragraphs=[
            "Please remit payment to Northwind Industrial Supply. "
            "Late invoices accrue 1.5% interest per month."
        ],
        tables=[INVOICE_TABLE],
    ),
    SampleDoc(
        key="financials_digital",
        title="FY2025 Quarterly Operating Results",
        subtitle="Acme Manufacturing  ·  Confidential",
        kind="digital",
        paragraphs=[
            "Figures below are unaudited and stated in millions of USD. "
            "Gross profit equals revenue minus cost of goods sold."
        ],
        tables=[FINANCIAL_TABLE],
    ),
    SampleDoc(
        key="financials_scanned",
        title="FY2025 Quarterly Operating Results",
        subtitle="Acme Manufacturing  ·  Confidential",
        kind="scanned",
        paragraphs=[
            "Figures below are unaudited and stated in millions of USD. "
            "Gross profit equals revenue minus cost of goods sold."
        ],
        tables=[FINANCIAL_TABLE],
    ),
    SampleDoc(
        key="account_form_digital",
        title="Utility Service Statement",
        subtitle="Harbor Energy  ·  Statement date 02 August 2026",
        kind="digital",
        kv={
            "Customer Name": "Jordan Hale",
            "Account Number": "AC-88921",
        },
        paragraphs=["Payment is due within 21 days of the statement date."],
        tables=[FORM_TABLE],
    ),
]


def sample_by_key(key: str) -> SampleDoc:
    for sample in SAMPLES:
        if sample.key == key:
            return sample
    raise KeyError(key)
