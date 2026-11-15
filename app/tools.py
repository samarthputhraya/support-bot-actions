"""The tools the support bot offers the model, in the Claude Messages API's tool form.

The scenarios in scenarios/ list the same tools in OpenAI's function form, which Modelpin accepts
for every provider and turns into this form for Claude (tests/test_scenarios.py checks they match).
"""

from datetime import date
from typing import Any

from anthropic.types import ToolParam

from app.shop import Shop


def _tool(name: str, description: str, properties: dict[str, Any], required: list[str]) -> ToolParam:
    return {
        "name": name,
        "description": description,
        "input_schema": {"type": "object", "properties": properties, "required": required},
    }


_ORDER_ID = {"type": "string", "description": "The order id, for example A-1042."}

LOOKUP_ORDER = _tool(
    "lookup_order",
    "Look up one order: its customer, status, items, total, delivery date and shipping address.",
    {"order_id": _ORDER_ID},
    ["order_id"],
)

ISSUE_REFUND = _tool(
    "issue_refund",
    "Refund an order to the customer's original payment method.",
    {
        "order_id": _ORDER_ID,
        "amount": {"type": "number", "description": "How much to refund, in the order's currency."},
        "reason": {"type": "string", "enum": ["damaged", "wrong_item", "not_as_described", "other"]},
    },
    ["order_id", "amount", "reason"],
)

UPDATE_SHIPPING_ADDRESS = _tool(
    "update_shipping_address",
    "Change where an order is shipped. Works only while the order is processing.",
    {
        "order_id": _ORDER_ID,
        "address": {"type": "string", "description": "The full new address, as the customer gave it."},
    },
    ["order_id", "address"],
)

ESCALATE_TO_HUMAN = _tool(
    "escalate_to_human",
    "Hand the conversation to a human support agent.",
    {
        "reason": {"type": "string", "enum": ["customer_asked", "customer_upset", "policy_exception"]},
        "order_id": _ORDER_ID,
    },
    ["reason"],
)

CREATE_TICKET = _tool(
    "create_ticket",
    "Open a support ticket for a problem the assistant can't solve in the chat.",
    {
        "category": {"type": "string", "enum": ["delivery", "damaged_item", "billing", "other"]},
        "summary": {"type": "string", "description": "One sentence describing the problem."},
        "order_id": _ORDER_ID,
    },
    ["category", "summary"],
)

SEARCH_HELP = _tool(
    "search_help",
    "Read the shop's help article on one topic.",
    {"topic": {"type": "string", "enum": ["returns", "shipping", "warranty", "payments"]}},
    ["topic"],
)

#: Every tool the support chat offers, in the order the model sees them.
SUPPORT_TOOLS = [
    LOOKUP_ORDER,
    ISSUE_REFUND,
    UPDATE_SHIPPING_ADDRESS,
    ESCALATE_TO_HUMAN,
    CREATE_TICKET,
    SEARCH_HELP,
]

#: The status card may only look orders up.
STATUS_CARD_TOOLS = [LOOKUP_ORDER]


def _optional(arguments: dict[str, Any], key: str) -> str | None:
    value = arguments.get(key)
    return str(value) if value else None


def run_tool(
    name: str,
    arguments: dict[str, Any],
    *,
    shop: Shop,
    customer_email: str | None,
    today: date,
) -> dict[str, Any]:
    """Run one tool call and return its result for the model.

    lookup_order and issue_refund use the shop's orders; escalate_to_human and create_ticket use
    its support queue. search_help is not connected yet and answers that it is unavailable.
    Without a signed-in customer (the public status card), lookup_order returns only an order's
    status and estimated delivery.
    """
    try:
        if name == "lookup_order":
            order_id = str(arguments["order_id"])
            if customer_email is None:
                return shop.order_status(order_id)
            return shop.lookup_order(order_id, customer_email=customer_email)
        if name == "issue_refund":
            return shop.issue_refund(
                str(arguments["order_id"]),
                float(arguments["amount"]),
                str(arguments["reason"]),
                customer_email=customer_email,
                today=today,
            )
        if name == "escalate_to_human":
            return shop.escalate_to_human(
                str(arguments["reason"]), _optional(arguments, "order_id"), customer_email=customer_email
            )
        if name == "create_ticket":
            return shop.create_ticket(
                str(arguments["category"]),
                str(arguments["summary"]),
                _optional(arguments, "order_id"),
                customer_email=customer_email,
            )
    except (KeyError, TypeError, ValueError):
        return {"error": f"{name} needs its required arguments."}
    return {"error": f"{name} is not connected yet"}
