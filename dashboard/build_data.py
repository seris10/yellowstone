"""Assemble dashboard data from the component inventories and the fixes ledger.

Writes data/dashboard-data.js, which index.html loads as a plain script.
"""

from __future__ import annotations

import datetime
import json
import re
import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DATA = HERE / "data"
FIXES = ROOT / "yellowstone_python_spec" / "fixes"
LEDGER = FIXES / "ledger"

COMPONENT_STATUSES = ["rendered", "python_only", "partial_unwired", "not_started", "next_phase"]
COUPLING_STATUSES = ["wired", "partial", "missing", "proposed"]
VERDICTS = ["implemented", "shortcut", "partial", "missing", "superseded", "conflicts"]

DOC_ID = re.compile(r"^fixes-(\d+(?:\.\d+)*)")
SUMMARY = re.compile(
    r"Summary:\s*(\d+)\s*items?:\s*(\d+)\s*implemented,\s*(\d+)\s*shortcut,\s*(\d+)\s*partial,"
    r"\s*(\d+)\s*missing,\s*(\d+)\s*superseded,\s*(\d+)\s*conflicts"
)
FINDING = re.compile(r"^###\s+\d+\.", re.MULTILINE)


def load_json(path: Path, default):
    if not path.exists():
        return default
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def doc_sort_key(doc_id: str):
    return tuple(int(part) for part in doc_id.split("."))


def normalize_verdict(raw: str) -> str | None:
    text = raw.strip().strip("`*_ ").lower()
    for verdict in VERDICTS:
        if text.startswith(verdict):
            return verdict
    return None


def split_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def ledger_counts(text: str) -> tuple[dict, int]:
    """Count verdicts from table rows; the Summary line is the fallback."""
    counts = {verdict: 0 for verdict in VERDICTS}
    rows = 0
    verdict_col = None
    for line in text.splitlines():
        if not line.lstrip().startswith("|"):
            verdict_col = None if not line.strip() else verdict_col
            continue
        cells = split_row(line)
        lowered = [cell.lower() for cell in cells]
        if "verdict" in lowered:
            verdict_col = lowered.index("verdict")
            continue
        if verdict_col is None or set(line.replace("|", "").strip()) <= set("-: "):
            continue
        if verdict_col < len(cells):
            verdict = normalize_verdict(cells[verdict_col])
            if verdict:
                counts[verdict] += 1
                rows += 1
    if rows == 0:
        match = SUMMARY.search(text)
        if match:
            values = [int(value) for value in match.groups()]
            rows = values[0]
            counts = dict(zip(VERDICTS, values[1:]))
    return counts, rows


def ledger_targets(text: str) -> list[str]:
    match = re.search(r"targets:\s*(.+)", text)
    if not match:
        return []
    targets = []
    for part in match.group(1).split(";"):
        path = part.strip().split(" sha256")[0].strip()
        if path:
            targets.append(path)
    return targets


def doc_area(doc_id: str, areas: dict) -> str:
    for area, ids in areas.items():
        if doc_id in ids:
            return area
    return "N"


def collect_docs(node_map: dict) -> list[dict]:
    docs = {}
    for path in sorted(FIXES.iterdir()):
        match = DOC_ID.match(path.name)
        if not match or path.is_dir():
            continue
        doc_id = match.group(1)
        if doc_id in docs:
            continue
        ledger_path = LEDGER / f"fixes-{doc_id}.md"
        if not ledger_path.exists():
            named = sorted(LEDGER.glob(f"fixes-{doc_id}-*.md"))
            ledger_path = named[0] if named else ledger_path
        entry: dict = {
            "id": doc_id,
            "file": str(path.relative_to(ROOT)),
            "area": doc_area(doc_id, node_map.get("doc_areas", {})),
            "ledger": None,
            "counts": {verdict: 0 for verdict in VERDICTS},
            "items": 0,
            "targets": [],
        }
        if ledger_path.exists():
            text = ledger_path.read_text(encoding="utf-8")
            entry["ledger"] = str(ledger_path.relative_to(ROOT))
            entry["counts"], entry["items"] = ledger_counts(text)
            entry["targets"] = ledger_targets(text)
        else:
            findings = len(FINDING.findall(path.read_text(encoding="utf-8", errors="replace")))
            entry["items"] = findings
            entry["counts"]["missing"] = findings
        docs[doc_id] = entry
    return [docs[key] for key in sorted(docs, key=doc_sort_key)]


def merge_components(python_inv: dict, plans_inv: dict, node_map: dict) -> tuple[list, list]:
    components = {}
    for source, inventory in (("python", python_inv), ("plans", plans_inv)):
        for comp in inventory.get("components", []):
            if comp["id"] in components:
                continue
            item = dict(comp)
            item["source_inventory"] = source
            item["kind"] = "component"
            components[comp["id"]] = item

    couplings = []
    for inventory in (python_inv, plans_inv):
        for coupling in inventory.get("couplings", []):
            couplings.append(dict(coupling))

    interface_domains = node_map.get("interface_domains", {})
    for coupling in couplings:
        for end in (coupling["from"], coupling["to"]):
            if end not in components:
                components[end] = {
                    "id": end,
                    "label": end.replace("_", " "),
                    "domain": interface_domains.get(end, "infrastructure"),
                    "status": "interface",
                    "kind": "interface",
                    "evidence": [],
                    "notes": "Quantity or artifact named by a coupling; not a module.",
                }
    for coupling in couplings:
        a = components[coupling["from"]].get("domain")
        b = components[coupling["to"]].get("domain")
        coupling["cross_domain"] = a != b
    return list(components.values()), couplings


def attach_rendering(components: list, godot_inv: dict, node_map: dict) -> list:
    renders = node_map.get("renders", {})
    by_id = {comp["id"]: comp for comp in components}
    render_rows = []
    for comp in godot_inv.get("components", []):
        sources = renders.get(comp["id"], [])
        render_rows.append({
            "id": comp["id"],
            "label": comp.get("label", comp["id"]),
            "domain": comp.get("domain"),
            "status": comp.get("status"),
            "godot": comp.get("godot", []),
            "evidence": comp.get("evidence", []),
            "notes": comp.get("notes", ""),
            "sources": sources,
        })
        for source in sources:
            if source in by_id:
                by_id[source].setdefault("rendered_by", []).append(
                    {"id": comp["id"], "status": comp.get("status")}
                )
    return render_rows


def tally(items: list, key: str, keys: list) -> dict:
    counts = {k: 0 for k in keys}
    for item in items:
        value = item.get(key)
        if value in counts:
            counts[value] += 1
    return counts


def receipt_status(receipt: dict, root: Path = ROOT) -> str:
    """Resolve execution evidence against current source and fixture bytes."""
    if not receipt.get("source_hashes"):
        return "unavailable"
    if receipt.get("complete_source_inventory"):
        inventory = receipt["source_inventory"]
        discovered = {str(path.relative_to(root)) for directory in inventory["directories"]
                      for path in (root / directory).rglob("*")
                      if path.is_file() and path.suffix in inventory["suffixes"]}
        discovered.update(name for name in inventory["files"] if (root / name).is_file())
        if discovered != set(receipt["source_hashes"]):
            return "stale"
    artifacts = {**receipt["source_hashes"], **receipt.get("fixture_hashes", {})}
    if receipt.get("output"):
        artifacts[receipt["output"]] = receipt.get("output_sha256")
    for relative, expected in artifacts.items():
        path = root / relative
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            return "stale"
    return receipt.get("status", "unavailable")


def collect_receipts(root: Path = ROOT) -> list[dict]:
    """Collect the latest source-bound command receipt for each named check."""
    latest = {}
    for path in sorted((root / "evidence/receipts").glob("*.json")):
        receipt = load_json(path, {})
        name = receipt.get("name")
        if not name:
            continue
        entry = {"name": name, "status": receipt_status(receipt, root),
                 "command": receipt.get("command"), "tests": receipt.get("tests", {}),
                 "started_utc": receipt.get("started_utc", ""),
                 "source_identity": receipt.get("source_identity"),
                 "source_commit": receipt.get("source_commit"), "receipt": str(path.relative_to(root))}
        if name not in latest or entry["started_utc"] > latest[name]["started_utc"]:
            latest[name] = entry
    return [latest[name] for name in sorted(latest)]


def main() -> None:
    node_map = load_json(DATA / "node-map.json", {})
    python_inv = load_json(DATA / "inventory-python.json", {})
    godot_inv = load_json(DATA / "inventory-godot.json", {})
    plans_inv = load_json(DATA / "inventory-plans.json", {})

    components, couplings = merge_components(python_inv, plans_inv, node_map)
    render_rows = attach_rendering(components, godot_inv, node_map)
    docs = collect_docs(node_map)

    verdict_totals = {verdict: sum(doc["counts"][verdict] for doc in docs) for verdict in VERDICTS}
    payload = {
        "generated_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "sources": {
            "inventory_python": python_inv.get("generated_from", ""),
            "inventory_godot": godot_inv.get("generated_from", ""),
            "inventory_plans": plans_inv.get("generated_from", ""),
        },
        "verified": {
            "python": python_inv.get("verified_utc", ""),
            "godot": godot_inv.get("verified_utc", ""),
            "plans": plans_inv.get("verified_utc", ""),
        },
        "component_statuses": COMPONENT_STATUSES,
        "coupling_statuses": COUPLING_STATUSES,
        "verdicts": VERDICTS,
        "area_labels": node_map.get("area_labels", {}),
        "components": components,
        "couplings": couplings,
        "rendering": render_rows,
        "docs": docs,
        "execution_evidence": collect_receipts(),
        "inventory_evidence_kind": "declared implementation and ledger assertions",
        "totals": {
            "components": tally([c for c in components if c["kind"] == "component"], "status", COMPONENT_STATUSES),
            "couplings": tally(couplings, "status", COUPLING_STATUSES),
            "rendering": tally(render_rows, "status", COMPONENT_STATUSES),
            "verdicts": verdict_totals,
            "fix_items": sum(doc["items"] for doc in docs),
        },
    }
    out = DATA / "dashboard-data.js"
    tmp = out.with_suffix(".js.tmp")
    tmp.write_text("window.YS_DASHBOARD = " + json.dumps(payload, indent=1) + ";\n", encoding="utf-8")
    tmp.replace(out)
    print(f"wrote {out.relative_to(ROOT)}: {len(components)} nodes, {len(couplings)} couplings, "
          f"{len(render_rows)} render rows, {len(docs)} fixes docs")


if __name__ == "__main__":
    main()
