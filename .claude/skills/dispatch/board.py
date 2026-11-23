#!/usr/bin/env python3
"""Read the issue board and propose a batch of issues that can run in parallel.

Usage:
  python3 board.py [--batch N] [--repo owner/name]      # reads open issues via gh
  python3 board.py --from-file issues.json [--batch N]  # same JSON, for tests

Rules:
  - candidates: open, labelled `ready` (or `blocked` whose blockers have all
    closed), not `spec`, `in-progress` or `needs-review`, unassigned
  - an issue is blocked while any "Blocked by #n" it names is still open
  - ranked by how many open issues it unblocks (directly or further down), then oldest first
  - a batch never contains two issues whose "Files:" lists overlap (or that both
    leave Files empty: unknown scope is treated as overlapping everything)
Prints a plan as JSON. Changes nothing.
"""
import argparse
import json
import re
import subprocess
import sys

BLOCK_RE = re.compile(r"blocked by[:\s]*((?:#\d+[\s,and]*)+)", re.I)
NUM_RE = re.compile(r"#(\d+)")
FILES_RE = re.compile(r"^[ \t]*[-*]?[ \t]*Files:[ \t]*(.*)$", re.I | re.M)
TYPE_RE = re.compile(r"^[ \t]*[-*]?[ \t]*Type:[ \t]*([a-z-]+)", re.I | re.M)
SKIP_LABELS = {"spec", "in-progress", "needs-review"}


def load(args):
    if args.from_file:
        with open(args.from_file) as f:
            return json.load(f)
    cmd = ["gh", "issue", "list", "--state", "open", "--limit", "200",
           "--json", "number,title,labels,body,assignees,createdAt"]
    if args.repo:
        cmd += ["--repo", args.repo]
    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit(f"gh failed: {out.stderr.strip()}")
    return json.loads(out.stdout)


def labels(issue):
    return {(l["name"] if isinstance(l, dict) else l).lower() for l in issue.get("labels", [])}


def blockers(body):
    nums = set()
    for m in BLOCK_RE.finditer(re.sub(r"<!--.*?-->", "", body or "", flags=re.S)):
        nums.update(int(n) for n in NUM_RE.findall(m.group(1)))
    return nums


def files(body):
    m = FILES_RE.search(re.sub(r"<!--.*?-->", "", body or "", flags=re.S))
    if not m:
        return set()
    raw = re.sub(r"[`<>]", "", m.group(1))
    return {p.strip().rstrip("/") for p in re.split(r"[,\s]+", raw) if p.strip() and p.strip() not in ("-", "none", "unknown")}


def overlaps(a, b):
    if not a or not b:
        return True
    for x in a:
        for y in b:
            if x == y or x.startswith(y + "/") or y.startswith(x + "/"):
                return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-file")
    ap.add_argument("--repo")
    ap.add_argument("--batch", type=int, default=3)
    args = ap.parse_args()

    issues = load(args)
    open_nums = {i["number"] for i in issues}
    by_num = {i["number"]: i for i in issues}

    # who does each issue (transitively) unblock?
    unblocks = {n: set() for n in open_nums}
    for i in issues:
        for b in blockers(i.get("body")):
            if b in unblocks:
                unblocks[b].add(i["number"])

    def reach(n, seen=None):
        seen = seen if seen is not None else set()
        for m in unblocks.get(n, ()):
            if m not in seen:
                seen.add(m)
                reach(m, seen)
        return seen

    candidates, waiting = [], []
    for i in issues:
        ls = labels(i)
        open_blockers = sorted(b for b in blockers(i.get("body")) if b in open_nums)
        info = {
            "number": i["number"],
            "title": i["title"],
            "type": (TYPE_RE.search(i.get("body") or "") or [None, "unknown"])[1].lower(),
            "files": sorted(files(i.get("body"))),
            "unblocks": len(reach(i["number"])),
        }
        if not ls & {"ready", "blocked"} or ls & SKIP_LABELS or i.get("assignees"):
            continue
        if "blocked" in ls and not open_blockers:
            info["note"] = "labelled blocked but its blockers are closed: relabel to ready"
        if open_blockers:
            info["blocked_by"] = open_blockers
            waiting.append(info)
        else:
            candidates.append(info)

    candidates.sort(key=lambda c: (-c["unblocks"], by_num[c["number"]].get("createdAt", ""), c["number"]))

    batch, held = [], []
    for c in candidates:
        clash = [b["number"] for b in batch if overlaps(set(c["files"]), set(b["files"]))]
        if len(batch) < args.batch and not clash:
            batch.append(c)
        else:
            c["held_because"] = f"overlaps #{clash[0]}" if clash else "batch full"
            held.append(c)

    print(json.dumps({"batch": batch, "held": held, "blocked": waiting,
                      "in_progress": [i["number"] for i in issues if "in-progress" in labels(i)]}, indent=2))


if __name__ == "__main__":
    main()
