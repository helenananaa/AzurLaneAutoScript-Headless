#!/usr/bin/env python3
"""Inspect and optionally accept the exact reviewed game agreement DOM."""

from __future__ import annotations

import argparse
import json
import urllib.request
from typing import Any, Mapping, Sequence


SDK_AGREEMENT_TITLE = "sdk\u534f\u8bae"
AGREE_TEXT = "\u540c\u610f"
DISAGREE_TEXT = "\u62d2\u7edd"


INSPECT_EXPRESSION = r"""
(() => {
  const inspect = (selector) => {
    const nodes = Array.from(document.querySelectorAll(selector));
    const node = nodes.length === 1 ? nodes[0] : null;
    if (!node) return {count: nodes.length};
    const rect = node.getBoundingClientRect();
    const style = getComputedStyle(node);
    return {
      count: 1,
      text: (node.innerText || node.textContent || '').trim(),
      disabled: node.matches(':disabled') || node.hasAttribute('disabled') ||
        node.getAttribute('aria-disabled') === 'true',
      visible: rect.width > 0 && rect.height > 0 && style.display !== 'none' &&
        style.visibility === 'visible' && style.opacity !== '0',
      rect: {left: rect.left, top: rect.top, width: rect.width, height: rect.height}
    };
  };
  return {title: document.title, agree: inspect('.agree'), disagree: inspect('.disagree')};
})()
"""

CLICK_EXPRESSION = r"""
(() => {
  const nodes = Array.from(document.querySelectorAll('.agree'));
  if (nodes.length !== 1) throw new Error('agree target count changed');
  nodes[0].click();
  return {clicked: true, count: 1, className: nodes[0].className};
})()
"""


def validate_dom(value: Mapping[str, Any], expected_title: str) -> None:
    if value.get("title") != expected_title:
        raise ValueError("agreement title mismatch")
    expectations = (("agree", AGREE_TEXT), ("disagree", DISAGREE_TEXT))
    for name, text in expectations:
        element = value.get(name)
        if not isinstance(element, dict):
            raise ValueError(f"{name} element result is malformed")
        rect = element.get("rect")
        if (
            element.get("count") != 1
            or element.get("text") != text
            or element.get("disabled") is not False
            or element.get("visible") is not True
            or not isinstance(rect, dict)
            or not isinstance(rect.get("width"), (int, float))
            or not isinstance(rect.get("height"), (int, float))
            or rect["width"] <= 0
            or rect["height"] <= 0
        ):
            raise ValueError(f"{name} element does not match the reviewed contract")


def _send_command(socket: Any, command_id: int, method: str, params: Mapping[str, Any]) -> Any:
    socket.send(json.dumps({"id": command_id, "method": method, "params": params}))
    while True:
        response = json.loads(socket.recv())
        if response.get("id") != command_id:
            continue
        if "error" in response:
            raise RuntimeError(f"CDP {method} failed: {response['error']}")
        result = response.get("result", {}).get("result", {})
        if "exceptionDetails" in response.get("result", {}):
            raise RuntimeError(f"CDP {method} raised an exception")
        if "value" not in result:
            raise RuntimeError(f"CDP {method} returned no by-value result")
        return result["value"]


def run(endpoint: str, expected_title: str, click: bool) -> Mapping[str, Any]:
    try:
        import websocket
    except ImportError as exc:
        raise RuntimeError("websocket-client is required for Android WebView CDP") from exc

    with urllib.request.urlopen(endpoint.rstrip("/") + "/json", timeout=5) as response:
        targets = json.load(response)
    matches = [
        target
        for target in targets
        if target.get("type") == "page"
        and target.get("title") == expected_title
        and target.get("url")
        and target.get("webSocketDebuggerUrl")
    ]
    if len(matches) != 1:
        raise RuntimeError(f"expected exactly one reviewed agreement target, found {len(matches)}")
    target = matches[0]
    socket = websocket.create_connection(
        target["webSocketDebuggerUrl"], timeout=5, suppress_origin=True
    )
    try:
        dom = _send_command(
            socket,
            1,
            "Runtime.evaluate",
            {"expression": INSPECT_EXPRESSION, "returnByValue": True},
        )
        if not isinstance(dom, dict):
            raise RuntimeError("agreement DOM result is malformed")
        validate_dom(dom, expected_title)
        action = None
        if click:
            action = _send_command(
                socket,
                2,
                "Runtime.evaluate",
                {"expression": CLICK_EXPRESSION, "returnByValue": True},
            )
            if not isinstance(action, dict) or action.get("clicked") is not True:
                raise RuntimeError("CDP did not confirm the unique agreement action")
        return {
            "target": {key: target.get(key) for key in ("id", "title", "url")},
            "dom": dom,
            "action": action,
        }
    finally:
        socket.close()


def main(argv: Sequence[str] = ()) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--expected-title", default=SDK_AGREEMENT_TITLE)
    parser.add_argument("--click", action="store_true")
    args = parser.parse_args(list(argv) if argv else None)
    print(json.dumps(run(args.endpoint, args.expected_title, args.click), ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
