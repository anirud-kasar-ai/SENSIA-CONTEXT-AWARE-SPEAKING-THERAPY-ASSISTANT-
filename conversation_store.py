"""Redis-backed conversation turns with in-memory fallback when Redis is unavailable."""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Optional
from urllib.parse import quote

logger = logging.getLogger(__name__)

_DEFAULT_LIMIT = 30
_KEY_PREFIX_DEFAULT = "sensia:chat:"
_SUMMARY_PREFIX_DEFAULT = "sensia:summary:"

_redis_client: Any = None
_use_redis: Optional[bool] = None
_redis_client_url: Optional[str] = None
_last_redis_connect_fail_at: float = 0.0
_last_redis_connect_fail_url: str = ""
_memory_store: dict[str, list[dict[str, str]]] = {}
_memory_summary: dict[str, dict[str, Any]] = {}


def _redis_url() -> str:
    """
    Connection URL for redis.from_url.

    Priority:
    1) REDIS_URL if set and non-empty (full URL, e.g. redis://user:pass@host:port/0 or rediss://...)
    2) Built from REDIS_HOST + REDIS_PORT + REDIS_PASSWORD + numeric REDIS_DB (+ optional REDIS_USERNAME, REDIS_SSL)
    3) Local default redis://localhost:6379/0
    """
    explicit = (os.getenv("REDIS_URL") or "").strip()
    if explicit and not explicit.startswith("#"):
        return explicit

    host = (os.getenv("REDIS_HOST") or "").strip()
    if not host:
        return "redis://localhost:6379/0"

    port = (os.getenv("REDIS_PORT") or "6379").strip()
    password = (os.getenv("REDIS_PASSWORD") or "").strip()
    username = (os.getenv("REDIS_USERNAME") or "").strip()

    db_raw = (os.getenv("REDIS_DB") or "0").strip()
    try:
        db_index = int(db_raw)
        if db_index < 0:
            db_index = 0
    except ValueError:
        logger.warning(
            "REDIS_DB must be a numeric Redis database index (e.g. 0). Got %r — using 0. "
            "For a logical namespace use REDIS_KEY_PREFIX / REDIS_SUMMARY_PREFIX instead.",
            db_raw,
        )
        db_index = 0

    ssl_on = (os.getenv("REDIS_SSL", "").strip().lower() in ("1", "true", "yes"))
    scheme = "rediss" if ssl_on else "redis"

    if password:
        pw = quote(password, safe="")
        if username:
            user_q = quote(username, safe="")
            auth = f"{user_q}:{pw}@"
        else:
            # Many hosted Redis (e.g. Redis Cloud) expect ACL user "default"
            auth = f"default:{pw}@"
    elif username:
        auth = f"{quote(username, safe='')}@"
    else:
        auth = ""

    return f"{scheme}://{auth}{host}:{port}/{db_index}"


def _key_prefix() -> str:
    return os.getenv("REDIS_KEY_PREFIX", _KEY_PREFIX_DEFAULT).strip() or _KEY_PREFIX_DEFAULT


def _ttl() -> Optional[int]:
    raw = os.getenv("REDIS_CHAT_TTL", "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _key(session_id: str) -> str:
    return f"{_key_prefix()}{session_id}"


def _summary_key_prefix() -> str:
    return os.getenv("REDIS_SUMMARY_PREFIX", _SUMMARY_PREFIX_DEFAULT).strip() or _SUMMARY_PREFIX_DEFAULT


def _summary_key(session_id: str) -> str:
    return f"{_summary_key_prefix()}{session_id}"


def _get_client() -> Any:
    global _redis_client, _use_redis, _redis_client_url, _last_redis_connect_fail_at, _last_redis_connect_fail_url
    if os.getenv("REDIS_DISABLED", "").strip().lower() in ("1", "true", "yes"):
        _use_redis = False
        return None

    url = _redis_url()
    if _redis_client is not None and _redis_client_url != url:
        try:
            _redis_client.close()
        except Exception:
            pass
        _redis_client = None
        _use_redis = None
        _redis_client_url = None

    if _redis_client is not None:
        return _redis_client

    # Avoid hammering Redis on every widget rerun after a hard failure (same URL)
    if _use_redis is False and url == _last_redis_connect_fail_url:
        if time.time() - _last_redis_connect_fail_at < 30.0:
            return None

    try:
        import redis
    except ImportError:
        logger.warning("redis package not installed; using in-memory conversation store")
        _use_redis = False
        return None

    if not url or url.startswith("#"):
        _use_redis = False
        return None
    try:
        _redis_client = redis.from_url(url, decode_responses=True)
        _redis_client.ping()
        _use_redis = True
        _redis_client_url = url
        _last_redis_connect_fail_url = ""
        return _redis_client
    except Exception as e:
        logger.warning("Redis unavailable (%s); using in-memory conversation store", e)
        _use_redis = False
        _redis_client = None
        _redis_client_url = None
        _last_redis_connect_fail_at = time.time()
        _last_redis_connect_fail_url = url
        return None


def is_redis_active() -> bool:
    """True if the last successful client init used Redis."""
    if _use_redis is None:
        _get_client()
    return bool(_use_redis)


def append_turn(session_id: str, user_text: str, bot_text: str) -> None:
    payload = {"user": user_text, "bot": bot_text}
    client = _get_client()
    if client is not None:
        key = _key(session_id)
        client.rpush(key, json.dumps(payload, ensure_ascii=False))
        ttl = _ttl()
        if ttl:
            client.expire(key, ttl)
        return
    mem = _memory_store.setdefault(session_id, [])
    mem.append(payload)


def get_recent_turns(session_id: str, limit: int = _DEFAULT_LIMIT) -> list[dict[str, str]]:
    if limit < 1:
        return []
    client = _get_client()
    if client is not None:
        key = _key(session_id)
        n = client.llen(key)
        if n == 0:
            return []
        start = max(0, n - limit)
        raw = client.lrange(key, start, -1)
        out: list[dict[str, str]] = []
        for line in raw:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out
    return list(_memory_store.get(session_id, [])[-limit:])


def get_turn_count(session_id: str) -> int:
    client = _get_client()
    if client is not None:
        return int(client.llen(_key(session_id)))
    return len(_memory_store.get(session_id, []))


def get_turns_slice(session_id: str, start: int, count: int) -> list[dict[str, str]]:
    """Return up to `count` turns starting at Redis list index `start` (0-based)."""
    if count < 1 or start < 0:
        return []
    client = _get_client()
    if client is not None:
        key = _key(session_id)
        n = client.llen(key)
        if start >= n:
            return []
        end_idx = min(start + count - 1, n - 1)
        raw = client.lrange(key, start, end_idx)
        out: list[dict[str, str]] = []
        for line in raw:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out
    mem = _memory_store.get(session_id, [])
    return mem[start : start + count]


def get_session_summary(session_id: str) -> dict[str, Any]:
    """Rolling summary state: text (cumulative) and cursor (turns folded into text)."""
    default = {"text": "", "cursor": 0}
    client = _get_client()
    if client is not None:
        sk = _summary_key(session_id)
        raw = client.get(sk)
        if not raw:
            return dict(default)
        try:
            data = json.loads(raw)
            text = str(data.get("text", ""))
            cursor = int(data.get("cursor", 0))
            if cursor < 0:
                cursor = 0
            return {"text": text, "cursor": cursor}
        except (json.JSONDecodeError, TypeError, ValueError):
            return dict(default)
    return dict(_memory_summary.get(session_id, default))


def set_session_summary(session_id: str, text: str, cursor: int) -> None:
    payload = {"text": text, "cursor": max(0, int(cursor))}
    raw = json.dumps(payload, ensure_ascii=False)
    client = _get_client()
    if client is not None:
        sk = _summary_key(session_id)
        client.set(sk, raw)
        ttl = _ttl()
        if ttl:
            client.expire(sk, ttl)
        return
    _memory_summary[session_id] = payload


def clear_session(session_id: str) -> None:
    client = _get_client()
    if client is not None:
        client.delete(_key(session_id))
        client.delete(_summary_key(session_id))
    _memory_store.pop(session_id, None)
    _memory_summary.pop(session_id, None)


__all__ = [
    "append_turn",
    "clear_session",
    "get_recent_turns",
    "get_turn_count",
    "get_turns_slice",
    "get_session_summary",
    "set_session_summary",
    "is_redis_active",
]
