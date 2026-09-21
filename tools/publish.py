#!/usr/bin/env python3
"""
Validate the Scam School scenario library and build the file the app downloads.

  python3 tools/publish.py                # validate + build site/ScamLibrary.json
  python3 tools/publish.py --check-links  # also confirm every source link responds

The version number and date are stamped automatically from git history
(every commit to main gets a higher version), so editors never edit them.
The rules below mirror ScamSchool/Models/LibraryValidator.swift in the app.
"""
import argparse
import datetime
import glob
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTENT = os.path.join(ROOT, "content")
SITE = os.path.join(ROOT, "site")

CHANNELS = {"sms", "email", "call", "voicemail", "website", "popup", "marketplace",
            "payment", "qr", "social", "letter", "message"}
OUTCOMES = {"safe", "risky", "costly"}
TRENDS = {"evergreen", "emerging"}
REQUIRED = ["id", "category", "channel", "difficulty", "isScam", "trend", "title", "setup",
            "content", "options", "redFlags", "safestAction", "sources", "addedOn"]
MIN_ACTIVE = 12
# Keeps published versions above the v1 library bundled in the first app build.
VERSION_OFFSET = 100


def validate(s, category_ids):
    tag = f"[{s.get('id', '?')}]"
    missing = [k for k in REQUIRED if k not in s]
    if missing:
        return [f"{tag} missing {', '.join(missing)}"]
    p = []
    if s["category"] not in category_ids:
        p.append(f"{tag} unknown category '{s['category']}'")
    if s["channel"] not in CHANNELS:
        p.append(f"{tag} unknown channel '{s['channel']}'")
    if s["difficulty"] not in (1, 2, 3):
        p.append(f"{tag} difficulty must be 1, 2, or 3")
    if s["trend"] not in TRENDS:
        p.append(f"{tag} trend must be evergreen or emerging")
    opts = s["options"]
    if not 2 <= len(opts) <= 4:
        p.append(f"{tag} needs 2-4 options")
    ids = [o.get("id") for o in opts]
    if len(set(ids)) != len(ids):
        p.append(f"{tag} duplicate option ids")
    if not any(o.get("outcome") == "safe" for o in opts):
        p.append(f"{tag} needs at least one safe option")
    for o in opts:
        oid = o.get("id", "?")
        loss = o.get("loss", 0) or 0
        if o.get("outcome") not in OUTCOMES:
            p.append(f"{tag} option {oid}: outcome must be safe, risky, or costly")
        if o.get("outcome") == "safe" and loss > 0:
            p.append(f"{tag} option {oid}: safe options can't lose money")
        if o.get("outcome") == "costly" and loss <= 0:
            p.append(f"{tag} option {oid}: costly options need a loss")
        if loss > 10000:
            p.append(f"{tag} option {oid}: loss is more than the $10,000 starting balance")
        if not o.get("label") or not o.get("feedback"):
            p.append(f"{tag} option {oid}: missing label or feedback")
    if not s["redFlags"]:
        p.append(f"{tag} needs at least one red flag")
    if not s["sources"]:
        p.append(f"{tag} needs at least one source")
    for src in s["sources"]:
        if not str(src.get("url", "")).startswith("https://"):
            p.append(f"{tag} source URL must start with https://")
    try:
        datetime.date.fromisoformat(s["addedOn"])
    except ValueError:
        p.append(f"{tag} addedOn must look like 2026-09-18")
    if "level" in s and s["level"] not in (1, 2, 3, 4, 5):
        p.append(f"{tag} level must be 1-5")
    p += chain_problems(s, tag)
    return p


def chain_problems(s, tag):
    """Follow-up beats: ids resolve, beats are reachable, timers name their option."""
    p = []
    steps = {"start": s}
    for beat in s.get("followUps", []):
        if beat.get("id") in steps:
            p.append(f"{tag} follow-up id '{beat.get('id')}' is used twice")
        steps[beat.get("id")] = beat
        if not beat.get("setup"):
            p.append(f"{tag} follow-up '{beat.get('id')}' needs a setup line saying what just happened")
        if not beat.get("content"):
            p.append(f"{tag} follow-up '{beat.get('id')}' needs content")
        opts = beat.get("options", [])
        if not 2 <= len(opts) <= 4:
            p.append(f"{tag} follow-up '{beat.get('id')}' needs 2-4 options")
        if not any(o.get("outcome") == "safe" for o in opts):
            p.append(f"{tag} follow-up '{beat.get('id')}' needs at least one safe option")
        for o in opts:
            loss = o.get("loss", 0) or 0
            if o.get("outcome") == "safe" and loss > 0:
                p.append(f"{tag} follow-up '{beat.get('id')}' option {o.get('id')}: safe options can't lose money")
            if o.get("outcome") == "costly" and loss <= 0:
                p.append(f"{tag} follow-up '{beat.get('id')}' option {o.get('id')}: costly options need a loss")
            if not o.get("label") or not o.get("feedback"):
                p.append(f"{tag} follow-up '{beat.get('id')}' option {o.get('id')}: missing label or feedback")

    reachable = {"start"}
    frontier = ["start"]
    while frontier:
        step = steps.get(frontier.pop())
        for o in (step or {}).get("options", []):
            nxt = o.get("next")
            if nxt and nxt not in steps:
                p.append(f"{tag} option {o.get('id')} points at '{nxt}', which doesn't exist")
            elif nxt and nxt not in reachable:
                reachable.add(nxt); frontier.append(nxt)
    for beat in s.get("followUps", []):
        if beat.get("id") not in reachable:
            p.append(f"{tag} follow-up '{beat.get('id')}' can't be reached from any option")

    for step_id, step in steps.items():
        if "timeLimit" not in step:
            continue
        where = tag if step_id == "start" else f"{tag} follow-up '{step_id}'"
        if not 5 <= step["timeLimit"] <= 120:
            p.append(f"{where} timeLimit must be 5-120 seconds")
        if not step.get("timeoutOption"):
            p.append(f"{where} is timed, so it needs a timeoutOption")
        elif step["timeoutOption"] not in [o.get("id") for o in step.get("options", [])]:
            p.append(f"{where} timeoutOption '{step['timeoutOption']}' isn't one of its options")
    return p


def git(*args):
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return ""


def check_links(scenarios):
    bad = []
    for url in sorted({src["url"] for s in scenarios for src in s["sources"]}):
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Scam School link check)"})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                status = r.status
        except urllib.error.HTTPError as e:
            status = e.code
        except Exception as e:
            status = type(e).__name__
        ok = status in (200, 403)  # several .gov sites return 403 to scripts but work in browsers
        print(f"  {'ok ' if ok else 'BAD'} {status} {url}")
        if not ok:
            bad.append(url)
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check-links", action="store_true")
    args = ap.parse_args()

    meta = json.load(open(os.path.join(CONTENT, "library.json")))
    category_ids = {c["id"] for c in meta["categories"]}
    scenarios, problems, seen = [], [], set()
    for path in sorted(glob.glob(os.path.join(CONTENT, "scenarios", "*.json"))):
        name = os.path.basename(path)
        try:
            items = json.load(open(path))
        except json.JSONDecodeError as e:
            problems.append(f"{name}: not valid JSON (line {e.lineno}, column {e.colno}): {e.msg}")
            continue
        for s in items:
            p = validate(s, category_ids)
            if s.get("id") in seen:
                p.append(f"[{s.get('id')}] id is used twice")
            seen.add(s.get("id"))
            problems += [f"{name} {x}" for x in p]
            scenarios.append(s)

    active = [s for s in scenarios if s.get("active", True)]
    if len(active) < MIN_ACTIVE:
        problems.append(f"only {len(active)} active scenarios; the app needs at least {MIN_ACTIVE}")

    print(f"{len(active)} active scenarios: {sum(s['isScam'] for s in active)} scams, "
          f"{sum(not s['isScam'] for s in active)} legit, "
          f"{sum(s['trend'] == 'emerging' for s in active)} emerging, "
          f"{sum(1 for s in active if s.get('followUps'))} that keep going, "
          f"{sum(1 for s in active if s.get('timeLimit'))} timed")
    for lvl in (1, 2, 3, 4, 5):
        in_level = [s for s in active if s.get("level") == lvl]
        legit = sum(1 for s in in_level if not s["isScam"])
        print(f"  Level {lvl}: {len(in_level):>2} scenarios, {legit} legit")
        if not in_level:
            problems.append(f"Level {lvl} has no scenarios; the course needs all five")
        elif legit == 0:
            print(f"    note: every situation in Level {lvl} is a scam")

    if args.check_links:
        print("Checking source links...")
        problems += [f"source link failed: {u}" for u in check_links(scenarios)]

    if problems:
        print("\nFix these before publishing:")
        for p in problems:
            print("  - " + p)
        sys.exit(1)

    count = git("rev-list", "--count", "HEAD")
    version = VERSION_OFFSET + (int(count) if count.isdigit() else 0)
    updated = git("log", "-1", "--format=%cs") or datetime.date.today().isoformat()

    library = {"schemaVersion": meta["schemaVersion"], "version": version, "updatedAt": updated,
               "categories": meta["categories"], "scenarios": scenarios}
    os.makedirs(SITE, exist_ok=True)
    with open(os.path.join(SITE, "ScamLibrary.json"), "w") as f:
        json.dump(library, f, ensure_ascii=False, separators=(",", ":"))
    with open(os.path.join(SITE, "index.html"), "w") as f:
        f.write("<!doctype html><meta charset=utf-8><title>Scam School content</title>"
                "<p>Scenario library for the Scam School app. "
                f"Version {version}, updated {updated}, {len(active)} scenarios. "
                "<a href=ScamLibrary.json>ScamLibrary.json</a></p>\n")
    print(f"\nBuilt version {version} ({updated}) -> site/ScamLibrary.json")


if __name__ == "__main__":
    main()
