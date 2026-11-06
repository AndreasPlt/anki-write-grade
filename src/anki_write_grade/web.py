"""The HTML the add-on appends to a card - no Anki imports.

One snippet for both sides: the card's own stylesheet tokens style it, and
`check.js` draws whatever state Python hands it. Python owns the state; the
script only renders it and sends the sentence back.
"""

from __future__ import annotations

import json
import os
from typing import Any

_HERE = os.path.dirname(os.path.abspath(__file__))


def _asset(name: str) -> str:
    with open(os.path.join(_HERE, name), encoding="utf-8") as source:
        return source.read()


CSS = _asset("check.css")
JS = _asset("check.js")


def snippet(side: str, card_id: int, model: str, attempt: dict[str, Any] | None) -> str:
    state = {"side": side, "card": card_id, "model": model, "attempt": attempt}
    # `</` would close the script element early if a sentence contained "</script>".
    data = json.dumps(state, ensure_ascii=False).replace("</", "<\\/")
    return (
        f"<style>{CSS}</style>"
        '<div id="wg-root"></div>'
        f"<script>{JS}\nWriteGrade.mount({data});</script>"
    )


def show_js(attempt: dict[str, Any]) -> str:
    """JS that redraws the attempt on whichever side is showing."""
    return f"window.WriteGrade && WriteGrade.show({json.dumps(attempt, ensure_ascii=False)});"
