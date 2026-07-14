"""Pydantic boundary models and enums for the retail domain.

SQLite is the source of truth; these models validate and carry data at
application boundaries. They never hold database connections.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

NonNegativeCents = Annotated[int, Field(ge=0)]
PositiveCents = Annotated[int, Field(gt=0)]
PositiveQuantity = Annotated[int, Field(gt=0)]
NonNegativeQuantity = Annotated[int, Field(ge=0)]


class OrderStatus(StrEnum):
    PLACED = "placed"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class PaymentStatus(StrEnum):
    PENDING = "pending"
    CAPTURED = "captured"
    REFUNDED = "refunded"
    FAILED = "failed"


class ReturnStatus(StrEnum):
    REQUESTED = "requested"
    APPROVED = "approved"
    COMPLETED = "completed"
    REJECTED = "rejected"


class RefundStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    COMPLETED = "completed"
    REJECTED = "rejected"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"


class PaymentMethod(StrEnum):
    CARD = "card"
    STORE_CREDIT = "store_credit"
    OTHER = "other"


class CaseEventType(StrEnum):
    NOTE = "note"
    VERIFICATION = "verification"
    POLICY_CHECK = "policy_check"
    MUTATION = "mutation"


class RetailModel(BaseModel):
    """Shared config for retail boundary models."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def _require_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        msg = "datetime must be timezone-aware"
        raise ValueError(msg)
    return value.astimezone(UTC)


class Customer(RetailModel):
    customer_id: str
    full_name: str
    email: str
    phone: str
    verified: bool
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def _utc(cls, value: datetime) -> datetime:
        return _require_aware_utc(value)


class Product(RetailModel):
    product_id: str
    sku: str
    name: str
    unit_price_cents: NonNegativeCents
    final_sale: bool


class InventoryItem(RetailModel):
    inventory_item_id: str
    product_id: str
    quantity_on_hand: NonNegativeQuantity


class Order(RetailModel):
    order_id: str
    customer_id: str
    status: OrderStatus
    ordered_at: datetime
    delivered_at: datetime | None = None

    @field_validator("ordered_at", "delivered_at")
    @classmethod
    def _utc_optional(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return _require_aware_utc(value)


class OrderItem(RetailModel):
    order_item_id: str
    order_id: str
    product_id: str
    quantity: PositiveQuantity
    unit_price_cents: NonNegativeCents


class Payment(RetailModel):
    payment_id: str
    order_id: str
    amount_cents: PositiveCents
    status: PaymentStatus
    method: PaymentMethod
    paid_at: datetime

    @field_validator("paid_at")
    @classmethod
    def _utc(cls, value: datetime) -> datetime:
        return _require_aware_utc(value)


class Return(RetailModel):
    return_id: str
    order_id: str
    customer_id: str
    status: ReturnStatus
    requested_at: datetime
    idempotency_key: str

    @field_validator("requested_at")
    @classmethod
    def _utc(cls, value: datetime) -> datetime:
        return _require_aware_utc(value)


class ReturnItem(RetailModel):
    return_item_id: str
    return_id: str
    order_item_id: str
    quantity: PositiveQuantity


class Refund(RetailModel):
    refund_id: str
    return_id: str
    payment_id: str
    amount_cents: PositiveCents
    status: RefundStatus
    created_at: datetime
    idempotency_key: str

    @field_validator("created_at")
    @classmethod
    def _utc(cls, value: datetime) -> datetime:
        return _require_aware_utc(value)


class Approval(RetailModel):
    """Manager approval for a proposed refund amount.

    Approval is requested before high-value refund creation. ``refund_id`` stays
    null until ``create_refund`` links the completed refund.
    """

    approval_id: str
    order_id: str
    payment_id: str
    amount_cents: PositiveCents
    status: ApprovalStatus
    requested_at: datetime
    resolved_at: datetime | None = None
    refund_id: str | None = None

    @field_validator("requested_at", "resolved_at")
    @classmethod
    def _utc_optional(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return _require_aware_utc(value)


class CaseEvent(RetailModel):
    case_event_id: str
    customer_id: str | None = None
    order_id: str | None = None
    event_type: CaseEventType
    payload_json: str
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def _utc(cls, value: datetime) -> datetime:
        return _require_aware_utc(value)
