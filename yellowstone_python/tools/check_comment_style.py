"""Check comments and docstrings against the Agents comment rules.

Covers Python, GDScript and Godot shaders; reports only.
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
import tokenize
from dataclasses import asdict, dataclass
from pathlib import Path

SUFFIXES = (".py", ".gd", ".gdshader")
ACRONYMS = {
    "USGS", "NWIS", "SNOTEL", "NAIP", "HRRR", "RTMA", "NOAA", "NASA", "NRCS", "AWDB", "JSON", "HTTP",
    "HTTPS", "UTC", "DEM", "SWE", "UILT", "CTMAX", "PNG", "JPEG", "API", "URL", "CLI", "MODFLOW", "NETCDF",
    "WGS84", "NAVD88", "UTM", "GDAL", "BUILD", "CHECKS", "EPT", "TOA", "PAR", "LIDAR", "LAZ", "GLB",
    "GLTF", "SRGB", "HDR", "FIPY", "SALIB", "BMI", "PHREEQC", "SNODAS", "SPOTPY", "MOFFAT", "RMSE",
    "NSE", "KGE", "AIC", "BIC", "CFL", "ODE", "PDE", "RK45", "IVP", "NULL", "TRUE", "FALSE", "NONE",
    "TODO", "NOTE", "WARNING", "UUID", "SHA256", "ASCII", "UTF8", "GPU", "CPU", "FPS", "HUD", "FSM",
    "MESH", "TSCN", "TRES", "IUCN", "NPS", "YNP", "USFWS", "NDEP", "WTEQ", "PRCP", "SNWD", "TAVG", "TMAX",
    "TMIN", "OPEN", "METEO",
}
BRITISH = {
    "colour": "color", "colours": "colors", "behaviour": "behavior", "metre": "meter", "metres": "meters",
    "vapour": "vapor", "centre": "center", "centres": "centers", "analyse": "analyze", "organise": "organize",
    "modelling": "modeling", "modelled": "modeled", "labelled": "labeled", "labelling": "labeling",
    "favour": "favor", "neighbour": "neighbor", "neighbours": "neighbors", "grey": "gray", "licence": "license",
    "defence": "defense", "programme": "program", "litre": "liter", "litres": "liters", "travelling": "traveling",
    "normalise": "normalize", "normalised": "normalized", "initialise": "initialize", "parametrise": "parametrize",
}
RULES = [
    ("dash", re.compile("[" + chr(0x2013) + chr(0x2014) + "]"), "em or en dash"),
    ("first_person", re.compile(r"\b(?:I(?![/\w])|we|We|our|Our|my|My|us)\b"), "first person"),
    ("reader", re.compile(r"\b(?:you|You|your|Your|yours)\b"), "addresses the reader"),
    ("contrast", re.compile(r",\s+not\s+\w|\brather than\b|\binstead of\b"), "X, not Y contrast"),
    ("hypothetical", re.compile(r"\bnever silently\b|\bsilently\b|\bcannot drift\b|\bso that nothing\b", re.I),
     "hypothetical-failure narrative"),
    ("temporal", re.compile(r"\b(?:legacy|now|used to|audit fix|new work|previously|no longer|currently|"
                            r"anymore|for now|recently|old version)\b", re.I), "temporal reference"),
    ("every", re.compile(r"\bEvery\b"), "Every comprehensiveness claim"),
]
CAPS = re.compile(r"\b[A-Z][A-Z]{3,}\b")
WORD = re.compile(r"[A-Za-z]+")


@dataclass
class Finding:
    file: str
    line: int
    rule: str
    detail: str
    text: str


def check_text(text: str) -> list[tuple[str, str]]:
    hits = []
    for rule, pattern, detail in RULES:
        if pattern.search(text):
            hits.append((rule, detail))
    caps = [w for w in CAPS.findall(text) if w not in ACRONYMS and not any(ch.isdigit() for ch in w)]
    if caps:
        hits.append(("caps", "ALL-CAPS emphasis: " + ", ".join(sorted(set(caps))[:3])))
    british = sorted({w.lower() for w in WORD.findall(text) if w.lower() in BRITISH})
    if british:
        hits.append(("spelling", "British spelling: " + ", ".join(f"{w}->{BRITISH[w]}" for w in british)))
    return hits


def python_comments(source: str) -> list[tuple[int, str, str]]:
    """Return (line, kind, text) for each comment and docstring in Python source."""
    out: list[tuple[int, str, str]] = []
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return out
    previous = tokenize.NEWLINE
    for tok in tokens:
        if tok.type == tokenize.COMMENT:
            text = tok.string.lstrip("#").strip()
            if not text.startswith(("!", "type:", "noqa")):
                kind = "comment" if tok.line.strip().startswith("#") else "inline"
                out.append((tok.start[0], kind, text))
        elif tok.type == tokenize.STRING and previous in (tokenize.NEWLINE, tokenize.INDENT, tokenize.NL,
                                                          tokenize.DEDENT, tokenize.ENCODING):
            body = tok.string
            if body[:3] in ('"""', "'''") or body[1:4] in ('"""', "'''"):
                out.append((tok.start[0], "docstring", body))
        if tok.type not in (tokenize.COMMENT, tokenize.NL):
            previous = tok.type
    return out


def godot_comments(source: str, shader: bool) -> list[tuple[int, str, str]]:
    out = []
    marker = "//" if shader else "#"
    for number, line in enumerate(source.splitlines(), start=1):
        index = line.find(marker)
        if index < 0 or (not shader and line.strip().startswith("#!")):
            continue
        if line[:index].count('"') % 2:
            continue
        text = line[index:].lstrip("#/").strip()
        if text:
            out.append((number, "comment" if line.strip().startswith(marker) else "inline", text))
    return out


def docstring_length(body: str) -> int:
    inner = body.strip().lstrip("rRbBuU").strip("\"'")
    return len([line for line in inner.strip().splitlines() if line.strip()])


def check_file(path: Path, root: Path) -> list[Finding]:
    try:
        source = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []
    if path.suffix == ".py":
        items = python_comments(source)
    else:
        items = godot_comments(source, shader=path.suffix == ".gdshader")
    rel = str(path.relative_to(root)) if path.is_relative_to(root) else str(path)
    findings = []
    block_start, block_len, last_line = 0, 0, -2
    for line, kind, text in items:
        first = text.strip().strip("\"'").strip().splitlines()
        snippet = first[0][:140] if first else ""
        for rule, detail in check_text(text):
            findings.append(Finding(rel, line, rule, detail, snippet))
        if kind == "docstring" and docstring_length(text) > 2:
            findings.append(Finding(rel, line, "docstring_length",
                                    f"docstring has {docstring_length(text)} lines (max 2)", snippet))
        if kind == "comment":
            if line == last_line + 1:
                block_len += 1
            else:
                if block_len > 1:
                    findings.append(Finding(rel, block_start, "comment_block",
                                            f"{block_len}-line comment block (inline comments are one line)", ""))
                block_start, block_len = line, 1
            last_line = line
    if block_len > 1:
        findings.append(Finding(rel, block_start, "comment_block",
                                f"{block_len}-line comment block (inline comments are one line)", ""))
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="*", type=Path, help="files to check (.py, .gd, .gdshader)")
    parser.add_argument("--list", type=Path, help="file holding one path per line")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--json", action="store_true", help="print findings as JSON")
    parser.add_argument("--summary", action="store_true", help="print counts per rule and file only")
    parser.add_argument("--report-only", action="store_true", help="exit 0 even when findings exist")
    args = parser.parse_args(argv)

    paths = list(args.files)
    if args.list:
        paths += [Path(line.strip()) for line in args.list.read_text(encoding="utf-8").splitlines() if line.strip()]
    files = sorted({p.resolve() for p in paths if p.suffix in SUFFIXES and p.is_file()})
    if not files:
        print("no .py, .gd or .gdshader files given", file=sys.stderr)
        return 2
    root = args.root.resolve()
    findings = [f for path in files for f in check_file(path, root)]
    if args.json:
        print(json.dumps([asdict(f) for f in findings], indent=1))
    elif args.summary:
        by_rule: dict[str, int] = {}
        by_file: dict[str, int] = {}
        for f in findings:
            by_rule[f.rule] = by_rule.get(f.rule, 0) + 1
            by_file[f.file] = by_file.get(f.file, 0) + 1
        print(f"{len(files)} files, {len(findings)} findings")
        for rule, count in sorted(by_rule.items(), key=lambda kv: -kv[1]):
            print(f"  {rule:18s} {count}")
        for name, count in sorted(by_file.items(), key=lambda kv: -kv[1]):
            print(f"{count:5d}  {name}")
    else:
        for f in findings:
            print(f"{f.file}:{f.line}: [{f.rule}] {f.detail}: {f.text}")
    return 0 if args.report_only or not findings else 1


if __name__ == "__main__":
    sys.exit(main())
