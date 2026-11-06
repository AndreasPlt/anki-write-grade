"""Anki add-on: write a sentence on the front of a card and have an agent CLI grade it.

On the configured note type and card type a box sits under the prompt. Enter sends the
sentence, the prompt on screen and the configured fields to the CLI with your rubric;
the verdict appears under the box, the attempt is logged, and after the flip it shows on
the back above the reference.

* :mod:`anki_write_grade.grade` - prompt, CLI run, parsing, the log; no Anki imports.
* :mod:`anki_write_grade.web` - the HTML, CSS and JS added to the card.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from typing import Any

from . import grade, web

try:  # pragma: no cover - only available inside Anki
    from aqt import gui_hooks, mw
    from aqt.reviewer import Reviewer
    from aqt.utils import tooltip
except ImportError:  # imported outside Anki (tests)
    gui_hooks = mw = Reviewer = tooltip = None

_MESSAGE = "write-grade:"


@dataclass
class _Attempt:
    """The sentence checked for the card on screen; it lives until the next question."""

    card_id: int
    sentence: str
    checking: bool = True
    error: str = ""
    tries: int = 0
    result: grade.Result | None = field(default=None)

    def state(self) -> dict[str, Any]:
        return {
            "sentence": self.sentence,
            "checking": self.checking,
            "error": self.error,
            "tries": self.tries,
            "result": self.result.to_json() if self.result and not self.checking else None,
        }


_attempt: _Attempt | None = None
_running: grade.Check | None = None


def _config() -> grade.Config | None:
    try:
        return grade.Config.from_mapping(mw.addonManager.getConfig(__name__) or {})
    except ValueError as error:
        tooltip(f"Write & Grade: {error}")
        return None


def _applies(card, config: grade.Config) -> bool:
    return (
        card.note().note_type()["name"] == config.note_type
        and card.template()["name"] == config.card_type
    )


def _cancel() -> None:
    global _running
    if _running is not None:
        _running.cancel()
        _running = None


def _on_card_will_show(text: str, card, kind: str) -> str:
    global _attempt
    if kind not in ("reviewQuestion", "reviewAnswer"):
        return text
    config = _config()
    if config is None or not _applies(card, config):
        return text
    if kind == "reviewQuestion":
        _cancel()
        _attempt = None
        return text + web.snippet("front", card.id, config.model_label(), None)
    if _attempt is None or _attempt.card_id != card.id:
        return text
    return text + web.snippet("back", card.id, config.model_label(), _attempt.state())


def _on_js_message(handled: tuple[bool, Any], message: str, context: Any) -> tuple[bool, Any]:
    if not message.startswith(_MESSAGE):
        return handled
    if not isinstance(context, Reviewer) or context.card is None:
        return (True, None)
    request = json.loads(message[len(_MESSAGE) :])
    card = context.card
    if request.get("card") != card.id:
        return (True, None)  # a page left over from another card
    if _running is not None:
        _redraw(card.id)  # one check at a time: show the one still running
        return (True, None)
    config = _config()
    sentence = str(request.get("sentence") or "").strip()
    if config is not None and sentence:
        _start(config, card, sentence, str(request.get("situation") or ""))
    return (True, None)


def _start(config: grade.Config, card, sentence: str, situation: str) -> None:
    global _attempt, _running
    tries = _attempt.tries if _attempt is not None and _attempt.card_id == card.id else 0
    _attempt = _Attempt(card.id, sentence, tries=tries)
    fields = dict(card.note().items())
    check = grade.Check(config, fields, situation, sentence)
    _running = check
    _redraw(card.id)

    def work() -> None:
        result, error = None, ""
        try:
            result = check.run()
        except grade.CheckCancelledError:
            return
        except grade.CheckError as failure:
            error = str(failure)
        if result is not None:
            try:
                grade.log_attempt(config, fields, sentence, result)
            except OSError as failure:
                error = f"graded, but not logged: {failure}"
        mw.taskman.run_on_main(lambda: _finish(check, card.id, result, error))

    threading.Thread(target=work, daemon=True, name="write-grade").start()


def _finish(check: grade.Check, card_id: int, result: grade.Result | None, error: str) -> None:
    global _running
    if _running is not check:
        return  # cancelled: the card changed or review ended
    _running = None
    if _attempt is None or _attempt.card_id != card_id:
        return
    _attempt.checking = False
    _attempt.error = error
    if result is not None:
        _attempt.result = result
        _attempt.tries += 1
    _redraw(card_id)


def _redraw(card_id: int) -> None:
    reviewer = mw.reviewer
    if mw.state != "review" or reviewer.card is None or reviewer.card.id != card_id:
        return
    if _attempt is not None and _attempt.card_id == card_id:
        reviewer.web.eval(web.show_js(_attempt.state()))


def _on_state(new_state: str, _old_state: str) -> None:
    global _attempt
    if new_state != "review":
        _cancel()
        _attempt = None


if gui_hooks is not None:  # pragma: no cover - only inside Anki
    gui_hooks.card_will_show.append(_on_card_will_show)
    gui_hooks.webview_did_receive_js_message.append(_on_js_message)
    gui_hooks.state_did_change.append(_on_state)
    gui_hooks.profile_will_close.append(_cancel)
