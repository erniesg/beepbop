"""Wrapper around the `gsk` (Genspark CLI) binary.

All functions return parsed JSON from `gsk ... --output json`. Errors surface
as `GskError` exceptions.

gsk must be logged in (`gsk login`) or GSK_API_KEY must be set in env.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

GSK_BIN_CANDIDATES = [
    shutil.which("gsk"),
    "/Users/erniesg/code/erniesg/node_modules/.bin/gsk",
]


class GskError(RuntimeError):
    """gsk CLI returned a non-zero exit or unparseable output."""


def _gsk_bin() -> str:
    for candidate in GSK_BIN_CANDIDATES:
        if candidate and Path(candidate).exists():
            return candidate
    raise GskError("gsk binary not found (tried PATH and node_modules/.bin)")


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


def create_slides(prompt: str, task_name: str = "Pitch deck") -> dict:
    """Kick a slide-generation task on Genspark. Returns task id / share URL (async)."""
    return _run(
        ["create-task", "slides", "--task_name", task_name[:60], "--task", prompt],
        timeout=300,
    )


def create_sheet(prompt: str, task_name: str = "Quotation") -> dict:
    """Create a Google Sheets spreadsheet via create-task (agent-generated)."""
    return _run(
        ["create-task", "sheets", "--task_name", task_name[:60], "--task", prompt],
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
