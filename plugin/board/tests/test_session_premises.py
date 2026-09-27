"""The shell and git behaviour DISPATCH.md's *Every session* section rests on.

    python3 -m unittest discover board/tests

The contract tells background sessions to write ``rm -f`` rather than trust
``rm``, to use ``git rm`` / ``git mv`` in a git-tracked state directory, and
to check that a directory ``git mv`` has no existing destination. Each of
those rules is a claim about how the tools behave, and this module reproduces
every claim in a scratch directory, so the day a tool changes, a test fails
and the rule is revisited on purpose rather than silently going wrong.

Commands run under ``bash`` with ``expand_aliases`` and the ``-i`` aliases a
real operator's shell carries, with stdin at ``/dev/null`` -- no TTY, which is
what a background session has. Effects are asserted everywhere. Exit codes
are asserted only on macOS, where the contract's failures were observed: GNU
and BSD ``-i`` exit statuses may differ, and the effect is what matters.
"""

import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

DARWIN = sys.platform == "darwin"

ALIASES = "shopt -s expand_aliases\nalias rm='rm -vi'\nalias cp='cp -vi'\nalias mv='mv -vi'\n"

#: Keep the operator's own git configuration out of the fixtures, and never
#: write to it: identity is set per repository below.
GIT_ENV = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull,
           "GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0"}


def sh(cwd: Path, command: str) -> subprocess.CompletedProcess:
    """Run ``command`` under bash with the ``-i`` aliases active and no TTY.

    The aliases are defined on lines before the command: bash expands an
    alias only on a line read after its definition.
    """
    with TemporaryDirectory() as scratch, open(os.devnull) as devnull:
        # Outside ``cwd``, so a fixture repository never sees the script.
        script = Path(scratch) / "premise.sh"
        script.write_text(ALIASES + command + "\n")
        return subprocess.run(["bash", str(script)], cwd=cwd, stdin=devnull,
                              capture_output=True, text=True, env=GIT_ENV,
                              timeout=30, check=False)


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                          text=True, env=GIT_ENV, check=True).stdout


def new_repo(root: Path) -> Path:
    repo = root / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "Premise Test")
    git(repo, "config", "user.email", "premise@example.invalid")
    git(repo, "config", "commit.gpgsign", "false")
    return repo


def commit_all(repo: Path) -> None:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "fixture")


class AliasPremisesTest(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_aliased_rm_without_a_tty_leaves_the_file(self):
        victim = self.dir / "victim"
        victim.write_text("still here\n")
        proc = sh(self.dir, "rm victim")
        self.assertTrue(victim.exists(), "an -i alias with no TTY must decline")
        if DARWIN:
            self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_aliased_mv_onto_an_existing_file_leaves_both(self):
        (self.dir / "src").write_text("source\n")
        (self.dir / "dst").write_text("destination\n")
        proc = sh(self.dir, "mv src dst")
        self.assertEqual((self.dir / "src").read_text(), "source\n")
        self.assertEqual((self.dir / "dst").read_text(), "destination\n")
        if DARWIN:
            self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_rm_f_under_the_alias_removes_the_file(self):
        victim = self.dir / "victim"
        victim.write_text("gone\n")
        proc = sh(self.dir, "rm -f victim")
        self.assertFalse(victim.exists(), proc.stderr)
        if DARWIN:
            self.assertEqual(proc.returncode, 0, proc.stderr)


class GitVerbPremisesTest(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.repo = new_repo(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def test_git_rm_under_the_alias_removes_and_stages(self):
        (self.repo / "victim").write_text("tracked\n")
        commit_all(self.repo)
        proc = sh(self.repo, "git rm -q victim")
        self.assertFalse((self.repo / "victim").exists(), proc.stderr)
        self.assertEqual(git(self.repo, "status", "--porcelain"), "D  victim\n")
        if DARWIN:
            self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_git_mv_of_a_file_onto_an_existing_file_fails(self):
        (self.repo / "src").write_text("source\n")
        (self.repo / "dst").write_text("destination\n")
        commit_all(self.repo)
        proc = sh(self.repo, "git mv src dst")
        self.assertEqual((self.repo / "src").read_text(), "source\n")
        self.assertEqual((self.repo / "dst").read_text(), "destination\n")
        self.assertEqual(git(self.repo, "status", "--porcelain"), "")
        if DARWIN:
            self.assertEqual(proc.returncode, 128, proc.stderr)

    def test_git_mv_of_a_directory_onto_an_existing_directory_nests(self):
        # The case the contract's absent-destination check exists for. If a
        # future git refuses this loudly, this test fails and the rule is
        # revisited deliberately.
        (self.repo / "a/x").mkdir(parents=True)
        (self.repo / "a/x/SPEC.md").write_text("moving\n")
        (self.repo / "b/x").mkdir(parents=True)
        (self.repo / "b/x/SPEC.md").write_text("already there\n")
        commit_all(self.repo)
        proc = sh(self.repo, "git mv a/x b/x")
        self.assertEqual((self.repo / "b/x/x/SPEC.md").read_text(), "moving\n",
                         proc.stderr)
        self.assertEqual((self.repo / "b/x/SPEC.md").read_text(), "already there\n")
        self.assertFalse((self.repo / "a/x").exists())
        if DARWIN:
            self.assertEqual(proc.returncode, 0, proc.stderr)


if __name__ == "__main__":
    unittest.main()
