"""Tests for deterministic retail fixtures."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from agent_reliability_lab.domains.retail.database import connect, initialize_schema
from agent_reliability_lab.domains.retail.environment import RetailEnvironment
from agent_reliability_lab.domains.retail.seed import list_fixture_ids, seed_fixture

TABLES_FOR_DUMP = (
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


def _logical_dump(
    connection: sqlite3.Connection,
) -> dict[str, list[tuple[object, ...]]]:
    dump: dict[str, list[tuple[object, ...]]] = {}
    for table in TABLES_FOR_DUMP:
        rows = connection.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall()
        dump[table] = [tuple(row) for row in rows]
    return dump


def test_fixture_ids_are_discoverable() -> None:
    ids = list_fixture_ids()
    assert ids == tuple(sorted(ids))
    expected = {
        "eligible_return",
        "expired_return",
        "final_sale",
        "partial_return",
        "high_value_refund",
        "verification_failure",
        "cross_customer_access",
        "already_refunded",
        "missing_order",
        "idempotent_retry",
    }
    assert set(ids) == expected


def test_every_registered_fixture_can_be_seeded(tmp_path: Path) -> None:
    for fixture_id in list_fixture_ids():
        path = tmp_path / f"{fixture_id}.db"
        connection = connect(path)
        initialize_schema(connection)
        seed_fixture(connection, fixture_id)
        connection.close()


def test_equal_fixture_ids_produce_equal_logical_records() -> None:
    for fixture_id in list_fixture_ids():
        with (
            RetailEnvironment(fixture_id) as left,
            RetailEnvironment(fixture_id) as right,
        ):
            assert _logical_dump(left.connection) == _logical_dump(right.connection)
            assert left.db_path != right.db_path


def test_unknown_fixture_id_raises(tmp_path: Path) -> None:
    path = tmp_path / "bad.db"
    connection = connect(path)
    initialize_schema(connection)
    with pytest.raises(ValueError, match="unknown fixture_id"):
        seed_fixture(connection, "does_not_exist")
    connection.close()


def test_cross_customer_access_includes_two_customers() -> None:
    with RetailEnvironment("cross_customer_access") as env:
        count = env.connection.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
        assert count == 2
        owner = env.connection.execute(
            "SELECT customer_id FROM orders ORDER BY order_id"
        ).fetchone()[0]
        assert owner == "cc_cust_alice"


def test_partial_return_has_quantity_greater_than_one() -> None:
    with RetailEnvironment("partial_return") as env:
        quantity = env.connection.execute(
            "SELECT quantity FROM order_items ORDER BY order_item_id"
        ).fetchone()[0]
        assert quantity > 1


def test_high_value_refund_exceeds_threshold() -> None:
    with RetailEnvironment("high_value_refund") as env:
        amount = env.connection.execute(
            "SELECT amount_cents FROM payments ORDER BY payment_id"
        ).fetchone()[0]
        assert amount > 50_000


def test_already_refunded_includes_completed_refund() -> None:
    with RetailEnvironment("already_refunded") as env:
        status = env.connection.execute(
            "SELECT status FROM refunds ORDER BY refund_id"
        ).fetchone()[0]
        assert status == "completed"


def test_missing_order_has_customer_without_orders() -> None:
    with RetailEnvironment("missing_order") as env:
        customers = env.connection.execute("SELECT COUNT(*) FROM customers").fetchone()[
            0
        ]
        orders = env.connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        assert customers >= 1
        assert orders == 0


def test_verification_failure_customer_unverified() -> None:
    with RetailEnvironment("verification_failure") as env:
        verified = env.connection.execute(
            "SELECT verified FROM customers ORDER BY customer_id"
        ).fetchone()[0]
        assert verified == 0


def test_final_sale_product_flag() -> None:
    with RetailEnvironment("final_sale") as env:
        final_sale = env.connection.execute(
            "SELECT final_sale FROM products ORDER BY product_id"
        ).fetchone()[0]
        assert final_sale == 1


def test_idempotent_retry_reserves_keys() -> None:
    with RetailEnvironment("idempotent_retry") as env:
        payload = env.connection.execute(
            """
            SELECT payload_json FROM case_events
            WHERE case_event_id = 'ir_evt_idem'
            """
        ).fetchone()[0]
        assert "ir-idem-return-1" in payload
        assert "ir-idem-refund-1" in payload
