"""Tests for retail SQLite schema and constraints."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from agent_reliability_lab.domains.retail.database import (
    REQUIRED_TABLES,
    connect,
    initialize_schema,
)
from agent_reliability_lab.domains.retail.seed import REFERENCE_TIME


@pytest.fixture
def db_conn(tmp_path: Path) -> sqlite3.Connection:
    path = tmp_path / "schema.db"
    connection = connect(path)
    initialize_schema(connection)
    yield connection
    connection.close()


def test_all_required_tables_are_created(db_conn: sqlite3.Connection) -> None:
    rows = db_conn.execute(
        """
        SELECT name FROM sqlite_master
        WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
        ORDER BY name
        """
    ).fetchall()
    names = {row["name"] for row in rows}
    assert set(REQUIRED_TABLES) <= names


def test_foreign_keys_are_enabled(db_conn: sqlite3.Connection) -> None:
    value = db_conn.execute("PRAGMA foreign_keys").fetchone()[0]
    assert value == 1


def test_foreign_key_constraint_rejects_invalid_order(
    db_conn: sqlite3.Connection,
) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        db_conn.execute(
            """
            INSERT INTO orders (
                order_id, customer_id, status, ordered_at, delivered_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                "ord_x",
                "missing_customer",
                "delivered",
                REFERENCE_TIME.isoformat(),
                None,
            ),
        )


def test_money_check_rejects_negative_product_price(
    db_conn: sqlite3.Connection,
) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        db_conn.execute(
            """
            INSERT INTO products (
                product_id, sku, name, unit_price_cents, final_sale
            ) VALUES (?, ?, ?, ?, ?)
            """,
            ("prod_x", "SKU-X", "Bad", -1, 0),
        )


def test_quantity_check_rejects_zero_order_item(db_conn: sqlite3.Connection) -> None:
    db_conn.execute(
        """
        INSERT INTO customers (
            customer_id, full_name, email, phone, verified, created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            "cust_1",
            "Test User",
            "test@example.test",
            "+1-555-0000",
            1,
            REFERENCE_TIME.isoformat(),
        ),
    )
    db_conn.execute(
        """
        INSERT INTO products (
            product_id, sku, name, unit_price_cents, final_sale
        ) VALUES (?, ?, ?, ?, ?)
        """,
        ("prod_1", "SKU-1", "Item", 100, 0),
    )
    db_conn.execute(
        """
        INSERT INTO orders (
            order_id, customer_id, status, ordered_at, delivered_at
        ) VALUES (?, ?, ?, ?, ?)
        """,
        ("ord_1", "cust_1", "delivered", REFERENCE_TIME.isoformat(), None),
    )
    with pytest.raises(sqlite3.IntegrityError):
        db_conn.execute(
            """
            INSERT INTO order_items (
                order_item_id, order_id, product_id, quantity, unit_price_cents
            ) VALUES (?, ?, ?, ?, ?)
            """,
            ("oi_1", "ord_1", "prod_1", 0, 100),
        )


def test_unique_idempotency_keys_enforced_on_returns_and_refunds(
    db_conn: sqlite3.Connection,
) -> None:
    db_conn.execute(
        """
        INSERT INTO customers (
            customer_id, full_name, email, phone, verified, created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            "cust_1",
            "Test User",
            "test@example.test",
            "+1-555-0000",
            1,
            REFERENCE_TIME.isoformat(),
        ),
    )
    db_conn.execute(
        """
        INSERT INTO products (
            product_id, sku, name, unit_price_cents, final_sale
        ) VALUES (?, ?, ?, ?, ?)
        """,
        ("prod_1", "SKU-1", "Item", 1000, 0),
    )
    db_conn.execute(
        """
        INSERT INTO orders (
            order_id, customer_id, status, ordered_at, delivered_at
        ) VALUES (?, ?, ?, ?, ?)
        """,
        ("ord_1", "cust_1", "delivered", REFERENCE_TIME.isoformat(), None),
    )
    db_conn.execute(
        """
        INSERT INTO order_items (
            order_item_id, order_id, product_id, quantity, unit_price_cents
        ) VALUES (?, ?, ?, ?, ?)
        """,
        ("oi_1", "ord_1", "prod_1", 1, 1000),
    )
    db_conn.execute(
        """
        INSERT INTO payments (
            payment_id, order_id, amount_cents, status, method, paid_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("pay_1", "ord_1", 1000, "captured", "card", REFERENCE_TIME.isoformat()),
    )
    db_conn.execute(
        """
        INSERT INTO returns (
            return_id, order_id, customer_id, status, requested_at, idempotency_key
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            "ret_1",
            "ord_1",
            "cust_1",
            "completed",
            REFERENCE_TIME.isoformat(),
            "idem-return",
        ),
    )
    with pytest.raises(sqlite3.IntegrityError):
        db_conn.execute(
            """
            INSERT INTO returns (
                return_id, order_id, customer_id, status, requested_at, idempotency_key
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "ret_2",
                "ord_1",
                "cust_1",
                "requested",
                REFERENCE_TIME.isoformat(),
                "idem-return",
            ),
        )

    db_conn.execute(
        """
        INSERT INTO refunds (
            refund_id, return_id, payment_id, amount_cents, status,
            created_at, idempotency_key
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "ref_1",
            "ret_1",
            "pay_1",
            1000,
            "completed",
            REFERENCE_TIME.isoformat(),
            "idem-refund",
        ),
    )
    with pytest.raises(sqlite3.IntegrityError):
        db_conn.execute(
            """
            INSERT INTO refunds (
                refund_id, return_id, payment_id, amount_cents, status,
                created_at, idempotency_key
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ref_2",
                "ret_1",
                "pay_1",
                1000,
                "pending",
                REFERENCE_TIME.isoformat(),
                "idem-refund",
            ),
        )
