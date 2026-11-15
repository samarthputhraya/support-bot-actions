"""Support bot: answers a customer, calling the shop's tools as needed.

The model id lives in app/model.txt, so switching models is a one-line change that Modelpin
checks before it merges. The bot calls Claude through Anthropic's Messages API with the key in
ANTHROPIC_API_KEY.
"""

import json
import re
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

from anthropic import Anthropic
from anthropic.types import MessageParam, ToolParam, ToolResultBlockParam

from app.prompts import STATUS_CARD_PROMPT, support_prompt
from app.shop import Shop
from app.tools import STATUS_CARD_TOOLS, SUPPORT_TOOLS, run_tool

MODEL_FILE = Path(__file__).with_name("model.txt")

#: The most model calls one answer may take while tools are being called.
MAX_TOOL_TURNS = 6

#: The longest answer one model call may write. Newer Claude models may think before they answer,
#: and thinking counts against this limit, so it is set as Modelpin sets it for its replays.
MAX_TOKENS = 4096

#: The shop's orders, in memory until the bot is connected to the real order system.
SHOP = Shop.with_sample_orders()

ToolRunner = Callable[[str, dict[str, Any]], dict[str, Any]]

#: Order ids look like A-2041. The public status card refuses anything else before calling the model.
ORDER_ID = re.compile(r"A-[0-9]{4}")


def model_id() -> str:
    return MODEL_FILE.read_text(encoding="utf-8").strip()


def _answer(system: str, text: str, tools: list[ToolParam], client: Anthropic, run: ToolRunner) -> str:
    messages: list[MessageParam] = [{"role": "user", "content": text}]
    for _ in range(MAX_TOOL_TURNS):
        response = client.messages.create(
            model=model_id(), max_tokens=MAX_TOKENS, system=system, messages=messages, tools=tools
        )
        calls = [block for block in response.content if block.type == "tool_use"]
        if not calls:
            return "".join(block.text for block in response.content if block.type == "text")
        # The model's turn goes back unchanged, then every tool result in one user message, in the
        # order the model called them.
        messages.append({"role": "assistant", "content": response.content})
        results: list[ToolResultBlockParam] = [
            {
                "type": "tool_result",
                "tool_use_id": call.id,
                "content": json.dumps(run(call.name, dict(call.input))),
            }
            for call in calls
        ]
        messages.append({"role": "user", "content": results})
    raise RuntimeError(f"No answer after {MAX_TOOL_TURNS} model calls")


def reply(customer_email: str, text: str, client: Anthropic | None = None) -> str:
    """The bot's reply to one message from a signed-in customer."""
    today = date.today()

    def run(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return run_tool(name, arguments, shop=SHOP, customer_email=customer_email, today=today)

    system = support_prompt(customer_email, today.isoformat())
    return _answer(system, text, SUPPORT_TOOLS, client or Anthropic(), run)


def status_card(order_id: str, client: Anthropic | None = None) -> str:
    """The JSON status card for one order, as the shop's website shows it."""
    if not ORDER_ID.fullmatch(order_id):
        raise ValueError("not an order id")

    def run(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        # No signed-in customer here: lookup_order returns only the status fields (app/tools.py).
        return run_tool(name, arguments, shop=SHOP, customer_email=None, today=date.today())

    return _answer(STATUS_CARD_PROMPT, order_id, STATUS_CARD_TOOLS, client or Anthropic(), run)
