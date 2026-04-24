"""Wrapper around the `gsk` (Genspark CLI) binary.

Most functions shell out to gsk and return parsed JSON. The exception is
``_create_task_streaming`` (used by ``create_slides`` / ``create_sheet`` when
an ``on_project_id`` callback is supplied), which calls the gsk server API
directly via httpx so we can surface the project_id mid-stream instead of
waiting for the subprocess to finish 2-6 minutes later.

gsk must be logged in (`gsk login`) or GSK_API_KEY must be set in env.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

import httpx

# UUID v4 (project_id format) — used to scrape project_id out of free-text fields
# (heartbeat "message" / "debug") when the gsk server doesn't promote it to a
# top-level key in intermediate stream messages.
_UUID_RE = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)

GSK_BIN_CANDIDATES = [
    shutil.which("gsk"),
    "/Users/erniesg/code/erniesg/node_modules/.bin/gsk",
]

# Mirrors the CLI defaults (node_modules/@genspark/cli/dist/config.js + index.js)
_GSK_DEFAULT_BASE_URL = "https://www.genspark.ai"
_GSK_CONFIG_PATH = Path.home() / ".genspark-tool-cli" / "config.json"
_GSK_STREAM_LOG = Path("/tmp/beepbop-gsk-stream.jsonl")


class GskError(RuntimeError):
    """gsk CLI returned a non-zero exit or unparseable output."""


def _gsk_bin() -> str:
    for candidate in GSK_BIN_CANDIDATES:
        if candidate and Path(candidate).exists():
            return candidate
    raise GskError("gsk binary not found (tried PATH and node_modules/.bin)")


def _gsk_api_credentials() -> tuple[str, str]:
    """Return (base_url, api_key). Mirrors the CLI's CLI-flag > env > file precedence."""
    base_url = os.environ.get("GSK_BASE_URL") or _GSK_DEFAULT_BASE_URL
    api_key = os.environ.get("GSK_API_KEY") or ""
    if not api_key and _GSK_CONFIG_PATH.exists():
        try:
            cfg = json.loads(_GSK_CONFIG_PATH.read_text())
            api_key = cfg.get("api_key") or ""
            base_url = cfg.get("base_url") or base_url
        except Exception as e:  # noqa: BLE001
            raise GskError(f"failed to read {_GSK_CONFIG_PATH}: {e}") from e
    if not api_key:
        raise GskError("no gsk api key (set GSK_API_KEY or run `gsk login`)")
    return base_url.rstrip("/"), api_key


def _stream_log(record: dict) -> None:
    """Append one NDJSON line to the stream log; never raise."""
    try:
        with _GSK_STREAM_LOG.open("a") as f:
            f.write(json.dumps(record, default=str) + "\n")
    except Exception:  # noqa: BLE001
        pass


def _extract_project_id(payload: Any) -> str:
    """Find a project_id anywhere useful in a streaming gsk message.

    Tries (in order):
      1. Top-level ``project_id`` / ``task_id`` / ``job_id`` keys
      2. Same keys nested under ``data``
      3. UUID v4 substring scan of free-text fields the server does emit in
         every intermediate heartbeat (``message``, ``debug``, ``url``,
         ``share_url``, ``project_url``) — the create_task endpoint does NOT
         promote project_id to a top-level key mid-stream, but the URL it
         eventually returns is built as ``/agents?id=<uuid>`` so any UUID in
         these fields is the project_id.
    """
    if not isinstance(payload, dict):
        return ""
    for key in ("project_id", "task_id", "job_id"):
        v = payload.get(key)
        if isinstance(v, str) and v:
            return v
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    for key in ("project_id", "task_id", "job_id"):
        v = data.get(key)
        if isinstance(v, str) and v:
            return v
    # Free-text scan — only safe to do across known string fields, otherwise
    # we'd risk picking up a UUID from a tool_call_id or similar internal id.
    for key in ("project_url", "share_url", "url", "message", "debug"):
        for source in (payload, data):
            v = source.get(key) if isinstance(source, dict) else None
            if isinstance(v, str):
                m = _UUID_RE.search(v)
                if m:
                    return m.group(0)
    return ""


def _agent_ask_streaming(
    task_type: str,
    message: str,
    *,
    on_project_id: Callable[[str], None] | None = None,
    timeout: int = 600,
) -> dict:
    """Call POST /api/tool_cli/agent_ask and stream NDJSON line-by-line.

    Unlike create_task (whose heartbeats only carry {version, debug, message,
    heartbeat, elapsed_seconds}), agent_ask promotes ``project_id`` to a
    top-level key in early intermediate messages — see askAgent() in
    node_modules/@genspark/cli/dist/acp-serve.js line 502, the same callback
    ACP mode relies on for mid-flight session persistence. So the URL DM
    can fire ~10-20s in instead of waiting for the final response.
    """
    base_url, api_key = _gsk_api_credentials()
    url = f"{base_url}/api/tool_cli/agent_ask"
    body = {"message": message, "task_type": task_type}
    headers = {
        "Content-Type": "application/json",
        "X-Api-Key": api_key,
        "Accept": "application/x-ndjson, application/json",
    }

    fired_pid = ""
    final_result: dict | None = None
    started = time.time()
    _stream_log({"ts": started, "event": "request",
                 "endpoint": "agent_ask", "task_type": task_type})

    try:
        with httpx.stream("POST", url, json=body, headers=headers, timeout=timeout) as resp:
            if resp.status_code >= 400:
                err_body = b"".join(resp.iter_bytes()).decode("utf-8", errors="replace")
                _stream_log({"ts": time.time(), "event": "http_error",
                             "status": resp.status_code, "body": err_body[:500]})
                raise GskError(f"gsk agent_ask HTTP {resp.status_code}: {err_body[:300]}")
            line_count = 0
            for raw in resp.iter_lines():
                line = (raw or "").strip()
                if not line or not line.startswith("{"):
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                line_count += 1
                if line_count <= 5:
                    _stream_log({"ts": time.time(), "event": "line",
                                 "endpoint": "agent_ask", "n": line_count, "body": msg})
                if on_project_id and not fired_pid:
                    pid = _extract_project_id(msg)
                    if pid:
                        fired_pid = pid
                        _stream_log({"ts": time.time(), "event": "project_id",
                                     "endpoint": "agent_ask", "pid": pid,
                                     "elapsed": round(time.time() - started, 1)})
                        try:
                            on_project_id(pid)
                        except Exception as e:  # noqa: BLE001
                            _stream_log({"ts": time.time(), "event": "callback_error", "err": str(e)})
                if msg.get("status"):
                    final_result = msg
    except httpx.HTTPError as e:
        raise GskError(f"gsk agent_ask stream error: {e}") from e

    if not final_result:
        raise GskError("gsk agent_ask stream ended with no final status")
    if final_result.get("status") == "error":
        raise GskError(f"gsk agent_ask error: {final_result.get('message', '')}")
    _stream_log({"ts": time.time(), "event": "done",
                 "endpoint": "agent_ask", "elapsed": round(time.time() - started, 1)})
    return final_result


def _create_task_streaming(
    task_type: str,
    task_name: str,
    query: str,
    instructions: str,
    *,
    on_project_id: Callable[[str], None] | None = None,
    timeout: int = 600,
) -> dict:
    """Call POST /api/tool_cli/create_task and stream NDJSON line-by-line.

    Mirrors the gsk CLI's request shape (see node_modules/@genspark/cli/dist/index.js
    around line 553 + client.js line 86), but reads the stream incrementally so we
    can fire ``on_project_id`` the moment the server emits the project_id (typically
    10-30s into a slides job, vs the 2-6min the final response takes).

    Raises GskError on HTTP failure or if no final result with status="ok" arrives.
    Returns the final result dict (matches the shape of subprocess _run for create_task).
    """
    base_url, api_key = _gsk_api_credentials()
    url = f"{base_url}/api/tool_cli/create_task"
    body = {
        "task_type": task_type,
        "task_name": task_name[:60],
        "query": query,
        "instructions": instructions,
    }
    headers = {
        "Content-Type": "application/json",
        "X-Api-Key": api_key,
        "Accept": "application/x-ndjson, application/json",
    }

    fired_pid = ""
    final_result: dict | None = None
    started = time.time()
    _stream_log({"ts": started, "event": "request", "task_type": task_type, "task_name": task_name})

    try:
        with httpx.stream("POST", url, json=body, headers=headers, timeout=timeout) as resp:
            if resp.status_code >= 400:
                # Drain body for the error message before raising
                err_body = b"".join(resp.iter_bytes()).decode("utf-8", errors="replace")
                _stream_log({"ts": time.time(), "event": "http_error",
                             "status": resp.status_code, "body": err_body[:500]})
                raise GskError(f"gsk HTTP {resp.status_code}: {err_body[:300]}")

            line_count = 0
            for raw in resp.iter_lines():
                line = (raw or "").strip()
                if not line or not line.startswith("{"):
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                line_count += 1
                # Log full body for the first 5 lines (so we can see what
                # heartbeats actually contain) and a body snippet thereafter.
                # Truncate aggressively — the final result can be 50KB+.
                if line_count <= 5:
                    _stream_log({"ts": time.time(), "event": "line",
                                 "n": line_count, "body": msg})
                else:
                    snippet = {k: (v if not isinstance(v, str) else v[:200])
                               for k, v in msg.items() if k != "data"}
                    _stream_log({"ts": time.time(), "event": "line",
                                 "n": line_count, "msg_keys": list(msg.keys()),
                                 "snippet": snippet})

                # Fire URL callback the first time we see a project_id anywhere
                if on_project_id and not fired_pid:
                    pid = _extract_project_id(msg)
                    if pid:
                        fired_pid = pid
                        _stream_log({"ts": time.time(), "event": "project_id", "pid": pid,
                                     "elapsed": round(time.time() - started, 1)})
                        try:
                            on_project_id(pid)
                        except Exception as e:  # noqa: BLE001
                            _stream_log({"ts": time.time(), "event": "callback_error", "err": str(e)})

                # Final result has a "status" field
                if msg.get("status"):
                    final_result = msg
    except httpx.HTTPError as e:
        raise GskError(f"gsk stream HTTP error: {e}") from e

    if not final_result:
        raise GskError("gsk stream ended with no final status")
    if final_result.get("status") == "error":
        raise GskError(f"gsk task error: {final_result.get('message', '')}")
    _stream_log({"ts": time.time(), "event": "done",
                 "elapsed": round(time.time() - started, 1)})
    return final_result


def _run(args: list[str], timeout: int = 120) -> Any:
    cmd = [_gsk_bin(), "--output", "json", *args]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as e:
        raise GskError(f"gsk timeout after {timeout}s: {' '.join(cmd)}") from e
    if result.returncode != 0:
        raise GskError(f"gsk exit={result.returncode}: {result.stderr.strip() or result.stdout.strip()}")
    try:
        return json.loads(result.stdout) if result.stdout.strip() else {}
    except json.JSONDecodeError:
        # Some gsk commands emit non-JSON on success; return raw text
        return {"_raw": result.stdout.strip()}


def me() -> dict:
    """Return gsk login info, or raise if not authed."""
    return _run(["me"])


SLIDES_INSTRUCTIONS = (
    "You are a pitch-deck specialist creating slides for a Singapore creative SME bidding on a government tender. "
    "Use the user's context (rates, services, past work, preferences) to tailor every slide. "
    "Keep language clear, professional, and use the tone the user requested. "
    "Structure: About us, Understanding of the opportunity, Proposed approach, Team + past work, Timeline, Pricing headline, Why us, Next steps."
)

SHEETS_INSTRUCTIONS = (
    "You are a quotation specialist for a Singapore creative SME. "
    "Create a Google Sheets quotation using the user's rates card as the source of truth. "
    "Columns: Item | Qty | Unit | Rate SGD | Subtotal. "
    "Include a summary row with subtotal, 9% GST, and grand total. "
    "Keep line items tied to the tender scope described in the query."
)


def create_slides(
    prompt: str,
    task_name: str = "Pitch deck",
    *,
    on_project_id: Callable[[str], None] | None = None,
) -> dict:
    """Kick a slide-generation task on Genspark.

    When ``on_project_id`` is supplied we bypass the gsk subprocess and stream
    the server's NDJSON response directly so we can surface the project_id
    within ~30s instead of waiting for the full 2-6min slide build.

    Slide agent routinely takes 3-6 min — 10-min timeout keeps headroom over Genspark variance.
    """
    if on_project_id is not None:
        # agent_ask is the streaming-friendly endpoint — it surfaces project_id
        # mid-stream where create_task only emits opaque heartbeats. Bake the
        # SLIDES_INSTRUCTIONS into the message body since agent_ask has no
        # separate instructions slot.
        return _agent_ask_streaming(
            "slides",
            f"{SLIDES_INSTRUCTIONS}\n\n{prompt}",
            on_project_id=on_project_id, timeout=600,
        )
    return _run(
        ["create_task", "slides",
         "--task_name", task_name[:60],
         "--query", prompt,
         "--instructions", SLIDES_INSTRUCTIONS],
        timeout=600,
    )


def create_sheet(
    prompt: str,
    task_name: str = "Quotation",
    *,
    on_project_id: Callable[[str], None] | None = None,
) -> dict:
    """Create a Google Sheets spreadsheet via create_task (agent-generated).

    Sheets agent is faster than slides — 5-min timeout is plenty.
    Streams via agent_ask when ``on_project_id`` is supplied (see ``create_slides``).
    """
    if on_project_id is not None:
        return _agent_ask_streaming(
            "sheets",
            f"{SHEETS_INSTRUCTIONS}\n\n{prompt}",
            on_project_id=on_project_id, timeout=300,
        )
    return _run(
        ["create_task", "sheets",
         "--task_name", task_name[:60],
         "--query", prompt,
         "--instructions", SHEETS_INSTRUCTIONS],
        timeout=300,
    )


def email_send(
    to: str,
    subject: str,
    body_html: str,
    *,
    cc: list[str] | None = None,
    skip_confirmation: bool = True,
) -> dict:
    """Send an email via the authenticated gsk mail provider (Gmail or Outlook)."""
    args = [
        "gmail", "send",
        "--to", to,
        "--subject", subject,
        "--body", body_html,
        "--content_type", "text/html",
    ]
    if skip_confirmation:
        args += ["--skip_confirmation", "true"]
    if cc:
        args += ["--cc", json.dumps(cc)]
    return _run(args, timeout=60)


def phone_call(recipient: str, script: str) -> dict:
    """Initiate an AI phone call."""
    return _run(["phone-call", recipient, "--message", script], timeout=30)


def calendar_create(
    title: str, start_iso: str, end_iso: str, attendees: list[str], description: str = ""
) -> dict:
    """Create a Google Calendar event."""
    return _run(
        [
            "google-calendar", "create",
            "--title", title,
            "--start_time", start_iso,
            "--end_time", end_iso,
            "--attendees", json.dumps(attendees),
            "--description", description,
        ],
        timeout=30,
    )


def claw_share_link(vm_name: str, path: str, expires_minutes: int = 1440) -> dict:
    """Generate a time-limited share URL for a file on a Genspark Claw VM."""
    return _run(
        ["claw", "share_link", "--vm_name", vm_name, path, "--expires_minutes", str(expires_minutes)],
        timeout=30,
    )
