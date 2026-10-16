"""AI-tell checks over prose and comments, driven by a JSON pattern library."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from html.parser import HTMLParser
from pathlib import Path

try:
    from tools.check_comment_style import SUFFIXES as HOUSE_SUFFIXES
    from tools.check_comment_style import check_file as house_check_file
    from tools.check_comment_style import godot_comments, python_comments
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from tools.check_comment_style import SUFFIXES as HOUSE_SUFFIXES
    from tools.check_comment_style import check_file as house_check_file
    from tools.check_comment_style import godot_comments, python_comments

LIBRARY_ENV = "AI_TELLS_LIBRARY"
DEFAULT_LIBRARY = Path(__file__).resolve().parents[2] / "yellowstone_python_spec" / "ai-tells" / "library"
SEGMENT_KINDS = ("heading", "prose", "comment", "raw")
SEVERITIES = ("edit", "review")
KINDS = ("regex", "builtin", "density")
REGEX_FLAGS = {"i": re.I, "m": re.M, "s": re.S}
DASH_CLASS = "[" + chr(0x2013) + chr(0x2014) + "]"
DASH_RE = re.compile(DASH_CLASS)
IGNORE_MARKER = re.compile(r"ai-tells:\s*ignore(?:[ \t]+([\w,\- \t]+))?", re.I)
SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(\[])")
QUOTE_LIMIT = 160
MIN_BASELINE_QUOTE = 20
HOUSE_FIX = {
    "dash": "Use ASCII punctuation; split the sentence or use a colon, comma, or period.",
    "first_person": "Describe the code or data directly; drop the author's voice.",
    "reader": "Describe the code or data directly; drop the address to the reader.",
    "contrast": "State what the code does; drop the X-not-Y contrast.",
    "hypothetical": "Drop the failure narrative; state the operation.",
    "temporal": "Describe the present behavior; drop the history or timing word.",
    "every": "Name the scope; drop the comprehensiveness claim.",
    "process_tag": "Remove the internal process label.",
    "history": "Describe the present behavior; drop the history narration.",
    "session_narration": "Drop the session narration; cite the source or value class.",
    "vocabulary": "Use plain technical wording.",
    "non_ascii": "Replace with ASCII (m3/s, C, ->, plain hyphen).",
    "citation_format": "Write the citation as Author (YYYY).",
    "dated_prose": "Drop the operational date; keep dates that are data values.",
    "caps": "Use regular case.",
    "spelling": "Use the American spelling.",
    "docstring_shape": "Reduce the docstring to one imperative line under 100 characters.",
    "docstring_length": "Reduce the docstring to at most two lines.",
    "comment_block": "Reduce the comment block to one line; move detail to the README.",
}


@dataclass
class Segment:
    line: int
    kind: str
    text: str


@dataclass
class Finding:
    line: int
    pattern: str
    severity: str
    message: str
    fix: str
    quote: str = ""
    library: str = ""
    catalog: str = ""
    context: str = ""


@dataclass
class Pattern:
    id: str
    library: str
    scope: str
    kind: str
    applies: list[str]
    severity: str
    message: str
    fix: str
    catalog: str = ""
    regex: re.Pattern | None = None
    unit: str = "sentence"
    params: dict = field(default_factory=dict)
    extensions: list[str] = field(default_factory=list)
    examples: dict = field(default_factory=dict)
    where: dict = field(default_factory=dict)


@dataclass
class Context:
    path: str
    text: str
    segments: list[Segment]
    baseline: str | None = None


def norm(text: str) -> str:
    """Return case-folded text with whitespace collapsed."""
    return re.sub(r"\s+", " ", text.replace(chr(0x2019), "'")).strip().casefold()


def sentences(text: str) -> list[str]:
    """Split a paragraph into sentences."""
    return [part.strip() for part in SENTENCE_BREAK.split(text) if part.strip()]


def library_dir(override: Path | str | None = None) -> Path:
    """Return the pattern library folder: argument, then environment, then the spec default."""
    if override:
        return Path(override)
    env = os.environ.get(LIBRARY_ENV)
    return Path(env) if env else DEFAULT_LIBRARY


def compile_regex(source: str, flags: str) -> re.Pattern:
    """Compile a library regex with the letter flags used in the JSON files."""
    bits = 0
    for letter in flags:
        bits |= REGEX_FLAGS[letter]
    return re.compile(source, bits)


def load_library(root: Path | str | None = None) -> tuple[list[Pattern], list[str]]:
    """Load every pattern file under the library folder; return patterns and load errors."""
    folder = library_dir(root)
    patterns: list[Pattern] = []
    errors: list[str] = []
    if not folder.is_dir():
        return patterns, [f"library folder missing: {folder.name}"]
    for path in sorted(folder.glob("*.json")):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            errors.append(f"{path.name}: unreadable ({exc})")
            continue
        name = doc.get("library", path.stem)
        scope = doc.get("scope", "general")
        when = doc.get("applies_when") or {}
        for entry in doc.get("patterns", []):
            try:
                pattern = build_pattern(entry, name, scope, when)
            except (KeyError, re.error, ValueError, TypeError) as exc:
                errors.append(f"{path.name}: {entry.get('id', '?')}: {type(exc).__name__}: {exc}")
                continue
            patterns.append(pattern)
    if not patterns:
        errors.append("library contains no patterns")
    return patterns, errors


def build_pattern(entry: dict, library: str, scope: str, when: dict) -> Pattern:
    """Validate one library entry and compile its regex."""
    kind = entry.get("kind", "regex")
    if kind not in KINDS:
        raise ValueError(f"unknown kind {kind}")
    severity = entry.get("severity", "edit")
    if severity not in SEVERITIES:
        raise ValueError(f"unknown severity {severity}")
    applies = entry.get("applies", ["prose"])
    if any(item not in SEGMENT_KINDS for item in applies):
        raise ValueError("unknown applies value")
    regex = None
    if kind in ("regex", "density"):
        regex = compile_regex(entry["pattern"], entry.get("flags", ""))
    elif entry.get("detector") not in DETECTORS:
        raise ValueError(f"unknown detector {entry.get('detector')}")
    return Pattern(
        id=entry["id"], library=library, scope=scope, kind=kind, applies=applies, severity=severity,
        message=entry["message"], fix=entry["fix"], catalog=entry.get("catalog", ""), regex=regex,
        unit=entry.get("unit", "sentence"),
        params={k: v for k, v in entry.items() if k in ("detector", "min")},
        extensions=[e.lower() for e in entry.get("extensions", [])], examples=entry.get("examples", {}),
        where={k: [v.lower() for v in vals] for k, vals in when.items()})


def pattern_in_scope(pattern: Pattern, path: str) -> bool:
    """Return whether the pattern's library and own extension list cover this path."""
    lowered = path.lower()
    suffix = Path(lowered).suffix
    exts = pattern.where.get("extensions")
    if exts and suffix not in exts:
        return False
    if pattern.extensions and suffix not in pattern.extensions:
        return False
    parts = pattern.where.get("path_contains")
    return not parts or any(part in lowered for part in parts)


BLOCK_TAGS = {
    "p", "div", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "br", "tr", "td", "th", "section",
    "article", "header", "footer", "nav", "table", "label", "button", "option", "dt", "dd", "blockquote",
    "figcaption", "summary", "main", "aside", "form", "fieldset", "legend", "title", "caption", "body", "html",
}
HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6", "title", "legend"}
META_COPY = {"description", "og:description", "og:title", "twitter:description", "twitter:title"}


class HtmlText(HTMLParser):
    """Collect visible text blocks with the source line where each begins."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.segments: list[Segment] = []
        self.buffer: list[str] = []
        self.start = 1
        self.kind = "prose"
        self.skip = 0
        self.heading = 0

    def flush(self) -> None:
        text = " ".join("".join(self.buffer).split())
        if text:
            self.segments.append(Segment(self.start, self.kind, text))
        self.buffer = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "template"):
            self.skip += 1
            return
        if tag == "meta":
            attr = dict(attrs)
            key = (attr.get("name") or attr.get("property") or "").lower()
            if key in META_COPY and attr.get("content"):
                self.segments.append(Segment(self.getpos()[0], "prose", attr["content"].strip()))
            return
        if tag in BLOCK_TAGS:
            self.flush()
            if tag in HEADING_TAGS:
                self.heading += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style", "template"):
            self.skip = max(0, self.skip - 1)
            return
        if tag in BLOCK_TAGS:
            self.flush()
            if tag in HEADING_TAGS:
                self.heading = max(0, self.heading - 1)

    def handle_data(self, data):
        if self.skip:
            return
        if not self.buffer:
            self.start = self.getpos()[0]
            self.kind = "heading" if self.heading else "prose"
        self.buffer.append(data)


def html_segments(text: str) -> list[Segment]:
    parser = HtmlText()
    parser.feed(text)
    parser.close()
    parser.flush()
    return parser.segments


def strip_markdown(text: str) -> str:
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"`+[^`]*`+", " ", text)
    return re.sub(r"[*_]{1,3}", "", text).replace("|", " ")


def markdown_segments(text: str) -> list[Segment]:
    """Return headings and merged paragraphs from Markdown or plain text, skipping fenced code."""
    out: list[Segment] = []
    para: list[str] = []
    start = 0
    fence = None

    def flush() -> None:
        if para:
            out.append(Segment(start, "prose", " ".join(para)))
        para.clear()

    for number, line in enumerate(text.splitlines(), 1):
        marker = re.match(r"^\s*(`{3,}|~{3,})", line)
        if marker:
            flush()
            fence = None if fence == marker.group(1)[0] else (fence or marker.group(1)[0])
            continue
        if fence:
            continue
        head = re.match(r"^\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$", line)
        if head:
            flush()
            out.append(Segment(number, "heading", strip_markdown(head.group(1)).strip()))
            continue
        item = re.match(r"^\s*(?:[-*+]|\d+[.)])\s+(.*)$", line)
        if not line.strip() or item:
            flush()
        body = strip_markdown(item.group(1) if item else line).strip()
        if body:
            if not para:
                start = number
            para.append(body)
    flush()
    return out


def js_comments(text: str) -> list[tuple[int, str]]:
    """Return line comments and block comments from JavaScript-like source."""
    out: list[tuple[int, str]] = []
    i, line, quote = 0, 1, ""
    while i < len(text):
        ch = text[i]
        if ch == "\n":
            line += 1
        if quote:
            if ch == "\\":
                i += 1
            elif ch == quote:
                quote = ""
        elif ch in "\"'`":
            quote = ch
        elif text.startswith("//", i):
            end = text.find("\n", i)
            end = len(text) if end < 0 else end
            out.append((line, text[i + 2:end].strip()))
            i = end - 1
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            end = len(text) if end < 0 else end
            out.append((line, " ".join(text[i + 2:end].replace("\n * ", " ").split())))
            line += text.count("\n", i, end)
            i = end + 1
        i += 1
    return [(n, c) for n, c in out if c]


def json_segments(text: str) -> list[Segment]:
    try:
        doc = json.loads(text)
    except ValueError:
        return []
    found: list[str] = []

    def walk(node) -> None:
        if isinstance(node, str):
            if len(node.split()) >= 3:
                found.append(node)
        elif isinstance(node, dict):
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(doc)
    out = []
    for value in found:
        encoded = json.dumps(value[:30])[1:-1]
        at = text.find(encoded)
        out.append(Segment(text.count("\n", 0, max(at, 0)) + 1, "prose", value))
    return out


def extract_segments(path: str, text: str) -> list[Segment]:
    """Return the text blocks of a file that a reader or maintainer sees."""
    suffix = Path(path).suffix.lower()
    if suffix in (".html", ".htm", ".liquid"):
        return html_segments(text)
    if suffix == ".py":
        return [Segment(n, "comment", t) for n, k, t in python_comments(text)
                if k in ("comment", "inline", "docstring")]
    if suffix in (".gd", ".gdshader", ".gdshaderinc"):
        shader = suffix != ".gd"
        return [Segment(n, "comment", t) for n, _, t in godot_comments(text, shader)]
    if suffix in (".js", ".mjs", ".ts", ".jsx", ".tsx", ".css"):
        return [Segment(n, "comment", t) for n, t in js_comments(text)]
    if suffix == ".json":
        return json_segments(text)
    return markdown_segments(text)


def raw_segments(text: str) -> list[Segment]:
    return [Segment(n, "raw", line.strip()) for n, line in enumerate(text.splitlines(), 1) if line.strip()]


def ignored(lines: list[str], finding: Finding) -> bool:
    """Return whether the finding's line or the line above carries an ai-tells ignore marker."""
    for number in (finding.line, finding.line - 1):
        if 1 <= number <= len(lines):
            marker = IGNORE_MARKER.search(lines[number - 1])
            if marker:
                named = re.split(r"[,\s]+", (marker.group(1) or "").strip())
                if not marker.group(1) or finding.pattern in named:
                    return True
    return False


def split_form(text: str) -> tuple[str, str] | None:
    """Return (form, severity) when a heading joins a plain title to an appended half."""
    if re.match(r"^(.{3,}?)\s+(?:-{1,2}|" + DASH_CLASS + r")\s+(.{3,})$", text):
        return "dash", "edit"
    if re.match(r"^[^()]{3,}?\s*\([^()]{2,}\)\s*$", text):
        return "parentheses", "edit"
    colon = re.match(r"^([^:]{3,}):\s+(.{3,})$", text)
    if colon and not re.match(r"^(?:Step|Phase|Week|Day|Part|Month|Question|Q\d*|Note|Example|Option|Tier|"
                              r"\d+[.)]?\s)", colon.group(1)):
        return "colon", "review"
    if re.match(r"^[^,]{3,},\s+(?:with|without|and|not|but|where|so|while|which|because)\b", text):
        return "comma", "review"
    return None


def detect_split_headings(ctx: Context, pattern: Pattern) -> list[Finding]:
    """Flag headings built as a title plus an appended hook, note, or name."""
    heads = [s for s in ctx.segments if s.kind == "heading"]
    hits = [(s, split_form(s.text)) for s in heads]
    hits = [(s, f) for s, f in hits if f]
    note = f" ({len(hits)} of {len(heads)} headings use it)" if len(hits) >= 3 else ""
    return [Finding(s.line, pattern.id, severity, f"{pattern.message}: {form} form{note}", pattern.fix,
                    s.text[:QUOTE_LIMIT], pattern.library, pattern.catalog) for s, (form, severity) in hits]


def detect_house_style(ctx: Context, pattern: Pattern) -> list[Finding]:
    """Run the repository comment-style gate over the text and map its findings."""
    suffix = Path(ctx.path).suffix
    if suffix not in HOUSE_SUFFIXES:
        return []
    with tempfile.TemporaryDirectory() as folder:
        target = Path(folder) / ("subject" + suffix)
        target.write_text(ctx.text, encoding="utf-8")
        found = house_check_file(target, Path(folder))
    return [Finding(f.line, f"house-{f.rule}", "edit" if f.severity == "error" else "review",
                    f"{f.detail}", HOUSE_FIX.get(f.rule, "Rewrite to the AGENTS.md section 2 style."),
                    f.text[:QUOTE_LIMIT], pattern.library, pattern.catalog) for f in found]


def detect_dashes(ctx: Context, pattern: Pattern) -> list[Finding]:
    """Flag em and en dash characters in headings and prose."""
    return [Finding(s.line, pattern.id, pattern.severity, pattern.message, pattern.fix, s.text[:QUOTE_LIMIT],
                    pattern.library, pattern.catalog)
            for s in ctx.segments if s.kind in pattern.applies and DASH_RE.search(s.text)]


DETECTORS = {"split_headings": detect_split_headings, "house_comment_style": detect_house_style,
             "dash_characters": detect_dashes}


def regex_findings(ctx: Context, pattern: Pattern) -> list[Finding]:
    out = []
    for seg in ctx.segments:
        if seg.kind not in pattern.applies:
            continue
        units = [seg.text] if pattern.unit == "segment" or seg.kind in ("heading", "raw") else sentences(seg.text)
        for unit in units:
            if pattern.regex.search(unit):
                out.append(Finding(seg.line, pattern.id, pattern.severity, pattern.message, pattern.fix,
                                   unit[:QUOTE_LIMIT], pattern.library, pattern.catalog, seg.text))
    return out


def density_findings(ctx: Context, pattern: Pattern) -> list[Finding]:
    """Report once when a marker recurs across the document."""
    floor = int(pattern.params.get("min", 3))
    hits = [seg for seg in ctx.segments if seg.kind in pattern.applies and pattern.regex.search(seg.text)]
    total = sum(len(pattern.regex.findall(seg.text)) for seg in hits)
    if total < floor:
        return []
    return [Finding(hits[0].line, pattern.id, pattern.severity, f"{pattern.message}: {total} instances",
                    pattern.fix, hits[0].text[:QUOTE_LIMIT], pattern.library, pattern.catalog)]


def run_pattern(ctx: Context, pattern: Pattern) -> list[Finding]:
    if pattern.kind == "regex":
        return regex_findings(ctx, pattern)
    if pattern.kind == "density":
        return density_findings(ctx, pattern)
    return DETECTORS[pattern.params["detector"]](ctx, pattern)


def check_text(path: str, text: str, *, baseline: str | None = None, exempt=None,
               library: list[Pattern] | None = None) -> list[Finding]:
    """Return findings for the text; baseline text and exempt sentences are left out."""
    patterns = library if library is not None else load_library()[0]
    scoped = [p for p in patterns if pattern_in_scope(p, path)]
    segments = extract_segments(path, text) + raw_segments(text)
    haystack = ""
    if baseline:
        base_segments = extract_segments(path, baseline)
        haystack = norm(" ".join(s.text for s in base_segments)) + "\n" + norm(baseline)
    ctx = Context(path, text, segments, baseline)
    findings: list[Finding] = []
    seen: set[tuple] = set()
    source_lines = text.splitlines()
    for pattern in scoped:
        for found in run_pattern(ctx, pattern):
            key = (found.line, found.pattern, found.quote)
            quote = norm(found.quote)
            if key in seen or ignored(source_lines, found):
                continue
            if baseline and (len(quote) >= MIN_BASELINE_QUOTE and quote in haystack
                             or found.context and norm(found.context) in haystack):
                continue
            if exempt and quote and exempt(quote):
                continue
            seen.add(key)
            findings.append(found)
    return sorted(findings, key=lambda f: (f.line, f.pattern))


def check_file(path: Path, **kwargs) -> list[Finding]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    return check_text(str(path), text, **kwargs)


def render(findings: list[Finding], target: str) -> str:
    """Format findings as a list of edits to make."""
    must = [f for f in findings if f.severity == "edit"]
    check = [f for f in findings if f.severity == "review"]
    lines = [f"AI TELLS in {target}: {len(must)} required edit(s), {len(check)} to check."]

    def block(title: str, rows: list[Finding]) -> None:
        if not rows:
            return
        lines.append(title)
        for f in rows:
            shown = f' "{f.quote}"' if f.quote else ""
            lines.append(f"  L{f.line} [{f.pattern}]{shown}")
            lines.append(f"      {f.message}. {f.fix}")

    block("Required edits (change each one):", must)
    block("Check these (edit when the tell is real, leave when the wording is deliberate):", check)
    return "\n".join(lines)


def self_test(patterns: list[Pattern]) -> list[str]:
    """Run each pattern's hit and clean examples; return failure descriptions."""
    failures = []
    seen = set()
    for pattern in patterns:
        if pattern.id in seen:
            failures.append(f"{pattern.id}: duplicate id")
        seen.add(pattern.id)
        if pattern.kind != "regex":
            continue
        kind = pattern.applies[0]
        for label, expected in (("hit", True), ("clean", False)):
            for example in pattern.examples.get(label, []):
                ctx = Context("example.md", example, [Segment(1, kind, example)])
                got = bool(regex_findings(ctx, pattern))
                if got != expected:
                    verb = "missed" if expected else "matched"
                    failures.append(f"{pattern.id}: {label} example {verb}: {example[:60]}")
        if not pattern.examples.get("hit"):
            failures.append(f"{pattern.id}: no hit example")
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="*", type=Path, help="files to check")
    parser.add_argument("--library", type=Path, help="pattern library folder")
    parser.add_argument("--baseline", type=Path, help="earlier copy of a single file; its text is not reported")
    parser.add_argument("--json", action="store_true", help="print findings as JSON")
    parser.add_argument("--list-patterns", action="store_true", help="print the loaded patterns")
    parser.add_argument("--self-test", action="store_true", help="check the library examples")
    parser.add_argument("--report-only", action="store_true", help="exit 0 even when findings exist")
    args = parser.parse_args(argv)

    patterns, errors = load_library(args.library)
    for message in errors:
        print(f"library error: {message}", file=sys.stderr)
    if errors:
        return 2
    if args.list_patterns:
        for p in patterns:
            print(f"{p.library:18s} {p.scope:9s} {p.severity:7s} {p.id}")
        return 0
    if args.self_test:
        failures = errors + self_test(patterns)
        print(f"{len(patterns)} patterns, {len(failures)} failure(s)")
        for failure in failures:
            print(f"  {failure}")
        return 1 if failures else 0
    if not args.files:
        print("no files given", file=sys.stderr)
        return 2
    baseline = args.baseline.read_text(encoding="utf-8") if args.baseline else None
    total = 0
    report = {}
    for path in args.files:
        found = check_file(path, baseline=baseline, library=patterns)
        total += len(found)
        report[str(path)] = found
        if not args.json and found:
            print(render(found, str(path)))
    if args.json:
        print(json.dumps({name: [asdict(f) for f in rows] for name, rows in report.items()}, indent=1))
    return 0 if args.report_only or total == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
