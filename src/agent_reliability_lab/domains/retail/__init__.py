"""Retail domain: SQLite source of truth, boundary models, and fixtures.

Checkpoint 1 implements schema, models, deterministic fixtures, and
environment isolation. Policies and tools remain planned.
"""

from agent_reliability_lab.domains.retail.database import (
    REQUIRED_TABLES,
    connect,
    initialize_schema,
    row_to_customer,
    row_to_order,
    row_to_order_item,
    row_to_refund,
    row_to_return,
    row_to_return_item,
    transaction,
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
from agent_reliability_lab.domains.retail.seed import (
    FIXTURE_REGISTRY,
    REFERENCE_TIME,
    list_fixture_ids,
    seed_fixture,
)

__all__ = [
    "FIXTURE_REGISTRY",
    "REFERENCE_TIME",
    "REQUIRED_TABLES",
    "Approval",
    "ApprovalStatus",
    "CaseEvent",
    "CaseEventType",
    "Customer",
    "InventoryItem",
    "Order",
    "OrderItem",
    "OrderStatus",
    "Payment",
    "PaymentMethod",
    "PaymentStatus",
    "Product",
    "Refund",
    "RefundStatus",
    "RetailEnvironment",
    "Return",
    "ReturnItem",
    "ReturnStatus",
    "connect",
    "initialize_schema",
    "list_fixture_ids",
    "row_to_customer",
    "row_to_order",
    "row_to_order_item",
    "row_to_refund",
    "row_to_return",
    "row_to_return_item",
    "seed_fixture",
    "transaction",
]
