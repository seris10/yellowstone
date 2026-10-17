"""Tests for tools/check_ai_tells.py (synthetic/offline only)."""

import json
import pytest

from tools import check_ai_tells as cat

EM = chr(0x2014)
EN = chr(0x2013)


def ids(findings):
    return {f.pattern for f in findings}


def run(path, text, **kwargs):
    return cat.check_text(path, text, library=LIBRARY, **kwargs)


LIBRARY, LOAD_ERRORS = cat.load_library()


def test_library_loads_clean():
    assert LOAD_ERRORS == []
    assert len(LIBRARY) >= 30


def test_library_examples_pass():
    assert cat.self_test(LIBRARY) == []


def test_pattern_ids_are_unique():
    names = [p.id for p in LIBRARY]
    assert len(names) == len(set(names))


def test_every_pattern_names_a_fix_and_a_catalog_source():
    for pattern in LIBRARY:
        assert pattern.fix and pattern.message
        assert pattern.catalog, pattern.id


def test_dash_characters_flagged_in_headings_and_prose():
    found = run("a.md", f"# Plan {EM} overview\n\nOpen pages 4{EN}9 now.\n")
    assert [f.pattern for f in found].count("em-dash") == 2
    assert "em-dash" not in ids(run("a.md", "# Plan, overview\n\nOpen pages 4-9 now.\n"))


def test_split_headings_forms_and_exemptions():
    text = "\n".join(["# Fall - Four Moves", "# Winter (Read This)", "# Step 6: Wait for Approval",
                      "# Spring, with a plan", "# Summer"])
    found = [f for f in run("a.md", text) if f.pattern == "split-hook-heading"]
    forms = {f.quote: f.message for f in found}
    assert "Fall - Four Moves" in forms and "dash form" in forms["Fall - Four Moves"]
    assert "Winter (Read This)" in forms and "parentheses form" in forms["Winter (Read This)"]
    assert "Spring, with a plan" in forms
    assert "Step 6: Wait for Approval" not in forms and "Summer" not in forms
    assert any("headings use it" in f.message for f in found)


def test_severity_split_between_edits_and_checks():
    found = run("a.md", "Recommend path 1 for round 1. It works either way.\n")
    by_id = {f.pattern: f.severity for f in found}
    assert by_id["self-recommendation"] == "edit"
    assert by_id["either-way"] == "review"


def test_baseline_text_is_not_reported_again():
    before = "<p>Yes. The important distinction is that data differs from methods.</p>"
    after = before + "<p>I'd start with the audit and keep going.</p>"
    found = run("a.html", after, baseline=before)
    assert ids(found) == {"first-person"}


def test_short_quote_in_unchanged_paragraph_stays_suppressed():
    before = "<p>Yes. The important distinction is that data differs from methods.</p>"
    found = run("a.html", "<div>" + before + "</div>", baseline=before)
    assert found == []


def test_exempt_callback_drops_matching_sentences():
    text = "I'd start with the audit and keep going."
    assert run("a.md", text)
    assert run("a.md", text, exempt=lambda quote: quote.startswith("i'd start")) == []


def test_html_reads_visible_text_and_meta_copy():
    page = ("<html><head><meta name='description' content='I wrote this page for you.'>"
            "<script>var s = 'I am code';</script><style>p{}</style></head>"
            "<body><h2>Dates</h2><p>Open in October.</p></body></html>")
    found = run("a.html", page)
    assert [f.pattern for f in found] == ["first-person"]
    assert found[0].line == 1


def test_html_line_numbers_follow_the_source():
    page = "<html>\n<body>\n<p>Fine sentence here.</p>\n<p>We list it. I'd start now.</p>\n</body></html>"
    assert [f.line for f in run("a.html", page) if f.pattern == "first-person"] == [4]


def test_markdown_fenced_code_is_skipped():
    text = "```\nI'd start now. NEVER stop.\n```\n\nPlain sentence about dates.\n"
    assert run("a.md", text) == []


def test_density_reports_once_for_repeated_markers():
    text = "Recommend path 1.\n\nRecommend leaving it.\n\nRecommend deleting it.\n"
    found = [f for f in run("a.md", text) if f.pattern == "recommend-density"]
    assert len(found) == 1 and "3 instances" in found[0].message


def test_machine_path_and_contorted_literal_in_code():
    # ai-tells: ignore contorted-literal machine-path
    code = "BANNED = chr(67) + 'x'\nROOT = '/Users/someone/project'\n"
    assert {"contorted-literal", "machine-path"} <= ids(run("tool.py", code))


def test_ignore_marker_silences_named_patterns_on_its_line_and_the_next():
    # ai-tells: ignore machine-path
    line = "ROOT = '/Users/someone/project'"
    assert "machine-path" in ids(run("tool.py", line + "\n"))
    assert run("tool.py", line + "  # ai-tells: ignore machine-path\n") == []
    assert run("tool.py", "# ai-tells: ignore\n" + line + "\n") == []
    assert "machine-path" in ids(run("tool.py", line + "  # ai-tells: ignore em-dash\n"))


def test_specific_libraries_apply_only_under_their_paths(tmp_path):
    # Role-scoped libraries are operator-local; a synthetic scope tests the mechanism.
    scoped = tmp_path / "scoped.json"
    scoped.write_text(json.dumps({
        "library": "scoped",
        "scope": "specific",
        "applies_when": {"path_contains": ["scope-x"], "extensions": [".md"]},
        "patterns": [{
            "id": "status-slash",
            "catalog": "test fixture",
            "applies": ["raw"],
            "pattern": r"\*\*[A-Za-z-]+\*\* / \*\*[A-Za-z-]+\*\*",
            "message": "Two status codes on one row",
            "fix": "Pick one status.",
            "examples": {"hit": ["**V-add** / **V** note."], "clean": ["**V-add** note."]},
        }],
    }), encoding="utf-8")
    library, errors = cat.load_library(tmp_path)
    assert errors == []
    row = "**V-add** / **V** note."
    assert "status-slash" in ids(cat.check_text("scope-x/audit.md", row, library=library))
    assert "status-slash" not in ids(cat.check_text("other/audit.md", row, library=library))
    text = "Start here for your goal."
    assert "reader-address" in ids(run("yellowstone/doc.md", text))
    assert "reader-address" not in ids(run("other/doc.md", text))


def test_house_style_findings_come_through_for_comments():
    code = "def f(x):\n    # we clamp the value, never silently\n    return x\n"
    found = ids(run("yellowstone/mod.py", code))
    assert {"house-first_person", "house-hypothetical"} <= found


def test_house_comment_length_is_a_review_finding():
    found = run("yellowstone/mod.py", "# " + "x" * 101 + "\n")
    assert len(found) == 1
    assert found[0].pattern == "house-comment_length"
    assert found[0].severity == "review"
    assert found[0].message == "comment has 101 characters (max 100)"
    assert "100 characters" in found[0].fix


@pytest.mark.parametrize("name", ["AGENTS.md", "CLAUDE.md", "SKILL.md"])
def test_instruction_files_keep_directives_and_other_prose_checks(name):
    text = "# Analysis store (SQLite)\n\nDo not invent distributions.\n"
    assert run("yellowstone/" + name, text) == []
    assert {"split-hook-heading", "imperative-to-self"} <= ids(run("yellowstone/README.md", text))
    assert "first-person" in ids(run("yellowstone/" + name, "I'd start with the guide.\n"))
    assert "em-dash" in ids(run("yellowstone/" + name, "# Data " + EM + " input\n"))


def test_render_lists_edits_before_checks():
    findings = run("a.md", "Recommend path 1. It works either way.\n")
    report = cat.render(findings, "a.md")
    assert report.index("Required edits") < report.index("Check these")
    assert "1 required edit(s), 1 to check" in report


def test_new_library_file_is_picked_up(tmp_path):
    (tmp_path / "extra.json").write_text(json.dumps({
        "library": "extra", "scope": "specific", "patterns": [{
            "id": "banned-word", "applies": ["prose"], "pattern": "\\bsynergy\\b", "flags": "i",
            "message": "Buzzword", "fix": "Name the thing.", "examples": {"hit": ["Pure synergy."]}}]}))
    patterns, errors = cat.load_library(tmp_path)
    assert errors == [] and [p.id for p in patterns] == ["banned-word"]
    assert ids(cat.check_text("a.md", "We use synergy here.", library=patterns)) == {"banned-word"}
    assert cat.self_test(patterns) == []


def test_bad_library_entries_are_reported_not_fatal(tmp_path):
    (tmp_path / "bad.json").write_text(json.dumps({"library": "bad", "patterns": [
        {"id": "broken", "pattern": "(unclosed", "message": "m", "fix": "f"},
        {"id": "fine", "pattern": "x", "message": "m", "fix": "f", "examples": {"hit": ["x"]}}]}))
    patterns, errors = cat.load_library(tmp_path)
    assert [p.id for p in patterns] == ["fine"]
    assert len(errors) == 1 and "broken" in errors[0]


def test_missing_library_folder_is_reported(tmp_path):
    patterns, errors = cat.load_library(tmp_path / "absent")
    assert patterns == [] and errors


def test_cli_exit_codes(tmp_path, capsys):
    page = tmp_path / "page.md"
    page.write_text("Recommend path 1 for round 1.\n")
    assert cat.main([str(page)]) == 1
    assert "[self-recommendation]" in capsys.readouterr().out
    assert cat.main([str(page), "--report-only"]) == 0
    page.write_text("Use path 1 for round 1.\n")
    assert cat.main([str(page)]) == 0
    assert cat.main(["--self-test"]) == 0


@pytest.mark.parametrize("mode", [[], ["--self-test"], ["--list-patterns"], ["--report-only"]])
@pytest.mark.parametrize("state", ["missing", "empty", "malformed", "partial"])
def test_cli_refuses_invalid_libraries(tmp_path, capsys, mode, state):
    page = tmp_path / "page.md"
    page.write_text("Plain text.\n")
    library = tmp_path / "patterns"
    if state != "missing":
        library.mkdir()
    if state == "malformed":
        (library / "broken.json").write_text("{")
    if state == "partial":
        (library / "partial.json").write_text(json.dumps({"patterns": [
            {"id": "fine", "pattern": "x", "message": "m", "fix": "f"},
            {"id": "broken", "pattern": "(", "message": "m", "fix": "f"}]}))
    assert cat.main([str(page), "--library", str(library), *mode]) == 2
    assert "library error:" in capsys.readouterr().err
