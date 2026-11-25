**profiles** — the note types that get the box, one object each, so a deck can hold several
graded note types side by side. A profile is matched by the note type's name and the
template's name, both exactly as Anki shows them. Every profile is its own grading
world: its own fields, rubric, log and CLI. Required, at least one. A config with no
`profiles` at all is read as a single profile, so a config written before profiles
existed keeps working.

**name** — what the config calls this profile, only used in messages, e.g. `"Chinese
pattern"`. Empty: `note type / card type`.

**note_type** / **card_type** — the note type's name and the template's name, exactly as
Anki shows them. Required. Two profiles may not name the same pair.

Everything else below can sit beside `profiles` as a default for all of them, or inside a
profile to be that profile's own. A key inside a profile replaces the default wholesale —
an empty `log` there turns logging off for that profile, and `labels` are not merged.

    "repo": "~/dev/learning/zh_agentic",
    "profiles": [
        {"note_type": "ZJU Chinese Pattern", "card_type": "Production",
         "fields": ["Pattern", "Function", "Slots"], "rubric": "spec/grading_rubric.md",
         "log": "logs/patterns.tsv"},
        {"note_type": "ZJU Hanzi", "card_type": "Recall", "fields": ["Hanzi", "Meaning"],
         "rubric": "spec/hanzi_rubric.md", "log": "logs/hanzi.tsv",
         "timeout_s": 90}
    ]

**fields** — what the grader is told about the card: the card fields, in the order it reads
them. A list, not an object, because Anki's Config dialog sorts an object's keys when it
saves. Empty fields are left out; HTML and `[sound:]` tags are stripped. Required.

**labels** — another name for a field in what the grader sees, e.g. `{"Disambiguation":
"Similar"}`. A field not listed goes by its own name.

**repo** — the directory the CLI runs in; `rubric` and `log` are relative to it. `~` is
expanded. Empty: your home folder.

**rubric** — the grading rubric, read fresh on every check. Required. It must make the grader
answer in these lines, which the add-on parses:

    VERDICT: ✅ natural | 🟡 understandable but off | ❌ wrong
    TARGET: ok | <what is off>
    GRAMMAR: ok | <what is off>
    NATURALNESS: ok | <what is off>
    HINT: <hint>            (on 🟡 and ❌)
    IMPROVE: <one line>     (on ✅)

**log** — the attempts log, a TSV with one row per graded sentence: `at surface target sense
sentence verdict note`, with `surface` = `card`. A new file gets the header row. Empty:
nothing is logged.

**log_target** / **log_sense** — the fields whose text fills the log's `target` and `sense`
columns. `log_target` defaults to the first of `fields`; `log_sense` empty leaves the
column empty.

**instructions** — sent ahead of the rubric: what the grader is grading and how to answer.
Empty: a generic default.

**command** — the CLI as an argument list; `{prompt}` is replaced by the grading prompt. This
is where the model is chosen, and profiles may point at different models. The `pi` command
here runs with nothing but the prompt — no tools, no session, no project files — so a check
is one fast call that cannot touch anything. Sonnet instead:

    "command": ["/opt/homebrew/bin/pi", "-p", "{prompt}", "--no-session", "--no-tools", "--no-context-files", "--no-extensions", "--no-skills", "--no-prompt-templates", "--offline", "--model", "anthropic/claude-sonnet-5", "--thinking", "low"]

Use absolute paths: Anki started from the Dock does not get your shell's PATH. The CLI's own
directory is put on PATH for it (that is where Homebrew keeps `node`). The waiting line names
the `--model` value.

**timeout_s** — give up on a check after this many seconds.
