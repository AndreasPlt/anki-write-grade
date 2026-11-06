# anki-write-grade

Anki add-on **Write & Grade**: write a sentence on the front of a card and have an agent CLI
(`pi -p`, `claude -p`, ...) grade it against your rubric.

- On the configured note type and card type, a box sits under the prompt. Enter checks;
  Esc leaves the box so Space flips again. While an IME is composing, Enter picks the
  candidate and does not check.
- The CLI gets your rubric (read fresh on every check), the card fields you configured, the
  prompt actually on screen, and the sentence. The verdict shows under the box in the
  rubric's lines; edit and press Enter again to retry.
- After the flip, your last sentence and its verdict sit between the replayed prompt and the
  reference. Flip without checking and the back is unchanged.
- Every graded sentence can be appended to an attempts log.
- The note type is not touched: the box is added when the card is shown (`card_will_show`),
  so the phone apps show the card as before.
- It does not rate the card; you still press Again / Good.

What it assumes about the template: the box goes after an element with class `.todo` on the
front and `.replay` on the back, and the prompt on screen is `.quote .rot-on` (or `.quote`).
Without them the box goes to the bottom of the card and no prompt is sent.

## Install

```bash
uv run python scripts/install.py
```

This builds `dist/anki_write_grade.ankiaddon` and opens it with Anki. Confirm the install and
restart Anki. `uv run python scripts/build.py` only builds the file.

Configure under Tools → Add-ons → Write & Grade → Config; the keys are documented in
[`config.md`](src/anki_write_grade/config.md).

## Layout

- `grade.py` — config, prompt, CLI run, parsing the rubric's lines, the log row. No Anki
  imports, so it is unit-tested and runs outside Anki.
- `web.py`, `check.js`, `check.css` — what is added to the card. Python owns the state; the
  script only draws it and sends the sentence back.
- `__init__.py` — hooks: adding the box, the sentence message, one check at a time,
  dropping a result that arrives after the card changed.

## Development

```bash
uv run pytest
uv run ruff check . && uv run ruff format --check .
```
