"""The shop's orders, kept in memory until the bot is connected to the real order system.

The sample orders are the ones the Modelpin scenarios use, so the bot and its scenarios agree.
"""

from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from typing import Any

#: A delivered order can be refunded in full within this many days of delivery (the prompt's rule 3).
REFUND_WINDOW_DAYS = 30

REFUND_REASONS = frozenset({"damaged", "wrong_item", "not_as_described", "other"})
ESCALATION_REASONS = frozenset({"customer_asked", "customer_upset", "policy_exception"})
TICKET_CATEGORIES = frozenset({"delivery", "damaged_item", "billing", "other"})

#: What the support team promises a customer handed over from the chat.
EXPECTED_WAIT_MINUTES = 10


@dataclass
class Order:
    order_id: str
    customer_email: str
    status: str
    items: list[dict[str, Any]]
    total: float
    currency: str
    delivered_on: str | None
    estimated_delivery: str | None
    shipping_address: str

    def as_tool_result(self) -> dict[str, Any]:
        return asdict(self)


def _order(order_id: str, email: str, status: str, item: str, price: float, **dates: str | None) -> Order:
    return Order(
        order_id=order_id,
        customer_email=email,
        status=status,
        items=[{"name": item, "quantity": 1, "price": price}],
        total=price,
        currency="USD",
        delivered_on=dates.get("delivered_on"),
        estimated_delivery=dates.get("estimated_delivery"),
        shipping_address=dates.get("address") or "220 Pine Avenue, Seattle, WA 98101",
    )


def sample_orders() -> list[Order]:
    dana = "dana.reyes@example.com"
    return [
        _order("A-1903", dana, "delivered", "Stormline rain jacket", 120.0, delivered_on="2026-09-12"),
        _order("A-2041", dana, "delivered", "Ridgeline 2-person tent", 189.0, delivered_on="2026-10-30"),
        _order("A-2077", dana, "processing", "Crest 40 L backpack", 98.0, estimated_delivery="2026-11-14"),
        _order("A-2098", dana, "delivered", "Talus hiking boots", 145.0, delivered_on="2026-11-02"),
        _order(
            "A-2110",
            "marcus.lee@example.com",
            "shipped",
            "Ember camp stove",
            64.0,
            estimated_delivery="2026-11-11",
            address="18 Birch Road, Seattle, WA 98103",
        ),
        _order("A-2150", dana, "shipped", "Ember camp stove", 64.0, estimated_delivery="2026-11-13"),
        _order("A-2152", dana, "shipped", "Talus hiking boots", 145.0, estimated_delivery="2026-11-12"),
    ]


@dataclass
class Shop:
    """Orders, refunds and the support queue.

    Who may see or change an order is checked here, not only in the prompt: a signed-in customer
    gets only their own orders, and another customer's order answers exactly like a missing one,
    so a reply never shows that it exists.
    """

    orders: dict[str, Order]
    refunds: dict[str, dict[str, Any]] = field(default_factory=dict)
    next_refund_number: int = 50817
    handoffs: list[dict[str, Any]] = field(default_factory=list)
    next_handoff_number: int = 3310
    tickets: list[dict[str, Any]] = field(default_factory=list)
    next_ticket_number: int = 88401

    @classmethod
    def with_sample_orders(cls) -> "Shop":
        return cls({order.order_id: order for order in sample_orders()})

    def _customers_order(self, order_id: str, customer_email: str | None) -> Order | None:
        order = self.orders.get(order_id)
        if order is None or customer_email is None or order.customer_email != customer_email:
            return None
        return order

    def lookup_order(self, order_id: str, *, customer_email: str) -> dict[str, Any]:
        order = self._customers_order(order_id, customer_email)
        if order is None:
            return {"error": f"No order {order_id}."}
        return order.as_tool_result()

    def order_status(self, order_id: str) -> dict[str, Any]:
        """The three fields the public status card shows; nothing about the customer."""
        order = self.orders.get(order_id)
        if order is None:
            return {"error": f"No order {order_id}."}
        return {"order_id": order.order_id, "status": order.status, "estimated_delivery": order.estimated_delivery}

    def issue_refund(
        self, order_id: str, amount: float, reason: str, *, customer_email: str | None, today: date
    ) -> dict[str, Any]:
        order = self._customers_order(order_id, customer_email)
        if order is None:
            return {"error": f"No order {order_id}."}
        if order_id in self.refunds:
            return {"error": f"Order {order_id} was already refunded.", **self.refunds[order_id]}
        if reason not in REFUND_REASONS:
            return {"error": f"Unknown refund reason {reason!r}."}
        if order.status != "delivered" or order.delivered_on is None:
            return {"error": "Only a delivered order can be refunded."}
        last_day = date.fromisoformat(order.delivered_on) + timedelta(days=REFUND_WINDOW_DAYS)
        if today > last_day:
            return {"error": f"The refund window closed on {last_day.isoformat()}."}
        if not 0 < amount <= order.total:
            return {"error": f"A refund must be more than 0 and at most {order.total} {order.currency}."}
        refund = {
            "order_id": order_id,
            "refund_id": f"RF-{self.next_refund_number}",
            "refunded": amount,
            "currency": order.currency,
        }
        self.next_refund_number += 1
        self.refunds[order_id] = refund
        return refund

    def _own_order(self, order_id: str | None, customer_email: str | None) -> str | None:
        """An error when an order is given that isn't this customer's, else None."""
        if order_id is None or self._customers_order(order_id, customer_email) is not None:
            return None
        return f"No order {order_id}."

    def escalate_to_human(
        self, reason: str, order_id: str | None, *, customer_email: str | None
    ) -> dict[str, Any]:
        """Queue the chat for a person on the support team."""
        if reason not in ESCALATION_REASONS:
            return {"error": f"Unknown escalation reason {reason!r}."}
        problem = self._own_order(order_id, customer_email)
        if problem:
            return {"error": problem}
        handoff = {"handoff_id": f"H-{self.next_handoff_number}", "expected_wait_minutes": EXPECTED_WAIT_MINUTES}
        self.next_handoff_number += 1
        self.handoffs.append({**handoff, "reason": reason, "order_id": order_id, "customer_email": customer_email})
        return handoff

    def create_ticket(
        self, category: str, summary: str, order_id: str | None, *, customer_email: str | None
    ) -> dict[str, Any]:
        """Open a ticket for a problem the chat can't solve."""
        if category not in TICKET_CATEGORIES:
            return {"error": f"Unknown ticket category {category!r}."}
        if not summary.strip():
            return {"error": "A ticket needs a one-sentence summary."}
        problem = self._own_order(order_id, customer_email)
        if problem:
            return {"error": problem}
        ticket = {"ticket_id": f"T-{self.next_ticket_number}"}
        self.next_ticket_number += 1
        self.tickets.append({**ticket, "category": category, "summary": summary[:500], "order_id": order_id})
        return ticket
