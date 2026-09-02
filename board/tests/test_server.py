"""Tests for the drydock board server.

    python3 -m unittest discover board/tests

Everything runs against a throwaway fixture queue built in setUpClass, and the
HTTP cases talk to a real server bound to an ephemeral port on 127.0.0.1.
"""

import json
import os
import sys
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import server  # noqa: E402


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def build_fixture(root: Path) -> None:
    """A queue with one item per behaviour the board has to get right."""

    # --- inbox: dependencies met vs unmet -------------------------------
    write(root / "specs/inbox/inbox-ready/SPEC.md",
          "track: report\ndepends_on: [dep-done]  # already delivered\n"
          "\n# Spec: Ready to start\n")
    write(root / "specs/inbox/inbox-waiting/SPEC.md",
          "track: code\n"
          "depends_on:\n"
          "  - dep-done          # delivered, so met\n"
          "  - never-shipped     # unmet\n"
          "  # - commented-out   # must not count\n"
          "\n# Waiting on an upstream\n")

    # --- active: plain vs handed off for review --------------------------
    write(root / "specs/active/active-plain/SPEC.md",
          "track: code\n\n# Spec: Under construction\n")
    write(root / "specs/active/active-ready/SPEC.md",
          "track: code\n\n# Handed off\n")
    write(root / "specs/active/active-ready/READY.md", "done, awaiting review\n")

    # --- blocked: explicit blocker vs TL;DR fallback ---------------------
    write(root / "specs/blocked/blocked-blocker/SPEC.md",
          "track: report\n\n# Spec: Needs a decision\n")
    write(root / "specs/blocked/blocked-blocker/QUESTION.md",
          "blocker: which datastore should this use?\n\n## TL;DR\nignored\n")
    write(root / "specs/blocked/blocked-tldr/SPEC.md",
          "track: report\n\n# No blocker field\n")
    write(root / "specs/blocked/blocked-tldr/QUESTION.md",
          "## TL;DR\n\nThe   API contract\nis ambiguous.\n\nMore prose below.\n")
    # Contract-shaped: frontmatter inside a ```yaml fence, free-form question.
    write(root / "specs/blocked/blocked-prose/SPEC.md",
          "# Spec: Fenced frontmatter\n\n"
          "```yaml\n"
          "id: blocked-prose\n"
          "track: code\n"
          "status: blocked\n"
          "depends_on: []\n"
          "```\n")
    write(root / "specs/blocked/blocked-prose/QUESTION.md",
          "# Question\n\nThe retry budget is not specified anywhere.\n\nIgnored tail.\n")

    # --- deliverables: pr, relative report, verdict ----------------------
    write(root / "deliverables/dep-done/SPEC.md", "track: code\n\n# Dependency\n")
    write(root / "deliverables/dep-done/DELIVERABLE.md",
          "pr_url: https://github.com/example/repo/pull/7\n")
    write(root / "deliverables/deliv-report/SPEC.md", "track: report\n\n# Report item\n")
    write(root / "deliverables/deliv-report/DELIVERABLE.md",
          "report_url: reports/deep.html\n")
    write(root / "deliverables/deliv-report/deep.html", "<h1>findings</h1>\n")
    write(root / "deliverables/deliv-report/notes.txt", "scratch\n")
    write(root / "deliverables/deliv-review/SPEC.md", "track: code\n\n# Reviewed item\n")
    write(root / "deliverables/deliv-review/REVIEW.md", "verdict: ship\n")
    write(root / "deliverables/deliv-review/SECRETS.md", "not in ALLOWED_FILES\n")
    write(root / "deliverables/deliv-review/.hidden.md", "dotfile\n")

    # --- archive, plus things the scanner must ignore --------------------
    write(root / "archive/arch-old/SPEC.md", "track: code\n\n# Shipped long ago\n")
    write(root / "archive/arch-untitled/SPEC.md", "notes with no heading and no track\n")
    write(root / "archive/.hidden-item/SPEC.md", "track: code\n\n# Hidden\n")
    write(root / "archive/loose-file.txt", "not an item\n")

    # A symlink out of the repo must not become a servable item file.
    outside = write(root.parent / "outside-secret.md", "leaked\n")
    os.symlink(outside, root / "archive/arch-old/ESCAPE.md")

    # Fix mtimes last — writing into a directory bumps it.
    stamps = {
        "deliverables/dep-done": 1_700_000_300,
        "deliverables/deliv-report": 1_700_000_200,
        "deliverables/deliv-review": 1_700_000_100,
    }
    for rel, when in stamps.items():
        os.utime(root / rel, (when, when))


class BoardTestCase(unittest.TestCase):
    """Fixture queue + a live server, shared by every test in the module."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = TemporaryDirectory()
        cls.root = (Path(cls._tmp.name) / "repo").resolve()
        cls.root.mkdir()
        build_fixture(cls.root)

        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), server.make_handler(cls.root))
        cls.server.daemon_threads = True
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)
        cls._tmp.cleanup()

    def get(self, path):
        """(status, body, content-type) — never raises on a 4xx."""
        try:
            with urllib.request.urlopen(self.base + path, timeout=5) as res:
                return res.status, res.read(), res.headers.get("Content-Type", "")
        except urllib.error.HTTPError as exc:
            with exc:
                return exc.code, exc.read(), exc.headers.get("Content-Type", "")

    def item(self, state, item_id):
        rows = server.scan(self.root)[state]
        matches = [r for r in rows if r["id"] == item_id]
        self.assertEqual(len(matches), 1, f"{item_id} not found in {state}")
        return matches[0]


class TestDepsParsing(unittest.TestCase):
    def test_inline_list(self):
        self.assertEqual(server.deps_of("depends_on: [alpha-1, beta-2]"),
                         ["alpha-1", "beta-2"])

    def test_inline_list_with_trailing_comment(self):
        self.assertEqual(server.deps_of("depends_on: [alpha-1]  # beta-2 is optional"),
                         ["alpha-1"])

    def test_block_list(self):
        spec = "depends_on:\n  - alpha-1\n  - beta-2\n\nnext: value\n"
        self.assertEqual(server.deps_of(spec), ["alpha-1", "beta-2"])

    def test_block_list_with_comments(self):
        spec = ("depends_on:   # upstream work\n"
                "  - alpha-1   # inline note\n"
                "  - beta-2\n")
        self.assertEqual(server.deps_of(spec), ["alpha-1", "beta-2"])

    def test_missing_key(self):
        self.assertEqual(server.deps_of("track: code\n\n# Title\n"), [])

    def test_empty_inline_list(self):
        self.assertEqual(server.deps_of("depends_on: []\n"), [])

    def test_stops_at_non_list_line(self):
        spec = "depends_on:\n  - alpha-1\nowner: someone\n  - not-a-dep\n"
        self.assertEqual(server.deps_of(spec), ["alpha-1"])


class TestFieldParsing(unittest.TestCase):
    def test_strips_quotes_and_whitespace(self):
        self.assertEqual(server.field("track:  'report'  \n", "track"), "report")
        self.assertEqual(server.field('title: "A thing"\n', "title"), "A thing")

    def test_missing_field_is_empty(self):
        self.assertEqual(server.field("track: code\n", "verdict"), "")


class TestScan(BoardTestCase):
    def test_all_states_present(self):
        state = server.scan(self.root)
        for name in server.STATES:
            self.assertIn(name, state)
        self.assertEqual(state["repo"], self.root.name)
        self.assertIsInstance(state["now_epoch"], int)

    def test_counts_skip_hidden_dirs_and_loose_files(self):
        state = server.scan(self.root)
        self.assertEqual(sorted(r["id"] for r in state["archive"]),
                         ["arch-old", "arch-untitled"])
        self.assertEqual(len(state["inbox"]), 2)
        self.assertEqual(len(state["active"]), 2)
        self.assertEqual(len(state["blocked"]), 3)
        self.assertEqual(len(state["delivered"]), 3)

    def test_newest_first(self):
        ids = [r["id"] for r in server.scan(self.root)["delivered"]]
        self.assertEqual(ids, ["dep-done", "deliv-report", "deliv-review"])

    def test_title_and_track(self):
        row = self.item("inbox", "inbox-ready")
        self.assertEqual(row["title"], "Ready to start")   # "Spec: " prefix dropped
        self.assertEqual(row["track"], "report")

    def test_title_falls_back_to_id_and_track_to_question_mark(self):
        row = self.item("archive", "arch-untitled")
        self.assertEqual(row["title"], "arch-untitled")
        self.assertEqual(row["track"], "?")

    def test_title_without_spec_prefix(self):
        self.assertEqual(self.item("active", "active-plain")["title"], "Under construction")
        self.assertEqual(self.item("archive", "arch-old")["title"], "Shipped long ago")

    def test_unmet_dependency_becomes_waiting_gist(self):
        self.assertEqual(self.item("inbox", "inbox-waiting")["gist"],
                         "waiting on: never-shipped")

    def test_met_dependencies_produce_no_gist(self):
        self.assertEqual(self.item("inbox", "inbox-ready")["gist"], "")

    def test_blocker_field_wins_over_tldr(self):
        self.assertEqual(self.item("blocked", "blocked-blocker")["gist"],
                         "which datastore should this use?")

    def test_tldr_fallback_is_collapsed_to_one_line(self):
        self.assertEqual(self.item("blocked", "blocked-tldr")["gist"],
                         "The API contract is ambiguous.")

    def test_first_paragraph_fallback_skips_headings(self):
        self.assertEqual(self.item("blocked", "blocked-prose")["gist"],
                         "The retry budget is not specified anywhere.")

    def test_frontmatter_is_read_inside_a_yaml_fence(self):
        row = self.item("blocked", "blocked-prose")
        self.assertEqual(row["track"], "code")
        self.assertEqual(row["title"], "Fenced frontmatter")

    def test_pr_url_passes_through(self):
        row = self.item("delivered", "dep-done")
        self.assertEqual(row["kind"], "pr")
        self.assertEqual(row["url"], "https://github.com/example/repo/pull/7")

    def test_relative_report_url_is_rewritten_to_item_route(self):
        row = self.item("delivered", "deliv-report")
        self.assertEqual(row["kind"], "report")
        self.assertEqual(row["url"], "/item/deliv-report/deep.html")

    def test_verdict_from_review_file(self):
        self.assertEqual(self.item("delivered", "deliv-review")["review"], "ship")

    def test_ready_marker_makes_active_item_in_review(self):
        self.assertEqual(self.item("active", "active-ready")["review"], "in-review")
        self.assertEqual(self.item("active", "active-plain")["review"], "")

    def test_files_list_is_limited_to_allowed_files(self):
        self.assertEqual(self.item("delivered", "deliv-review")["files"],
                         ["REVIEW.md", "SPEC.md"])
        self.assertEqual(self.item("delivered", "deliv-report")["files"],
                         ["DELIVERABLE.md", "SPEC.md"])

    def test_missing_state_directory_is_empty_not_an_error(self):
        with TemporaryDirectory() as tmp:
            state = server.scan(Path(tmp))
            self.assertEqual([state[s] for s in server.STATES], [[], [], [], [], []])


class TestPathGuards(BoardTestCase):
    def test_rejects_traversal_in_id_and_name(self):
        for item_id, name in [("..", "SPEC.md"),
                              ("../deliverables", "SPEC.md"),
                              ("arch-old", ".."),
                              ("arch-old", "../../SPEC.md"),
                              ("arch-old", "sub/SPEC.md")]:
            with self.subTest(item_id=item_id, name=name):
                self.assertIsNone(server.find_item_path(self.root, item_id, name))

    def test_rejects_absolute_paths(self):
        self.assertIsNone(server.find_item_path(self.root, "arch-old", "/etc/passwd"))
        self.assertIsNone(server.find_item_path(self.root, "/etc", "passwd"))

    def test_rejects_dotfiles(self):
        self.assertIsNone(server.find_item_path(self.root, "deliv-review", ".hidden.md"))
        self.assertIsNone(server.find_item_path(self.root, ".hidden-item", "SPEC.md"))

    def test_rejects_empty_components(self):
        self.assertIsNone(server.find_item_path(self.root, "", "SPEC.md"))
        self.assertIsNone(server.find_item_path(self.root, "arch-old", ""))

    def test_rejects_symlink_escaping_the_repo(self):
        self.assertTrue((self.root / "archive/arch-old/ESCAPE.md").is_symlink())
        self.assertIsNone(server.find_item_path(self.root, "arch-old", "ESCAPE.md"))

    def test_finds_a_real_file(self):
        found = server.find_item_path(self.root, "arch-old", "SPEC.md")
        self.assertIsNotNone(found)
        self.assertEqual(found, (self.root / "archive/arch-old/SPEC.md").resolve())

    def test_item_file_honours_the_allowlist(self):
        self.assertIsNone(server.item_file(self.root, "deliv-review", "SECRETS.md"))
        self.assertIsNone(server.item_file(self.root, "deliv-report", "notes.txt"))
        self.assertIn("verdict: ship", server.item_file(self.root, "deliv-review", "REVIEW.md"))

    def test_static_guard_rejects_escapes(self):
        for rel in ["../server.py", "..", "", ".hidden", "sub/app.js", "/etc/passwd"]:
            with self.subTest(rel=rel):
                self.assertIsNone(server.find_static_path(rel))
        self.assertIsNotNone(server.find_static_path("app.js"))


class TestHttp(BoardTestCase):
    def test_healthz(self):
        status, body, ctype = self.get("/healthz")
        self.assertEqual(status, 200)
        self.assertEqual(body, b"ok")
        self.assertTrue(ctype.startswith("text/plain"))

    def test_index_is_served_from_disk(self):
        status, body, ctype = self.get("/")
        self.assertEqual(status, 200)
        self.assertTrue(ctype.startswith("text/html"))
        self.assertIn(b"/static/app.js", body)

    def test_static_content_types(self):
        for path, expected in [("/static/app.js", "text/javascript"),
                               ("/static/app.css", "text/css"),
                               ("/static/favicon.svg", "image/svg+xml")]:
            with self.subTest(path=path):
                status, _, ctype = self.get(path)
                self.assertEqual(status, 200)
                self.assertTrue(ctype.startswith(expected), ctype)

    def test_api_state_is_json_and_matches_scan(self):
        status, body, ctype = self.get("/api/state")
        self.assertEqual(status, 200)
        self.assertTrue(ctype.startswith("application/json"))
        payload = json.loads(body)
        self.assertEqual([r["id"] for r in payload["delivered"]],
                         ["dep-done", "deliv-report", "deliv-review"])

    def test_api_file_returns_plain_text(self):
        status, body, ctype = self.get("/api/file?id=blocked-blocker&name=QUESTION.md")
        self.assertEqual(status, 200)
        self.assertTrue(ctype.startswith("text/plain"))
        self.assertIn(b"which datastore", body)

    def test_api_file_404s_on_disallowed_and_missing(self):
        for path in ["/api/file?id=deliv-review&name=SECRETS.md",
                     "/api/file?id=deliv-review&name=.hidden.md",
                     "/api/file?id=nope&name=SPEC.md",
                     "/api/file?id=deliv-review",
                     "/api/file"]:
            with self.subTest(path=path):
                self.assertEqual(self.get(path)[0], 404)

    def test_item_route_content_types(self):
        status, body, ctype = self.get("/item/deliv-report/deep.html")
        self.assertEqual(status, 200)
        self.assertTrue(ctype.startswith("text/html"))
        self.assertIn(b"findings", body)

        status, _, ctype = self.get("/item/arch-old/SPEC.md")
        self.assertEqual(status, 200)
        self.assertTrue(ctype.startswith("text/plain"))

    def test_item_route_rejects_other_suffixes(self):
        # notes.txt is servable (.txt), the DELIVERABLE.md sibling too — but a
        # suffix outside the item allowlist is not reachable at all.
        self.assertEqual(self.get("/item/deliv-report/notes.txt")[0], 200)
        self.assertEqual(self.get("/item/arch-old/ESCAPE.md")[0], 404)

    def test_traversal_attempts_404(self):
        for path in ["/item/../../etc/passwd",
                     "/item/%2e%2e/%2e%2e/etc/passwd",
                     "/item/arch-old/../../../etc/passwd",
                     "/item/arch-old/..%2f..%2fSPEC.md",
                     "/item/.hidden-item/SPEC.md",
                     "/item/arch-old",
                     "/api/file?id=..&name=SPEC.md",
                     "/api/file?id=..%2F..&name=SPEC.md",
                     "/api/file?id=arch-old&name=..%2FSPEC.md",
                     "/static/../server.py",
                     "/static/..%2fserver.py",
                     "/static/.hidden",
                     "/nope"]:
            with self.subTest(path=path):
                self.assertEqual(self.get(path)[0], 404, path)


if __name__ == "__main__":
    unittest.main()
