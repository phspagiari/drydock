#!/usr/bin/env python3
"""drydock board — live queue dashboard for a drydock STATE_HOME.

    board/server.py serve [--port 8642] [--root <state-home>]

Serves a static frontend from ``board/static/`` plus a small JSON API. Queue
state is read from disk on every request: no cache, no background daemon, no
regeneration step — what you see is what is on disk right now.

Standard library only, on purpose: no install step and no dependency surface.

The socket binds 127.0.0.1 only. This is a local tool and serves file contents
from the STATE_HOME it is pointed at; do not expose it.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

DEFAULT_PORT = 8642

#: Item files the API will hand out. Anything else in an item directory stays
#: private, whatever the request asks for.
ALLOWED_FILES = frozenset({
    "SPEC.md", "QUESTION.md", "DELIVERABLE.md", "RUN.md",
    "REJECTION.md", "REPORT.md", "REVIEW.md", "READY.md",
})

#: Queue states, in the order the board presents them.
STATES = ("blocked", "delivered", "active", "inbox", "archive")

#: Suffixes servable from an item directory over ``/item/<id>/<file>``.
ITEM_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".md": "text/plain; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
}

STATIC_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".woff2": "font/woff2",
}

STATIC_DIR = Path(__file__).resolve().parent / "static"


# --------------------------------------------------------------------------
# queue parsing
# --------------------------------------------------------------------------

def read_text(path: Path) -> str:
    try:
        return path.read_text(errors="replace")
    except OSError:
        return ""


def field(text: str, key: str) -> str:
    """Value of a yaml-ish ``key: value`` line, quotes stripped."""
    m = re.search(rf"^\s*{re.escape(key)}:\s*(.+?)\s*$", text, re.M)
    return m.group(1).strip("'\"") if m else ""


def deps_of(spec: str) -> list[str]:
    """``depends_on`` ids — inline ``[a, b]`` or YAML block list, comments stripped."""
    m = re.search(r"^depends_on:[ \t]*(\[[^\]\n]*\])?[ \t]*(?:#[^\n]*)?"
                  r"((?:\n[ \t]*-[ \t]*[^\n]+)*)", spec, re.M)
    if not m:
        return []
    ids = re.findall(r"[\w][\w.-]{3,}", (m.group(1) or "").split("#")[0])
    for line in (m.group(2) or "").splitlines():
        mm = re.search(r"-[ \t]*([\w][\w.-]{3,})", line.split("#")[0])
        if mm:
            ids.append(mm.group(1))
    return ids


def state_dir(root: Path, state: str) -> Path:
    if state == "delivered":
        return root / "deliverables"
    if state == "archive":
        return root / "archive"
    return root / "specs" / state


def _title_of(spec: str, fallback: str) -> str:
    m = re.search(r"^#\s+(?:Spec:\s*)?(.+)$", spec, re.M)
    return m.group(1).strip() if m else fallback


def _question_gist(question: str) -> str:
    """The one line a blocked card shows. QUESTION.md has no fixed shape, so:
    an explicit ``blocker:`` field, else the TL;DR, else its first paragraph."""
    explicit = field(question, "blocker")
    if explicit:
        return explicit
    section = re.search(r"##\s*TL;DR\s*\n+(.+?)(?:\n\n|\Z)", question, re.S)
    if section:
        return re.sub(r"\s+", " ", section.group(1)).strip()[:280]
    for para in re.split(r"\n\s*\n", question):
        para = para.strip()
        if para and not para.startswith(("#", "```", "---", "<!--")):
            return re.sub(r"\s+", " ", para)[:280]
    return ""


def _gist_of(root: Path, state: str, spec: str, question: str) -> str:
    """One line of context: the blocker, or the dependencies still unmet."""
    if state == "blocked":
        return _question_gist(question)
    if state == "inbox":
        unmet = [d for d in deps_of(spec)
                 if not ((root / "deliverables" / d).is_dir()
                         or (root / "archive" / d).is_dir())]
        if unmet:
            return "waiting on: " + ", ".join(unmet)
    return ""


def scan_item(root: Path, item: Path, state: str) -> dict:
    spec = read_text(item / "SPEC.md")
    deliverable = read_text(item / "DELIVERABLE.md")
    question = read_text(item / "QUESTION.md") if state == "blocked" else ""

    pr = field(deliverable, "pr_url")
    url = pr or field(deliverable, "report_url")
    if url and not url.startswith(("http://", "https://")):
        # A repo-relative report path is only reachable through the item route.
        url = f"/item/{item.name}/{Path(url).name}"

    verdict = field(read_text(item / "REVIEW.md"), "verdict")
    if not verdict and state == "active" and (item / "READY.md").is_file():
        verdict = "in-review"

    return {
        "id": item.name,
        "title": _title_of(spec, item.name),
        "track": field(spec, "track") or "?",
        "mtime": int(item.stat().st_mtime),
        "gist": _gist_of(root, state, spec, question),
        "kind": "pr" if pr else ("report" if url else ""),
        "url": url,
        "review": verdict,
        "files": sorted(f.name for f in item.iterdir()
                        if f.is_file() and f.name in ALLOWED_FILES),
    }


def scan(root: Path) -> dict:
    """Full queue state, read fresh from disk."""
    out: dict = {}
    for state in STATES:
        base = state_dir(root, state)
        rows = []
        if base.is_dir():
            items = [d for d in base.iterdir()
                     if d.is_dir() and not d.name.startswith(".")]
            # Newest first, id as the tiebreak so equal mtimes stay deterministic.
            items.sort(key=lambda p: (-p.stat().st_mtime, p.name))
            rows = [scan_item(root, d, state) for d in items]
        out[state] = rows
    now = datetime.now().astimezone()
    out["now"] = now.strftime("%Y-%m-%d %H:%M:%S %Z").strip()
    out["now_epoch"] = int(now.timestamp())
    out["repo"] = root.name
    return out


# --------------------------------------------------------------------------
# path guards
# --------------------------------------------------------------------------

def safe_component(value: str) -> bool:
    """True for a single, non-hidden path component with no traversal in it."""
    return bool(value) and not value.startswith(".") and value == Path(value).name \
        and "\\" not in value and "\x00" not in value


def _under(path: Path, base: Path) -> bool:
    try:
        return path.resolve().is_relative_to(base.resolve())
    except (OSError, ValueError):
        return False


def find_item_path(root: Path, item_id: str, name: str) -> Path | None:
    """Resolve ``<state>/<item_id>/<name>`` to a real file inside ``root``."""
    if not safe_component(item_id) or not safe_component(name):
        return None
    for state in STATES:
        candidate = state_dir(root, state) / item_id / name
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if not resolved.is_file():
            continue
        # Belt and braces: the resolved file must still live inside the repo
        # (kills symlinks pointing out) and inside the item directory it named.
        if not _under(resolved, root):
            continue
        if resolved.parent.name != item_id:
            continue
        return resolved
    return None


def item_file(root: Path, item_id: str, name: str) -> str | None:
    if name not in ALLOWED_FILES:
        return None
    path = find_item_path(root, item_id, name)
    return read_text(path) if path else None


def find_static_path(rel: str) -> Path | None:
    """Resolve a ``/static/<name>`` request against ``board/static/``."""
    if not safe_component(rel):
        return None
    candidate = STATIC_DIR / rel
    if not candidate.is_file() or not _under(candidate, STATIC_DIR):
        return None
    return candidate.resolve()


# --------------------------------------------------------------------------
# http
# --------------------------------------------------------------------------

class BoardHandler(BaseHTTPRequestHandler):
    """Read-only HTTP surface. ``root`` is injected by :func:`make_handler`."""

    root: Path = Path.cwd()
    server_version = "drydock-board"
    sys_version = ""

    def log_message(self, *args):  # keep the terminal for the operator
        pass

    def send_payload(self, code: int, body, ctype: str = "text/plain; charset=utf-8"):
        data = body if isinstance(body, bytes) else str(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def not_found(self):
        self.send_payload(404, "not found")

    def do_GET(self):
        url = urlparse(self.path)
        path = unquote(url.path)

        if path == "/" or path == "/index.html":
            return self.serve_static("index.html")
        if path == "/healthz":
            return self.send_payload(200, "ok")
        if path == "/api/state":
            return self.send_payload(200, json.dumps(scan(self.root)),
                                     "application/json")
        if path == "/api/file":
            query = parse_qs(url.query)
            body = item_file(self.root,
                             query.get("id", [""])[0],
                             query.get("name", [""])[0])
            if body is None:
                return self.not_found()
            return self.send_payload(200, body)
        if path.startswith("/static/"):
            return self.serve_static(path[len("/static/"):])
        if path.startswith("/item/"):
            return self.serve_item(path)
        return self.not_found()

    do_HEAD = do_GET

    def serve_item(self, path: str):
        parts = path.split("/", 3)  # ['', 'item', '<id>', '<name>']
        if len(parts) != 4:
            return self.not_found()
        resolved = find_item_path(self.root, parts[2], parts[3])
        if resolved is None or resolved.suffix not in ITEM_TYPES:
            return self.not_found()
        self.send_payload(200, resolved.read_bytes(), ITEM_TYPES[resolved.suffix])

    def serve_static(self, rel: str):
        resolved = find_static_path(rel)
        if resolved is None:
            return self.not_found()
        ctype = STATIC_TYPES.get(resolved.suffix, "application/octet-stream")
        self.send_payload(200, resolved.read_bytes(), ctype)


def make_handler(root: Path) -> type[BoardHandler]:
    return type("BoundBoardHandler", (BoardHandler,), {"root": root.resolve()})


def make_server(root: Path, port: int = DEFAULT_PORT,
                host: str = "127.0.0.1") -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, port), make_handler(root))
    server.daemon_threads = True
    return server


# --------------------------------------------------------------------------
# cli
# --------------------------------------------------------------------------

def default_root() -> Path:
    """The drydock STATE_HOME: ``$DRYDOCK_STATE_HOME``, else ``~/.drydock``.

    Deliberately NOT wherever this script lives — that is the plugin
    package (read-only, updated via ``/plugin update``), never the queue.
    """
    env = os.environ.get("DRYDOCK_STATE_HOME")
    return Path(env) if env else Path.home() / ".drydock"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="board", description="drydock board — live queue dashboard")
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="serve the dashboard on 127.0.0.1")
    serve.add_argument("--port", type=int, default=DEFAULT_PORT,
                       help=f"port to bind (default {DEFAULT_PORT})")
    serve.add_argument("--root", type=Path, default=None,
                       help="drydock STATE_HOME to read "
                            "(default: $DRYDOCK_STATE_HOME or ~/.drydock)")
    args = parser.parse_args(argv)

    root = (args.root or default_root()).resolve()
    if not root.is_dir():
        print(f"board: no such directory: {root}", file=sys.stderr)
        return 2

    server = make_server(root, args.port)
    print(f"drydock board: http://127.0.0.1:{server.server_address[1]}  (root: {root})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
