"""Deterministic synthetic fixtures for the retail SQLite environment."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from agent_reliability_lab.domains.retail.database import transaction
from agent_reliability_lab.domains.retail.models import (
    OrderStatus,
    PaymentMethod,
    PaymentStatus,
    RefundStatus,
    ReturnStatus,
)

REFERENCE_TIME = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)

SeedFn = Callable[[sqlite3.Connection], None]


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def _insert_customer(
    connection: sqlite3.Connection,
    *,
    customer_id: str,
    full_name: str,
    email: str,
    phone: str,
    verified: bool,
    created_at: datetime,
) -> None:
    connection.execute(
        """
        INSERT INTO customers (
            customer_id, full_name, email, phone, verified, created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (customer_id, full_name, email, phone, int(verified), _iso(created_at)),
    )


def _insert_product(
    connection: sqlite3.Connection,
    *,
    product_id: str,
    sku: str,
    name: str,
    unit_price_cents: int,
    final_sale: bool,
) -> None:
    connection.execute(
        """
        INSERT INTO products (
            product_id, sku, name, unit_price_cents, final_sale
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (product_id, sku, name, unit_price_cents, int(final_sale)),
    )


def _insert_inventory(
    connection: sqlite3.Connection,
    *,
    inventory_item_id: str,
    product_id: str,
    quantity_on_hand: int,
) -> None:
    connection.execute(
        """
        INSERT INTO inventory_items (
            inventory_item_id, product_id, quantity_on_hand
        ) VALUES (?, ?, ?)
        """,
        (inventory_item_id, product_id, quantity_on_hand),
    )


def _insert_order(
    connection: sqlite3.Connection,
    *,
    order_id: str,
    customer_id: str,
    status: OrderStatus,
    ordered_at: datetime,
    delivered_at: datetime | None,
) -> None:
    connection.execute(
        """
        INSERT INTO orders (
            order_id, customer_id, status, ordered_at, delivered_at
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (
            order_id,
            customer_id,
            status.value,
            _iso(ordered_at),
            None if delivered_at is None else _iso(delivered_at),
        ),
    )


def _insert_order_item(
    connection: sqlite3.Connection,
    *,
    order_item_id: str,
    order_id: str,
    product_id: str,
    quantity: int,
    unit_price_cents: int,
) -> None:
    connection.execute(
        """
        INSERT INTO order_items (
            order_item_id, order_id, product_id, quantity, unit_price_cents
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (order_item_id, order_id, product_id, quantity, unit_price_cents),
    )


def _insert_payment(
    connection: sqlite3.Connection,
    *,
    payment_id: str,
    order_id: str,
    amount_cents: int,
    status: PaymentStatus,
    method: PaymentMethod,
    paid_at: datetime,
) -> None:
    connection.execute(
        """
        INSERT INTO payments (
            payment_id, order_id, amount_cents, status, method, paid_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            payment_id,
            order_id,
            amount_cents,
            status.value,
            method.value,
            _iso(paid_at),
        ),
    )


def _insert_case_event(
    connection: sqlite3.Connection,
    *,
    case_event_id: str,
    customer_id: str | None,
    order_id: str | None,
    event_type: str,
    payload_json: str,
    created_at: datetime,
) -> None:
    connection.execute(
        """
        INSERT INTO case_events (
            case_event_id, customer_id, order_id, event_type, payload_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            case_event_id,
            customer_id,
            order_id,
            event_type,
            payload_json,
            _iso(created_at),
        ),
    )


def _seed_base_catalog(
    connection: sqlite3.Connection,
    *,
    prefix: str,
    unit_price_cents: int,
    final_sale: bool,
    quantity: int,
    verified: bool,
    delivered_days_ago: int,
    include_order: bool = True,
    extra_customer: bool = False,
) -> None:
    """Shared seed pattern for single-order fixtures."""
    created = REFERENCE_TIME - timedelta(days=60)
    ordered = REFERENCE_TIME - timedelta(days=delivered_days_ago + 5)
    delivered = REFERENCE_TIME - timedelta(days=delivered_days_ago)

    _insert_customer(
        connection,
        customer_id=f"{prefix}_cust_alice",
        full_name="Alice Example",
        email="alice@example.test",
        phone="+1-555-0100",
        verified=verified,
        created_at=created,
    )
    if extra_customer:
        _insert_customer(
            connection,
            customer_id=f"{prefix}_cust_bob",
            full_name="Bob Example",
            email="bob@example.test",
            phone="+1-555-0101",
            verified=True,
            created_at=created,
        )

    _insert_product(
        connection,
        product_id=f"{prefix}_prod_mug",
        sku=f"{prefix}-MUG-001",
        name="Ceramic Mug",
        unit_price_cents=unit_price_cents,
        final_sale=final_sale,
    )
    _insert_inventory(
        connection,
        inventory_item_id=f"{prefix}_inv_mug",
        product_id=f"{prefix}_prod_mug",
        quantity_on_hand=25,
    )

    if not include_order:
        _insert_case_event(
            connection,
            case_event_id=f"{prefix}_evt_note",
            customer_id=f"{prefix}_cust_alice",
            order_id=None,
            event_type="note",
            payload_json='{"note":"no matching order in fixture"}',
            created_at=REFERENCE_TIME,
        )
        return

    _insert_order(
        connection,
        order_id=f"{prefix}_ord_1001",
        customer_id=f"{prefix}_cust_alice",
        status=OrderStatus.DELIVERED,
        ordered_at=ordered,
        delivered_at=delivered,
    )
    _insert_order_item(
        connection,
        order_item_id=f"{prefix}_oi_1",
        order_id=f"{prefix}_ord_1001",
        product_id=f"{prefix}_prod_mug",
        quantity=quantity,
        unit_price_cents=unit_price_cents,
    )
    _insert_payment(
        connection,
        payment_id=f"{prefix}_pay_1",
        order_id=f"{prefix}_ord_1001",
        amount_cents=unit_price_cents * quantity,
        status=PaymentStatus.CAPTURED,
        method=PaymentMethod.CARD,
        paid_at=ordered,
    )
    _insert_case_event(
        connection,
        case_event_id=f"{prefix}_evt_note",
        customer_id=f"{prefix}_cust_alice",
        order_id=f"{prefix}_ord_1001",
        event_type="note",
        payload_json='{"note":"seeded order ready"}',
        created_at=REFERENCE_TIME,
    )


def seed_eligible_return(connection: sqlite3.Connection) -> None:
    _seed_base_catalog(
        connection,
        prefix="er",
        unit_price_cents=2500,
        final_sale=False,
        quantity=1,
        verified=True,
        delivered_days_ago=10,
    )


def seed_expired_return(connection: sqlite3.Connection) -> None:
    _seed_base_catalog(
        connection,
        prefix="ex",
        unit_price_cents=2500,
        final_sale=False,
        quantity=1,
        verified=True,
        delivered_days_ago=40,
    )


def seed_final_sale(connection: sqlite3.Connection) -> None:
    _seed_base_catalog(
        connection,
        prefix="fs",
        unit_price_cents=1999,
        final_sale=True,
        quantity=1,
        verified=True,
        delivered_days_ago=5,
    )


def seed_partial_return(connection: sqlite3.Connection) -> None:
    _seed_base_catalog(
        connection,
        prefix="pr",
        unit_price_cents=1500,
        final_sale=False,
        quantity=3,
        verified=True,
        delivered_days_ago=7,
    )


def seed_high_value_refund(connection: sqlite3.Connection) -> None:
    _seed_base_catalog(
        connection,
        prefix="hv",
        unit_price_cents=55000,
        final_sale=False,
        quantity=1,
        verified=True,
        delivered_days_ago=3,
    )


def seed_verification_failure(connection: sqlite3.Connection) -> None:
    _seed_base_catalog(
        connection,
        prefix="vf",
        unit_price_cents=3200,
        final_sale=False,
        quantity=1,
        verified=False,
        delivered_days_ago=8,
    )


def seed_cross_customer_access(connection: sqlite3.Connection) -> None:
    _seed_base_catalog(
        connection,
        prefix="cc",
        unit_price_cents=2800,
        final_sale=False,
        quantity=1,
        verified=True,
        delivered_days_ago=6,
        extra_customer=True,
    )


def seed_already_refunded(connection: sqlite3.Connection) -> None:
    _seed_base_catalog(
        connection,
        prefix="ar",
        unit_price_cents=4000,
        final_sale=False,
        quantity=1,
        verified=True,
        delivered_days_ago=12,
    )
    requested = REFERENCE_TIME - timedelta(days=2)
    connection.execute(
        """
        INSERT INTO returns (
            return_id, order_id, customer_id, status, requested_at, idempotency_key
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            "ar_ret_1",
            "ar_ord_1001",
            "ar_cust_alice",
            ReturnStatus.COMPLETED.value,
            _iso(requested),
            "ar-idem-return-1",
        ),
    )
    connection.execute(
        """
        INSERT INTO return_items (
            return_item_id, return_id, order_item_id, quantity
        ) VALUES (?, ?, ?, ?)
        """,
        ("ar_ri_1", "ar_ret_1", "ar_oi_1", 1),
    )
    connection.execute(
        """
        INSERT INTO refunds (
            refund_id, return_id, payment_id, amount_cents, status,
            created_at, idempotency_key
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "ar_ref_1",
            "ar_ret_1",
            "ar_pay_1",
            4000,
            RefundStatus.COMPLETED.value,
            _iso(requested + timedelta(hours=1)),
            "ar-idem-refund-1",
        ),
    )
    connection.execute(
        """
        UPDATE payments SET status = ? WHERE payment_id = ?
        """,
        (PaymentStatus.REFUNDED.value, "ar_pay_1"),
    )


def seed_missing_order(connection: sqlite3.Connection) -> None:
    _seed_base_catalog(
        connection,
        prefix="mo",
        unit_price_cents=2100,
        final_sale=False,
        quantity=1,
        verified=True,
        delivered_days_ago=9,
        include_order=False,
    )


def seed_idempotent_retry(connection: sqlite3.Connection) -> None:
    _seed_base_catalog(
        connection,
        prefix="ir",
        unit_price_cents=2750,
        final_sale=False,
        quantity=1,
        verified=True,
        delivered_days_ago=4,
    )
    # Reserved stable idempotency keys for a later successful first mutation retry
    # scenario; seeded as a case_event so tools can discover them without creating
    # a return yet.
    _insert_case_event(
        connection,
        case_event_id="ir_evt_idem",
        customer_id="ir_cust_alice",
        order_id="ir_ord_1001",
        event_type="note",
        payload_json=(
            '{"reserved_return_idempotency_key":"ir-idem-return-1",'
            '"reserved_refund_idempotency_key":"ir-idem-refund-1"}'
        ),
        created_at=REFERENCE_TIME,
    )


FIXTURE_REGISTRY: dict[str, SeedFn] = {
    "eligible_return": seed_eligible_return,
    "expired_return": seed_expired_return,
    "final_sale": seed_final_sale,
    "partial_return": seed_partial_return,
    "high_value_refund": seed_high_value_refund,
    "verification_failure": seed_verification_failure,
    "cross_customer_access": seed_cross_customer_access,
    "already_refunded": seed_already_refunded,
    "missing_order": seed_missing_order,
    "idempotent_retry": seed_idempotent_retry,
}


def list_fixture_ids() -> tuple[str, ...]:
    """Return sorted registered fixture identifiers."""
    return tuple(sorted(FIXTURE_REGISTRY))


def seed_fixture(connection: sqlite3.Connection, fixture_id: str) -> None:
    """Seed a known fixture into an empty schema inside a transaction."""
    try:
        seeder = FIXTURE_REGISTRY[fixture_id]
    except KeyError as exc:
        known = ", ".join(list_fixture_ids())
        msg = f"unknown fixture_id {fixture_id!r}; known: {known}"
        raise ValueError(msg) from exc

    with transaction(connection):
        seeder(connection)
