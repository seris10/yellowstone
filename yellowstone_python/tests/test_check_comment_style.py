"""Tests for tools/check_comment_style.py (synthetic/offline only)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

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
