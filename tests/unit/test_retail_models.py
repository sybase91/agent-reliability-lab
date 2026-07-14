"""Tests for retail Pydantic boundary models."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from agent_reliability_lab.domains.retail.database import (
    row_to_customer,
    row_to_order,
    row_to_order_item,
    row_to_refund,
    row_to_return,
    row_to_return_item,
)
from agent_reliability_lab.domains.retail.environment import RetailEnvironment
from agent_reliability_lab.domains.retail.models import (
    Approval,
    ApprovalStatus,
    CaseEvent,
    CaseEventType,
    Customer,
    InventoryItem,
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
from agent_reliability_lab.domains.retail.seed import REFERENCE_TIME


def test_all_models_accept_valid_data() -> None:
    Customer(
        customer_id="c1",
        full_name="Alice Example",
        email="alice@example.test",
        phone="+1-555-0100",
        verified=True,
        created_at=REFERENCE_TIME,
    )
    Product(
        product_id="p1",
        sku="SKU-1",
        name="Mug",
        unit_price_cents=2500,
        final_sale=False,
    )
    InventoryItem(inventory_item_id="i1", product_id="p1", quantity_on_hand=0)
    Order(
        order_id="o1",
        customer_id="c1",
        status=OrderStatus.DELIVERED,
        ordered_at=REFERENCE_TIME,
        delivered_at=REFERENCE_TIME,
    )
    OrderItem(
        order_item_id="oi1",
        order_id="o1",
        product_id="p1",
        quantity=1,
        unit_price_cents=2500,
    )
    Payment(
        payment_id="pay1",
        order_id="o1",
        amount_cents=2500,
        status=PaymentStatus.CAPTURED,
        method=PaymentMethod.CARD,
        paid_at=REFERENCE_TIME,
    )
    ret = Return(
        return_id="r1",
        order_id="o1",
        customer_id="c1",
        status=ReturnStatus.REQUESTED,
        requested_at=REFERENCE_TIME,
        idempotency_key="idem-1",
    )
    ReturnItem(
        return_item_id="ri1",
        return_id=ret.return_id,
        order_item_id="oi1",
        quantity=1,
    )
    refund = Refund(
        refund_id="rf1",
        return_id="r1",
        payment_id="pay1",
        amount_cents=2500,
        status=RefundStatus.PENDING,
        created_at=REFERENCE_TIME,
        idempotency_key="idem-rf-1",
    )
    Approval(
        approval_id="a1",
        refund_id=refund.refund_id,
        status=ApprovalStatus.PENDING,
        requested_at=REFERENCE_TIME,
        resolved_at=None,
    )
    CaseEvent(
        case_event_id="e1",
        customer_id="c1",
        order_id="o1",
        event_type=CaseEventType.NOTE,
        payload_json="{}",
        created_at=REFERENCE_TIME,
    )


def test_negative_money_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Product(
            product_id="p1",
            sku="SKU-1",
            name="Mug",
            unit_price_cents=-1,
            final_sale=False,
        )
    with pytest.raises(ValidationError):
        Payment(
            payment_id="pay1",
            order_id="o1",
            amount_cents=-5,
            status=PaymentStatus.CAPTURED,
            method=PaymentMethod.CARD,
            paid_at=REFERENCE_TIME,
        )


def test_zero_or_negative_required_quantities_are_rejected() -> None:
    with pytest.raises(ValidationError):
        OrderItem(
            order_item_id="oi1",
            order_id="o1",
            product_id="p1",
            quantity=0,
            unit_price_cents=100,
        )
    with pytest.raises(ValidationError):
        ReturnItem(
            return_item_id="ri1",
            return_id="r1",
            order_item_id="oi1",
            quantity=-1,
        )


def test_naive_timestamps_are_rejected() -> None:
    naive = datetime(2024, 6, 15, 12, 0, 0)
    with pytest.raises(ValidationError):
        Customer(
            customer_id="c1",
            full_name="Alice Example",
            email="alice@example.test",
            phone="+1-555-0100",
            verified=True,
            created_at=naive,
        )


def test_non_utc_timestamps_are_normalized_to_utc() -> None:
    eastern = timezone(timedelta(hours=-4))
    local = datetime(2024, 6, 15, 8, 0, 0, tzinfo=eastern)
    customer = Customer(
        customer_id="c1",
        full_name="Alice Example",
        email="alice@example.test",
        phone="+1-555-0100",
        verified=True,
        created_at=local,
    )
    assert customer.created_at.tzinfo == UTC
    assert customer.created_at == datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)


def test_extra_fields_are_forbidden() -> None:
    with pytest.raises(ValidationError):
        Product(
            product_id="p1",
            sku="SKU-1",
            name="Mug",
            unit_price_cents=100,
            final_sale=False,
            unexpected="nope",  # type: ignore[call-arg]
        )


def test_return_items_support_partial_quantities() -> None:
    item = ReturnItem(
        return_item_id="ri1",
        return_id="r1",
        order_item_id="oi1",
        quantity=2,
    )
    assert item.quantity == 2


def test_representative_rows_round_trip_into_models(tmp_path: Path) -> None:
    del tmp_path  # environment uses its own temp file
    with RetailEnvironment("already_refunded") as env:
        customer_row = env.connection.execute(
            "SELECT * FROM customers ORDER BY customer_id"
        ).fetchone()
        order_row = env.connection.execute(
            "SELECT * FROM orders ORDER BY order_id"
        ).fetchone()
        order_item_row = env.connection.execute(
            "SELECT * FROM order_items ORDER BY order_item_id"
        ).fetchone()
        return_row = env.connection.execute(
            "SELECT * FROM returns ORDER BY return_id"
        ).fetchone()
        return_item_row = env.connection.execute(
            "SELECT * FROM return_items ORDER BY return_item_id"
        ).fetchone()
        refund_row = env.connection.execute(
            "SELECT * FROM refunds ORDER BY refund_id"
        ).fetchone()

        customer = row_to_customer(customer_row)
        order = row_to_order(order_row)
        order_item = row_to_order_item(order_item_row)
        ret = row_to_return(return_row)
        return_item = row_to_return_item(return_item_row)
        refund = row_to_refund(refund_row)

        assert customer.customer_id == "ar_cust_alice"
        assert order.status == OrderStatus.DELIVERED
        assert order_item.quantity == 1
        assert ret.status == ReturnStatus.COMPLETED
        assert return_item.quantity == 1
        assert refund.status == RefundStatus.COMPLETED
        assert refund.amount_cents == 4000
