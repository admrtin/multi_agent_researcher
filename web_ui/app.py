from __future__ import annotations

import json
import os
import re
import time
import threading
import shutil
from pathlib import Path
from typing import Iterator

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    send_from_directory,
    jsonify,
)
import markdown
import subprocess

ROOT = Path(__file__).resolve().parent
WORKSPACE_ROOT = ROOT.parent
OUTPUTS_DIR = ROOT / "outputs"
LOG_FILE = Path("/tmp/agents_log/agent.latest.log")
INPUTS_DIR = ROOT / "inputs"
INPUTS_DIR.mkdir(exist_ok=True)

# file to store explicit prompt handoff for planner
PLANNER_INPUT_FILE = ROOT.parent / "web_ui_last_prompt.txt"
ANSI_ESCAPE_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
LOG_LINE_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} [0-9:,.-]+) - (?P<level>[A-Z]+) - (?P<logger>[^ ]+) - (?P<message>.*)$"
)
ALLOWED_LOG_SOURCES = {"WEB_UI", "PLANNER", "RESEARCHER", "SYNTHESIZER", "VALIDATOR"}

app = Flask(__name__, template_folder=str(ROOT / "templates"), static_folder=str(ROOT / "static"))


def tail_file(path: Path, sleep: float = 0.2) -> Iterator[str]:
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as fh:
            # Seek to end
            fh.seek(0, os.SEEK_END)
            while True:
                line = fh.readline()
                if line:
                    yield line
                else:
                    time.sleep(sleep)
    except FileNotFoundError:
        while True:
            yield ""
            time.sleep(sleep)


def _resolve_view_path(path_text: str) -> Path:
    candidate = Path(path_text)
    if candidate.is_absolute():
        return candidate.resolve()
    return (WORKSPACE_ROOT / candidate).resolve()


def _is_within_workspace(path: Path) -> bool:
    try:
        path.relative_to(WORKSPACE_ROOT)
        return True
    except ValueError:
        return False


def _workspace_relative(path: Path) -> str:
    return path.resolve().relative_to(WORKSPACE_ROOT).as_posix()


def _classify_file(file_path: Path) -> dict[str, str]:
    name = file_path.name.lower()
    kind = "file"
    kind_label = "File"

    if name.endswith("final_literature_review.md"):
        kind = "synthesis"
        kind_label = "Synthesis"
    elif name.endswith("planning_overview.md"):
        kind = "planner"
        kind_label = "Planner Overview"
    elif name.endswith("review.md"):
        kind = "research"
        kind_label = "Research Review"

    return {"kind": kind, "kind_label": kind_label}


def _normalize_log_message(message: str) -> tuple[str, str, str, bool]:
    raw = ANSI_ESCAPE_RE.sub("", message).strip()
    if not raw:
        return "", "", "", True

    if any(fragment in raw for fragment in ["_api_client.py:646", "google_llm.py:185", "google_llm.py:250"]):
        return "", "", "", True

    if "Running agent ROOT" in raw:
        return "ui", "WEB_UI", "Agent started", False
    if "Aborted!" in raw:
        return "error", "WEB_UI", "Run aborted", False
    if "Closing runner" in raw:
        return "", "", "", True
    if "Runner closed" in raw:
        return "", "", "", True
    if raw.startswith("[WEB_UI]"):
        return "ui", "WEB_UI", raw.replace("[WEB_UI]", "", 1).strip() or "UI event", False
    if raw.startswith("[PLANNER:") or raw.startswith("[RESEARCHER:") or raw.startswith("[SYNTHESIZER:") or raw.startswith("[VALIDATOR:"):
        agent_match = re.match(r"^\[(?P<agent>[A-Z_]+)(?::(?P<level>[A-Z]+))?\]\s*(?P<msg>.*)$", raw)
        if agent_match:
            agent = agent_match.group("agent")
            level = (agent_match.group("level") or "INFO").lower()
            msg = agent_match.group("msg").strip() or "Agent event"
            return level, agent, msg, False

    generic_match = LOG_LINE_RE.match(raw)
    if generic_match:
        level = generic_match.group("level").lower()
        logger = generic_match.group("logger")
        message_text = generic_match.group("message").strip()
        source = logger.split(".")[0].upper()
        if source == "RUNNERS" and ("Closing runner" in message_text or "Runner closed" in message_text):
            return "", "", "", True
        if source not in ALLOWED_LOG_SOURCES:
            return "", "", "", True
        if level == "warning":
            level = "warn"
        return level, source, message_text, False

    return "info", "SYSTEM", raw, False


def _parse_log_line(raw_line: str) -> dict[str, str | bool]:
    level, source, message, skip = _normalize_log_message(raw_line)
    return {
        "level": level or "info",
        "source": source or "SYSTEM",
        "message": message,
        "skip": skip,
    }


def _load_recent_log_entries(limit: int = 160) -> list[dict[str, str | bool]]:
    if not LOG_FILE.exists():
        return []

    try:
        lines = LOG_FILE.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return []

    entries: list[dict[str, str | bool]] = []
    for line in lines[-max(limit * 2, limit):]:
        parsed = _parse_log_line(line)
        if parsed.get("skip"):
            continue
        entries.append(parsed)
    return entries[-limit:]


def _clear_previous_outputs() -> None:
    outputs_root = WORKSPACE_ROOT / "outputs"
    outputs_root.mkdir(parents=True, exist_ok=True)
    for child in outputs_root.iterdir():
        if child.name == ".gitkeep":
            continue
        try:
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink(missing_ok=True)
        except Exception:
            continue


def _build_output_catalog() -> list[dict[str, object]]:
    categories: list[dict[str, object]] = []
    if not OUTPUTS_DIR.exists():
        return categories

    for category_dir in sorted(OUTPUTS_DIR.iterdir(), key=lambda item: item.name):
        if not category_dir.is_dir():
            continue

        category_runs: list[dict[str, object]] = []
        for run_dir in sorted(category_dir.iterdir(), key=lambda item: item.name, reverse=True):
            if not run_dir.is_dir():
                continue

            file_nodes: list[dict[str, str]] = []
            for child in sorted(run_dir.iterdir(), key=lambda item: item.name):
                if not child.is_file() or child.suffix.lower() != ".md":
                    continue
                resolved = child.resolve()
                classification = _classify_file(resolved)
                file_nodes.append(
                    {
                        "name": child.name,
                        "path": _workspace_relative(resolved),
                        "kind": classification["kind"],
                        "kind_label": classification["kind_label"],
                    }
                )

            if not file_nodes:
                continue

            category_runs.append(
                {
                    "run_name": run_dir.name,
                    "run_path": _workspace_relative(run_dir.resolve()),
                    "file_count": len(file_nodes),
                    "files": file_nodes,
                }
            )

        categories.append({"name": category_dir.name, "runs": category_runs})

    return categories


@app.route("/")
def index():
    return render_template(
        "index.html",
        categories=_build_output_catalog(),
        latest_prompt=_load_latest_prompt(),
        log_entries=_load_recent_log_entries(),
    )


@app.route("/outputs-catalog")
def outputs_catalog():
    return jsonify({"categories": _build_output_catalog()})


@app.route("/submit", methods=["POST"])
def submit_prompt():
    prompt = request.form.get("prompt", "").strip()
    if not prompt:
        return redirect(url_for("index"))

    _clear_previous_outputs()

    timestamp = int(time.time())
    file = INPUTS_DIR / f"prompt_{timestamp}.txt"
    file.write_text(prompt, encoding="utf-8")

    # Write a simple marker file with the latest prompt (for humans/tools)
    try:
        PLANNER_INPUT_FILE.write_text(prompt, encoding="utf-8")
    except Exception:
        pass

    # Append to the agent latest log so it appears in the UI quickly
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as lf:
            lf.write(f"[WEB_UI] Prompt submitted at {time.ctime(timestamp)}:\n{prompt}\n\n")
            lf.flush()
    except Exception:
        pass

    # Auto-start an agent run so user sees progress immediately
    try:
        thread = threading.Thread(target=_run_agent_subprocess, kwargs={"prompt_text": prompt}, daemon=True)
        thread.start()
    except Exception:
        try:
            with LOG_FILE.open("a", encoding="utf-8") as lf:
                lf.write("[WEB_UI] Failed to auto-start agent run\n")
                lf.flush()
        except Exception:
            pass

    return redirect(url_for("index"))


@app.route("/runs/")
def list_runs():
    runs = []
    if OUTPUTS_DIR.exists():
        for child in sorted(OUTPUTS_DIR.iterdir(), reverse=True):
            if child.is_dir():
                runs.append(child.name)
    return jsonify(runs)


@app.route("/view/")
def view_file():
    path = request.args.get("path")
    if not path:
        return "Missing path", 400
    safe = _resolve_view_path(path)
    if not safe.exists() or not _is_within_workspace(safe):
        return "File not found or unavailable.", 404

    if safe.is_dir():
        entries = []
        for child in sorted(safe.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower())):
            rel = _workspace_relative(child.resolve())
            label = child.name + ("/" if child.is_dir() else "")
            entries.append(
                f'<li class="dir-entry"><a href="/view/?path={rel}"><span>{label}</span><span class="dir-entry__meta">{child.stat().st_size if child.is_file() else "folder"}</span></a></li>'
            )
        content_html = "<div class='file-panel'><h2>Directory listing</h2><ul class='dir-list'>" + "".join(entries) + "</ul></div>"
        return render_template("view.html", content=content_html, path=str(safe.relative_to(WORKSPACE_ROOT)))

    text = safe.read_text(encoding="utf-8", errors="ignore")
    suffix = safe.suffix.lower()
    if suffix in {".md", ".markdown"}:
        content_html = markdown.markdown(text, extensions=["fenced_code", "tables"])
        content_html = f'<article class="markdown-body">{content_html}</article>'
    elif suffix == ".json":
        try:
            parsed = json.loads(text)
            pretty = json.dumps(parsed, indent=2, ensure_ascii=False)
        except Exception:
            pretty = text
        content_html = f'<pre class="code-view">{pretty}</pre>'
    else:
        content_html = f'<pre class="code-view">{text}</pre>'

    return render_template(
        "view.html",
        content=content_html,
        path=str(safe.relative_to(WORKSPACE_ROOT)),
        file_name=safe.name,
        file_kind=_classify_file(safe)["kind_label"],
        file_size=safe.stat().st_size,
    )


@app.route("/stream-logs")
def stream_logs():
    def generate():
        for line in tail_file(LOG_FILE):
            if line:
                parsed = _parse_log_line(line)
                if parsed.get("skip"):
                    continue
                yield "data: " + json.dumps(parsed, ensure_ascii=False) + "\n\n"

    return app.response_class(generate(), mimetype="text/event-stream")


def _load_latest_prompt() -> str:
    try:
        return PLANNER_INPUT_FILE.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def _run_agent_subprocess(prompt_text: str = ""):
    """Run `adk run .` in the workspace root and append output to the log file."""
    cmd = ["adk", "run", "."]
    cwd = str(ROOT.parent)
    prompt_text = (prompt_text or _load_latest_prompt()).strip()
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as lf:
            lf.write(f"[WEB_UI] Starting agent run in {cwd}\n")
            if prompt_text:
                lf.write(f"[WEB_UI] Prompt: {prompt_text}\n")
            lf.flush()
            proc = subprocess.Popen(cmd, cwd=cwd, stdin=subprocess.PIPE, stdout=lf, stderr=lf, text=True)
            proc.communicate(input=(prompt_text + "\n") if prompt_text else "\n")
            lf.write(f"[WEB_UI] Agent run finished with exit {proc.returncode}\n")
            lf.flush()
    except Exception as e:
        try:
            with LOG_FILE.open("a", encoding="utf-8") as lf:
                lf.write(f"[WEB_UI] Failed to start agent run: {e}\n")
                lf.flush()
        except Exception:
            pass


@app.route("/start-run", methods=["POST"])
def start_run():
    # Start the agent run in a background thread so the web UI remains responsive
    prompt_text = request.form.get("prompt", "").strip() or _load_latest_prompt()
    thread = threading.Thread(target=_run_agent_subprocess, kwargs={"prompt_text": prompt_text}, daemon=True)
    thread.start()
    return jsonify({"status": "started"})


@app.route("/log-history")
def log_history():
    return jsonify({"entries": _load_recent_log_entries()})


@app.route("/static/<path:fname>")
def static_files(fname: str):
    return send_from_directory(str(ROOT / "static"), fname)


def run(port: int = 8080):
    app.run(host="0.0.0.0", port=port, debug=False)


if __name__ == "__main__":
    run()
