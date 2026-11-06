**note_type** / **card_type** — the cards that get the box: the note type's name and the template's name, exactly as Anki shows them. Required.

**fields** — what the grader is told about the card: card field → the label it sees, in the order given. Empty fields are left out; HTML and `[sound:]` tags are stripped. Required.

**repo** — the directory the CLI runs in; `rubric` and `log` are relative to it. `~` is expanded. Empty: your home folder.

**rubric** — the grading rubric, read fresh on every check. Required. It must make the grader answer in these lines, which the add-on parses:

    VERDICT: ✅ natural | 🟡 understandable but off | ❌ wrong
    TARGET: ok | <what is off>
    GRAMMAR: ok | <what is off>
    NATURALNESS: ok | <what is off>
    HINT: <hint>            (on 🟡 and ❌)
    IMPROVE: <one line>     (on ✅)

**log** — the attempts log, a TSV with one row per graded sentence: `at surface target sense sentence verdict note`, with `surface` = `card`. A new file gets the header row. Empty: nothing is logged.

**log_target** / **log_sense** — the fields whose text fills the log's `target` and `sense` columns. `log_target` defaults to the first of `fields`; `log_sense` empty leaves the column empty.

**instructions** — sent ahead of the rubric: what the grader is grading and how to answer. Empty: a generic default.

**command** — the CLI as an argument list; `{prompt}` is replaced by the grading prompt. This is where the model is chosen. The `pi` command here runs with nothing but the prompt — no tools, no session, no project files — so a check is one fast call that cannot touch anything. Sonnet instead:

    "command": ["/opt/homebrew/bin/pi", "-p", "{prompt}", "--no-session", "--no-tools", "--no-context-files", "--no-extensions", "--no-skills", "--no-prompt-templates", "--offline", "--model", "anthropic/claude-sonnet-5", "--thinking", "low"]

Use absolute paths: Anki started from the Dock does not get your shell's PATH. The CLI's own directory is put on PATH for it (that is where Homebrew keeps `node`). The waiting line names the `--model` value.

**timeout_s** — give up on a check after this many seconds.
