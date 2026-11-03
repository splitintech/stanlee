#!/usr/bin/env python3
"""Inventory UI controls and native public API; fail on upstream surface drift.

This is evidence of discovery, not evidence of implementation or full semantic
coverage. Handwritten dialogs and dynamic actions are also recorded for review.
"""
import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from xml.etree import ElementTree

INTERACTIVE = {"QAction", "QPushButton", "QToolButton", "QCheckBox", "QRadioButton",
               "QComboBox", "QSpinBox", "QDoubleSpinBox", "QSlider", "QLineEdit",
               "QKeySequenceEdit", "QListWidget", "QTableWidget", "QTreeWidget",
               "QTabWidget", "QDialogButtonBox", "QPlainTextEdit", "QTextEdit"}


def family(path, name):
    text = (path + " " + name).lower()
    for match, group in [("export", "import_export"), ("import", "import_export"),
                         ("palette", "palette"), ("color", "palette"), ("camera", "camera"),
                         ("layer", "layers"), ("frame", "timeline"), ("timeline", "timeline"),
                         ("sound", "sound"), ("tool", "tools"), ("stroke", "tools"),
                         ("view", "viewport"), ("onion", "viewport"), ("file", "documents"),
                         ("document", "documents"), ("save", "documents"),
                         ("undo", "history"), ("redo", "history")]:
        if match in text:
            return group
    return "application"


def inventory(root):
    entries = []
    for path in sorted(root.rglob("*.ui")):
        if any(part.startswith("build") or part == ".git" for part in path.relative_to(root).parts):
            continue
        rel = path.relative_to(root).as_posix()
        for node in ElementTree.parse(path).getroot().iter():
            cls = "QAction" if node.tag == "action" else node.get("class", "")
            if cls not in INTERACTIVE:
                continue
            name = node.get("name", "")
            entries.append({"id": f"{rel}::{name}", "kind": cls, "source": rel,
                            "name": name, "label": node.findtext("./property[@name='text']/string", ""),
                            "family": family(rel, name),
                            "fingerprint": hashlib.sha256(ElementTree.tostring(node)).hexdigest()})
    # Include handwritten controls, dynamic menus and manager/tool public APIs.
    patterns = [r"new\s+QAction\s*\(", r"addAction\s*\(", r"addMenu\s*\(",
                r"new\s+Q(?:CheckBox|ComboBox|SpinBox|DoubleSpinBox|PushButton|Slider)\s*\("]
    for base in (root / "app/src", root / "core_lib/src"):
        for path in sorted(base.rglob("*")):
            if path.suffix not in {".h", ".cpp"}:
                continue
            rel = path.relative_to(root).as_posix()
            public = False
            for number, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
                if re.match(r"\s*(public|signals|public slots)\s*:", line):
                    public = True
                elif re.match(r"\s*(private|protected)( slots)?\s*:", line):
                    public = False
                api = path.suffix == ".h" and public and re.search(r"\w+\s*\([^;{}]*\)\s*(?:const)?\s*(?:override)?\s*(?:=\s*0)?\s*;", line)
                dynamic = any(re.search(pattern, line) for pattern in patterns)
                if not api and not dynamic:
                    continue
                signature = line.strip()
                entries.append({"id": f"{rel}::{signature}", "kind": "public_api" if api else "dynamic_ui",
                                "source": rel, "line": number, "name": signature,
                                "family": family(rel, signature),
                                "fingerprint": hashlib.sha256(signature.encode()).hexdigest()})
    # Identical handwritten expressions can occur several times; retain each.
    counts = {}
    for entry in entries:
        key = entry["id"]
        counts[key] = counts.get(key, 0) + 1
        entry["id"] = key + f"#{counts[key]}"
    return entries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, default=Path("contracts/coverage.json"))
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    discovered = inventory(args.source)
    revision = subprocess.check_output(["git", "-C", str(args.source), "rev-parse", "HEAD"], text=True).strip()
    if args.check:
        old = json.loads(args.output.read_text())["entries"]
        def surface(rows):
            return {row["id"]: row["fingerprint"] for row in rows}
        before, after = surface(old), surface(discovered)
        added, removed = sorted(after.keys()-before.keys()), sorted(before.keys()-after.keys())
        changed = sorted(k for k in before.keys() & after.keys() if before[k] != after[k])
        print(json.dumps({"added": added, "removed": removed, "changed": changed}, indent=2))
        raise SystemExit(bool(added or removed or changed))
    old_document = json.loads(args.output.read_text()) if args.output.exists() else {}
    old_entries = old_document.get('entries', [])
    annotations = {e["id"]: e for e in old_entries}
    for entry in discovered:
        old = annotations.get(entry["id"], {})
        for key, default in {
            "operation": None, "implementation": "pending", "documentation": "pending",
            "tests": [], "platforms": {p: "unqualified" for p in ("macos", "windows", "linux")},
            "preconditions": "requires semantic review", "effects": "requires semantic review",
            "undo": "requires semantic review", "inputs": "requires semantic review",
        }.items():
            entry[key] = old.get(key, default)
        # A native fingerprint change invalidates the review, not its history.
        # Never silently discard reviewed/non-applicable decisions on a refresh.
        for key in ("reviewed", "review_rationale"):
            if key in old:
                entry[key] = old[key]
        if old.get("fingerprint") != entry.get("fingerprint") and old.get("reviewed"):
            entry["reviewed"] = False
            entry["previous_review_rationale"] = old.get("review_rationale", "")
        elif "previous_review_rationale" in old:
            entry["previous_review_rationale"] = old["previous_review_rationale"]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    before = {entry['id']: entry.get('fingerprint') for entry in old_entries}
    after = {entry['id']: entry.get('fingerprint') for entry in discovered}
    reviewed_surface_unchanged = before == after
    retired = {entry['id']: entry for entry in old_document.get('retired_entries', [])}
    retired.update({entry['id']: entry for entry in old_entries if entry['id'] not in after})
    for key in after:
        retired.pop(key, None)
    args.output.write_text(json.dumps({"schema_version": 1, "upstream_revision": revision,
                                     "semantic_review_complete": bool(old_document.get('semantic_review_complete') and reviewed_surface_unchanged),
                                     "retired_entries": list(retired.values()), "entries": discovered}, indent=2)+"\n")
    print(json.dumps({"revision": revision, "entries": len(discovered),
                      "main_window_actions": sum(e["kind"] == "QAction" and e["source"] == "app/ui/mainwindow2.ui" for e in discovered)}))


if __name__ == "__main__":
    main()
