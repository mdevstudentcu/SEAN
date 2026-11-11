"""`analysis/recite.py` (#215, REQ-10): citations re-pointed after a rebase-merge.

Each test builds a small git repo in a temp folder with fixed dates, so its hashes are the same
on every run.
"""

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

_PATH = Path(__file__).parents[1] / "analysis" / "recite.py"
_spec = importlib.util.spec_from_file_location("recite", _PATH)
recite = importlib.util.module_from_spec(_spec)
sys.modules["recite"] = recite
_spec.loader.exec_module(recite)

DOC = "analysis/results/study/summary.md"
_ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
}
_tick = [0]


def git(repo: Path, *args: str) -> str:
    _tick[0] += 1
    when = f"2026-11-11T00:00:{_tick[0] % 60:02d}Z"
    env = {**os.environ, **_ENV, "GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when}
    return subprocess.run(
        ["git", "-c", "commit.gpgsign=false", *args],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def commit(repo: Path, subject: str, files: dict[str, str]) -> str:
    for name, text in files.items():
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text(text)
        git(repo, "add", name)
    git(repo, "commit", "-q", "-m", subject)
    return git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _tick[0] = 0
    git(tmp_path, "init", "-q", "-b", "main")
    commit(tmp_path, "chore: start", {"README.md": "index\n", "a.py": "A = 1\n"})
    return tmp_path


def branch_commit(repo: Path, subject: str, files: dict[str, str]) -> str:
    """A commit on a PR branch off `main`; `main` is checked out again after."""
    git(repo, "checkout", "-q", "-b", f"pr-{_tick[0]}", "main")
    sha = commit(repo, subject, files)
    git(repo, "checkout", "-q", "main")
    return sha


def cite(repo: Path, text: str, png: bytes | None = None) -> None:
    files = {DOC: text}
    commit(repo, "docs: cite", files)
    if png is not None:
        (repo / "analysis/results/study/fig.png").write_bytes(png)
        git(repo, "add", "analysis/results/study/fig.png")
        git(repo, "commit", "-q", "-m", "docs: figure")


def test_rebased_commit_maps_by_patch_id_req10(repo):
    old = branch_commit(repo, "feat: add b", {"b.py": "B = 2\n"})
    commit(repo, "feat: unrelated", {"c.py": "C = 3\n"})  # main moves on before the merge
    git(repo, "cherry-pick", old)  # "Rebase and merge": same patch, new hash
    new = git(repo, "rev-parse", "HEAD")
    assert new != old
    cite(repo, f"Computed at `{old[:7]}-dirty`; commit field {old[:12]}.\n")

    cites = recite.scan(repo, "main")
    assert {(c.token, c.new, c.twin.method) for c in cites} == {
        (old[:7], new[:7], "patch-id"),
        (old[:12], new[:12], "patch-id"),
    }
    assert recite.rewrite(repo, cites) == [DOC]
    text = (repo / DOC).read_text()
    assert text == f"Computed at `{new[:7]}-dirty`; commit field {new[:12]}.\n"
    assert recite.scan(repo, "main") == []  # a second run finds nothing left


def test_same_subject_alone_never_maps(repo):
    old = branch_commit(repo, "feat: add b", {"b.py": "B = 2\n"})
    commit(repo, "feat: add b", {"b.py": "B = 20\n"})  # same subject, different change
    cite(repo, f"Computed with `b.py` at {old}.\n")

    (c,) = recite.scan(repo, "main")
    assert c.new is None
    assert "diff differs" in c.twin.method
    assert recite.rewrite(repo, [c]) == []
    assert old in (repo / DOC).read_text()


def test_subject_match_needs_a_named_file(repo):
    old = branch_commit(repo, "feat: add b", {"b.py": "B = 2\n", "README.md": "index\nb\n"})
    # On main the README took a conflict resolution, so the patch differs; b.py is identical.
    commit(repo, "feat: add b", {"b.py": "B = 2\n", "README.md": "index\nb, merged\n"})
    new = git(repo, "rev-parse", "HEAD")

    cite(repo, f"Ran at {old}.\n")  # names no file the commit touches
    (c,) = recite.scan(repo, "main")
    assert c.new is None and "names one of its files" in c.twin.method

    cite(repo, f"`python b.py` at {old}.\n")  # names b.py, whose diff is identical
    (c,) = recite.scan(repo, "main")
    assert (c.new, c.twin.method) == (new[:40], "subject+files")


def test_ambiguous_patch_id_is_reported_not_guessed(repo):
    old = branch_commit(repo, "feat: add b", {"b.py": "B = 2\n"})
    git(repo, "cherry-pick", old)
    git(repo, "rm", "-q", "b.py")
    git(repo, "commit", "-q", "-m", "drop b")
    git(repo, "cherry-pick", old)  # the same patch lands on main twice
    cite(repo, f"At {old}.\n")

    (c,) = recite.scan(repo, "main")
    assert c.new is None and c.twin.method.startswith("ambiguous")


def test_reachable_hashes_and_non_commits_are_left_alone(repo):
    on_main = git(repo, "rev-parse", "HEAD")
    blob = git(repo, "rev-parse", "HEAD:a.py")
    cite(repo, f"At {on_main[:7]} and {on_main}; blob {blob}; number 1234567; deadbee.\n")
    before = (repo / DOC).read_text()

    assert recite.scan(repo, "main") == []
    assert recite.main(["--repo", str(repo), "--main", "main", "--write"]) == 0
    assert (repo / DOC).read_text() == before


def test_png_is_listed_never_rewritten(repo, capsys):
    old = branch_commit(repo, "feat: add b", {"b.py": "B = 2\n"})
    git(repo, "cherry-pick", old)
    png = b"\x89PNG\r\n\x1a\n" + old[:7].encode()
    cite(repo, f"Figure at {old[:7]}.\n", png=png)

    assert recite.main(["--repo", str(repo), "--main", "main"]) == 0  # dry run
    out = capsys.readouterr().out
    assert old[:7] in (repo / DOC).read_text()  # dry run writes nothing
    assert "analysis/results/study/fig.png" in out

    assert recite.main(["--repo", str(repo), "--main", "main", "--write"]) == 0
    assert old[:7] not in (repo / DOC).read_text()
    assert (repo / "analysis/results/study/fig.png").read_bytes() == png


def test_token_takes_all_digit_hashes_not_decimals():
    text = "fit from `0276028`; σ 0.1234567 m; at abc1234. deadbeef0123x"
    assert recite.TOKEN.findall(text) == ["0276028", "abc1234"]
