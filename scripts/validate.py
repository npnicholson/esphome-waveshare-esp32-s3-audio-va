#!/usr/bin/env python3
"""Offline sanity check for the ESPHome config.

ESPHome itself is the real validator, but a round trip through the dashboard is
slow and a YAML typo does not deserve one. This catches, locally:

  * YAML syntax errors (ESPHome's custom tags are stubbed out)
  * `${foo}` / `$foo` references with no matching substitution
  * substitutions that are defined but never used (dead config)
  * duplicate component `id:` values

    pip install pyyaml
    python validate.py ../base/core.yaml

Files that are only valid together - `base/core.yaml` plus one of the audio
path packages - are passed as one comma-separated group, and checked as if
merged: substitutions defined in either file satisfy references in the other,
and a duplicate id across the group is reported.

    python validate.py base/core.yaml,base/audio-stock.yaml \
                       base/core.yaml,base/audio-afe.yaml

Exit code is 1 if anything failed, so it works in a pre-commit hook.
"""
import re
import sys
from pathlib import Path

import yaml

# ESPHome tags carry no meaning for us; keep the value, drop the tag.
for tag in ("!secret", "!lambda", "!include", "!extend", "!remove", "!force"):
    yaml.SafeLoader.add_constructor(
        tag, lambda loader, node, t=tag: f"<{t[1:]}>"
    )
yaml.SafeLoader.add_multi_constructor(
    "!", lambda loader, suffix, node: f"<{suffix}>"
)

# Substitutions ESPHome injects itself, so an unresolved reference is expected.
BUILTIN_SUBS = {"name", "friendly_name", "device_name", "esphome_version"}

SUB_REF = re.compile(r"\$\{(\w+)\}|\$(\w+)")

# A top-level key: no indentation, not a list item, not a comment.
TOP_KEY = re.compile(r"^([A-Za-z_][\w.]*):", re.M)


def duplicate_top_level_keys(text):
    """Top-level keys that appear more than once in one file.

    PyYAML silently keeps only one of them, so a duplicate `esphome:` block
    loses everything in the losing copy without any error anywhere - it just
    goes missing from the compiled config.
    """
    seen = {}
    for m in TOP_KEY.finditer(text):
        seen.setdefault(m.group(1), []).append(text[: m.start()].count("\n") + 1)
    return {k: v for k, v in seen.items() if len(v) > 1}


def collect_ids(node, out, path="root", in_action=False):
    """Collect id: DECLARATIONS only.

    Every ESPHome action is a dotted key (`script.execute`, `light.turn_on`,
    `mixer_speaker.apply_ducking`, ...) and an `id:` underneath one is a
    reference to a component declared elsewhere, not a second declaration.
    Component declarations never sit under a dotted key.
    """
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "id" and isinstance(value, str) and not value.startswith("<"):
                if not in_action:
                    out.setdefault(value, []).append(path)
            collect_ids(
                value,
                out,
                f"{path}.{key}",
                in_action or ("." in str(key)),
            )
    elif isinstance(node, list):
        for i, item in enumerate(node):
            collect_ids(item, out, f"{path}[{i}]", in_action)


def check_group(paths) -> int:
    """Validate one or more files as a single merged config. Returns problem count."""
    problems = 0
    label = " + ".join(str(p) for p in paths)
    print(f"\n=== {label} ===")

    subs, bodies, ids, has_packages = {}, [], {}, False
    for path in paths:
        text = path.read_text(encoding="utf-8")

        # 1. Does it parse?
        try:
            doc = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            print(f"  FAIL  {path}: YAML does not parse:\n{exc}")
            return problems + 1

        if not isinstance(doc, dict):
            print(f"  FAIL  {path}: top level is not a mapping")
            return problems + 1

        dupes_top = duplicate_top_level_keys(text)
        if dupes_top:
            for key, lines in dupes_top.items():
                print(
                    f"  FAIL  {path}: top-level key '{key}' defined "
                    f"{len(lines)}x (lines {', '.join(map(str, lines))}); "
                    f"YAML keeps only one"
                )
            problems += 1

        subs.update(doc.get("substitutions") or {})
        has_packages = has_packages or "packages" in doc

        # References vs definitions. Strip the substitutions block itself so a
        # default that quotes another key does not count as a use.
        bodies.append(
            re.sub(r"^substitutions:.*?(?=^\S)", "", text, flags=re.S | re.M)
        )
        collect_ids(doc, ids, path=path.name)
    print("  OK    YAML parses")

    # 2. References resolve somewhere in the group.
    used = {
        m.group(1) or m.group(2)
        for body in bodies
        for m in SUB_REF.finditer(body)
    }
    undefined = sorted(used - set(subs) - BUILTIN_SUBS)
    if undefined:
        print(f"  FAIL  used but never defined: {', '.join(undefined)}")
        problems += 1
    else:
        print("  OK    every ${...} has a substitution")

    # A thin config exists precisely to define substitutions for a remote
    # package, so "unused here" says nothing. Only flag it on a standalone.
    if has_packages:
        print("  SKIP  unused substitutions (this file feeds a package)")
    else:
        unused = sorted(set(subs) - used - BUILTIN_SUBS)
        if unused:
            print(f"  WARN  defined but never used: {', '.join(unused)}")

    # 3. Duplicate ids, across the whole group.
    dupes = {k: v for k, v in ids.items() if len(v) > 1}
    if dupes:
        for dupe, where in dupes.items():
            print(f"  FAIL  duplicate id '{dupe}': {'; '.join(where)}")
        problems += 1
    else:
        print(f"  OK    {len(ids)} unique ids, no collisions")

    return problems


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2

    problems = 0
    for arg in sys.argv[1:]:
        problems += check_group([Path(p) for p in arg.split(",")])

    print("\n" + ("FAILED" if problems else "ALL GOOD"))
    return 1 if problems else 0



if __name__ == "__main__":
    sys.exit(main())
