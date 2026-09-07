"""Verifies the signed launch data MAX's Mini App SDK hands the frontend.

Kept separate from auth.py on purpose: this module is pure crypto and JSON
parsing with no database access, so it is trivial to unit-test against a
fixed bot token and a hand-built launch_params string, independent of
anything else in the auth stack.

Algorithm, from https://dev.max.ru/docs/webapps/validation (2026-09) — the
same construction Telegram Mini Apps uses:

    secret_key = HMAC_SHA256(key="WebAppData", message=bot_token)
    data_check_string = "\n".join(sorted(f"{k}={v}" for k, v in fields
                                          if k != "hash"))
    expected_hash = hex(HMAC_SHA256(key=secret_key, message=data_check_string))

`launch_params` is the exact string MAX's `window.WebApp.initData` exposes:
`&`-joined `key=value` pairs, values percent-encoded. It must reach the
server unmodified — do not re-encode or reorder it before verifying.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl


class MaxAuthError(ValueError):
    pass


@dataclass(frozen=True)
class MaxUser:
    """The subset of MAX's `user` field this app actually reads."""

    user_id: str
    username: str | None
    display_name: str


def _secret_key(bot_token: str) -> bytes:
    return hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()


def verify_launch_params(
    launch_params: str, bot_token: str, *, max_age_seconds: int = 3600
) -> dict[str, str]:
    """Returns the verified fields as a plain dict, or raises MaxAuthError.

    `max_age_seconds` bounds replay: MAX's `auth_date` field is a Unix
    timestamp set when the mini app opened, so a launch_params string
    captured once and replayed later stops verifying past this window. An
    hour matches the session the rest of V4 issues; there is nothing MAX-
    specific about that number.
    """
    if not launch_params or len(launch_params) > 4096:
        raise MaxAuthError("launch_params missing or implausibly long")
    if not bot_token:
        raise MaxAuthError("MAX bot token is not configured")

    try:
        # keep_blank_values so an empty field cannot silently vanish from the
        # check string and change what gets signed versus what gets verified
        pairs = parse_qsl(launch_params, keep_blank_values=True, strict_parsing=True)
    except ValueError as exc:
        raise MaxAuthError("launch_params is not well-formed") from None

    fields: dict[str, str] = {}
    for key, value in pairs:
        if key in fields:
            raise MaxAuthError(f"duplicate field in launch_params: {key}")
        fields[key] = value

    received_hash = fields.pop("hash", None)
    if not received_hash:
        raise MaxAuthError("launch_params has no hash field")

    check_string = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    secret = _secret_key(bot_token)
    expected_hash = hmac.new(
        secret, check_string.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    # Constant-time compare: this is the one line in the module that is
    # actually security-load-bearing, everything above just gets us here.
    if not hmac.compare_digest(expected_hash, received_hash):
        raise MaxAuthError("launch_params signature does not match")

    auth_date = fields.get("auth_date")
    if not auth_date or not auth_date.isdigit():
        raise MaxAuthError("launch_params has no valid auth_date")
    age = time.time() - int(auth_date)
    if age < -60 or age > max_age_seconds:
        raise MaxAuthError("launch_params has expired")

    return fields


def parse_user(fields: dict[str, str]) -> MaxUser:
    """`fields` is the verified dict from verify_launch_params — never parse
    an unverified `user` field, the signature covers the whole string."""
    raw_user = fields.get("user")
    if not raw_user:
        raise MaxAuthError("launch_params has no user field")
    try:
        parsed = json.loads(raw_user)
    except (TypeError, ValueError):
        raise MaxAuthError("launch_params user field is not valid JSON") from None

    user_id = parsed.get("id")
    if user_id is None:
        raise MaxAuthError("launch_params user field has no id")

    first = str(parsed.get("first_name") or "").strip()
    last = str(parsed.get("last_name") or "").strip()
    display_name = " ".join(part for part in (first, last) if part) or "MAX user"

    return MaxUser(
        user_id=str(user_id),
        username=(str(parsed["username"]).strip() or None)
        if parsed.get("username")
        else None,
        display_name=display_name,
    )
