"""Typed retail tools against SQLite with pure policy enforcement.

Tools query and mutate state, return structured ``ToolResult`` values, and do
not record harness traces. Business denials are ``ToolResult`` outcomes;
unexpected database or programming errors are not converted into policy codes.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from agent_reliability_lab.domains.retail.database import (
    row_to_approval,
    row_to_case_event,
    row_to_customer,
    row_to_order,
    row_to_order_item,
    row_to_payment,
    row_to_product,
    row_to_refund,
    row_to_return,
    row_to_return_item,
    transaction,
)
from agent_reliability_lab.domains.retail.models import (
    ApprovalStatus,
    CaseEventType,
    Order,
    PaymentStatus,
    PositiveCents,
    PositiveQuantity,
    RefundStatus,
    RetailModel,
    ReturnStatus,
)
from agent_reliability_lab.domains.retail.policies import (
    MANAGER_APPROVAL_THRESHOLD_CENTS,
    PolicyCode,
    PolicyDecision,
    check_duplicate_refund,
    check_duplicate_return,
    check_final_sale,
    check_identity_verification,
    check_manager_approval_required,
    check_order_ownership,
    check_refundable_amount,
    check_return_quantity,
    check_return_window,
    check_session_verified,
)

TOOL_NAMES: tuple[str, ...] = (
    "verify_customer",
    "get_order",
    "check_return_eligibility",
    "request_manager_approval",
    "create_return",
    "create_refund",
    "get_refund_status",
)


class ToolResult(BaseModel):
    """Stable typed tool outcome; JSON-serializable."""

    model_config = ConfigDict(extra="forbid")

    ok: bool
    code: PolicyCode
    message: str
    data: dict[str, Any] = Field(default_factory=dict)
    idempotent_replay: bool = False


class VerifyCustomerInput(RetailModel):
    customer_id: str
    email: str
    phone: str


class GetOrderInput(RetailModel):
    customer_id: str
    order_id: str


class CheckReturnEligibilityInput(RetailModel):
    customer_id: str
    order_id: str
    order_item_id: str
    quantity: PositiveQuantity
    as_of: datetime


class RequestManagerApprovalInput(RetailModel):
    customer_id: str
    order_id: str
    payment_id: str
    amount_cents: PositiveCents
    approval_id: str
    requested_at: datetime


class CreateReturnItemInput(RetailModel):
    return_item_id: str
    order_item_id: str
    quantity: PositiveQuantity


class CreateReturnInput(RetailModel):
    customer_id: str
    order_id: str
    return_id: str
    idempotency_key: str
    items: list[CreateReturnItemInput] = Field(min_length=1)
    requested_at: datetime
    as_of: datetime


class CreateRefundInput(RetailModel):
    customer_id: str
    return_id: str
    payment_id: str
    refund_id: str
    amount_cents: PositiveCents
    idempotency_key: str
    created_at: datetime
    as_of: datetime
    approval_id: str | None = None


class GetRefundStatusInput(RetailModel):
    customer_id: str
    refund_id: str


def _iso(value: datetime) -> str:
    return value.isoformat()


def _result(
    decision: PolicyDecision,
    *,
    data: dict[str, Any] | None = None,
    idempotent_replay: bool = False,
) -> ToolResult:
    return ToolResult(
        ok=decision.allowed,
        code=decision.code,
        message=decision.reason,
        data=data if data is not None else dict(decision.evidence),
        idempotent_replay=idempotent_replay,
    )


def _deny(
    code: PolicyCode,
    message: str,
    *,
    data: dict[str, Any] | None = None,
) -> ToolResult:
    return ToolResult(
        ok=False,
        code=code,
        message=message,
        data=data or {},
        idempotent_replay=False,
    )


def _ok(
    message: str,
    *,
    data: dict[str, Any] | None = None,
    idempotent_replay: bool = False,
) -> ToolResult:
    return ToolResult(
        ok=True,
        code=PolicyCode.OK,
        message=message,
        data=data or {},
        idempotent_replay=idempotent_replay,
    )


def _verification_event_id(customer_id: str) -> str:
    return f"verif_{customer_id}"


def _has_session_verification(connection: sqlite3.Connection, customer_id: str) -> bool:
    row = connection.execute(
        """
        SELECT 1 FROM case_events
        WHERE customer_id = ? AND event_type = ?
        LIMIT 1
        """,
        (customer_id, CaseEventType.VERIFICATION.value),
    ).fetchone()
    return row is not None


def _require_session(
    connection: sqlite3.Connection, customer_id: str
) -> ToolResult | None:
    decision = check_session_verified(
        session_verified=_has_session_verification(connection, customer_id)
    )
    if not decision.allowed:
        return _result(decision)
    return None


def _load_order(connection: sqlite3.Connection, order_id: str) -> Order | None:
    row = connection.execute(
        "SELECT * FROM orders WHERE order_id = ?", (order_id,)
    ).fetchone()
    return None if row is None else row_to_order(row)


def _already_returned_quantity(
    connection: sqlite3.Connection, order_item_id: str
) -> int:
    row = connection.execute(
        """
        SELECT COALESCE(SUM(ri.quantity), 0) AS total
        FROM return_items ri
        JOIN returns r ON r.return_id = ri.return_id
        WHERE ri.order_item_id = ? AND r.status != ?
        """,
        (order_item_id, ReturnStatus.REJECTED.value),
    ).fetchone()
    return int(row["total"])


def _already_refunded_cents(connection: sqlite3.Connection, payment_id: str) -> int:
    row = connection.execute(
        """
        SELECT COALESCE(SUM(amount_cents), 0) AS total
        FROM refunds
        WHERE payment_id = ? AND status != ?
        """,
        (payment_id, RefundStatus.REJECTED.value),
    ).fetchone()
    return int(row["total"])


def _approval_payload(approval: Any) -> dict[str, Any]:
    return {
        "approval_id": approval.approval_id,
        "order_id": approval.order_id,
        "payment_id": approval.payment_id,
        "amount_cents": approval.amount_cents,
        "status": approval.status.value,
        "requested_at": _iso(approval.requested_at),
        "resolved_at": None
        if approval.resolved_at is None
        else _iso(approval.resolved_at),
        "refund_id": approval.refund_id,
    }


def _return_payload(ret: Any, items: list[Any]) -> dict[str, Any]:
    return {
        "return_id": ret.return_id,
        "order_id": ret.order_id,
        "customer_id": ret.customer_id,
        "status": ret.status.value,
        "requested_at": _iso(ret.requested_at),
        "idempotency_key": ret.idempotency_key,
        "items": [
            {
                "return_item_id": item.return_item_id,
                "order_item_id": item.order_item_id,
                "quantity": item.quantity,
            }
            for item in items
        ],
    }


def _refund_payload(refund: Any) -> dict[str, Any]:
    return {
        "refund_id": refund.refund_id,
        "return_id": refund.return_id,
        "payment_id": refund.payment_id,
        "amount_cents": refund.amount_cents,
        "status": refund.status.value,
        "created_at": _iso(refund.created_at),
        "idempotency_key": refund.idempotency_key,
    }


def verify_customer(
    connection: sqlite3.Connection, params: VerifyCustomerInput
) -> ToolResult:
    """Verify synthetic customer credentials and record an idempotent event."""
    row = connection.execute(
        "SELECT * FROM customers WHERE customer_id = ?",
        (params.customer_id,),
    ).fetchone()
    if row is None:
        decision = check_identity_verification(
            customer_exists=False,
            account_verification_enabled=False,
            email_matches=False,
            phone_matches=False,
        )
        return _result(decision)

    customer = row_to_customer(row)
    decision = check_identity_verification(
        customer_exists=True,
        account_verification_enabled=customer.verified,
        email_matches=customer.email == params.email,
        phone_matches=customer.phone == params.phone,
    )
    if not decision.allowed:
        return _result(
            decision,
            data={"customer_id": params.customer_id},
        )

    event_id = _verification_event_id(params.customer_id)
    existing = connection.execute(
        "SELECT * FROM case_events WHERE case_event_id = ?",
        (event_id,),
    ).fetchone()
    if existing is not None:
        event = row_to_case_event(existing)
        return _ok(
            "Customer already verified in this session.",
            data={
                "customer_id": params.customer_id,
                "case_event_id": event.case_event_id,
                "event_type": event.event_type.value,
            },
            idempotent_replay=True,
        )

    with transaction(connection):
        connection.execute(
            """
            INSERT INTO case_events (
                case_event_id, customer_id, order_id, event_type,
                payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                params.customer_id,
                None,
                CaseEventType.VERIFICATION.value,
                json.dumps({"verified": True, "customer_id": params.customer_id}),
                _iso(customer.created_at),
            ),
        )

    return _ok(
        "Customer verification succeeded.",
        data={
            "customer_id": params.customer_id,
            "case_event_id": event_id,
            "event_type": CaseEventType.VERIFICATION.value,
        },
    )


def get_order(connection: sqlite3.Connection, params: GetOrderInput) -> ToolResult:
    """Return owned order summary without customer email or phone."""
    denied = _require_session(connection, params.customer_id)
    if denied is not None:
        return denied

    order = _load_order(connection, params.order_id)
    ownership = check_order_ownership(
        order_exists=order is not None,
        order_customer_id=None if order is None else order.customer_id,
        requesting_customer_id=params.customer_id,
    )
    if not ownership.allowed:
        return _result(ownership)

    assert order is not None
    item_rows = connection.execute(
        "SELECT * FROM order_items WHERE order_id = ? ORDER BY order_item_id",
        (params.order_id,),
    ).fetchall()
    items = [row_to_order_item(row) for row in item_rows]
    payment_rows = connection.execute(
        "SELECT * FROM payments WHERE order_id = ? ORDER BY payment_id",
        (params.order_id,),
    ).fetchall()
    payments = [row_to_payment(row) for row in payment_rows]

    return _ok(
        "Order retrieved.",
        data={
            "order": {
                "order_id": order.order_id,
                "customer_id": order.customer_id,
                "status": order.status.value,
                "ordered_at": _iso(order.ordered_at),
                "delivered_at": None
                if order.delivered_at is None
                else _iso(order.delivered_at),
            },
            "items": [
                {
                    "order_item_id": item.order_item_id,
                    "product_id": item.product_id,
                    "quantity": item.quantity,
                    "unit_price_cents": item.unit_price_cents,
                }
                for item in items
            ],
            "payments": [
                {
                    "payment_id": payment.payment_id,
                    "amount_cents": payment.amount_cents,
                    "status": payment.status.value,
                    "method": payment.method.value,
                    "paid_at": _iso(payment.paid_at),
                }
                for payment in payments
            ],
        },
    )


def check_return_eligibility(
    connection: sqlite3.Connection, params: CheckReturnEligibilityInput
) -> ToolResult:
    """Evaluate return eligibility with an explainable decision."""
    denied = _require_session(connection, params.customer_id)
    if denied is not None:
        return denied

    order = _load_order(connection, params.order_id)
    ownership = check_order_ownership(
        order_exists=order is not None,
        order_customer_id=None if order is None else order.customer_id,
        requesting_customer_id=params.customer_id,
    )
    if not ownership.allowed:
        return _result(ownership)
    assert order is not None

    item_row = connection.execute(
        "SELECT * FROM order_items WHERE order_item_id = ? AND order_id = ?",
        (params.order_item_id, params.order_id),
    ).fetchone()
    if item_row is None:
        return _deny(
            PolicyCode.INVALID_STATE,
            "Order item was not found on the order.",
            data={"order_id": params.order_id, "order_item_id": params.order_item_id},
        )
    order_item = row_to_order_item(item_row)

    window = check_return_window(
        order_status=order.status,
        delivered_at=order.delivered_at,
        as_of=params.as_of,
    )
    if not window.allowed:
        return _result(window)

    product_row = connection.execute(
        "SELECT * FROM products WHERE product_id = ?",
        (order_item.product_id,),
    ).fetchone()
    if product_row is None:
        return _deny(
            PolicyCode.INVALID_STATE,
            "Product was not found for order item.",
            data={"product_id": order_item.product_id},
        )
    product = row_to_product(product_row)
    final_sale = check_final_sale(
        final_sale=product.final_sale, product_id=product.product_id
    )
    if not final_sale.allowed:
        return _result(final_sale)

    already = _already_returned_quantity(connection, params.order_item_id)
    quantity = check_return_quantity(
        purchased_quantity=order_item.quantity,
        already_returned_quantity=already,
        requested_quantity=params.quantity,
    )
    if not quantity.allowed:
        return _result(quantity)

    return _ok(
        "Return is eligible.",
        data={
            "order_id": params.order_id,
            "order_item_id": params.order_item_id,
            "product_id": product.product_id,
            "requested_quantity": params.quantity,
            "purchased_quantity": order_item.quantity,
            "already_returned_quantity": already,
            "remaining_quantity": order_item.quantity - already,
            "final_sale": product.final_sale,
            "window": window.evidence,
        },
    )


def request_manager_approval(
    connection: sqlite3.Connection, params: RequestManagerApprovalInput
) -> ToolResult:
    """Deterministically simulate external manager approval for high-value refunds.

    This is a mock of an external approval system for Phase 1 fixtures, not a
    production approval service. Agents cannot supply an approval decision.
    """
    denied = _require_session(connection, params.customer_id)
    if denied is not None:
        return denied

    order = _load_order(connection, params.order_id)
    ownership = check_order_ownership(
        order_exists=order is not None,
        order_customer_id=None if order is None else order.customer_id,
        requesting_customer_id=params.customer_id,
    )
    if not ownership.allowed:
        return _result(ownership)
    assert order is not None

    payment_row = connection.execute(
        "SELECT * FROM payments WHERE payment_id = ?",
        (params.payment_id,),
    ).fetchone()
    payment = None if payment_row is None else row_to_payment(payment_row)
    if payment is None or payment.order_id != params.order_id:
        return _deny(
            PolicyCode.PAYMENT_NOT_FOUND,
            "Payment was not found for the order.",
            data={
                "payment_id": params.payment_id,
                "order_id": params.order_id,
            },
        )

    requirement = check_manager_approval_required(amount_cents=params.amount_cents)
    if requirement.allowed:
        return _deny(
            PolicyCode.INVALID_STATE,
            "Manager approval is not required for this refund amount.",
            data=requirement.evidence,
        )

    already = _already_refunded_cents(connection, params.payment_id)
    amount_ok = check_refundable_amount(
        payment_exists=True,
        payment_amount_cents=payment.amount_cents,
        already_refunded_cents=already,
        requested_amount_cents=params.amount_cents,
    )
    if not amount_ok.allowed:
        return _result(amount_ok)

    existing = connection.execute(
        "SELECT * FROM approvals WHERE approval_id = ?",
        (params.approval_id,),
    ).fetchone()
    if existing is not None:
        approval = row_to_approval(existing)
        return _ok(
            "Manager approval already recorded.",
            data=_approval_payload(approval),
            idempotent_replay=True,
        )

    matching = connection.execute(
        """
        SELECT * FROM approvals
        WHERE order_id = ? AND payment_id = ? AND amount_cents = ?
        ORDER BY approval_id
        LIMIT 1
        """,
        (params.order_id, params.payment_id, params.amount_cents),
    ).fetchone()
    if matching is not None:
        approval = row_to_approval(matching)
        return _ok(
            "Manager approval already recorded.",
            data=_approval_payload(approval),
            idempotent_replay=True,
        )

    with transaction(connection):
        connection.execute(
            """
            INSERT INTO approvals (
                approval_id, order_id, payment_id, amount_cents,
                status, requested_at, resolved_at, refund_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                params.approval_id,
                params.order_id,
                params.payment_id,
                params.amount_cents,
                ApprovalStatus.APPROVED.value,
                _iso(params.requested_at),
                _iso(params.requested_at),
                None,
            ),
        )

    approval_row = connection.execute(
        "SELECT * FROM approvals WHERE approval_id = ?",
        (params.approval_id,),
    ).fetchone()
    assert approval_row is not None
    approval = row_to_approval(approval_row)
    return _ok(
        "Manager approval granted (deterministic mock).",
        data=_approval_payload(approval),
    )


def create_return(
    connection: sqlite3.Connection, params: CreateReturnInput
) -> ToolResult:
    """Create an approved return and items transactionally (Phase 1 simplified)."""
    denied = _require_session(connection, params.customer_id)
    if denied is not None:
        return denied

    existing_key = connection.execute(
        "SELECT * FROM returns WHERE idempotency_key = ?",
        (params.idempotency_key,),
    ).fetchone()
    duplicate = check_duplicate_return(
        existing_idempotency_key_match=existing_key is not None,
        conflicting_return_exists=False,
    )
    if existing_key is not None and duplicate.allowed:
        ret = row_to_return(existing_key)
        item_rows = connection.execute(
            "SELECT * FROM return_items WHERE return_id = ? ORDER BY return_item_id",
            (ret.return_id,),
        ).fetchall()
        items = [row_to_return_item(row) for row in item_rows]
        return _ok(
            "Return already exists for idempotency key.",
            data=_return_payload(ret, items),
            idempotent_replay=True,
        )

    by_id = connection.execute(
        "SELECT * FROM returns WHERE return_id = ?",
        (params.return_id,),
    ).fetchone()
    if by_id is not None:
        return _result(
            check_duplicate_return(
                existing_idempotency_key_match=False,
                conflicting_return_exists=True,
            )
        )

    order = _load_order(connection, params.order_id)
    ownership = check_order_ownership(
        order_exists=order is not None,
        order_customer_id=None if order is None else order.customer_id,
        requesting_customer_id=params.customer_id,
    )
    if not ownership.allowed:
        return _result(ownership)
    assert order is not None

    window = check_return_window(
        order_status=order.status,
        delivered_at=order.delivered_at,
        as_of=params.as_of,
    )
    if not window.allowed:
        return _result(window)

    prepared_items: list[tuple[str, str, int, str]] = []
    for item in params.items:
        item_row = connection.execute(
            "SELECT * FROM order_items WHERE order_item_id = ? AND order_id = ?",
            (item.order_item_id, params.order_id),
        ).fetchone()
        if item_row is None:
            return _deny(
                PolicyCode.INVALID_STATE,
                "Order item was not found on the order.",
                data={
                    "order_id": params.order_id,
                    "order_item_id": item.order_item_id,
                },
            )
        order_item = row_to_order_item(item_row)
        product_row = connection.execute(
            "SELECT * FROM products WHERE product_id = ?",
            (order_item.product_id,),
        ).fetchone()
        if product_row is None:
            return _deny(
                PolicyCode.INVALID_STATE,
                "Product was not found for order item.",
                data={"product_id": order_item.product_id},
            )
        product = row_to_product(product_row)
        final_sale = check_final_sale(
            final_sale=product.final_sale, product_id=product.product_id
        )
        if not final_sale.allowed:
            return _result(final_sale)

        already = _already_returned_quantity(connection, item.order_item_id)
        quantity_decision = check_return_quantity(
            purchased_quantity=order_item.quantity,
            already_returned_quantity=already,
            requested_quantity=item.quantity,
        )
        if not quantity_decision.allowed:
            return _result(quantity_decision)
        prepared_items.append(
            (
                item.return_item_id,
                item.order_item_id,
                item.quantity,
                order_item.product_id,
            )
        )

    with transaction(connection):
        connection.execute(
            """
            INSERT INTO returns (
                return_id, order_id, customer_id, status,
                requested_at, idempotency_key
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                params.return_id,
                params.order_id,
                params.customer_id,
                ReturnStatus.APPROVED.value,
                _iso(params.requested_at),
                params.idempotency_key,
            ),
        )
        for return_item_id, order_item_id, quantity, _product_id in prepared_items:
            connection.execute(
                """
                INSERT INTO return_items (
                    return_item_id, return_id, order_item_id, quantity
                ) VALUES (?, ?, ?, ?)
                """,
                (return_item_id, params.return_id, order_item_id, quantity),
            )
        connection.execute(
            """
            INSERT INTO case_events (
                case_event_id, customer_id, order_id, event_type,
                payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                f"mut_return_{params.return_id}",
                params.customer_id,
                params.order_id,
                CaseEventType.MUTATION.value,
                json.dumps(
                    {
                        "mutation": "create_return",
                        "return_id": params.return_id,
                        "idempotency_key": params.idempotency_key,
                    }
                ),
                _iso(params.requested_at),
            ),
        )

    ret_row = connection.execute(
        "SELECT * FROM returns WHERE return_id = ?",
        (params.return_id,),
    ).fetchone()
    assert ret_row is not None
    ret = row_to_return(ret_row)
    item_rows = connection.execute(
        "SELECT * FROM return_items WHERE return_id = ? ORDER BY return_item_id",
        (params.return_id,),
    ).fetchall()
    items = [row_to_return_item(row) for row in item_rows]
    return _ok(
        "Return created.",
        data=_return_payload(ret, items),
    )


def create_refund(
    connection: sqlite3.Connection, params: CreateRefundInput
) -> ToolResult:
    """Create a refund transactionally, linking approval when required."""
    denied = _require_session(connection, params.customer_id)
    if denied is not None:
        return denied

    existing_key = connection.execute(
        "SELECT * FROM refunds WHERE idempotency_key = ?",
        (params.idempotency_key,),
    ).fetchone()
    if existing_key is not None:
        refund = row_to_refund(existing_key)
        return _ok(
            "Refund already exists for idempotency key.",
            data=_refund_payload(refund),
            idempotent_replay=True,
        )

    by_id = connection.execute(
        "SELECT * FROM refunds WHERE refund_id = ?",
        (params.refund_id,),
    ).fetchone()
    if by_id is not None:
        return _result(
            check_duplicate_refund(
                existing_idempotency_key_match=False,
                conflicting_refund_exists=True,
            )
        )

    return_row = connection.execute(
        "SELECT * FROM returns WHERE return_id = ?",
        (params.return_id,),
    ).fetchone()
    if return_row is None:
        return _deny(
            PolicyCode.INVALID_STATE,
            "Return was not found.",
            data={"return_id": params.return_id},
        )
    ret = row_to_return(return_row)
    if ret.status == ReturnStatus.REJECTED:
        return _deny(
            PolicyCode.INVALID_STATE,
            "Rejected returns cannot be refunded.",
            data={"return_id": params.return_id, "status": ret.status.value},
        )
    if ret.customer_id != params.customer_id:
        return _deny(
            PolicyCode.ORDER_ACCESS_DENIED,
            "Return does not belong to the requesting customer.",
            data={
                "return_id": params.return_id,
                "customer_id": params.customer_id,
            },
        )

    order = _load_order(connection, ret.order_id)
    ownership = check_order_ownership(
        order_exists=order is not None,
        order_customer_id=None if order is None else order.customer_id,
        requesting_customer_id=params.customer_id,
    )
    if not ownership.allowed:
        return _result(ownership)
    assert order is not None

    payment_row = connection.execute(
        "SELECT * FROM payments WHERE payment_id = ?",
        (params.payment_id,),
    ).fetchone()
    payment = None if payment_row is None else row_to_payment(payment_row)
    if payment is None or payment.order_id != ret.order_id:
        return _deny(
            PolicyCode.PAYMENT_NOT_FOUND,
            "Payment was not found for the return's order.",
            data={"payment_id": params.payment_id, "order_id": ret.order_id},
        )

    already = _already_refunded_cents(connection, params.payment_id)
    amount_ok = check_refundable_amount(
        payment_exists=True,
        payment_amount_cents=payment.amount_cents,
        already_refunded_cents=already,
        requested_amount_cents=params.amount_cents,
    )
    if not amount_ok.allowed:
        return _result(amount_ok)

    approval_required = not check_manager_approval_required(
        amount_cents=params.amount_cents
    ).allowed
    approval_row = None
    if approval_required:
        if params.approval_id is None:
            return _deny(
                PolicyCode.MANAGER_APPROVAL_REQUIRED,
                "High-value refund requires manager approval.",
                data={
                    "amount_cents": params.amount_cents,
                    "threshold_cents": MANAGER_APPROVAL_THRESHOLD_CENTS,
                },
            )
        approval_row = connection.execute(
            "SELECT * FROM approvals WHERE approval_id = ?",
            (params.approval_id,),
        ).fetchone()
        if approval_row is None:
            return _deny(
                PolicyCode.MANAGER_APPROVAL_NOT_FOUND,
                "Matching manager approval was not found.",
                data={"approval_id": params.approval_id},
            )
        approval = row_to_approval(approval_row)
        if (
            approval.status != ApprovalStatus.APPROVED
            or approval.order_id != ret.order_id
            or approval.payment_id != params.payment_id
            or approval.amount_cents != params.amount_cents
            or (
                approval.refund_id is not None
                and approval.refund_id != params.refund_id
            )
        ):
            return _deny(
                PolicyCode.MANAGER_APPROVAL_NOT_FOUND,
                "Manager approval does not match the proposed refund.",
                data=_approval_payload(approval),
            )

    remaining_after = payment.amount_cents - already - params.amount_cents
    with transaction(connection):
        connection.execute(
            """
            INSERT INTO refunds (
                refund_id, return_id, payment_id, amount_cents,
                status, created_at, idempotency_key
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                params.refund_id,
                params.return_id,
                params.payment_id,
                params.amount_cents,
                RefundStatus.COMPLETED.value,
                _iso(params.created_at),
                params.idempotency_key,
            ),
        )
        if approval_required and params.approval_id is not None:
            connection.execute(
                """
                UPDATE approvals
                SET refund_id = ?
                WHERE approval_id = ?
                """,
                (params.refund_id, params.approval_id),
            )
        if remaining_after == 0:
            connection.execute(
                "UPDATE payments SET status = ? WHERE payment_id = ?",
                (PaymentStatus.REFUNDED.value, params.payment_id),
            )
        connection.execute(
            """
            INSERT INTO case_events (
                case_event_id, customer_id, order_id, event_type,
                payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                f"mut_refund_{params.refund_id}",
                params.customer_id,
                ret.order_id,
                CaseEventType.MUTATION.value,
                json.dumps(
                    {
                        "mutation": "create_refund",
                        "refund_id": params.refund_id,
                        "idempotency_key": params.idempotency_key,
                        "amount_cents": params.amount_cents,
                    }
                ),
                _iso(params.created_at),
            ),
        )

    refund_row = connection.execute(
        "SELECT * FROM refunds WHERE refund_id = ?",
        (params.refund_id,),
    ).fetchone()
    assert refund_row is not None
    refund = row_to_refund(refund_row)
    return _ok("Refund created.", data=_refund_payload(refund))


def get_refund_status(
    connection: sqlite3.Connection, params: GetRefundStatusInput
) -> ToolResult:
    """Return non-sensitive refund status through ownership chain."""
    denied = _require_session(connection, params.customer_id)
    if denied is not None:
        return denied

    refund_row = connection.execute(
        "SELECT * FROM refunds WHERE refund_id = ?",
        (params.refund_id,),
    ).fetchone()
    if refund_row is None:
        return _deny(
            PolicyCode.INVALID_STATE,
            "Refund was not found.",
            data={"refund_id": params.refund_id},
        )
    refund = row_to_refund(refund_row)
    return_row = connection.execute(
        "SELECT * FROM returns WHERE return_id = ?",
        (refund.return_id,),
    ).fetchone()
    if return_row is None:
        return _deny(
            PolicyCode.INVALID_STATE,
            "Return for refund was not found.",
            data={"return_id": refund.return_id},
        )
    ret = row_to_return(return_row)
    order = _load_order(connection, ret.order_id)
    ownership = check_order_ownership(
        order_exists=order is not None,
        order_customer_id=None if order is None else order.customer_id,
        requesting_customer_id=params.customer_id,
    )
    if not ownership.allowed:
        return _result(ownership)

    return _ok(
        "Refund status retrieved.",
        data={
            **_refund_payload(refund),
            "order_id": ret.order_id,
            "customer_id": ret.customer_id,
        },
    )


_TOOL_HANDLERS: dict[str, tuple[type[RetailModel], Callable[..., ToolResult]]] = {
    "verify_customer": (VerifyCustomerInput, verify_customer),
    "get_order": (GetOrderInput, get_order),
    "check_return_eligibility": (CheckReturnEligibilityInput, check_return_eligibility),
    "request_manager_approval": (RequestManagerApprovalInput, request_manager_approval),
    "create_return": (CreateReturnInput, create_return),
    "create_refund": (CreateRefundInput, create_refund),
    "get_refund_status": (GetRefundStatusInput, get_refund_status),
}


def list_tool_names() -> tuple[str, ...]:
    """Return the seven registered tool names."""
    return TOOL_NAMES


def get_tool_input_schema(tool_name: str) -> dict[str, Any]:
    """Return the JSON schema for a registered tool's input model."""
    if tool_name not in _TOOL_HANDLERS:
        msg = f"unknown tool {tool_name!r}"
        raise KeyError(msg)
    input_model, _handler = _TOOL_HANDLERS[tool_name]
    return input_model.model_json_schema()


def list_tool_input_schemas() -> dict[str, dict[str, Any]]:
    """Return input schemas keyed by tool name."""
    return {name: get_tool_input_schema(name) for name in TOOL_NAMES}


def invoke_tool(
    connection: sqlite3.Connection,
    tool_name: str,
    arguments: dict[str, Any],
) -> ToolResult:
    """Validate arguments and invoke a registered tool.

    Does not record traces. Invalid argument shapes raise ``ValidationError``.
    Unknown tool names raise ``KeyError``.
    """
    if tool_name not in _TOOL_HANDLERS:
        msg = f"unknown tool {tool_name!r}; known: {', '.join(TOOL_NAMES)}"
        raise KeyError(msg)
    input_model, handler = _TOOL_HANDLERS[tool_name]
    params = input_model.model_validate(arguments)
    return handler(connection, params)


__all__ = [
    "TOOL_NAMES",
    "CheckReturnEligibilityInput",
    "CreateRefundInput",
    "CreateReturnInput",
    "CreateReturnItemInput",
    "GetOrderInput",
    "GetRefundStatusInput",
    "RequestManagerApprovalInput",
    "ToolResult",
    "VerifyCustomerInput",
    "check_return_eligibility",
    "create_refund",
    "create_return",
    "get_order",
    "get_refund_status",
    "get_tool_input_schema",
    "invoke_tool",
    "list_tool_input_schemas",
    "list_tool_names",
    "request_manager_approval",
    "verify_customer",
]
