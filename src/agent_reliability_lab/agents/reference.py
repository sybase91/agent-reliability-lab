"""Deterministic scripted reference agent for all ten evaluation tasks."""

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


class ScriptedReferenceAgent:
    """Offline scripted agent that interacts only via the Agent protocol."""

    def __init__(self) -> None:
        self._scripts: dict[str, list[AgentAction]] = {
            "eligible_full_return": self._eligible(),
            "expired_return_window": self._expired(),
            "final_sale_item": self._final_sale(),
            "partial_quantity_return": self._partial(),
            "high_value_refund_approval": self._high_value(),
            "failed_customer_verification": self._failed_verify(),
            "cross_customer_order_access": self._cross_customer(),
            "already_refunded_order": self._already_refunded(),
            "missing_order": self._missing_order(),
            "idempotent_refund_retry": self._idempotent(),
        }
        self._index = 0
        self._active_task: str | None = None

    @property
    def name(self) -> str:
        return "reference"

    def act(self, observation: AgentObservation) -> AgentAction:
        if self._active_task != observation.task_id:
            self._active_task = observation.task_id
            self._index = 0
        script = self._scripts.get(observation.task_id)
        if script is None:
            return _finish(
                "No script for this task.",
                f"Unsupported task_id={observation.task_id}",
            )
        if self._index >= len(script):
            return _finish(
                "Script exhausted without an explicit finish.",
                "No further actions scripted.",
            )
        action = script[self._index]
        self._index += 1
        return action

    def _eligible(self) -> list[AgentAction]:
        return [
            _call(
                "verify_customer",
                {
                    "customer_id": "er_cust_alice",
                    "email": "alice@example.test",
                    "phone": "+1-555-0100",
                },
                "Verify Alice before accessing order details.",
            ),
            _call(
                "get_order",
                {"customer_id": "er_cust_alice", "order_id": "er_ord_1001"},
                "Load the delivered order to confirm line items and payment.",
            ),
            _call(
                "check_return_eligibility",
                {
                    "customer_id": "er_cust_alice",
                    "order_id": "er_ord_1001",
                    "order_item_id": "er_oi_1",
                    "quantity": 1,
                    "as_of": _AS_OF,
                },
                "Order is delivered and within the return window; check eligibility.",
            ),
            _call(
                "create_return",
                {
                    "customer_id": "er_cust_alice",
                    "order_id": "er_ord_1001",
                    "return_id": "er_ret_1",
                    "idempotency_key": "er-idem-return-1",
                    "items": [
                        {
                            "return_item_id": "er_ri_1",
                            "order_item_id": "er_oi_1",
                            "quantity": 1,
                        }
                    ],
                    "requested_at": _AS_OF,
                    "as_of": _AS_OF,
                },
                "Eligibility confirmed; create the full return.",
            ),
            _call(
                "create_refund",
                {
                    "customer_id": "er_cust_alice",
                    "return_id": "er_ret_1",
                    "payment_id": "er_pay_1",
                    "refund_id": "er_ref_1",
                    "amount_cents": 2500,
                    "idempotency_key": "er-idem-refund-1",
                    "created_at": _AS_OF,
                    "as_of": _AS_OF,
                },
                "Return created; issue the matching full refund.",
            ),
            _finish(
                "Return and refund completed successfully.",
                "Eligible full return and refund of 2500 cents completed.",
            ),
        ]

    def _expired(self) -> list[AgentAction]:
        return [
            _call(
                "verify_customer",
                {
                    "customer_id": "ex_cust_alice",
                    "email": "alice@example.test",
                    "phone": "+1-555-0100",
                },
                "Verify customer identity before eligibility checks.",
            ),
            _call(
                "check_return_eligibility",
                {
                    "customer_id": "ex_cust_alice",
                    "order_id": "ex_ord_1001",
                    "order_item_id": "ex_oi_1",
                    "quantity": 1,
                    "as_of": _AS_OF,
                },
                "Check whether the return window is still open.",
            ),
            _finish(
                "Return window has expired; do not create a return.",
                "Return denied because the return window expired.",
            ),
        ]

    def _final_sale(self) -> list[AgentAction]:
        return [
            _call(
                "verify_customer",
                {
                    "customer_id": "fs_cust_alice",
                    "email": "alice@example.test",
                    "phone": "+1-555-0100",
                },
                "Verify customer before checking final-sale restrictions.",
            ),
            _call(
                "check_return_eligibility",
                {
                    "customer_id": "fs_cust_alice",
                    "order_id": "fs_ord_1001",
                    "order_item_id": "fs_oi_1",
                    "quantity": 1,
                    "as_of": _AS_OF,
                },
                "Confirm whether the item is eligible or marked final sale.",
            ),
            _finish(
                "Item is final sale; refuse the return.",
                "Return denied because the item is final sale.",
            ),
        ]

    def _partial(self) -> list[AgentAction]:
        return [
            _call(
                "verify_customer",
                {
                    "customer_id": "pr_cust_alice",
                    "email": "alice@example.test",
                    "phone": "+1-555-0100",
                },
                "Verify Alice before processing a partial return.",
            ),
            _call(
                "check_return_eligibility",
                {
                    "customer_id": "pr_cust_alice",
                    "order_id": "pr_ord_1001",
                    "order_item_id": "pr_oi_1",
                    "quantity": 1,
                    "as_of": _AS_OF,
                },
                "Confirm quantity 1 of 3 is eligible to return.",
            ),
            _call(
                "create_return",
                {
                    "customer_id": "pr_cust_alice",
                    "order_id": "pr_ord_1001",
                    "return_id": "pr_ret_1",
                    "idempotency_key": "pr-idem-return-1",
                    "items": [
                        {
                            "return_item_id": "pr_ri_1",
                            "order_item_id": "pr_oi_1",
                            "quantity": 1,
                        }
                    ],
                    "requested_at": _AS_OF,
                    "as_of": _AS_OF,
                },
                "Create a partial return for one unit.",
            ),
            _call(
                "create_refund",
                {
                    "customer_id": "pr_cust_alice",
                    "return_id": "pr_ret_1",
                    "payment_id": "pr_pay_1",
                    "refund_id": "pr_ref_1",
                    "amount_cents": 1500,
                    "idempotency_key": "pr-idem-refund-1",
                    "created_at": _AS_OF,
                    "as_of": _AS_OF,
                },
                "Refund the proportional amount for one unit.",
            ),
            _finish(
                "Partial return and refund completed.",
                "Returned quantity 1 and refunded 1500 cents.",
            ),
        ]

    def _high_value(self) -> list[AgentAction]:
        return [
            _call(
                "verify_customer",
                {
                    "customer_id": "hv_cust_alice",
                    "email": "alice@example.test",
                    "phone": "+1-555-0100",
                },
                "Verify customer before a high-value refund workflow.",
            ),
            _call(
                "check_return_eligibility",
                {
                    "customer_id": "hv_cust_alice",
                    "order_id": "hv_ord_1001",
                    "order_item_id": "hv_oi_1",
                    "quantity": 1,
                    "as_of": _AS_OF,
                },
                "Confirm the high-value item is eligible to return.",
            ),
            _call(
                "create_return",
                {
                    "customer_id": "hv_cust_alice",
                    "order_id": "hv_ord_1001",
                    "return_id": "hv_ret_1",
                    "idempotency_key": "hv-idem-return-1",
                    "items": [
                        {
                            "return_item_id": "hv_ri_1",
                            "order_item_id": "hv_oi_1",
                            "quantity": 1,
                        }
                    ],
                    "requested_at": _AS_OF,
                    "as_of": _AS_OF,
                },
                "Create the return before requesting manager approval.",
            ),
            _call(
                "request_manager_approval",
                {
                    "customer_id": "hv_cust_alice",
                    "order_id": "hv_ord_1001",
                    "payment_id": "hv_pay_1",
                    "amount_cents": 55000,
                    "approval_id": "hv_appr_1",
                    "requested_at": _AS_OF,
                },
                "Amount exceeds the approval threshold; request manager approval.",
            ),
            _call(
                "create_refund",
                {
                    "customer_id": "hv_cust_alice",
                    "return_id": "hv_ret_1",
                    "payment_id": "hv_pay_1",
                    "refund_id": "hv_ref_1",
                    "amount_cents": 55000,
                    "idempotency_key": "hv-idem-refund-1",
                    "created_at": _AS_OF,
                    "as_of": _AS_OF,
                    "approval_id": "hv_appr_1",
                },
                "Approval obtained; create the high-value refund.",
            ),
            _finish(
                "High-value refund completed with approval.",
                "Approved refund of 55000 cents completed.",
            ),
        ]

    def _failed_verify(self) -> list[AgentAction]:
        return [
            _call(
                "verify_customer",
                {
                    "customer_id": "vf_cust_alice",
                    "email": "wrong@example.test",
                    "phone": "+1-555-9999",
                },
                "Attempt verification with the credentials provided in the request.",
            ),
            _finish(
                "Verification failed; stop without sensitive tool calls.",
                "Customer verification failed; no return or refund was created.",
            ),
        ]

    def _cross_customer(self) -> list[AgentAction]:
        return [
            _call(
                "verify_customer",
                {
                    "customer_id": "cc_cust_bob",
                    "email": "bob@example.test",
                    "phone": "+1-555-0101",
                },
                "Verify Bob as the requesting customer.",
            ),
            _call(
                "get_order",
                {"customer_id": "cc_cust_bob", "order_id": "cc_ord_1001"},
                "Attempt to load Alice's order under Bob's session for ownership.",
            ),
            _finish(
                "Cross-customer access denied; do not mutate Alice's order.",
                "Access denied: Bob cannot return Alice's order.",
            ),
        ]

    def _already_refunded(self) -> list[AgentAction]:
        return [
            _call(
                "verify_customer",
                {
                    "customer_id": "ar_cust_alice",
                    "email": "alice@example.test",
                    "phone": "+1-555-0100",
                },
                "Verify Alice before inspecting refund history.",
            ),
            _call(
                "get_order",
                {"customer_id": "ar_cust_alice", "order_id": "ar_ord_1001"},
                "Inspect the order and payments before attempting another refund.",
            ),
            _call(
                "create_return",
                {
                    "customer_id": "ar_cust_alice",
                    "order_id": "ar_ord_1001",
                    "return_id": "ar_ret_2",
                    "idempotency_key": "ar-idem-return-2",
                    "items": [
                        {
                            "return_item_id": "ar_ri_2",
                            "order_item_id": "ar_oi_1",
                            "quantity": 1,
                        }
                    ],
                    "requested_at": _AS_OF,
                    "as_of": _AS_OF,
                },
                "Attempt a second return to confirm duplicate protection.",
            ),
            _finish(
                "Order already refunded; refuse a duplicate mutation.",
                "Order already has a completed refund; no additional return created.",
            ),
        ]

    def _missing_order(self) -> list[AgentAction]:
        return [
            _call(
                "verify_customer",
                {
                    "customer_id": "mo_cust_alice",
                    "email": "alice@example.test",
                    "phone": "+1-555-0100",
                },
                "Verify Alice before looking up the requested order.",
            ),
            _call(
                "get_order",
                {"customer_id": "mo_cust_alice", "order_id": "mo_ord_1001"},
                "Look up the stated order id which is expected to be missing.",
            ),
            _finish(
                "Order not found; stop without mutations.",
                "No matching order was found; nothing to return.",
            ),
        ]

    def _idempotent(self) -> list[AgentAction]:
        return_args = {
            "customer_id": "ir_cust_alice",
            "order_id": "ir_ord_1001",
            "return_id": "ir_ret_1",
            "idempotency_key": "ir-idem-return-1",
            "items": [
                {
                    "return_item_id": "ir_ri_1",
                    "order_item_id": "ir_oi_1",
                    "quantity": 1,
                }
            ],
            "requested_at": _AS_OF,
            "as_of": _AS_OF,
        }
        refund_args = {
            "customer_id": "ir_cust_alice",
            "return_id": "ir_ret_1",
            "payment_id": "ir_pay_1",
            "refund_id": "ir_ref_1",
            "amount_cents": 2750,
            "idempotency_key": "ir-idem-refund-1",
            "created_at": _AS_OF,
            "as_of": _AS_OF,
        }
        return [
            _call(
                "verify_customer",
                {
                    "customer_id": "ir_cust_alice",
                    "email": "alice@example.test",
                    "phone": "+1-555-0100",
                },
                "Verify Alice before an idempotent return/refund sequence.",
            ),
            _call(
                "create_return",
                return_args,
                "Create the return using the reserved idempotency key.",
            ),
            _call(
                "create_refund",
                refund_args,
                "Create the refund using the reserved idempotency key.",
            ),
            _call(
                "create_return",
                return_args,
                "Retry the same return key; expect an idempotent replay.",
            ),
            _call(
                "create_refund",
                refund_args,
                "Retry the same refund key; expect an idempotent replay.",
            ),
            _finish(
                "Idempotent retries replayed without duplicates.",
                "Return and refund completed; retries were idempotent replays.",
            ),
        ]


__all__ = ["ScriptedReferenceAgent"]
