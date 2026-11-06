from __future__ import annotations

import json
import re

from anki_write_grade import web


def mounted_state(html: str) -> dict:
    match = re.search(r"WriteGrade\.mount\((.*)\);</script>$", html, re.DOTALL)
    assert match, "the snippet must end by mounting its state"
    return json.loads(match[1].replace("<\\/", "</"))


def test_front_snippet_mounts_an_empty_front():
    html = web.snippet("front", 7, "deepseek/deepseek-flash", None)
    assert html.startswith("<style>") and '<div id="wg-root"></div>' in html
    assert mounted_state(html) == {
        "side": "front",
        "card": 7,
        "model": "deepseek/deepseek-flash",
        "attempt": None,
    }


def test_a_sentence_cannot_close_the_script_element():
    attempt = {"sentence": "我</script><b>", "checking": True}
    html = web.snippet("back", 7, "m", attempt)
    assert html.count("</script>") == 1
    assert mounted_state(html)["attempt"]["sentence"] == "我</script><b>"


def test_show_js_passes_the_attempt():
    js = web.show_js({"sentence": "句子", "checking": False})
    assert js == 'window.WriteGrade && WriteGrade.show({"sentence": "句子", "checking": false});'
