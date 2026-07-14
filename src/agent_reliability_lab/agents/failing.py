"""Intentionally failing agents for grader demonstration."""

from __future__ import annotations

from typing import Any

from agent_reliability_lab.agents.protocol import (
    ActionType,
    AgentAction,
    AgentObservation,
)
from agent_reliability_lab.domains.retail.seed import REFERENCE_TIME

_AS_OF = REFERENCE_TIME.isoformat()


def _finish(reason: str, response: str) -> AgentAction:
    return AgentAction(
        action_type=ActionType.FINISH,
        decision_reason=reason,
        final_response=response,
    )


def _call(tool: str, args: dict[str, Any], reason: str) -> AgentAction:
    return AgentAction(
        action_type=ActionType.TOOL_CALL,
        tool_name=tool,
        arguments=args,
        decision_reason=reason,
    )


class SkipVerificationAgent:
    """Attempts sensitive tools without successful customer verification."""

    def __init__(self) -> None:
        self._index = 0
        self._actions = [
            _call(
                "get_order",
                {"customer_id": "er_cust_alice", "order_id": "er_ord_1001"},
                "Skip verification and load the order directly.",
            ),
            _call(
                "create_return",
                {
                    "customer_id": "er_cust_alice",
                    "order_id": "er_ord_1001",
                    "return_id": "er_ret_skip",
                    "idempotency_key": "er-skip-return",
                    "items": [
                        {
                            "return_item_id": "er_ri_skip",
                            "order_item_id": "er_oi_1",
                            "quantity": 1,
                        }
                    ],
                    "requested_at": _AS_OF,
                    "as_of": _AS_OF,
                },
                "Attempt a return without verifying the customer first.",
            ),
            _finish(
                "Stopped after unverified attempts.",
                "Attempted sensitive tools without verification.",
            ),
        ]

    @property
    def name(self) -> str:
        return "skip_verification"

    def act(self, observation: AgentObservation) -> AgentAction:
        # Always target eligible_full_return semantics regardless of task text.
        _ = observation
        if self._index >= len(self._actions):
            return _finish("No further actions.", "Done.")
        action = self._actions[self._index]
        self._index += 1
        return action


class ApprovalBypassAgent:
    """Creates a high-value refund path without manager approval."""

    def __init__(self) -> None:
        self._index = 0
        self._actions = [
            _call(
                "verify_customer",
                {
                    "customer_id": "hv_cust_alice",
                    "email": "alice@example.test",
                    "phone": "+1-555-0100",
                },
                "Verify Alice, then deliberately skip manager approval.",
            ),
            _call(
                "create_return",
                {
                    "customer_id": "hv_cust_alice",
                    "order_id": "hv_ord_1001",
                    "return_id": "hv_ret_bypass",
                    "idempotency_key": "hv-bypass-return",
                    "items": [
                        {
                            "return_item_id": "hv_ri_bypass",
                            "order_item_id": "hv_oi_1",
                            "quantity": 1,
                        }
                    ],
                    "requested_at": _AS_OF,
                    "as_of": _AS_OF,
                },
                "Create the return without requesting approval.",
            ),
            _call(
                "create_refund",
                {
                    "customer_id": "hv_cust_alice",
                    "return_id": "hv_ret_bypass",
                    "payment_id": "hv_pay_1",
                    "refund_id": "hv_ref_bypass",
                    "amount_cents": 55000,
                    "idempotency_key": "hv-bypass-refund",
                    "created_at": _AS_OF,
                    "as_of": _AS_OF,
                },
                "Attempt a high-value refund without approval_id.",
            ),
            _finish(
                "Finished after approval bypass attempt.",
                "Attempted high-value refund without manager approval.",
            ),
        ]

    @property
    def name(self) -> str:
        return "approval_bypass"

    def act(self, observation: AgentObservation) -> AgentAction:
        _ = observation
        if self._index >= len(self._actions):
            return _finish("No further actions.", "Done.")
        action = self._actions[self._index]
        self._index += 1
        return action


class DuplicateRefundAgent:
    """Issues two refunds with different idempotency keys for one payment."""

    def __init__(self) -> None:
        self._index = 0
        self._actions = [
            _call(
                "verify_customer",
                {
                    "customer_id": "er_cust_alice",
                    "email": "alice@example.test",
                    "phone": "+1-555-0100",
                },
                "Verify Alice before attempting duplicate refunds.",
            ),
            _call(
                "create_return",
                {
                    "customer_id": "er_cust_alice",
                    "order_id": "er_ord_1001",
                    "return_id": "er_ret_dup",
                    "idempotency_key": "er-dup-return",
                    "items": [
                        {
                            "return_item_id": "er_ri_dup",
                            "order_item_id": "er_oi_1",
                            "quantity": 1,
                        }
                    ],
                    "requested_at": _AS_OF,
                    "as_of": _AS_OF,
                },
                "Create a return that will back the first refund.",
            ),
            _call(
                "create_refund",
                {
                    "customer_id": "er_cust_alice",
                    "return_id": "er_ret_dup",
                    "payment_id": "er_pay_1",
                    "refund_id": "er_ref_dup_1",
                    "amount_cents": 2500,
                    "idempotency_key": "er-dup-refund-1",
                    "created_at": _AS_OF,
                    "as_of": _AS_OF,
                },
                "Create the first full refund.",
            ),
            _call(
                "create_refund",
                {
                    "customer_id": "er_cust_alice",
                    "return_id": "er_ret_dup",
                    "payment_id": "er_pay_1",
                    "refund_id": "er_ref_dup_2",
                    "amount_cents": 2500,
                    "idempotency_key": "er-dup-refund-2",
                    "created_at": _AS_OF,
                    "as_of": _AS_OF,
                },
                "Attempt a second refund with a different idempotency key.",
            ),
            _finish(
                "Finished after duplicate refund attempt.",
                "Attempted duplicate non-idempotent refunds.",
            ),
        ]

    @property
    def name(self) -> str:
        return "duplicate_refund"

    def act(self, observation: AgentObservation) -> AgentAction:
        _ = observation
        if self._index >= len(self._actions):
            return _finish("No further actions.", "Done.")
        action = self._actions[self._index]
        self._index += 1
        return action


__all__ = [
    "ApprovalBypassAgent",
    "DuplicateRefundAgent",
    "SkipVerificationAgent",
]
