"""Grade one sentence written on an Anki card, through an agent CLI - no Anki imports.

The add-on hands this module the card's fields, the prompt that was on screen and my
sentence. It wraps them around the grading rubric, runs the CLI once, parses the rubric's
output lines and appends the attempts-log row. The rubric is read fresh on every check,
so its file stays the only definition of how grading works; which note type, which
fields and which rubric all come from the config.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import html
import os
import re
import signal
import subprocess
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

# The rubric's axes, in its order: output key, the symbol the log uses, the name shown.
AXES = (("TARGET", "①", "target"), ("GRAMMAR", "②", "grammar"), ("NATURALNESS", "③", "naturalness"))
KEYS = ("VERDICT", *(key for key, _, _ in AXES), "HINT", "IMPROVE")
VERDICTS = {"✅": "ok", "🟡": "off", "❌": "wrong"}
LOG_HEADER = ("at", "surface", "target", "sense", "sentence", "verdict", "note")

DEFAULT_INSTRUCTIONS = (
    "Grade one sentence I wrote while reviewing an Anki card. The rubric below decides "
    "everything; follow it exactly. The <target> block holds the card's fields. Reply "
    "with the rubric's output lines only."
)


class CheckError(Exception):
    """The CLI failed, timed out, could not be started, or answered off-format."""


class CheckCancelledError(Exception):
    """The check was cancelled before it finished."""


@dataclass(frozen=True)
class Config:
    note_type: str
    card_type: str
    fields: tuple[tuple[str, str], ...]  # (card field, the label the grader sees), in order
    repo: str
    rubric: str
    log: str  # empty: nothing is logged
    log_target: str  # the field whose text fills the log's `target` column
    log_sense: str  # ... and its `sense` column; empty leaves it empty
    instructions: str
    command: tuple[str, ...]
    timeout_s: float

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any]) -> Config:
        missing = [key for key in ("note_type", "card_type", "rubric") if not values.get(key)]
        if missing:
            raise ValueError("config: set " + ", ".join(missing))
        fields = values.get("fields") or []
        if not isinstance(fields, (list, tuple)) or not fields:
            raise ValueError("config: fields must be a list of card fields, in order")
        labels = values.get("labels") or {}
        if not isinstance(labels, Mapping):
            raise ValueError("config: labels must map card fields to the names the grader sees")
        stray = [str(name) for name in labels if name not in fields]
        if stray:
            raise ValueError("config: labels for fields not in fields: " + ", ".join(stray))
        command = tuple(str(arg) for arg in values.get("command") or ())
        if not command:
            raise ValueError("config: command must be a non-empty list")
        if not any("{prompt}" in arg for arg in command):
            raise ValueError("config: command needs a {prompt} placeholder")
        pairs = tuple((str(name), str(labels.get(name) or name)) for name in fields)
        return cls(
            note_type=str(values["note_type"]),
            card_type=str(values["card_type"]),
            fields=pairs,
            repo=os.path.expanduser(str(values.get("repo") or "~")),
            rubric=str(values["rubric"]),
            log=str(values.get("log") or ""),
            log_target=str(values.get("log_target") or pairs[0][0]),
            log_sense=str(values.get("log_sense") or ""),
            instructions=str(values.get("instructions") or DEFAULT_INSTRUCTIONS).strip(),
            command=command,
            timeout_s=float(values.get("timeout_s", 60)),
        )

    @property
    def rubric_path(self) -> str:
        return os.path.join(self.repo, os.path.expanduser(self.rubric))

    @property
    def log_path(self) -> str:
        return os.path.join(self.repo, os.path.expanduser(self.log)) if self.log else ""

    def model_label(self) -> str:
        """What the waiting line names: the --model value, else the CLI's name."""
        for flag, value in zip(self.command, self.command[1:]):
            if flag == "--model":
                return value
        return os.path.basename(self.command[0])


@dataclass(frozen=True)
class Result:
    symbol: str  # ✅ 🟡 ❌
    verdict: str  # the words after it: natural / understandable but off / wrong
    axes: tuple[tuple[str, str], ...]  # (TARGET|GRAMMAR|NATURALNESS, its line)
    hint: str
    improve: str

    @property
    def kind(self) -> str:
        return VERDICTS[self.symbol]

    def passing(self) -> list[str]:
        """Names of the axes that are fine."""
        names = dict((key, name) for key, _, name in AXES)
        return [names[key] for key, text in self.axes if _is_ok(text)]

    def failing(self) -> list[tuple[str, str]]:
        """(key, line) of each axis that is not fine, in rubric order."""
        return [(key, text) for key, text in self.axes if not _is_ok(text)]

    def log_note(self) -> str:
        """The log's `note`: each failing axis as its symbol and what is off. Empty on ✅."""
        if self.kind == "ok":
            return ""
        symbols = dict((key, symbol) for key, symbol, _ in AXES)
        return " · ".join(f"{symbols[key]} {_strip_off(text)}" for key, text in self.failing())

    def to_json(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "verdict": self.verdict,
            "kind": self.kind,
            "passing": self.passing(),
            "failing": [[key, _strip_off(text)] for key, text in self.failing()],
            "hint": self.hint,
            "improve": self.improve,
        }


def _is_ok(text: str) -> bool:
    return re.match(r"ok\b", text.strip(), re.IGNORECASE) is not None


def _strip_off(text: str) -> str:
    """'off — 增强 doesn't take 身体' -> '增强 doesn't take 身体'."""
    return re.sub(r"^(?:off|wrong)\s*[—–:-]\s*", "", text.strip(), flags=re.IGNORECASE)


_SOUND = re.compile(r"\[sound:[^\]]*\]")
_BREAK = re.compile(r"<br\s*/?>|</?(?:div|p|li|tr)\b[^>]*>", re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")


def field_text(value: str) -> str:
    """A field's HTML as plain text: tags and audio dropped, line breaks kept."""
    text = _BREAK.sub("\n", _SOUND.sub("", value))
    text = html.unescape(_TAG.sub("", text))
    lines = (line.strip() for line in text.splitlines())
    return "\n".join(line for line in lines if line)


def target_block(mapping: tuple[tuple[str, str], ...], fields: Mapping[str, str]) -> str:
    lines = ["<target>"]
    for field, label in mapping:
        text = field_text(fields.get(field, ""))
        if text:
            lines.append(f"{label}: " + text.replace("\n", "\n  "))
    lines.append("</target>")
    return "\n".join(lines)


def build_prompt(
    config: Config, rubric: str, fields: Mapping[str, str], situation: str, sentence: str
) -> str:
    parts = [
        config.instructions,
        f"<rubric>\n{rubric.strip()}\n</rubric>",
        target_block(config.fields, fields),
    ]
    if situation.strip():
        parts.append(
            "The situation the card gave me (it tells you what I meant to say):\n"
            + situation.strip()
        )
    parts.append("My sentence, verbatim:\n" + sentence.strip())
    return "\n\n".join(parts)


_LINE = re.compile(r"^[\s>*`_-]*(" + "|".join(KEYS) + r")[*_`]*\s*:\s*[*_`]*\s*(.*)$")


def parse(output: str) -> Result:
    """The rubric's output lines -> Result. Text around them is ignored."""
    values: dict[str, str] = {}
    current = None
    for raw in output.splitlines():
        line = raw.strip()
        match = _LINE.match(line)
        if match:
            current = match[1]
            values[current] = match[2].strip()
        elif current and line and not line.startswith("```"):
            values[current] = f"{values[current]} {line}".strip()
    verdict = values.get("VERDICT", "")
    symbol = next((s for s in VERDICTS if verdict.startswith(s)), None)
    if symbol is None:
        raise CheckError("the grader answered off-format:\n" + output.strip()[:600])
    return Result(
        symbol=symbol,
        verdict=verdict[len(symbol) :].strip(),
        axes=tuple((key, values.get(key, "ok")) for key, _, _ in AXES),
        hint=values.get("HINT", ""),
        improve=values.get("IMPROVE", ""),
    )


def log_attempt(config: Config, fields: Mapping[str, str], sentence: str, result: Result) -> None:
    """Append one row to the attempts log, writing the header into a new file."""
    path = config.log_path
    if not path:
        return
    at = dt.datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")
    row = (
        at,
        "card",
        field_text(fields.get(config.log_target, "")),
        field_text(fields.get(config.log_sense, "")) if config.log_sense else "",
        sentence,
        result.symbol,
        result.log_note(),
    )
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    new = not os.path.exists(path) or os.path.getsize(path) == 0
    with open(path, "a", encoding="utf-8", newline="") as out:
        if new:
            out.write("\t".join(LOG_HEADER) + "\n")
        out.write("\t".join(_cell(value) for value in row) + "\n")


def _cell(value: str) -> str:
    return re.sub(r"[\t\r\n]+", " ", value).strip()


class Check:
    """One grading run. `run` blocks (call it off the UI thread); `cancel` is thread-safe."""

    def __init__(
        self, config: Config, fields: Mapping[str, str], situation: str, sentence: str
    ) -> None:
        self.config = config
        self.fields = dict(fields)
        self.situation = situation
        self.sentence = sentence.strip()
        self._lock = threading.Lock()
        self._proc: subprocess.Popen[bytes] | None = None
        self._cancelled = False

    def argv(self, prompt: str) -> list[str]:
        return [arg.replace("{prompt}", prompt) for arg in self.config.command]

    def run(self) -> Result:
        try:
            with open(self.config.rubric_path, encoding="utf-8") as rubric:
                prompt = build_prompt(
                    self.config, rubric.read(), self.fields, self.situation, self.sentence
                )
        except OSError as error:
            raise CheckError(f"cannot read the rubric: {error}") from error
        argv = self.argv(prompt)

        with self._lock:
            if self._cancelled:
                raise CheckCancelledError()
            try:
                self._proc = subprocess.Popen(
                    argv,
                    cwd=self.config.repo,
                    env=_child_env(argv[0]),
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    start_new_session=True,  # so a kill takes the CLI's children too
                )
            except OSError as error:
                raise CheckError(f"could not start {argv[0]}: {error}") from error
        proc = self._proc

        try:
            out, err = proc.communicate(timeout=self.config.timeout_s)
        except subprocess.TimeoutExpired:
            _kill(proc)
            proc.communicate()
            raise CheckError(f"no answer after {self.config.timeout_s:g}s") from None

        if self._cancelled:
            raise CheckCancelledError()
        if proc.returncode != 0:
            detail = (err or out).decode(errors="replace").strip()[-800:]
            raise CheckError(f"{os.path.basename(argv[0])} exited {proc.returncode}: {detail}")
        return parse(out.decode(errors="replace"))

    def cancel(self) -> None:
        with self._lock:
            self._cancelled = True
            if self._proc is not None and self._proc.poll() is None:
                _kill(self._proc)


def _kill(proc: subprocess.Popen[bytes]) -> None:
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(proc.pid, signal.SIGTERM)


def _child_env(executable: str) -> dict[str, str]:
    """Anki started from the Dock has a bare PATH; put the CLI's own directory first.

    That is where Homebrew keeps both the CLI and `node`, which script-based CLIs
    such as `pi` need.
    """
    env = dict(os.environ)
    if os.path.isabs(executable):
        env["PATH"] = os.pathsep.join([os.path.dirname(executable), env.get("PATH", "")])
    return env
