"""Comment and documentation house-style checks."""

from __future__ import annotations

import argparse
import ast
import io
import json
import re
import sys
import tokenize
from dataclasses import asdict, dataclass
from pathlib import Path

SUFFIXES = (".py", ".gd", ".gdshader", ".gdshaderinc", ".md", ".ipynb")
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
EXTRA_RULES = [
    ("process_tag", re.compile(r"\bfixes-\d|\b(?:item|finding) \d+\b|\bM(?:0\d|1[0-2])[a-z]?\b|SHARED_WORLD_CONTRACT|\b[Pp]hase \d|\bWP-[A-Z]\d|\bB[1-4]\b"), "internal process reference"),
    ("history", re.compile(r"\b(?:kept for|retained for|replaces|no longer|now (?:takes|returns|carries|accepts|reports)|yet|at their own pace)\b", re.I), "history narration"),
    ("session_narration", re.compile(r"in-session|in session|WebSearch|verified via", re.I), "session narration"),
    ("vocabulary", re.compile(r"\bfail(?:s|ed)? loudly|single source of truth|comprehensive|honestly|stated plainly|\(not hidden\)|This (?:is not|module|function)", re.I), "review vocabulary"),
    ("non_ascii", re.compile(r"[^\x00-\x7f]"), "non-ASCII text"),
    ("citation_format", re.compile(r"(?<![\w(])\b[A-Z][a-z]+ (?:et al\.? )?(?:19|20)\d\d\b(?!\))"), "citation requires parentheses around the year"),
    ("dated_prose", re.compile(r"\b(?:verified|checked|frozen|refetched)(?: live)? 20\d\d-\d\d-\d\d\b", re.I), "operational date in prose"),
]
WARN_RULES = {"vocabulary", "citation_format"}
PROVENANCE_KEYS = {"status", "note", "reason", "source", "sources", "basis", "author_note", "component"}
MARKDOWN_RULES = {"dash", "non_ascii", "vocabulary", "process_tag", "dated_prose"}


CAPS = re.compile(r"\b[A-Z][A-Z]{3,}\b")
WORD = re.compile(r"[A-Za-z]+")


@dataclass
class Finding:
    file: str
    line: int
    rule: str
    detail: str
    text: str
    severity: str = "error"


def check_text(text: str) -> list[tuple[str, str]]:
    hits = []
    for rule, pattern, detail in RULES + EXTRA_RULES:
        if pattern.search(text):
            hits.append((rule, detail))
    caps_text = re.sub(r"(?:doi:)?10\.\d{4,9}/[^\s]+", "", text, flags=re.I)
    caps = [w for w in CAPS.findall(caps_text) if w not in ACRONYMS and not any(ch.isdigit() for ch in w)]
    if caps:
        hits.append(("caps", "ALL-CAPS emphasis: " + ", ".join(sorted(set(caps))[:3])))
    british = sorted({w.lower() for w in WORD.findall(text) if w.lower() in BRITISH})
    if british:
        hits.append(("spelling", "British spelling: " + ", ".join(f"{w}->{BRITISH[w]}" for w in british)))
    return hits


def python_comments(source: str) -> list[tuple[int, str, str]]:
    """Return comments, docstrings, and selected emitted strings from Python source."""
    out: list[tuple[int, str, str]] = []
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
        tree = ast.parse(source)
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return out
    for tok in tokens:
        if tok.type == tokenize.COMMENT:
            text = tok.string.lstrip("#").strip()
            if not text.startswith(("!", "type:", "noqa")):
                kind = "comment" if tok.line.strip().startswith("#") else "inline"
                out.append((tok.start[0], kind, text))
    selected: dict[int, tuple[ast.AST, str]] = {}

    def strings(node: ast.AST, kind: str) -> None:
        for child in ast.walk(node):
            if isinstance(child, ast.Constant) and isinstance(child.value, str):
                selected[id(child)] = (child, kind)

    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                value = body[0].value
                if isinstance(value.value, str):
                    selected[id(value)] = (value, "docstring")
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
                out.append((node.lineno, "test_name", node.name.replace("fixes_", "fixes-").replace("_", " ")))
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if isinstance(key, ast.Constant) and key.value in PROVENANCE_KEYS:
                    strings(value, "emitted")
        if isinstance(node, ast.keyword) and node.arg == "help":
            strings(node.value, "help")
        if isinstance(node, ast.Raise) and node.exc:
            strings(node.exc, "emitted")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print":
            for arg in node.args:
                strings(arg, "console")
    for node, kind in selected.values():
        out.append((node.lineno, kind, node.value))
    return sorted(out)


def markdown_prose(source: str) -> list[tuple[int, str, str]]:
    """Return Markdown prose lines outside fenced code and inline code spans."""
    out = []
    fence = None
    for number, line in enumerate(source.splitlines(), 1):
        marker = re.match(r"^\s*(`{3,}|~{3,})", line)
        if marker:
            if fence is None:
                fence = marker.group(1)[0]
            elif marker.group(1)[0] == fence:
                fence = None
            continue
        if fence is None:
            prose = re.sub(r"`+[^`]*`+", "", line)
            out.append((number, "markdown", prose))
    return out


def notebook_prose(source: str) -> list[tuple[int, str, str]]:
    """Return notebook Markdown cells with their JSON source line locations."""
    try:
        notebook = json.loads(source)
    except (ValueError, TypeError):
        return []
    out = []
    cursor = 0
    for cell in notebook.get("cells", []):
        if cell.get("cell_type") != "markdown":
            continue
        cell_source = cell.get("source", [])
        text = "".join(cell_source) if isinstance(cell_source, list) else cell_source
        if not isinstance(text, str):
            continue
        needle = json.dumps(text.splitlines(keepends=True)[0] if text else "")[1:-1]
        offset = source.find(needle, cursor)
        base = source.count("\n", 0, max(0, offset)) + 1
        cursor = max(cursor, offset + len(needle))
        out.extend((base + line - 1, kind, value) for line, kind, value in markdown_prose(text))
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
    inner = body.strip()
    return len([line for line in inner.strip().splitlines() if line.strip()])


def check_file(path: Path, root: Path) -> list[Finding]:
    try:
        source = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []
    if path.suffix == ".py":
        items = python_comments(source)
    elif path.suffix == ".md":
        items = markdown_prose(source)
    elif path.suffix == ".ipynb":
        items = notebook_prose(source)
    else:
        items = godot_comments(source, shader=path.suffix in (".gdshader", ".gdshaderinc"))
    rel = str(path.relative_to(root)) if path.is_relative_to(root) else str(path)
    findings = []
    block_start, block_len, last_line = 0, 0, -2
    for line, kind, text in items:
        first = text.strip().strip("\"'").strip().splitlines()
        snippet = first[0][:140] if first else ""
        hits = check_text(text)
        if kind == "markdown":
            hits = [(rule, detail) for rule, detail in hits if rule in MARKDOWN_RULES]
        elif kind == "console":
            hits = [(rule, detail) for rule, detail in hits if rule == "non_ascii"]
        elif kind == "test_name":
            hits = [(rule, detail) for rule, detail in hits if rule == "process_tag"]
        elif kind in ("emitted", "help"):
            hits = [(rule, detail) for rule, detail in hits if rule in
                    {"process_tag", "history", "session_narration", "non_ascii", "vocabulary", "citation_format"}]
        for rule, detail in hits:
            findings.append(Finding(rel, line, rule, detail, snippet,
                                    "warning" if rule in WARN_RULES else "error"))
        if kind == "docstring" and (docstring_length(text) > 2 or
                                      any(len(part) > 100 or part.count(";") >= 2
                                          for part in text.splitlines())):
            findings.append(Finding(rel, line, "docstring_shape",
                                    "docstring exceeds line, width, or clause limit", snippet))
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



def style_paths(project_root: Path) -> list[Path]:
    """Return source and public documentation paths covered by the style gate."""
    paths = []
    for folder in ("yellowstone_python", "tools", "tests", "notebooks"):
        paths.extend(path for path in (project_root / folder).rglob("*")
                     if path.is_file() and path.suffix in SUFFIXES)
    paths.extend(path for path in (project_root / "README.md", project_root / "AGENTS.md",
                                   project_root.parent / "README.md") if path.is_file())
    for name in ("yellowstone_midway", "yellowstone_atmosphere"):
        folder = project_root.parent / name
        for subfolder in ("scripts", "shaders", "tools"):
            paths.extend(path for path in (folder / subfolder).rglob("*")
                         if path.is_file() and path.suffix in SUFFIXES)
        if (folder / "README.md").is_file():
            paths.append(folder / "README.md")
    return sorted(set(paths))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="*", type=Path, help="source, Markdown, and notebook files to check")
    parser.add_argument("--list", type=Path, help="file holding one path per line")
    parser.add_argument("--tree", type=Path, help="Python project root for the whole-tree gate")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--json", action="store_true", help="print findings as JSON")
    parser.add_argument("--summary", action="store_true", help="print counts per rule and file only")
    parser.add_argument("--report-only", action="store_true", help="exit 0 even when findings exist")
    args = parser.parse_args(argv)

    paths = list(args.files)
    if args.tree:
        paths += style_paths(args.tree.resolve())
    if args.list:
        paths += [Path(line.strip()) for line in args.list.read_text(encoding="utf-8").splitlines() if line.strip()]
    files = sorted({p.resolve() for p in paths if p.suffix in SUFFIXES and p.is_file()})
    if not files:
        print("no supported source or documentation files given", file=sys.stderr)
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
    return 0 if args.report_only or not any(f.severity == "error" for f in findings) else 1


if __name__ == "__main__":
    raise SystemExit(main())
