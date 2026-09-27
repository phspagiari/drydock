"""The chained preflight in both directions, and the preflight window (DISPATCH 5, 7).

    python3 -m unittest discover plugin/board/tests

Throwaway local repositories only: a bare "origin", the dispatcher's clone,
and a second clone standing in for a human pushing to the same branch.
Nothing reads the host's git configuration or touches a network remote.
"""

import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent))
import liveness_rules as rules  # noqa: E402

BRANCH = "feature"


class Repos:
    def __init__(self, root: Path):
        self.root = root
        home = root / "home"
        home.mkdir()
        self.env = {**os.environ, "HOME": str(home), "GIT_CONFIG_NOSYSTEM": "1",
                    "GIT_CONFIG_GLOBAL": os.devnull, "GIT_TERMINAL_PROMPT": "0"}
        self.origin = root / "origin.git"
        self.git(root, "init", "-q", "--bare", "-b", "main", str(self.origin))
        seed = self.clone("seed")
        self.commit(seed, "base")
        self.git(seed, "push", "-q", "origin", "HEAD:refs/heads/main",
                 f"HEAD:refs/heads/{BRANCH}")
        self.local = self.clone("local")   # the dispatcher's target_repo
        self.human = self.clone("human")   # someone else pushing to the branch

    def git(self, cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        return subprocess.run(["git", *args], cwd=cwd, env=self.env, capture_output=True,
                              text=True, check=check, stdin=subprocess.DEVNULL)

    def clone(self, name: str) -> Path:
        path = self.root / name
        self.git(self.root, "clone", "-q", str(self.origin), str(path))
        for key, value in (("user.name", "t"), ("user.email", "t@example.invalid"),
                           ("commit.gpgsign", "false")):
            self.git(path, "config", key, value)
        return path

    def commit(self, repo: Path, msg: str) -> str:
        self.git(repo, "commit", "-q", "--allow-empty", "-m", msg)
        return self.git(repo, "rev-parse", "HEAD").stdout.strip()

    def track(self, repo: Path) -> None:
        self.git(repo, "fetch", "-q", "origin")
        self.git(repo, "checkout", "-q", "-B", BRANCH, f"origin/{BRANCH}")

    def human_pushes(self, n: int) -> None:
        self.track(self.human)
        for i in range(n):
            self.commit(self.human, f"human {i}")
        self.git(self.human, "push", "-q", "origin", BRANCH)

    def symmetric(self, repo: Path) -> subprocess.CompletedProcess:
        return self.git(repo, "rev-list", "--left-right", "--count",
                        f"{BRANCH}...origin/{BRANCH}", check=False)

    def behind_only(self, repo: Path) -> str:
        return self.git(repo, "rev-list", "--count", f"{BRANCH}..origin/{BRANCH}").stdout.strip()


class BranchDriftTest(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.r = Repos(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def test_in_sync(self):
        self.r.track(self.r.local)
        self.assertEqual(self.r.symmetric(self.r.local).stdout, "0\t0\n")

    def test_ahead_is_invisible_to_the_old_form_and_caught_by_the_new(self):
        self.r.track(self.r.local)
        self.r.commit(self.r.local, "unpushed wip")
        self.assertEqual(self.r.behind_only(self.r.local), "0")  # the old check passes it
        self.assertEqual(self.r.symmetric(self.r.local).stdout, "1\t0\n")
        # the escalation names the commit rather than a count
        log = self.r.git(self.r.local, "log", "--oneline", f"origin/{BRANCH}..{BRANCH}").stdout
        self.assertIn("unpushed wip", log)

    def test_behind(self):
        self.r.track(self.r.local)
        self.r.human_pushes(2)
        self.r.git(self.r.local, "fetch", "-q", "origin")
        self.assertEqual(self.r.symmetric(self.r.local).stdout, "0\t2\n")
        self.assertEqual(self.r.behind_only(self.r.local), "2")
        log = self.r.git(self.r.local, "log", "--oneline", f"{BRANCH}..origin/{BRANCH}").stdout
        self.assertEqual(len(log.splitlines()), 2)

    def test_diverged(self):
        self.r.track(self.r.local)
        self.r.commit(self.r.local, "unpushed wip")
        self.r.human_pushes(2)
        self.r.git(self.r.local, "fetch", "-q", "origin")
        self.assertEqual(self.r.symmetric(self.r.local).stdout, "1\t2\n")

    def test_no_local_ref_exits_128_so_the_checks_cannot_collapse(self):
        self.r.git(self.r.local, "fetch", "-q", "origin")
        self.assertNotEqual(self.r.git(self.r.local, "rev-parse", "--verify", "--quiet",
                                       f"refs/heads/{BRANCH}", check=False).returncode, 0)
        out = self.r.symmetric(self.r.local)
        self.assertEqual(out.returncode, 128)
        self.assertIn("ambiguous argument", out.stderr)


class PreflightWindowTest(unittest.TestCase):
    """A push between preflight's fetch and ``git worktree add``."""

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.r = Repos(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def preflight(self) -> str:
        self.r.git(self.r.local, "fetch", "-q", "origin")
        return self.r.git(self.r.local, "rev-parse", f"origin/{BRANCH}").stdout.strip()

    def worktree_head(self) -> str:
        path = self.r.root / "wt"
        self.r.git(self.r.local, "worktree", "add", "-q", str(path), BRANCH)
        return self.r.git(path, "rev-parse", "HEAD").stdout.strip()

    def ls_remote(self) -> str:
        """The remote as it is at cut time — no fetch, nothing local changes."""
        out = self.r.git(self.r.local, "ls-remote", "origin", f"refs/heads/{BRANCH}").stdout
        return out.split()[0]

    def tracking(self) -> str:
        return self.r.git(self.r.local, "rev-parse", f"origin/{BRANCH}").stdout.strip()

    def test_push_inside_the_window_is_detected_without_any_fetch(self):
        # Nothing fetches between step 5 and `git worktree add`,
        # so HEAD alone cannot see this push. ls-remote can.
        preflight_sha = self.preflight()
        self.r.human_pushes(1)
        head = self.worktree_head()
        self.assertEqual(self.tracking(), preflight_sha, "a fetch ran inside the window")
        self.assertEqual(head, preflight_sha, "HEAD alone is blind to the push")
        remote = self.ls_remote()
        self.assertNotEqual(remote, preflight_sha)
        self.assertEqual(rules.base_check(preflight_sha, head, remote, revalidated=False),
                         "revalidate")

    def test_local_ref_moved_inside_the_window_is_detected_by_head(self):
        self.r.track(self.r.local)
        preflight_sha = self.preflight()
        self.r.commit(self.r.local, "moved locally inside the window")
        self.r.git(self.r.local, "checkout", "-q", "--detach")
        head = self.worktree_head()
        remote = self.ls_remote()
        self.assertEqual(remote, preflight_sha)
        self.assertNotEqual(head, preflight_sha)
        self.assertEqual(rules.base_check(preflight_sha, head, remote, revalidated=False),
                         "revalidate")

    def test_nothing_moved_is_no_false_positive(self):
        preflight_sha = self.preflight()
        head, remote = self.worktree_head(), self.ls_remote()
        self.assertEqual((head, remote), (preflight_sha, preflight_sha))
        self.assertEqual(rules.base_check(preflight_sha, head, remote, revalidated=False),
                         "proceed")

    def test_non_chained_push_to_main_is_revalidated_repointed_and_proceeds(self):
        # A spec without `branch:`: preflight reads origin/main, step 7 cuts a
        # fresh branch from it, and a push to main lands in the window.
        def default_preflight() -> str:
            self.r.git(self.r.local, "fetch", "-q", "origin")
            return self.r.git(self.r.local, "rev-parse", "origin/main").stdout.strip()

        def main_remote() -> str:
            return self.r.git(self.r.local, "ls-remote", "origin",
                              "refs/heads/main").stdout.split()[0]

        def pushes_to_main() -> None:
            self.r.git(self.r.human, "fetch", "-q", "origin")
            self.r.git(self.r.human, "checkout", "-q", "-B", "main", "origin/main")
            self.r.commit(self.r.human, "benign push to main")
            self.r.git(self.r.human, "push", "-q", "origin", "main")

        preflight_sha = default_preflight()
        path = self.r.root / "wt"
        self.r.git(self.r.local, "worktree", "add", "-q", "-b", "drydock-x", str(path),
                   preflight_sha)
        pushes_to_main()
        head = self.r.git(path, "rev-parse", "HEAD").stdout.strip()
        self.assertEqual(rules.base_check(preflight_sha, head, main_remote(),
                                          revalidated=False), "revalidate")
        fresh = default_preflight()
        self.assertNotEqual(fresh, preflight_sha)
        # Without the re-point HEAD stays at the old sha, and a benign push
        # escalates.
        self.assertEqual(rules.base_check(fresh, head, main_remote(), revalidated=True),
                         "escalate")
        # With it, the second comparison agrees.
        self.r.git(path, "reset", "-q", "--hard", fresh)
        head = self.r.git(path, "rev-parse", "HEAD").stdout.strip()
        self.assertEqual(rules.base_check(fresh, head, main_remote(), revalidated=True),
                         "proceed")
        # A second move in the same dispatch still escalates.
        pushes_to_main()
        self.assertEqual(rules.base_check(fresh, head, main_remote(), revalidated=True),
                         "escalate")

    def test_second_mismatch_escalates_without_revalidating(self):
        self.assertEqual(rules.base_check("aaa", "bbb", "aaa", revalidated=True), "escalate")
        self.assertEqual(rules.base_check("aaa", "aaa", "bbb", revalidated=True), "escalate")


if __name__ == "__main__":
    unittest.main()
