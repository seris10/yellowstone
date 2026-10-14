"""Tests for tools/check_comment_style.py (synthetic/offline only)."""

import sys
from pathlib import Path

from tools.check_comment_style import check_file, check_text, main

VAPOR_UK = "vapo" + "ur"
COLOR_UK = "colo" + "ur"


def rules(text):
    return {rule for rule, _ in check_text(text)}


def test_clean_comment_has_no_findings():
    assert rules("Newton exchange is a lumped heat-loss term.") == set()


def test_each_rule_fires():
    assert "dash" in rules("heat loss " + chr(0x2014) + " lumped")
    assert "dash" not in rules("heat loss, lumped")
    assert "first_person" in rules("we clamp the value")
    assert "reader" in rules("set this before you run")
    assert "contrast" in rules("a proxy, not a measurement")
    assert "hypothetical" in rules("never silently lose time")
    assert "temporal" in rules("legacy path kept")
    assert "every" in rules("Every cell is checked")
    assert "caps" in rules("this is REQUIRED here")
    assert "spelling" in rules(f"water {VAPOR_UK} pressure")


def test_acronyms_and_io_are_not_flagged():
    assert rules("USGS NWIS discharge in m3/s at UTC") == set()
    assert "first_person" not in rules("file I/O is atomic")


def test_python_docstring_length_and_comment_block(tmp_path):
    source = tmp_path / "mod.py"
    source.write_text(
        '"""One line.\n\nTwo.\n\nThree."""\n'
        "x = 1  # one line\n"
        "# first\n"
        "# second\n"
        "y = 2\n",
        encoding="utf-8",
    )
    found = {(f.rule, f.line) for f in check_file(source, tmp_path)}
    assert ("docstring_length", 1) in found
    assert ("comment_block", 7) in found


def test_string_literals_are_not_comments(tmp_path):
    source = tmp_path / "mod.py"
    source.write_text('label = "we, not you"\n', encoding="utf-8")
    assert check_file(source, tmp_path) == []


def test_gdscript_and_shader_comments(tmp_path):
    gd = tmp_path / "a.gd"
    gd.write_text('var s = "#not a comment"\n# we update each frame\n', encoding="utf-8")
    shader = tmp_path / "b.gdshader"
    shader.write_text(f"float x; // {COLOR_UK} ramp\n", encoding="utf-8")
    assert {f.rule for f in check_file(gd, tmp_path)} == {"first_person"}
    assert {f.rule for f in check_file(shader, tmp_path)} == {"spelling"}


def test_cli_exit_codes(tmp_path):
    clean = tmp_path / "clean.py"
    clean.write_text("x = 1  # one line\n", encoding="utf-8")
    dirty = tmp_path / "dirty.py"
    dirty.write_text("x = 1  # we clamp\n", encoding="utf-8")
    assert main([str(clean), "--root", str(tmp_path)]) == 0
    assert main([str(dirty), "--root", str(tmp_path)]) == 1
    assert main([str(dirty), "--root", str(tmp_path), "--report-only"]) == 0
    assert main(["--root", str(tmp_path)]) == 2


def test_extended_rules_true_and_false_positives():
    cases = [
        ("process_tag", "Stage C per fixes-15 section 4C.", "Fit lateral discharge and temperature."),
        ("process_tag", "M01b transport and M05b food web", "Transport models Mg and Mn solutes."),
        ("history", "kept for ecosystem parity", "Transport preserves ecosystem parity."),
        ("session_narration", "original paper not opened in-session", "Davis (1975); literature values."),
        ("vocabulary", "single source of truth", "The shared source defines the threshold."),
        ("non_ascii", "delta " + chr(0x394), "delta temperature in C"),
        ("citation_format", "Davis 1975 minimum oxygen", "Davis (1975) minimum oxygen"),
        ("dated_prose", "verified live 2026-10-10", "Observation window starts 2026-10-10."),
    ]
    for rule, positive, negative in cases:
        assert rule in rules(positive)
        assert rule not in rules(negative)
    assert "history" not in rules("datetime.now() returns a timestamp")


def test_ast_scopes_provenance_help_exception_and_names(tmp_path):
    source = tmp_path / "scopes.py"
    source.write_text(
        'payload = {"source": "verified via WebSearch"}\n'
        'parser.add_argument("--x", help="fixes-15")\n'
        'def test_fixes_15():\n'
        '    raise ValueError("retained for parity")\n'
        'fixture = "verified via WebSearch"\n',
        encoding="utf-8",
    )
    found = {(f.rule, f.line) for f in check_file(source, tmp_path)}
    assert ("session_narration", 1) in found
    assert ("process_tag", 2) in found
    assert ("process_tag", 3) in found
    assert ("history", 4) in found
    assert not any(line == 5 for _, line in found)


def test_all_docstrings_have_shape_checked(tmp_path):
    source = tmp_path / "shape.py"
    source.write_text(
        'def f():\n    """Return the field.\n    Units are C.\n    The third line exceeds the limit."""\n'
        'class C:\n    """' + "x" * 101 + '"""\n',
        encoding="utf-8",
    )
    found = {f.line for f in check_file(source, tmp_path) if f.rule == "docstring_shape"}
    assert found == {2, 6}


def test_markdown_fences_and_notebook_cells(tmp_path):
    import json
    prose = "# Model\n\nheat loss " + chr(0x2014) + " lumped\n```python\n# fixes-15\n```\n"
    markdown = tmp_path / "README.md"
    markdown.write_text(prose, encoding="utf-8")
    notebook = tmp_path / "example.ipynb"
    notebook.write_text(json.dumps({"cells": [{"cell_type": "markdown", "source": [prose]}]}))
    for path in (markdown, notebook):
        found = {f.rule for f in check_file(path, tmp_path)}
        assert "dash" in found and "non_ascii" in found
        assert "process_tag" not in found


def test_review_vocabulary_is_warning(tmp_path):
    source = tmp_path / "review.py"
    source.write_text("# comprehensive\n")
    assert check_file(source, tmp_path)[0].severity == "warning"
    assert main([str(source), "--root", str(tmp_path)]) == 0


def test_doi_acronyms_preserve_identifier_case():
    assert "caps" not in rules("Stull (2011), doi:10.1175/JAMC-D-11-0143.1")
    assert "caps" in rules("This value is REQUIRED")
