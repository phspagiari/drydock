"""Tests for the prepared pull-request text helper.

    python3 -m unittest discover board/tests

Every fixture is synthetic. The CLI runs in a subprocess for exit codes and
stderr; the functions are called directly where bytes matter.
"""

import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pr_text  # noqa: E402

SCRIPT = Path(pr_text.__file__).resolve()
FENCE = "````"
BASE = "ab" * 32

BODY = """## Description

Adds a thing.

```sh
make thing
## not a heading, a shell comment
```

## Testing

- ran it"""


def ready(title: str = "Add a thing", body: str = BODY, *, base: str | None = None,
          title_fences: int = 1, body_fences: int = 1, after: str = "") -> str:
    """A READY.md with a prepared-text section built from its parts."""
    head = f"pr_text_base: {base}\n\n" if base is not None else ""
    tf = "".join(f"{FENCE}\n{title}\n{FENCE}\n\n" for _ in range(title_fences))
    bf = "".join(f"{FENCE}\n{body}\n{FENCE}\n\n" for _ in range(body_fences))
    return ("# Ready\n\n## Criteria\n\n| # | ok |\n\n## Prepared PR text\n\n"
            f"{head}### Title\n\n{tf}### Body\n\n{bf}{after}")


def cli(*argv: str, stdin: str = "") -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), *argv], input=stdin,
                          capture_output=True, text=True, check=False)


def live(title: str, body: str, **extra) -> str:
    return json.dumps({"title": title, "body": body, **extra})


class ExtractTest(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def extract(self, text: str, *, newline: str | None = None):
        src = self.dir / "READY.md"
        with open(src, "w", encoding="utf-8", newline=newline) as f:
            f.write(text)
        t, b = self.dir / "title.txt", self.dir / "body.txt"
        done = cli("extract", str(src), "--title-out", str(t), "--body-out", str(b))
        return done, t, b

    def assert_rejects(self, text: str, rule: str):
        done, _, _ = self.extract(text)
        self.assertEqual(done.returncode, 2, done.stderr)
        self.assertIn(rule, done.stderr)
        self.assertEqual(len(done.stderr.strip().splitlines()), 1, done.stderr)

    def test_round_trip_well_formed(self):
        done, t, b = self.extract(ready(after="## Assumptions\n\n- none\n"))
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(t.read_bytes(), b"Add a thing\n")
        self.assertEqual(b.read_text(encoding="utf-8"), BODY + "\n")
        verified = cli("verify", str(t), str(b), stdin=live("Add a thing", BODY))
        self.assertEqual(verified.returncode, 0, verified.stderr)

    def test_body_with_triple_fence_and_h2_survives_byte_exact(self):
        # The body's own "## Description" / "## Testing" and its ``` fence sit
        # inside the four-backtick fence: none of them ends the section.
        title, body = pr_text.extract_text(ready())
        self.assertEqual(title, "Add a thing")
        self.assertEqual(body, BODY)
        _, _, b = self.extract(ready())
        self.assertEqual(b.read_bytes(), (BODY + "\n").encode("utf-8"))

    def test_crlf_ready_md_extracts(self):
        done, t, b = self.extract(ready(), newline="\r\n")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(t.read_bytes(), b"Add a thing\n")
        self.assertEqual(b.read_bytes(), (BODY + "\n").encode("utf-8"))

    def test_missing_section(self):
        self.assert_rejects("# Ready\n\n## Criteria\n\nnothing here\n",
                            "## Prepared PR text missing")

    def test_missing_title_heading(self):
        text = ready().replace("### Title\n", "Title:\n")
        self.assert_rejects(text, "### Title missing")

    def test_missing_body_heading(self):
        text = ready().replace("### Body\n", "Body:\n")
        self.assert_rejects(text, "### Body missing")

    def test_addendum_shape_prose_plus_one_fence_no_title(self):
        # Prose and one fence whose ### headings live inside it: an addendum
        # for someone to paste, not a title and body to apply.
        text = ("# Ready\n\n## Prepared PR text\n\nAn optional addendum to the "
                "existing description; nothing here posts it.\n\n"
                f"{FENCE}\n### Title\n\nsomething\n\n### Body\n\nmore\n{FENCE}\n")
        self.assert_rejects(text, "### Title missing")

    def test_title_zero_fences(self):
        self.assert_rejects(ready(title_fences=0), "### Title: 0 fences")

    def test_title_two_fences(self):
        self.assert_rejects(ready(title_fences=2), "### Title: 2 fences")

    def test_body_zero_fences(self):
        self.assert_rejects(ready(body_fences=0), "### Body: 0 fences")

    def test_body_two_fences(self):
        self.assert_rejects(ready(body_fences=2), "### Body: 2 fences")

    def test_body_three_backtick_fence(self):
        text = ready().replace(f"### Body\n\n{FENCE}\n", "### Body\n\n```\n", 1)
        text = text.replace(f"- ran it\n{FENCE}\n", "- ran it\n```\n", 1)
        self.assert_rejects(text, "### Body: fence opens with 3 backticks")

    def test_body_fence_not_closed(self):
        text = ready().rsplit(FENCE, 1)[0]
        self.assert_rejects(text, "### Body: fence not closed")

    def test_title_empty(self):
        self.assert_rejects(ready(title="   "), "title is empty")

    def test_title_multi_line(self):
        self.assert_rejects(ready(title="Add a thing\nand another"),
                            "title spans 2 lines")

    def test_section_ends_at_next_h2_outside_fence(self):
        # A ### Body after the section's end is not the section's.
        text = ready().replace("### Body\n", "## Next\n\n### Body\n")
        self.assert_rejects(text, "### Body missing")


class BaseTest(unittest.TestCase):
    def run_base(self, text: str) -> subprocess.CompletedProcess:
        with TemporaryDirectory() as tmp:
            src = Path(tmp) / "READY.md"
            src.write_text(text, encoding="utf-8")
            return cli("base", str(src))

    def test_base_valid(self):
        done = self.run_base(ready(base=BASE))
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout, BASE + "\n")

    def test_base_missing(self):
        done = self.run_base(ready())
        self.assertEqual(done.returncode, 2)
        self.assertIn("pr_text_base missing", done.stderr)

    def test_base_malformed(self):
        for bad in ("AB" * 32, "ab" * 31, "zz" * 32, ""):
            with self.subTest(value=bad):
                done = self.run_base(ready(base=bad))
                self.assertEqual(done.returncode, 2)
                self.assertIn("not 64 lowercase hex", done.stderr)

    def test_base_repeated_or_after_title(self):
        twice = ready(base=BASE).replace("### Title", f"pr_text_base: {BASE}\n\n### Title")
        after = ready().replace("### Body", f"pr_text_base: {BASE}\n\n### Body")
        for text, rule in ((twice, "appears 2 times"), (after, "must precede")):
            with self.subTest(rule=rule):
                done = self.run_base(text)
                self.assertEqual(done.returncode, 2)
                self.assertIn(rule, done.stderr)

    def test_base_inside_a_fence_does_not_count(self):
        text = ready(body=f"pr_text_base: {BASE}\n\ntext")
        done = self.run_base(text)
        self.assertEqual(done.returncode, 2)
        self.assertIn("pr_text_base missing", done.stderr)


class DigestVerifyTest(unittest.TestCase):
    def digest(self, stdin: str) -> str:
        done = cli("digest", stdin=stdin)
        self.assertEqual(done.returncode, 0, done.stderr)
        return done.stdout.strip()

    def test_digest_stable_across_crlf_and_trailing_newline(self):
        plain = self.digest(live("T", "a\nb"))
        want = hashlib.sha256(b"T\n\x00\na\nb").hexdigest()
        self.assertEqual(plain, want)
        for body in ("a\nb\n", "a\r\nb", "a\r\nb\r\n", "a\nb\n\n"):
            with self.subTest(body=body):
                self.assertEqual(self.digest(live("T", body)), plain)
        self.assertEqual(self.digest(live("T", "a\nb", commits=[{"oid": "x"}])), plain)

    def test_digest_changes_on_one_byte(self):
        self.assertNotEqual(self.digest(live("T", "a\nb")),
                            self.digest(live("T", "a\nc")))
        self.assertNotEqual(self.digest(live("T", "a\nb")),
                            self.digest(live("U", "a\nb")))

    def test_digest_rejects_bad_json(self):
        for stdin in ("not json", "[]", json.dumps({"title": "T"}),
                      json.dumps({"title": "T", "body": None})):
            with self.subTest(stdin=stdin):
                done = cli("digest", stdin=stdin)
                self.assertEqual(done.returncode, 2)

    def files(self, tmp: str, title: str, body: str) -> tuple[str, str]:
        t, b = Path(tmp) / "t", Path(tmp) / "b"
        t.write_text(title, encoding="utf-8")
        b.write_text(body, encoding="utf-8")
        return str(t), str(b)

    def test_verify_match_tolerates_trailing_newline(self):
        with TemporaryDirectory() as tmp:
            t, b = self.files(tmp, "Add a thing\n", BODY + "\n")
            done = cli("verify", t, b, stdin=live("Add a thing", BODY))
            self.assertEqual(done.returncode, 0, done.stderr)
            done = cli("verify", t, b,
                       stdin=live("Add a thing", BODY.replace("\n", "\r\n") + "\r\n"))
            self.assertEqual(done.returncode, 0, done.stderr)

    def test_verify_mismatch_exits_1_with_diff(self):
        with TemporaryDirectory() as tmp:
            t, b = self.files(tmp, "Add a thing\n", BODY + "\n")
            done = cli("verify", t, b, stdin=live("Add a thing", BODY + "\nappended"))
            self.assertEqual(done.returncode, 1)
            self.assertIn("+appended", done.stderr)
            self.assertIn("body (pull request)", done.stderr)
            done = cli("verify", t, b, stdin=live("Other", BODY))
            self.assertEqual(done.returncode, 1)
            self.assertIn("-Add a thing", done.stderr)

    def test_verify_unreadable_file_exits_2(self):
        done = cli("verify", "/nonexistent/t", "/nonexistent/b", stdin=live("T", "b"))
        self.assertEqual(done.returncode, 2)


if __name__ == "__main__":
    unittest.main()
