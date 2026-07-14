"""Tests for retail typed tools, registry, verification, and mutations."""

from __future__ import annotations

import json
import sqlite3
from datetime import timedelta
from typing import Any

import pytest
from pydantic import ValidationError

from agent_reliability_lab.domains.retail.database import transaction
from agent_reliability_lab.domains.retail.environment import RetailEnvironment
from agent_reliability_lab.domains.retail.models import ReturnStatus
from agent_reliability_lab.domains.retail.policies import PolicyCode
from agent_reliability_lab.domains.retail.seed import REFERENCE_TIME
from agent_reliability_lab.domains.retail.tools import (
    TOOL_NAMES,
    CheckReturnEligibilityInput,
    CreateRefundInput,
    CreateReturnInput,
    CreateReturnItemInput,
    GetOrderInput,
    GetRefundStatusInput,
    RequestManagerApprovalInput,
    ToolResult,
    VerifyCustomerInput,
    check_return_eligibility,
    create_refund,
    create_return,
    get_order,
    get_refund_status,
    get_tool_input_schema,
    invoke_tool,
    list_tool_input_schemas,
    list_tool_names,
    request_manager_approval,
    verify_customer,
)


def _verify_alice(connection: sqlite3.Connection, customer_id: str) -> ToolResult:
    return verify_customer(
        connection,
        VerifyCustomerInput(
            customer_id=customer_id,
            email="alice@example.test",
            phone="+1-555-0100",
        ),
    )


def _assert_no_pii(payload: dict[str, Any]) -> None:
    serialized = json.dumps(payload)
    assert "email" not in serialized
    assert "phone" not in serialized
    assert "@example.test" not in serialized
    assert "+1-555" not in serialized


def test_all_seven_tools_are_registered() -> None:
    assert list_tool_names() == TOOL_NAMES
    assert set(TOOL_NAMES) == {
        "verify_customer",
        "get_order",
        "check_return_eligibility",
        "request_manager_approval",
        "create_return",
        "create_refund",
        "get_refund_status",
    }


def test_tool_input_schemas_are_available() -> None:
    schemas = list_tool_input_schemas()
    assert set(schemas) == set(TOOL_NAMES)
    for name in TOOL_NAMES:
        schema = get_tool_input_schema(name)
        assert schema["type"] == "object"
        assert "properties" in schema


def test_tool_result_is_json_serializable() -> None:
    result = ToolResult(
        ok=True,
        code=PolicyCode.OK,
        message="ok",
        data={"amount_cents": 100, "requested_at": REFERENCE_TIME.isoformat()},
        idempotent_replay=False,
    )
    payload = result.model_dump(mode="json")
    json.dumps(payload)


def test_verification_succeeds_and_excludes_credentials() -> None:
    with RetailEnvironment("eligible_return") as env:
        result = _verify_alice(env.connection, "er_cust_alice")
        assert result.ok
        assert result.code is PolicyCode.OK
        assert result.data["customer_id"] == "er_cust_alice"
        assert "email" not in result.data
        assert "phone" not in result.data
        event_count = env.connection.execute(
            "SELECT COUNT(*) FROM case_events WHERE event_type = 'verification'"
        ).fetchone()[0]
        assert event_count == 1


def test_verification_fails_safely() -> None:
    with RetailEnvironment("verification_failure") as env:
        result = verify_customer(
            env.connection,
            VerifyCustomerInput(
                customer_id="vf_cust_alice",
                email="alice@example.test",
                phone="+1-555-0100",
            ),
        )
        assert not result.ok
        assert result.code is PolicyCode.VERIFICATION_FAILED
        event_count = env.connection.execute(
            "SELECT COUNT(*) FROM case_events WHERE event_type = 'verification'"
        ).fetchone()[0]
        assert event_count == 0

    with RetailEnvironment("eligible_return") as env:
        bad = verify_customer(
            env.connection,
            VerifyCustomerInput(
                customer_id="er_cust_alice",
                email="wrong@example.test",
                phone="+1-555-0100",
            ),
        )
        assert bad.code is PolicyCode.VERIFICATION_FAILED


def test_verification_replay_is_idempotent() -> None:
    with RetailEnvironment("eligible_return") as env:
        first = _verify_alice(env.connection, "er_cust_alice")
        second = _verify_alice(env.connection, "er_cust_alice")
        assert first.ok
        assert second.ok
        assert second.idempotent_replay
        count = env.connection.execute(
            "SELECT COUNT(*) FROM case_events WHERE event_type = 'verification'"
        ).fetchone()[0]
        assert count == 1


def test_unverified_access_is_rejected() -> None:

    with RetailEnvironment("eligible_return") as env:
        result = get_order(
            env.connection,
            GetOrderInput(customer_id="er_cust_alice", order_id="er_ord_1001"),
        )
        assert result.code is PolicyCode.CUSTOMER_NOT_VERIFIED


def test_owned_order_retrieval_and_sensitive_output() -> None:

    with RetailEnvironment("eligible_return") as env:
        _verify_alice(env.connection, "er_cust_alice")
        result = get_order(
            env.connection,
            GetOrderInput(customer_id="er_cust_alice", order_id="er_ord_1001"),
        )
        assert result.ok
        assert result.data["order"]["order_id"] == "er_ord_1001"
        assert result.data["items"]
        assert result.data["payments"]
        _assert_no_pii(result.model_dump(mode="json"))


def test_cross_customer_order_access_is_rejected() -> None:

    with RetailEnvironment("cross_customer_access") as env:
        bob = verify_customer(
            env.connection,
            VerifyCustomerInput(
                customer_id="cc_cust_bob",
                email="bob@example.test",
                phone="+1-555-0101",
            ),
        )
        assert bob.ok
        result = get_order(
            env.connection,
            GetOrderInput(customer_id="cc_cust_bob", order_id="cc_ord_1001"),
        )
        assert result.code is PolicyCode.ORDER_ACCESS_DENIED


def test_return_eligibility_windows_and_final_sale() -> None:

    with RetailEnvironment("eligible_return") as env:
        _verify_alice(env.connection, "er_cust_alice")
        delivered = REFERENCE_TIME - timedelta(days=10)
        exact = check_return_eligibility(
            env.connection,
            CheckReturnEligibilityInput(
                customer_id="er_cust_alice",
                order_id="er_ord_1001",
                order_item_id="er_oi_1",
                quantity=1,
                as_of=delivered + timedelta(days=30),
            ),
        )
        assert exact.ok

    with RetailEnvironment("expired_return") as env:
        _verify_alice(env.connection, "ex_cust_alice")
        expired = check_return_eligibility(
            env.connection,
            CheckReturnEligibilityInput(
                customer_id="ex_cust_alice",
                order_id="ex_ord_1001",
                order_item_id="ex_oi_1",
                quantity=1,
                as_of=REFERENCE_TIME,
            ),
        )
        assert expired.code is PolicyCode.RETURN_WINDOW_EXPIRED

    with RetailEnvironment("final_sale") as env:
        _verify_alice(env.connection, "fs_cust_alice")
        final = check_return_eligibility(
            env.connection,
            CheckReturnEligibilityInput(
                customer_id="fs_cust_alice",
                order_id="fs_ord_1001",
                order_item_id="fs_oi_1",
                quantity=1,
                as_of=REFERENCE_TIME,
            ),
        )
        assert final.code is PolicyCode.FINAL_SALE_ITEM


def test_partial_quantity_eligible_and_excess_denied() -> None:

    with RetailEnvironment("partial_return") as env:
        _verify_alice(env.connection, "pr_cust_alice")
        ok = check_return_eligibility(
            env.connection,
            CheckReturnEligibilityInput(
                customer_id="pr_cust_alice",
                order_id="pr_ord_1001",
                order_item_id="pr_oi_1",
                quantity=2,
                as_of=REFERENCE_TIME,
            ),
        )
        assert ok.ok
        assert ok.data["remaining_quantity"] == 3

        excess = check_return_eligibility(
            env.connection,
            CheckReturnEligibilityInput(
                customer_id="pr_cust_alice",
                order_id="pr_ord_1001",
                order_item_id="pr_oi_1",
                quantity=4,
                as_of=REFERENCE_TIME,
            ),
        )
        assert excess.code is PolicyCode.RETURN_QUANTITY_EXCEEDED


def test_approval_threshold_and_deterministic_manager_approval() -> None:

    with RetailEnvironment("eligible_return") as env:
        _verify_alice(env.connection, "er_cust_alice")
        no_need = request_manager_approval(
            env.connection,
            RequestManagerApprovalInput(
                customer_id="er_cust_alice",
                order_id="er_ord_1001",
                payment_id="er_pay_1",
                amount_cents=50_000,
                approval_id="er_appr_low",
                requested_at=REFERENCE_TIME,
            ),
        )
        assert no_need.code is PolicyCode.INVALID_STATE

    with RetailEnvironment("high_value_refund") as env:
        _verify_alice(env.connection, "hv_cust_alice")
        approved = request_manager_approval(
            env.connection,
            RequestManagerApprovalInput(
                customer_id="hv_cust_alice",
                order_id="hv_ord_1001",
                payment_id="hv_pay_1",
                amount_cents=55_000,
                approval_id="hv_appr_1",
                requested_at=REFERENCE_TIME,
            ),
        )
        assert approved.ok
        assert approved.data["status"] == "approved"
        assert approved.data["refund_id"] is None

        replay = request_manager_approval(
            env.connection,
            RequestManagerApprovalInput(
                customer_id="hv_cust_alice",
                order_id="hv_ord_1001",
                payment_id="hv_pay_1",
                amount_cents=55_000,
                approval_id="hv_appr_1",
                requested_at=REFERENCE_TIME,
            ),
        )
        assert replay.idempotent_replay
        count = env.connection.execute("SELECT COUNT(*) FROM approvals").fetchone()[0]
        assert count == 1


def test_create_return_persists_and_replays() -> None:
    with RetailEnvironment("eligible_return") as env:
        _verify_alice(env.connection, "er_cust_alice")
        created = create_return(
            env.connection,
            CreateReturnInput(
                customer_id="er_cust_alice",
                order_id="er_ord_1001",
                return_id="er_ret_new",
                idempotency_key="er-idem-return-new",
                items=[
                    CreateReturnItemInput(
                        return_item_id="er_ri_new",
                        order_item_id="er_oi_1",
                        quantity=1,
                    )
                ],
                requested_at=REFERENCE_TIME,
                as_of=REFERENCE_TIME,
            ),
        )
        assert created.ok
        assert created.data["status"] == ReturnStatus.APPROVED.value
        row = env.connection.execute(
            "SELECT status FROM returns WHERE return_id = ?",
            ("er_ret_new",),
        ).fetchone()
        assert row["status"] == ReturnStatus.APPROVED.value
        items = env.connection.execute(
            "SELECT COUNT(*) AS c FROM return_items WHERE return_id = ?",
            ("er_ret_new",),
        ).fetchone()["c"]
        assert items == 1

        replay = create_return(
            env.connection,
            CreateReturnInput(
                customer_id="er_cust_alice",
                order_id="er_ord_1001",
                return_id="er_ret_new",
                idempotency_key="er-idem-return-new",
                items=[
                    CreateReturnItemInput(
                        return_item_id="er_ri_new",
                        order_item_id="er_oi_1",
                        quantity=1,
                    )
                ],
                requested_at=REFERENCE_TIME,
                as_of=REFERENCE_TIME,
            ),
        )
        assert replay.idempotent_replay
        count = env.connection.execute("SELECT COUNT(*) FROM returns").fetchone()[0]
        assert count == 1


def test_over_return_with_another_key_is_denied() -> None:
    with RetailEnvironment("eligible_return") as env:
        _verify_alice(env.connection, "er_cust_alice")
        first = create_return(
            env.connection,
            CreateReturnInput(
                customer_id="er_cust_alice",
                order_id="er_ord_1001",
                return_id="er_ret_a",
                idempotency_key="er-idem-a",
                items=[
                    CreateReturnItemInput(
                        return_item_id="er_ri_a",
                        order_item_id="er_oi_1",
                        quantity=1,
                    )
                ],
                requested_at=REFERENCE_TIME,
                as_of=REFERENCE_TIME,
            ),
        )
        assert first.ok
        second = create_return(
            env.connection,
            CreateReturnInput(
                customer_id="er_cust_alice",
                order_id="er_ord_1001",
                return_id="er_ret_b",
                idempotency_key="er-idem-b",
                items=[
                    CreateReturnItemInput(
                        return_item_id="er_ri_b",
                        order_item_id="er_oi_1",
                        quantity=1,
                    )
                ],
                requested_at=REFERENCE_TIME,
                as_of=REFERENCE_TIME,
            ),
        )
        assert second.code is PolicyCode.RETURN_QUANTITY_EXCEEDED
        assert env.connection.execute("SELECT COUNT(*) FROM returns").fetchone()[0] == 1


def test_create_refund_low_value_and_replay() -> None:
    with RetailEnvironment("eligible_return") as env:
        _verify_alice(env.connection, "er_cust_alice")
        create_return(
            env.connection,
            CreateReturnInput(
                customer_id="er_cust_alice",
                order_id="er_ord_1001",
                return_id="er_ret_rf",
                idempotency_key="er-idem-ret-rf",
                items=[
                    CreateReturnItemInput(
                        return_item_id="er_ri_rf",
                        order_item_id="er_oi_1",
                        quantity=1,
                    )
                ],
                requested_at=REFERENCE_TIME,
                as_of=REFERENCE_TIME,
            ),
        )
        refund = create_refund(
            env.connection,
            CreateRefundInput(
                customer_id="er_cust_alice",
                return_id="er_ret_rf",
                payment_id="er_pay_1",
                refund_id="er_ref_1",
                amount_cents=2500,
                idempotency_key="er-idem-ref-1",
                created_at=REFERENCE_TIME,
                as_of=REFERENCE_TIME,
            ),
        )
        assert refund.ok
        assert (
            env.connection.execute(
                "SELECT COUNT(*) FROM refunds WHERE refund_id = ?",
                ("er_ref_1",),
            ).fetchone()[0]
            == 1
        )
        status = env.connection.execute(
            "SELECT status FROM payments WHERE payment_id = ?",
            ("er_pay_1",),
        ).fetchone()["status"]
        assert status == "refunded"

        replay = create_refund(
            env.connection,
            CreateRefundInput(
                customer_id="er_cust_alice",
                return_id="er_ret_rf",
                payment_id="er_pay_1",
                refund_id="er_ref_1",
                amount_cents=2500,
                idempotency_key="er-idem-ref-1",
                created_at=REFERENCE_TIME,
                as_of=REFERENCE_TIME,
            ),
        )
        assert replay.idempotent_replay
        assert env.connection.execute("SELECT COUNT(*) FROM refunds").fetchone()[0] == 1


def test_high_value_refund_requires_matching_approval() -> None:

    with RetailEnvironment("high_value_refund") as env:
        _verify_alice(env.connection, "hv_cust_alice")
        create_return(
            env.connection,
            CreateReturnInput(
                customer_id="hv_cust_alice",
                order_id="hv_ord_1001",
                return_id="hv_ret_1",
                idempotency_key="hv-idem-ret",
                items=[
                    CreateReturnItemInput(
                        return_item_id="hv_ri_1",
                        order_item_id="hv_oi_1",
                        quantity=1,
                    )
                ],
                requested_at=REFERENCE_TIME,
                as_of=REFERENCE_TIME,
            ),
        )
        denied = create_refund(
            env.connection,
            CreateRefundInput(
                customer_id="hv_cust_alice",
                return_id="hv_ret_1",
                payment_id="hv_pay_1",
                refund_id="hv_ref_1",
                amount_cents=55_000,
                idempotency_key="hv-idem-ref",
                created_at=REFERENCE_TIME,
                as_of=REFERENCE_TIME,
            ),
        )
        assert denied.code is PolicyCode.MANAGER_APPROVAL_REQUIRED
        assert env.connection.execute("SELECT COUNT(*) FROM refunds").fetchone()[0] == 0

        request_manager_approval(
            env.connection,
            RequestManagerApprovalInput(
                customer_id="hv_cust_alice",
                order_id="hv_ord_1001",
                payment_id="hv_pay_1",
                amount_cents=55_000,
                approval_id="hv_appr_1",
                requested_at=REFERENCE_TIME,
            ),
        )
        ok = create_refund(
            env.connection,
            CreateRefundInput(
                customer_id="hv_cust_alice",
                return_id="hv_ret_1",
                payment_id="hv_pay_1",
                refund_id="hv_ref_1",
                amount_cents=55_000,
                idempotency_key="hv-idem-ref",
                created_at=REFERENCE_TIME,
                as_of=REFERENCE_TIME,
                approval_id="hv_appr_1",
            ),
        )
        assert ok.ok
        linked = env.connection.execute(
            "SELECT refund_id FROM approvals WHERE approval_id = ?",
            ("hv_appr_1",),
        ).fetchone()["refund_id"]
        assert linked == "hv_ref_1"


def test_refund_exceeding_available_payment_is_denied() -> None:
    with RetailEnvironment("already_refunded") as env:
        _verify_alice(env.connection, "ar_cust_alice")
        result = create_refund(
            env.connection,
            CreateRefundInput(
                customer_id="ar_cust_alice",
                return_id="ar_ret_1",
                payment_id="ar_pay_1",
                refund_id="ar_ref_extra",
                amount_cents=100,
                idempotency_key="ar-idem-extra",
                created_at=REFERENCE_TIME,
                as_of=REFERENCE_TIME,
            ),
        )
        assert result.code is PolicyCode.REFUND_EXCEEDS_AVAILABLE_AMOUNT


def test_get_refund_status_enforces_ownership() -> None:

    with RetailEnvironment("already_refunded") as env:
        _verify_alice(env.connection, "ar_cust_alice")
        owned = get_refund_status(
            env.connection,
            GetRefundStatusInput(customer_id="ar_cust_alice", refund_id="ar_ref_1"),
        )
        assert owned.ok
        _assert_no_pii(owned.model_dump(mode="json"))

        env.connection.execute(
            """
            INSERT INTO customers (
                customer_id, full_name, email, phone, verified, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "ar_cust_bob",
                "Bob Example",
                "bob@example.test",
                "+1-555-0101",
                1,
                REFERENCE_TIME.isoformat(),
            ),
        )
        env.connection.commit()
        verify_customer(
            env.connection,
            VerifyCustomerInput(
                customer_id="ar_cust_bob",
                email="bob@example.test",
                phone="+1-555-0101",
            ),
        )
        denied = get_refund_status(
            env.connection,
            GetRefundStatusInput(customer_id="ar_cust_bob", refund_id="ar_ref_1"),
        )
        assert denied.code is PolicyCode.ORDER_ACCESS_DENIED


def test_failed_multi_row_mutation_rolls_back() -> None:
    with RetailEnvironment("eligible_return") as env:
        with pytest.raises(sqlite3.IntegrityError), transaction(env.connection):
            env.connection.execute(
                """
                INSERT INTO returns (
                    return_id, order_id, customer_id, status,
                    requested_at, idempotency_key
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    "er_ret_rb",
                    "er_ord_1001",
                    "er_cust_alice",
                    ReturnStatus.APPROVED.value,
                    REFERENCE_TIME.isoformat(),
                    "er-idem-rb",
                ),
            )
            env.connection.execute(
                """
                INSERT INTO return_items (
                    return_item_id, return_id, order_item_id, quantity
                ) VALUES (?, ?, ?, ?)
                """,
                ("er_ri_rb", "er_ret_rb", "missing_oi", 1),
            )
        returns = env.connection.execute(
            "SELECT COUNT(*) FROM returns WHERE return_id = ?",
            ("er_ret_rb",),
        ).fetchone()[0]
        items = env.connection.execute(
            "SELECT COUNT(*) FROM return_items WHERE return_id = ?",
            ("er_ret_rb",),
        ).fetchone()[0]
        assert returns == 0
        assert items == 0


def test_invoke_tool_validates_and_dispatches() -> None:
    with RetailEnvironment("eligible_return") as env:
        result = invoke_tool(
            env.connection,
            "verify_customer",
            {
                "customer_id": "er_cust_alice",
                "email": "alice@example.test",
                "phone": "+1-555-0100",
            },
        )
        assert result.ok
        with pytest.raises(KeyError):
            invoke_tool(env.connection, "not_a_tool", {})
        with pytest.raises(ValidationError):
            invoke_tool(env.connection, "verify_customer", {"customer_id": "x"})
