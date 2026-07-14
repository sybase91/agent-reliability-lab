"""Unit tests for pure retail policies."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from agent_reliability_lab.domains.retail.models import OrderStatus
from agent_reliability_lab.domains.retail.policies import (
    MANAGER_APPROVAL_THRESHOLD_CENTS,
    PolicyCode,
    check_final_sale,
    check_identity_verification,
    check_manager_approval_required,
    check_order_ownership,
    check_refundable_amount,
    check_return_quantity,
    check_return_window,
    check_session_verified,
)
from agent_reliability_lab.domains.retail.seed import REFERENCE_TIME


def test_identity_verification_success_and_failure() -> None:
    ok = check_identity_verification(
        customer_exists=True,
        account_verification_enabled=True,
        email_matches=True,
        phone_matches=True,
    )
    assert ok.allowed
    assert ok.code is PolicyCode.OK

    missing = check_identity_verification(
        customer_exists=False,
        account_verification_enabled=False,
        email_matches=False,
        phone_matches=False,
    )
    assert not missing.allowed
    assert missing.code is PolicyCode.CUSTOMER_NOT_FOUND

    failed = check_identity_verification(
        customer_exists=True,
        account_verification_enabled=False,
        email_matches=True,
        phone_matches=True,
    )
    assert not failed.allowed
    assert failed.code is PolicyCode.VERIFICATION_FAILED


def test_session_verification_required() -> None:
    assert check_session_verified(session_verified=True).allowed
    denied = check_session_verified(session_verified=False)
    assert denied.code is PolicyCode.CUSTOMER_NOT_VERIFIED


def test_order_ownership() -> None:
    assert check_order_ownership(
        order_exists=True,
        order_customer_id="c1",
        requesting_customer_id="c1",
    ).allowed
    assert (
        check_order_ownership(
            order_exists=False,
            order_customer_id=None,
            requesting_customer_id="c1",
        ).code
        is PolicyCode.ORDER_NOT_FOUND
    )
    assert (
        check_order_ownership(
            order_exists=True,
            order_customer_id="c1",
            requesting_customer_id="c2",
        ).code
        is PolicyCode.ORDER_ACCESS_DENIED
    )


def test_return_window_exactly_30_days_eligible() -> None:
    delivered = REFERENCE_TIME - timedelta(days=30)
    decision = check_return_window(
        order_status=OrderStatus.DELIVERED,
        delivered_at=delivered,
        as_of=REFERENCE_TIME,
    )
    assert decision.allowed
    assert decision.evidence["days_since_delivery"] == 30


def test_return_window_over_30_days_denied() -> None:
    delivered = REFERENCE_TIME - timedelta(days=31)
    decision = check_return_window(
        order_status=OrderStatus.DELIVERED,
        delivered_at=delivered,
        as_of=REFERENCE_TIME,
    )
    assert not decision.allowed
    assert decision.code is PolicyCode.RETURN_WINDOW_EXPIRED


def test_return_window_not_delivered() -> None:
    decision = check_return_window(
        order_status=OrderStatus.SHIPPED,
        delivered_at=None,
        as_of=REFERENCE_TIME,
    )
    assert decision.code is PolicyCode.ORDER_NOT_DELIVERED


def test_final_sale_denied() -> None:
    decision = check_final_sale(final_sale=True, product_id="p1")
    assert decision.code is PolicyCode.FINAL_SALE_ITEM


def test_return_quantity_rules() -> None:
    ok = check_return_quantity(
        purchased_quantity=3,
        already_returned_quantity=1,
        requested_quantity=2,
    )
    assert ok.allowed

    invalid = check_return_quantity(
        purchased_quantity=3,
        already_returned_quantity=0,
        requested_quantity=0,
    )
    assert invalid.code is PolicyCode.INVALID_RETURN_QUANTITY

    exceeded = check_return_quantity(
        purchased_quantity=3,
        already_returned_quantity=1,
        requested_quantity=3,
    )
    assert exceeded.code is PolicyCode.RETURN_QUANTITY_EXCEEDED


def test_refund_amount_and_approval_threshold() -> None:
    ok = check_refundable_amount(
        payment_exists=True,
        payment_amount_cents=10_000,
        already_refunded_cents=1_000,
        requested_amount_cents=9_000,
    )
    assert ok.allowed

    exceeded = check_refundable_amount(
        payment_exists=True,
        payment_amount_cents=10_000,
        already_refunded_cents=1_000,
        requested_amount_cents=9_001,
    )
    assert exceeded.code is PolicyCode.REFUND_EXCEEDS_AVAILABLE_AMOUNT

    at_threshold = check_manager_approval_required(
        amount_cents=MANAGER_APPROVAL_THRESHOLD_CENTS
    )
    assert at_threshold.allowed

    above = check_manager_approval_required(
        amount_cents=MANAGER_APPROVAL_THRESHOLD_CENTS + 1
    )
    assert above.code is PolicyCode.MANAGER_APPROVAL_REQUIRED


def test_as_of_must_be_explicit_timezone_aware() -> None:
    as_of = datetime(2024, 6, 15, 12, 0, tzinfo=UTC)
    delivered = as_of - timedelta(days=10)
    decision = check_return_window(
        order_status=OrderStatus.DELIVERED,
        delivered_at=delivered,
        as_of=as_of,
    )
    assert decision.allowed
