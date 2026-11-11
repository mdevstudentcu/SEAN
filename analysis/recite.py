"""Re-cite committed results and docs after a rebase-merge (#215, REQ-10).

"Rebase and merge" gives every commit of a pull request a new hash on `main`, so a result or doc
that cited the branch commit points at a hash that is not on `main`. This script finds those
citations and rewrites each to the commit's twin on `main`.

Scanned (tracked files only): `analysis/results/**` (`.md`, `.json`), `analysis/pr-evidence/**`
(`.md`, `.json`), `systems/**/*.md`, `deploy/**/*.md` and `analysis/README.md`. A citation is a
7-40 character lowercase hex token (not the digits after a decimal point) that names exactly one
commit object. A cited commit reachable from `--main` (default `origin/main`) is left alone. A
number that happens to name an unmerged commit would show in the dry run: read it before --write.

The twin of an unreachable commit is found, in order:
1. `git patch-id --stable`: the one non-merge commit on `--main` with the same patch.
2. Fallback: the one commit on `--main` with the identical subject AND an identical diff of every
   file the commit touches that a file citing it names (full path, or a distinctive file name).
   A rebase that resolved a conflict in an unrelated file (an index README) is matched this way.
   The subject alone never matches.
No twin, or more than one, is reported and the citation is left as it is: never guessed.

A rewritten citation keeps its length (at least 7) and any suffix such as `-dirty`. The report
also gives how many files differ between the cited commit's tree and its twin's: the twin has the
same change, not necessarily the same tree. PNG files are never touched (a title drawn into an
image cannot be rewritten): those beside a rewritten file are listed, saying when a script the
file names has `--redraw`.

    python analysis/recite.py            # dry run: what would change
    python analysis/recite.py --write    # apply
"""

from __future__ import annotations

import argparse
import re
import subprocess
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

GLOBS = (
    "analysis/results/**",
    "analysis/pr-evidence/**",
    "systems/**",
    "deploy/**",
    "analysis/README.md",
)
SUFFIXES = {
    "analysis/results/": {".md", ".json"},
    "analysis/pr-evidence/": {".md", ".json"},
    "systems/": {".md"},
    "deploy/": {".md"},
    "analysis/README.md": {".md"},
}
# Not the digits of a decimal (`0.1234567`) nor part of a longer word or hash.
TOKEN = re.compile(r"(?<![\w.])[0-9a-f]{7,40}(?!\w|\.\d)")
GENERIC_NAMES = {"__init__.py", "README.md", "summary.md", "summary.json", "NOTES.md"}
SCRIPT = re.compile(r"\banalysis/[\w-]+\.py\b")


def git(repo: Path, *args: str, stdin: str | None = None) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, input=stdin, capture_output=True, text=True, check=True
    ).stdout


def patch_ids(repo: Path, *args: str) -> list[str]:
    """`git patch-id --stable` lines for the patch `git <args>` prints, kept as bytes until then
    (a diff need not be UTF-8)."""
    diff = subprocess.run(["git", *args], cwd=repo, capture_output=True, check=True).stdout
    out = subprocess.run(
        ["git", "patch-id", "--stable"], cwd=repo, input=diff, capture_output=True, check=True
    ).stdout
    return out.decode().splitlines()


def scanned_files(repo: Path) -> list[str]:
    """Tracked text files that may cite a commit."""
    out = []
    for path in git(repo, "ls-files", "-z", "--", *GLOBS).split("\0"):
        for prefix, suffixes in SUFFIXES.items():
            if path.startswith(prefix) and PurePosixPath(path).suffix in suffixes:
                out.append(path)
                break
    return sorted(set(out))


def resolve(repo: Path, tokens: set[str]) -> dict[str, str]:
    """Token -> full commit hash, for tokens that name exactly one commit."""
    if not tokens:
        return {}
    order = sorted(tokens)
    query = "".join(f"{t}^{{commit}}\n" for t in order)
    lines = git(repo, "cat-file", "--batch-check", stdin=query)
    out = {}
    for token, line in zip(order, lines.splitlines(), strict=True):
        parts = line.split()
        if len(parts) == 3 and parts[1] == "commit":
            out[token] = parts[0]
    return out


def patch_id(repo: Path, commit: str, *paths: str) -> str | None:
    lines = patch_ids(repo, "show", "--format=commit %H", "-p", commit, "--", *paths)
    return lines[0].split()[0] if lines else None


@dataclass
class Main:
    reachable: set[str]
    by_patch: dict[str, list[str]]
    by_subject: dict[str, list[str]]


def index_main(repo: Path, main: str) -> Main:
    reachable = set(git(repo, "rev-list", main).split())
    by_patch: dict[str, list[str]] = defaultdict(list)
    for line in patch_ids(repo, "log", "-p", "--no-merges", "--format=commit %H", main):
        pid, commit = line.split()
        by_patch[pid].append(commit)
    by_subject: dict[str, list[str]] = defaultdict(list)
    for line in git(repo, "log", "--no-merges", "--format=%H%x00%s", main).splitlines():
        commit, subject = line.split("\0", 1)
        by_subject[subject].append(commit)
    return Main(reachable, by_patch, by_subject)


def touched(repo: Path, commit: str) -> list[str]:
    return [p for p in git(repo, "show", "--format=", "--name-only", commit).splitlines() if p]


def named_in(text: str, paths: list[str]) -> list[str]:
    """The paths a citing file names: in full, or by a file name that is not generic."""
    out = []
    for p in paths:
        name = PurePosixPath(p).name
        if p in text or (name not in GENERIC_NAMES and re.search(rf"\b{re.escape(name)}\b", text)):
            out.append(p)
    return out


@dataclass
class Twin:
    commit: str | None  # full hash on main, or None
    method: str  # "patch-id", "subject+files", or why there is none


def find_twin(repo: Path, commit: str, text: str, main: Main) -> Twin:
    parents = git(repo, "rev-list", "--parents", "-n1", commit).split()[1:]
    if len(parents) > 1:
        return Twin(None, "merge commit: no patch to match")
    pid = patch_id(repo, commit)
    if pid is not None:
        hits = main.by_patch.get(pid, [])
        if len(hits) == 1:
            return Twin(hits[0], "patch-id")
        if len(hits) > 1:
            short = ", ".join(h[:7] for h in hits)
            return Twin(None, f"ambiguous: patch-id matches {short}")
    subject = git(repo, "log", "-1", "--format=%s", commit).rstrip("\n")
    same_subject = main.by_subject.get(subject, [])
    if not same_subject:
        return Twin(None, "no commit on main with the same patch or subject")
    cited = named_in(text, touched(repo, commit))
    if not cited:
        return Twin(None, "same subject on main, but no citing file names one of its files")
    ok = []
    for cand in same_subject:
        cand_files = set(touched(repo, cand))
        if all(
            f in cand_files and patch_id(repo, commit, f) == patch_id(repo, cand, f) for f in cited
        ):
            ok.append(cand)
    if len(ok) == 1:
        return Twin(ok[0], "subject+files")
    if not ok:
        return Twin(None, "same subject on main, but a cited file's diff differs")
    return Twin(None, "ambiguous: " + ", ".join(c[:7] for c in ok))


@dataclass
class Citation:
    path: str
    line: int
    token: str
    commit: str
    twin: Twin
    new: str | None
    tree_diff: int | None  # files that differ between the cited tree and the twin's


def scan(repo: Path, main_ref: str) -> list[Citation]:
    files = {p: (repo / p).read_text(encoding="utf-8") for p in scanned_files(repo)}
    tokens = {t for text in files.values() for t in TOKEN.findall(text)}
    commits = resolve(repo, tokens)
    main = index_main(repo, main_ref)
    found: list[tuple[str, int, str, str]] = []  # path, line, token, commit
    citing: dict[str, list[str]] = defaultdict(list)  # commit -> files citing it
    for path, text in files.items():
        for n, line in enumerate(text.splitlines(), 1):
            for token in dict.fromkeys(TOKEN.findall(line)):
                commit = commits.get(token)
                if commit is None or commit in main.reachable:
                    continue
                found.append((path, n, token, commit))
                if path not in citing[commit]:
                    citing[commit].append(path)
    twins: dict[str, Twin] = {}
    tree_diff: dict[str, int] = {}
    for commit, paths in citing.items():
        # One twin per commit, from every file that cites it: a summary.json names no script,
        # but the summary.md beside it does.
        twins[commit] = find_twin(repo, commit, "\n".join(files[p] for p in paths), main)
        if twins[commit].commit is not None:
            names = git(repo, "diff", "--name-only", commit, twins[commit].commit)
            tree_diff[commit] = len(names.splitlines())
    out = []
    for path, n, token, commit in found:
        twin = twins[commit]
        new = None
        if twin.commit is not None:
            width = max(7, len(token))
            new = git(repo, "rev-parse", f"--short={width}", twin.commit).strip()
        out.append(Citation(path, n, token, commit, twin, new, tree_diff.get(commit)))
    return out


def rewrite(repo: Path, cites: list[Citation]) -> list[str]:
    """Apply every mapped citation; returns the files changed."""
    by_file: dict[str, dict[str, str]] = defaultdict(dict)
    for c in cites:
        if c.new is not None:
            by_file[c.path][c.token] = c.new
    changed = []
    for path, subs in sorted(by_file.items()):
        f = repo / path
        text = f.read_text(encoding="utf-8")
        new = TOKEN.sub(lambda m, subs=subs: subs.get(m.group(0), m.group(0)), text)
        if new != text:
            f.write_text(new, encoding="utf-8")
            changed.append(path)
    return changed


def figures(repo: Path, paths: list[str]) -> list[str]:
    """PNGs beside rewritten files, with a `--redraw` command where a named script has one."""
    out = []
    for d in sorted({str(PurePosixPath(p).parent) for p in paths}):
        pngs = [p for p in git(repo, "ls-files", "--", f"{d}/*.png").splitlines() if p]
        if not pngs:
            continue
        scripts = set()
        for p in paths:
            if str(PurePosixPath(p).parent) == d:
                scripts |= set(SCRIPT.findall((repo / p).read_text(encoding="utf-8")))
        redraw = [s for s in sorted(scripts) if "--redraw" in _read(repo / s)]
        how = (
            "; ".join(f"{s} has --redraw: rebuild from that script's data files" for s in redraw)
            if redraw
            else "no --redraw: a human re-runs the script or leaves the old title"
        )
        out.extend(f"{png}: may show the old hash in its title; {how}" for png in pngs)
    return out


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def report(cites: list[Citation]) -> str:
    if not cites:
        return "Every cited commit is on main."
    groups: dict[tuple[str, str | None], list[Citation]] = defaultdict(list)
    for c in cites:
        groups[(c.token, c.new)].append(c)
    mapped = [(k, v) for k, v in groups.items() if k[1] is not None]
    unmapped = [(k, v) for k, v in groups.items() if k[1] is None]
    lines = []
    if mapped:
        lines.append("Mapped: old -> new (method; files that differ between the two trees): where")
        for (token, new), cs in mapped:
            where = ", ".join(f"{c.path}:{c.line}" for c in cs)
            c = cs[0]
            lines.append(f"  {token} -> {new} ({c.twin.method}; {c.tree_diff} differ): {where}")
    if unmapped:
        lines.append("Not mapped, left as they are: old (why): where")
        for (token, _), cs in unmapped:
            where = ", ".join(f"{c.path}:{c.line}" for c in cs)
            lines.append(f"  {token} ({cs[0].twin.method}): {where}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--main", default="origin/main", help="the branch citations must be on")
    p.add_argument("--repo", type=Path, default=Path.cwd())
    p.add_argument("--write", action="store_true", help="rewrite the files (default: dry run)")
    a = p.parse_args(argv)
    repo = Path(git(a.repo, "rev-parse", "--show-toplevel").strip())
    cites = scan(repo, a.main)
    print(report(cites))
    paths = sorted({c.path for c in cites if c.new is not None})
    if a.write:
        changed = rewrite(repo, cites)
        print(f"Rewrote {len(changed)} file(s). Read each change before committing.")
    elif paths:
        print("Dry run: nothing written. --write applies the mapped rows.")
    for line in figures(repo, paths):
        print(f"  PNG {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
