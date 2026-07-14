"""Explicit SQLite access for the retail domain (no ORM)."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from agent_reliability_lab.domains.retail.models import (
    Approval,
    ApprovalStatus,
    CaseEvent,
    CaseEventType,
    Customer,
    Order,
    OrderItem,
    OrderStatus,
    Payment,
    PaymentMethod,
    PaymentStatus,
    Product,
    Refund,
    RefundStatus,
    Return,
    ReturnItem,
    ReturnStatus,
)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS customers (
    customer_id TEXT PRIMARY KEY,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL,
    phone TEXT NOT NULL,
    verified INTEGER NOT NULL CHECK (verified IN (0, 1)),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS products (
    product_id TEXT PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    unit_price_cents INTEGER NOT NULL CHECK (unit_price_cents >= 0),
    final_sale INTEGER NOT NULL CHECK (final_sale IN (0, 1))
);

CREATE TABLE IF NOT EXISTS inventory_items (
    inventory_item_id TEXT PRIMARY KEY,
    product_id TEXT NOT NULL UNIQUE REFERENCES products(product_id),
    quantity_on_hand INTEGER NOT NULL CHECK (quantity_on_hand >= 0)
);

CREATE TABLE IF NOT EXISTS orders (
    order_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES customers(customer_id),
    status TEXT NOT NULL,
    ordered_at TEXT NOT NULL,
    delivered_at TEXT
);

CREATE TABLE IF NOT EXISTS order_items (
    order_item_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL REFERENCES orders(order_id),
    product_id TEXT NOT NULL REFERENCES products(product_id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_cents INTEGER NOT NULL CHECK (unit_price_cents >= 0)
);

CREATE TABLE IF NOT EXISTS payments (
    payment_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL REFERENCES orders(order_id),
    amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
    status TEXT NOT NULL,
    method TEXT NOT NULL,
    paid_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS returns (
    return_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL REFERENCES orders(order_id),
    customer_id TEXT NOT NULL REFERENCES customers(customer_id),
    status TEXT NOT NULL,
    requested_at TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS return_items (
    return_item_id TEXT PRIMARY KEY,
    return_id TEXT NOT NULL REFERENCES returns(return_id),
    order_item_id TEXT NOT NULL REFERENCES order_items(order_item_id),
    quantity INTEGER NOT NULL CHECK (quantity > 0)
);

CREATE TABLE IF NOT EXISTS refunds (
    refund_id TEXT PRIMARY KEY,
    return_id TEXT NOT NULL REFERENCES returns(return_id),
    payment_id TEXT NOT NULL REFERENCES payments(payment_id),
    amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS approvals (
    approval_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL REFERENCES orders(order_id),
    payment_id TEXT NOT NULL REFERENCES payments(payment_id),
    amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
    status TEXT NOT NULL,
    requested_at TEXT NOT NULL,
    resolved_at TEXT,
    refund_id TEXT REFERENCES refunds(refund_id)
);

CREATE TABLE IF NOT EXISTS case_events (
    case_event_id TEXT PRIMARY KEY,
    customer_id TEXT REFERENCES customers(customer_id),
    order_id TEXT REFERENCES orders(order_id),
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_orders_customer_id ON orders(customer_id);
CREATE INDEX IF NOT EXISTS idx_order_items_order_id ON order_items(order_id);
CREATE INDEX IF NOT EXISTS idx_payments_order_id ON payments(order_id);
CREATE INDEX IF NOT EXISTS idx_returns_order_id ON returns(order_id);
CREATE INDEX IF NOT EXISTS idx_return_items_return_id ON return_items(return_id);
CREATE INDEX IF NOT EXISTS idx_refunds_return_id ON refunds(return_id);
CREATE INDEX IF NOT EXISTS idx_approvals_order_id ON approvals(order_id);
CREATE INDEX IF NOT EXISTS idx_approvals_payment_id ON approvals(payment_id);
"""

REQUIRED_TABLES: tuple[str, ...] = (
    "customers",
    "products",
    "inventory_items",
    "orders",
    "order_items",
    "payments",
    "returns",
    "return_items",
    "refunds",
    "approvals",
    "case_events",
)


def connect(db_path: Path | str) -> sqlite3.Connection:
    """Open a SQLite connection with foreign keys enabled and Row factory."""
    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_schema(connection: sqlite3.Connection) -> None:
    """Create retail tables, constraints, and indexes."""
    connection.executescript(SCHEMA_SQL)
    connection.commit()


@contextmanager
def transaction(connection: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Commit on success; roll back and re-raise on failure."""
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _parse_utc_optional(value: str | None) -> datetime | None:
    if value is None:
        return None
    return _parse_utc(value)


def row_to_customer(row: sqlite3.Row) -> Customer:
    """Convert a customers row into a Customer model."""
    return Customer(
        customer_id=row["customer_id"],
        full_name=row["full_name"],
        email=row["email"],
        phone=row["phone"],
        verified=bool(row["verified"]),
        created_at=_parse_utc(row["created_at"]),
    )


def row_to_order(row: sqlite3.Row) -> Order:
    """Convert an orders row into an Order model."""
    return Order(
        order_id=row["order_id"],
        customer_id=row["customer_id"],
        status=OrderStatus(row["status"]),
        ordered_at=_parse_utc(row["ordered_at"]),
        delivered_at=_parse_utc_optional(row["delivered_at"]),
    )


def row_to_order_item(row: sqlite3.Row) -> OrderItem:
    """Convert an order_items row into an OrderItem model."""
    return OrderItem(
        order_item_id=row["order_item_id"],
        order_id=row["order_id"],
        product_id=row["product_id"],
        quantity=row["quantity"],
        unit_price_cents=row["unit_price_cents"],
    )


def row_to_return(row: sqlite3.Row) -> Return:
    """Convert a returns row into a Return model."""
    return Return(
        return_id=row["return_id"],
        order_id=row["order_id"],
        customer_id=row["customer_id"],
        status=ReturnStatus(row["status"]),
        requested_at=_parse_utc(row["requested_at"]),
        idempotency_key=row["idempotency_key"],
    )


def row_to_return_item(row: sqlite3.Row) -> ReturnItem:
    """Convert a return_items row into a ReturnItem model."""
    return ReturnItem(
        return_item_id=row["return_item_id"],
        return_id=row["return_id"],
        order_item_id=row["order_item_id"],
        quantity=row["quantity"],
    )


def row_to_refund(row: sqlite3.Row) -> Refund:
    """Convert a refunds row into a Refund model."""
    return Refund(
        refund_id=row["refund_id"],
        return_id=row["return_id"],
        payment_id=row["payment_id"],
        amount_cents=row["amount_cents"],
        status=RefundStatus(row["status"]),
        created_at=_parse_utc(row["created_at"]),
        idempotency_key=row["idempotency_key"],
    )


def row_to_payment(row: sqlite3.Row) -> Payment:
    """Convert a payments row into a Payment model."""
    return Payment(
        payment_id=row["payment_id"],
        order_id=row["order_id"],
        amount_cents=row["amount_cents"],
        status=PaymentStatus(row["status"]),
        method=PaymentMethod(row["method"]),
        paid_at=_parse_utc(row["paid_at"]),
    )


def row_to_product(row: sqlite3.Row) -> Product:
    """Convert a products row into a Product model."""
    return Product(
        product_id=row["product_id"],
        sku=row["sku"],
        name=row["name"],
        unit_price_cents=row["unit_price_cents"],
        final_sale=bool(row["final_sale"]),
    )


def row_to_approval(row: sqlite3.Row) -> Approval:
    """Convert an approvals row into an Approval model."""
    return Approval(
        approval_id=row["approval_id"],
        order_id=row["order_id"],
        payment_id=row["payment_id"],
        amount_cents=row["amount_cents"],
        status=ApprovalStatus(row["status"]),
        requested_at=_parse_utc(row["requested_at"]),
        resolved_at=_parse_utc_optional(row["resolved_at"]),
        refund_id=row["refund_id"],
    )


def row_to_case_event(row: sqlite3.Row) -> CaseEvent:
    """Convert a case_events row into a CaseEvent model."""
    return CaseEvent(
        case_event_id=row["case_event_id"],
        customer_id=row["customer_id"],
        order_id=row["order_id"],
        event_type=CaseEventType(row["event_type"]),
        payload_json=row["payload_json"],
        created_at=_parse_utc(row["created_at"]),
    )
