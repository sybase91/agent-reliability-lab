"""Pure retail business policies.

No database connections, SQL, wall clock, or harness tracing.
Callers supply explicit context including timezone-aware ``as_of``.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from agent_reliability_lab.domains.retail.models import OrderStatus

RETURN_WINDOW_DAYS = 30
MANAGER_APPROVAL_THRESHOLD_CENTS = 50_000


class PolicyCode(StrEnum):
    """Stable machine-readable business outcome codes."""

    OK = "OK"
    CUSTOMER_NOT_FOUND = "CUSTOMER_NOT_FOUND"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"
    CUSTOMER_NOT_VERIFIED = "CUSTOMER_NOT_VERIFIED"
    ORDER_NOT_FOUND = "ORDER_NOT_FOUND"
    ORDER_ACCESS_DENIED = "ORDER_ACCESS_DENIED"
    ORDER_NOT_DELIVERED = "ORDER_NOT_DELIVERED"
    RETURN_WINDOW_EXPIRED = "RETURN_WINDOW_EXPIRED"
    FINAL_SALE_ITEM = "FINAL_SALE_ITEM"
    INVALID_RETURN_QUANTITY = "INVALID_RETURN_QUANTITY"
    RETURN_QUANTITY_EXCEEDED = "RETURN_QUANTITY_EXCEEDED"
    PAYMENT_NOT_FOUND = "PAYMENT_NOT_FOUND"
    REFUND_EXCEEDS_AVAILABLE_AMOUNT = "REFUND_EXCEEDS_AVAILABLE_AMOUNT"
    MANAGER_APPROVAL_REQUIRED = "MANAGER_APPROVAL_REQUIRED"
    MANAGER_APPROVAL_NOT_FOUND = "MANAGER_APPROVAL_NOT_FOUND"
    RETURN_ALREADY_EXISTS = "RETURN_ALREADY_EXISTS"
    REFUND_ALREADY_EXISTS = "REFUND_ALREADY_EXISTS"
    INVALID_STATE = "INVALID_STATE"


class PolicyDecision(BaseModel):
    """Typed policy result; business denials are not exceptions."""

    model_config = ConfigDict(extra="forbid")

    allowed: bool
    code: PolicyCode
    reason: str
    evidence: dict[str, Any] = Field(default_factory=dict)


def _ok(reason: str, **evidence: Any) -> PolicyDecision:
    return PolicyDecision(
        allowed=True,
        code=PolicyCode.OK,
        reason=reason,
        evidence=evidence,
    )


def _deny(code: PolicyCode, reason: str, **evidence: Any) -> PolicyDecision:
    return PolicyDecision(
        allowed=False,
        code=code,
        reason=reason,
        evidence=evidence,
    )


def check_identity_verification(
    *,
    customer_exists: bool,
    account_verification_enabled: bool,
    email_matches: bool,
    phone_matches: bool,
) -> PolicyDecision:
    """Decide whether synthetic credentials verify the customer account."""
    if not customer_exists:
        return _deny(
            PolicyCode.CUSTOMER_NOT_FOUND,
            "Customer was not found.",
        )
    if not account_verification_enabled or not email_matches or not phone_matches:
        return _deny(
            PolicyCode.VERIFICATION_FAILED,
            "Customer verification failed.",
            account_verification_enabled=account_verification_enabled,
            email_matches=email_matches,
            phone_matches=phone_matches,
        )
    return _ok("Customer verification succeeded.")


def check_session_verified(*, session_verified: bool) -> PolicyDecision:
    """Require a successful verification CaseEvent in the current environment."""
    if not session_verified:
        return _deny(
            PolicyCode.CUSTOMER_NOT_VERIFIED,
            "Customer has not completed verification in this session.",
        )
    return _ok("Customer session is verified.")


def check_order_ownership(
    *,
    order_exists: bool,
    order_customer_id: str | None,
    requesting_customer_id: str,
) -> PolicyDecision:
    """Enforce that the requester owns the order."""
    if not order_exists:
        return _deny(
            PolicyCode.ORDER_NOT_FOUND,
            "Order was not found.",
            requesting_customer_id=requesting_customer_id,
        )
    if order_customer_id != requesting_customer_id:
        return _deny(
            PolicyCode.ORDER_ACCESS_DENIED,
            "Order does not belong to the requesting customer.",
            requesting_customer_id=requesting_customer_id,
            order_customer_id=order_customer_id,
        )
    return _ok(
        "Order ownership confirmed.",
        requesting_customer_id=requesting_customer_id,
        order_customer_id=order_customer_id,
    )


def check_return_window(
    *,
    order_status: OrderStatus | str,
    delivered_at: datetime | None,
    as_of: datetime,
) -> PolicyDecision:
    """Return window is 30 days from delivery; day 30 inclusive."""
    status = (
        order_status
        if isinstance(order_status, OrderStatus)
        else OrderStatus(order_status)
    )
    if status != OrderStatus.DELIVERED or delivered_at is None:
        return _deny(
            PolicyCode.ORDER_NOT_DELIVERED,
            "Order is not delivered.",
            order_status=status.value,
            delivered_at=None if delivered_at is None else delivered_at.isoformat(),
        )
    days_since = (as_of.date() - delivered_at.date()).days
    evidence = {
        "days_since_delivery": days_since,
        "return_window_days": RETURN_WINDOW_DAYS,
        "delivered_at": delivered_at.isoformat(),
        "as_of": as_of.isoformat(),
    }
    if days_since > RETURN_WINDOW_DAYS:
        return _deny(
            PolicyCode.RETURN_WINDOW_EXPIRED,
            "Return window has expired.",
            **evidence,
        )
    return _ok("Return window is open.", **evidence)


def check_final_sale(*, final_sale: bool, product_id: str) -> PolicyDecision:
    """Final-sale items are ineligible for return."""
    if final_sale:
        return _deny(
            PolicyCode.FINAL_SALE_ITEM,
            "Item is final sale and cannot be returned.",
            product_id=product_id,
            final_sale=True,
        )
    return _ok("Item is eligible for return.", product_id=product_id, final_sale=False)


def check_return_quantity(
    *,
    purchased_quantity: int,
    already_returned_quantity: int,
    requested_quantity: int,
) -> PolicyDecision:
    """Requested quantity must be positive and within remaining eligibility."""
    remaining = purchased_quantity - already_returned_quantity
    evidence = {
        "purchased_quantity": purchased_quantity,
        "already_returned_quantity": already_returned_quantity,
        "requested_quantity": requested_quantity,
        "remaining_quantity": remaining,
    }
    if requested_quantity <= 0:
        return _deny(
            PolicyCode.INVALID_RETURN_QUANTITY,
            "Return quantity must be positive.",
            **evidence,
        )
    if requested_quantity > remaining:
        return _deny(
            PolicyCode.RETURN_QUANTITY_EXCEEDED,
            "Return quantity exceeds remaining eligible quantity.",
            **evidence,
        )
    return _ok("Return quantity is available.", **evidence)


def check_refundable_amount(
    *,
    payment_exists: bool,
    payment_amount_cents: int,
    already_refunded_cents: int,
    requested_amount_cents: int,
) -> PolicyDecision:
    """Refund cannot exceed captured payment minus non-rejected refunds."""
    if not payment_exists:
        return _deny(
            PolicyCode.PAYMENT_NOT_FOUND,
            "Payment was not found.",
        )
    available = payment_amount_cents - already_refunded_cents
    evidence = {
        "payment_amount_cents": payment_amount_cents,
        "already_refunded_cents": already_refunded_cents,
        "available_cents": available,
        "requested_amount_cents": requested_amount_cents,
    }
    if requested_amount_cents <= 0 or requested_amount_cents > available:
        return _deny(
            PolicyCode.REFUND_EXCEEDS_AVAILABLE_AMOUNT,
            "Refund amount exceeds available refundable payment.",
            **evidence,
        )
    return _ok("Refund amount is within available payment.", **evidence)


def check_manager_approval_required(*, amount_cents: int) -> PolicyDecision:
    """Refunds above 50,000 cents require manager approval."""
    evidence = {
        "amount_cents": amount_cents,
        "threshold_cents": MANAGER_APPROVAL_THRESHOLD_CENTS,
    }
    if amount_cents > MANAGER_APPROVAL_THRESHOLD_CENTS:
        return _deny(
            PolicyCode.MANAGER_APPROVAL_REQUIRED,
            "Refund amount requires manager approval.",
            **evidence,
        )
    return _ok("Refund amount does not require manager approval.", **evidence)


def check_duplicate_return(
    *,
    existing_idempotency_key_match: bool,
    conflicting_return_exists: bool,
) -> PolicyDecision:
    """Detect exact idempotent replay vs conflicting duplicate return."""
    if existing_idempotency_key_match:
        return _ok(
            "Existing return matches idempotency key.",
            idempotent_replay=True,
        )
    if conflicting_return_exists:
        return _deny(
            PolicyCode.RETURN_ALREADY_EXISTS,
            "A conflicting return already exists.",
        )
    return _ok("No duplicate return detected.")


def check_duplicate_refund(
    *,
    existing_idempotency_key_match: bool,
    conflicting_refund_exists: bool,
) -> PolicyDecision:
    """Detect exact idempotent replay vs conflicting duplicate refund."""
    if existing_idempotency_key_match:
        return _ok(
            "Existing refund matches idempotency key.",
            idempotent_replay=True,
        )
    if conflicting_refund_exists:
        return _deny(
            PolicyCode.REFUND_ALREADY_EXISTS,
            "A conflicting refund already exists.",
        )
    return _ok("No duplicate refund detected.")
