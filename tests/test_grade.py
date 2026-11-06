from __future__ import annotations

import csv
import json
import os
import sys
import threading
import time

import pytest

from anki_write_grade import grade

FIELDS = {
    "Pattern": "再 + [Adj] + 也/都 …",
    "PY": "zài + [Adj] + yě/dōu …",
    "Function": "no matter how [Adj] it gets, the outcome stays the same",
    "Slots": "- [Adj] = how much of something<br>- 也 or 都",
    "Use": "",
    "Avoid": "- no 很 before the [Adj]: ~~再很晚~~ → 再晚",
    "Disambiguation": "- 更: compares two real things",
    "ExampleAudio": "[sound:x.mp3]",
}

WRONG = """\
VERDICT: ❌ wrong
TARGET: ok
GRAMMAR: wrong — 很 can't sit between 再 and the adjective
NATURALNESS: ok
HINT: look at what sits between 再 and 也
"""


BASE = {
    "note_type": "Chinese Pattern",
    "card_type": "Production",
    "fields": ["Pattern", "Function", "Slots", "Use", "Avoid", "Disambiguation"],
    "labels": {"Disambiguation": "Similar"},
    "rubric": "rubric.md",
    "command": ["cli", "{prompt}"],
}
CFG = grade.Config.from_mapping(BASE)


def config(tmp_path, **overrides) -> grade.Config:
    (tmp_path / "rubric.md").write_text("THE RUBRIC", encoding="utf-8")
    return grade.Config.from_mapping({**BASE, "repo": str(tmp_path), **overrides})


def test_parse_reads_the_rubric_lines():
    result = grade.parse(WRONG)
    assert (result.symbol, result.verdict, result.kind) == ("❌", "wrong", "wrong")
    assert result.passing() == ["target", "naturalness"]
    assert result.failing() == [("GRAMMAR", "wrong — 很 can't sit between 再 and the adjective")]
    assert result.hint == "look at what sits between 再 and 也"
    assert result.improve == ""


def test_parse_ignores_wrapping_markdown_and_joins_continuation_lines():
    output = (
        "Here is my judgement.\n```\n**VERDICT:** ✅ natural\nTARGET: ok — frame used\n"
        "GRAMMAR: ok\nNATURALNESS: ok\nIMPROVE: 雨下得再大，\n  我也要去。\n```\n"
    )
    result = grade.parse(output)
    assert result.kind == "ok"
    assert result.passing() == ["target", "grammar", "naturalness"]
    assert result.improve == "雨下得再大， 我也要去。"


def test_parse_treats_a_missing_axis_as_ok():
    result = grade.parse("VERDICT: 🟡 understandable but off\nNATURALNESS: off — stiff\nHINT: x")
    assert result.kind == "off"
    assert result.failing() == [("NATURALNESS", "off — stiff")]


def test_parse_refuses_output_without_a_verdict():
    with pytest.raises(grade.CheckError, match="off-format"):
        grade.parse("I think this sentence is fine.")


def test_log_note_is_symbol_and_what_is_off_and_empty_on_ok():
    assert grade.parse(WRONG).log_note() == "② 很 can't sit between 再 and the adjective"
    two = grade.parse("VERDICT: ❌ wrong\nTARGET: no 再\nGRAMMAR: off: 了 after 晚")
    assert two.log_note() == "① no 再 · ② 了 after 晚"
    assert grade.parse("VERDICT: ✅ natural\nIMPROVE: x").log_note() == ""


def test_to_json_strips_the_off_label():
    data = grade.parse(WRONG).to_json()
    assert data["failing"] == [["GRAMMAR", "很 can't sit between 再 and the adjective"]]
    assert data["passing"] == ["target", "naturalness"]


def test_prompt_has_instructions_rubric_target_situation_and_sentence():
    prompt = grade.build_prompt(CFG, "RUBRIC", FIELDS, "  It's pouring.  ", " 雨再大，我也要去。 ")
    assert prompt.startswith(grade.DEFAULT_INSTRUCTIONS + "\n\n<rubric>\nRUBRIC\n</rubric>")
    assert "Similar: - 更: compares two real things" in prompt  # the configured label
    assert "Slots: - [Adj] = how much of something\n  - 也 or 都" in prompt
    assert "Use:" not in prompt  # empty fields are left out
    assert "PY:" not in prompt and "sound:" not in prompt  # only the configured fields
    assert prompt.endswith("It's pouring.\n\nMy sentence, verbatim:\n雨再大，我也要去。")


def test_prompt_follows_the_configured_fields_and_instructions():
    cfg = grade.Config.from_mapping(
        {
            **BASE,
            "fields": ["Function", "Pattern"],
            "labels": {"Function": "", "Pattern": "Frame"},
            "instructions": " Be strict. ",
        }
    )
    prompt = grade.build_prompt(cfg, "R", FIELDS, "", "句子")
    assert prompt.startswith("Be strict.\n\n")
    assert "<target>\nFunction: no matter how" in prompt  # in the configured order
    assert "Frame: 再 + [Adj]" in prompt and "Slots:" not in prompt


def test_prompt_without_a_situation_leaves_that_part_out():
    assert "situation" not in grade.build_prompt(CFG, "R", FIELDS, " ", "句子")


def test_log_writes_the_header_once_and_flattens_cells(tmp_path):
    cfg = config(tmp_path, log="logs/attempts.tsv", log_sense="Function")
    grade.log_attempt(cfg, FIELDS, "雨再很大，\t我也要去。", grade.parse(WRONG))
    grade.log_attempt(cfg, FIELDS, "雨再大，我也要去。", grade.parse("VERDICT: ✅ natural"))
    path = tmp_path / "logs" / "attempts.tsv"
    rows = list(csv.reader(path.open(encoding="utf-8"), delimiter="\t"))
    assert rows[0] == list(grade.LOG_HEADER)
    assert rows[1][1:] == [
        "card",
        "再 + [Adj] + 也/都 …",
        "no matter how [Adj] it gets, the outcome stays the same",
        "雨再很大， 我也要去。",
        "❌",
        "② 很 can't sit between 再 and the adjective",
    ]
    assert rows[2][5:] == ["✅", ""]
    assert len(rows) == 3


def test_no_log_configured_writes_nothing(tmp_path):
    cfg = config(tmp_path)
    assert cfg.log_path == ""
    grade.log_attempt(cfg, FIELDS, "句子", grade.parse(WRONG))
    assert sorted(p.name for p in tmp_path.iterdir()) == ["rubric.md"]


def test_log_target_defaults_to_the_first_field_and_sense_to_empty(tmp_path):
    cfg = config(tmp_path, log="a.tsv")
    assert (cfg.log_target, cfg.log_sense) == ("Pattern", "")
    grade.log_attempt(cfg, FIELDS, "句子", grade.parse(WRONG))
    row = (tmp_path / "a.tsv").read_text(encoding="utf-8").splitlines()[1].split("\t")
    assert row[2:4] == ["再 + [Adj] + 也/都 …", ""]


def test_config_defaults_and_validation():
    assert (CFG.repo, CFG.timeout_s, CFG.instructions) == (
        os.path.expanduser("~"),
        60,
        grade.DEFAULT_INSTRUCTIONS,
    )
    assert CFG.fields[-1] == ("Disambiguation", "Similar")
    assert CFG.model_label() == "cli"
    model = grade.Config.from_mapping(
        {**BASE, "command": ["/bin/pi", "{prompt}", "--model", "m/x"]}
    )
    assert model.model_label() == "m/x"
    for key in ("note_type", "card_type", "rubric"):
        with pytest.raises(ValueError, match=f"set {key}"):
            grade.Config.from_mapping({**BASE, key: ""})
    with pytest.raises(ValueError, match="fields must be a list"):  # the old object form
        grade.Config.from_mapping({**BASE, "fields": {"Pattern": "Pattern"}})
    with pytest.raises(ValueError, match="labels for fields not in fields: Use"):
        grade.Config.from_mapping({**BASE, "fields": ["Pattern"], "labels": {"Use": "Usage"}})
    with pytest.raises(ValueError, match="labels must map"):
        grade.Config.from_mapping({**BASE, "labels": ["Similar"]})
    with pytest.raises(ValueError, match="non-empty"):
        grade.Config.from_mapping({**BASE, "command": []})
    with pytest.raises(ValueError, match="placeholder"):
        grade.Config.from_mapping({**BASE, "command": ["cli", "-p"]})


def test_the_shipped_config_names_what_to_set():
    path = os.path.join(os.path.dirname(grade.__file__), "config.json")
    with open(path, encoding="utf-8") as shipped:
        values = json.load(shipped)
    with pytest.raises(ValueError, match="set note_type, card_type, rubric"):
        grade.Config.from_mapping(values)


def python_cli(script: str) -> list[str]:
    return [sys.executable, "-c", script, "{prompt}"]


def test_check_runs_the_cli_with_the_prompt_and_parses_its_answer(tmp_path):
    script = (
        "import sys; p = sys.argv[1]; "
        "assert 'THE RUBRIC' in p and p.endswith('句子'); "
        f"print({WRONG!r})"
    )
    cfg = config(tmp_path, command=python_cli(script))
    assert grade.Check(cfg, FIELDS, "", "句子").run().kind == "wrong"


def test_a_placeholder_inside_the_prompt_is_not_expanded(tmp_path):
    check = grade.Check(config(tmp_path), FIELDS, "", "{prompt}")
    assert check.argv("say {prompt}") == ["cli", "say {prompt}"]


def test_failing_cli_is_a_check_error(tmp_path):
    cfg = config(
        tmp_path, command=python_cli("import sys; print('boom', file=sys.stderr); sys.exit(3)")
    )
    with pytest.raises(grade.CheckError, match="exited 3: boom"):
        grade.Check(cfg, FIELDS, "", "句子").run()


def test_missing_rubric_and_missing_cli_are_check_errors(tmp_path):
    with pytest.raises(grade.CheckError, match="rubric"):
        grade.Check(config(tmp_path, rubric="nope.md"), FIELDS, "", "x").run()
    with pytest.raises(grade.CheckError, match="could not start"):
        grade.Check(
            config(tmp_path, command=["/nonexistent/cli", "{prompt}"]), FIELDS, "", "x"
        ).run()


def test_timeout_kills_the_cli(tmp_path):
    cfg = config(tmp_path, command=python_cli("import time; time.sleep(30)"), timeout_s=0.5)
    started = time.monotonic()
    with pytest.raises(grade.CheckError, match="no answer after 0.5s"):
        grade.Check(cfg, FIELDS, "", "x").run()
    assert time.monotonic() - started < 5


def test_cancel_stops_a_running_check(tmp_path):
    check = grade.Check(
        config(tmp_path, command=python_cli("import time; time.sleep(30)")), FIELDS, "", "x"
    )
    outcome: list[BaseException] = []

    def run() -> None:
        try:
            check.run()
        except BaseException as error:  # noqa: BLE001
            outcome.append(error)

    worker = threading.Thread(target=run)
    worker.start()
    time.sleep(0.3)
    check.cancel()
    worker.join(5)
    assert not worker.is_alive()
    assert isinstance(outcome[0], grade.CheckCancelledError)
