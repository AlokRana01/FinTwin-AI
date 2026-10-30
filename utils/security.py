"""
utils/security.py
==================
Central security utilities for FinTwin AI.

Contains:
  - Input sanitization and validation helpers
  - Password strength enforcement
  - Email validation
  - Rate limiter for brute-force protection
  - Prompt injection filter for AI chatbot
  - Session timeout helpers

IMPORTANT: This module adds SECURITY CONTROLS only.
It does NOT alter business logic, financial calculations, AI models, or workflows.
"""

from __future__ import annotations

import re
import time
import threading
from html import escape as _he
from typing import Tuple

# ── Constants ────────────────────────────────────────────────────────────────

# Input length caps
MAX_NAME_LEN        = 80
MAX_EMAIL_LEN       = 254
MAX_OCCUPATION_LEN  = 100
MAX_CITY_LEN        = 100
MAX_GOAL_NAME_LEN   = 120
MAX_CHAT_MSG_LEN    = 1000
MAX_PASSWORD_LEN    = 64
MIN_PASSWORD_LEN    = 8

# Rate limiting
_RATE_LOCK_WINDOW   = 300   # seconds (5 minutes)
_RATE_MAX_ATTEMPTS  = 5     # failures before lockout

# Session timeout
SESSION_TIMEOUT_SECONDS = 3_600  # 1 hour of inactivity

# ── Regex patterns ──────────────────────────────────────────────────────────

# Strict RFC-5321 compatible email regex
_EMAIL_RE = re.compile(
    r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$'
)

# Safe name: letters, spaces, hyphens, apostrophes, periods
_NAME_RE = re.compile(r"^[a-zA-Z\s\.\-']{1,80}$")

# Password complexity: upper + lower + digit or special
_PASSWORD_RE = re.compile(
    r'^(?=.*[a-z])(?=.*[A-Z])(?=.*[\d!@#$%^&*()\-_=+\[\]{}|;:,.<>?]).{8,64}$'
)

# Prompt injection detection patterns (lightweight, non-breaking)
_INJECTION_PATTERNS = re.compile(
    r'ignore\s+(all\s+|previous\s+|above\s+|the\s+)?(instructions?|prompts?|guidelines?|rules?)'
    r'|(reveal|print|output|show|display|repeat|tell\s+me)\s+(the\s+|your\s+|all\s+|this\s+)?(system\s+)?prompt'
    r'|you\s+are\s+(now\s+)?(a\s+|an\s+)?(different|new|other|evil|unrestricted)\s+(AI|assistant|model|bot|entity)'
    r'|(pretend|act)\s+(you\s+are|to\s+be)\s+(a\s+|an\s+)?(different|evil|unrestricted|other)'
    r'|jailbreak|DAN\s+mode|developer\s+mode|training\s+data'
    r'|<\s*script|<\s*img\s|<\s*iframe|javascript\s*:',
    re.IGNORECASE
)

# Dangerous HTML/script pattern (matches opening and closing tags)
_DANGEROUS_HTML_RE = re.compile(
    r'</?\s*(script|iframe|object|embed|link|meta|form|input|svg|img)[^>]*>|'
    r'javascript\s*:|on\w+\s*=',
    re.IGNORECASE
)


# ── Input sanitization ───────────────────────────────────────────────────────

def sanitize_text(text: str, max_len: int = 500) -> str:
    """
    General-purpose text sanitizer.
    - Strips leading/trailing whitespace
    - Collapses excessive inner whitespace
    - Enforces max length
    - Does NOT HTML-escape (caller decides rendering context)
    """
    if not isinstance(text, str):
        text = str(text)
    text = text.strip()
    text = re.sub(r'[ \t]{2,}', ' ', text)      # collapse spaces/tabs
    text = re.sub(r'\n{3,}', '\n\n', text)       # max 2 consecutive newlines
    return text[:max_len]


def sanitize_html_output(text: str) -> str:
    """
    Escape text for safe rendering inside unsafe_allow_html=True HTML blocks.
    Use this on any user-controlled string embedded into an HTML f-string.
    """
    return _he(str(text), quote=True)


def escape_html(value: object) -> str:
    """
    Convenience alias for escaping dynamic content destined for HTML contexts.
    Quotes attribute-breaking characters (' and ") safely.
    """
    return _he(str(value), quote=True)


# ── Validation ───────────────────────────────────────────────────────────────

def validate_name(name: str) -> Tuple[bool, str]:
    """
    Validates a user display name.
    Returns (is_valid, error_message_or_empty_string).
    """
    name = name.strip()
    if not name:
        return False, "Name is required."
    if len(name) > MAX_NAME_LEN:
        return False, f"Name must not exceed {MAX_NAME_LEN} characters."
    if not _NAME_RE.match(name):
        return False, "Name may only contain letters, spaces, hyphens, apostrophes, or periods."
    return True, ""


def validate_email(email: str) -> Tuple[bool, str]:
    """
    Validates an email address format.
    Returns (is_valid, error_message_or_empty_string).
    """
    email = email.strip().lower()
    if not email:
        return False, "Email is required."
    if len(email) > MAX_EMAIL_LEN:
        return False, f"Email must not exceed {MAX_EMAIL_LEN} characters."
    if not _EMAIL_RE.match(email):
        return False, "Please enter a valid email address (e.g., user@example.com)."
    return True, ""


def validate_password(password: str) -> Tuple[bool, str]:
    """
    Validates password strength.
    Requirements: 8–64 chars, upper, lower, digit or special char.
    Returns (is_valid, error_message_or_empty_string).
    """
    if not password:
        return False, "Password is required."
    if len(password) < MIN_PASSWORD_LEN:
        return False, f"Password must be at least {MIN_PASSWORD_LEN} characters."
    if len(password) > MAX_PASSWORD_LEN:
        return False, f"Password must not exceed {MAX_PASSWORD_LEN} characters."
    if not _PASSWORD_RE.match(password):
        return False, (
            "Password must include at least one uppercase letter, one lowercase letter, "
            "and one number or special character (!@#$%^&* etc.)."
        )
    return True, ""


def sanitize_chat_message(text: str) -> str:
    """
    Sanitizes a user chat message before:
      1. Displaying it in the UI
      2. Sending it to the AI API

    - Enforces MAX_CHAT_MSG_LEN
    - Strips dangerous HTML/script tags
    - Neutralizes detected prompt injection attempts (replaces with [filtered])
    """
    if not isinstance(text, str):
        return ""
    text = text.strip()[:MAX_CHAT_MSG_LEN]

    # Strip dangerous HTML injections
    text = _DANGEROUS_HTML_RE.sub("[removed]", text)

    # Neutralize prompt injection attempts
    text = _INJECTION_PATTERNS.sub("[filtered]", text)

    return text


# ── Rate Limiter ─────────────────────────────────────────────────────────────

import abc
import os
import logging

_sec_logger = logging.getLogger(__name__)


class BaseRateLimiterBackend(abc.ABC):
    """Abstract interface for rate limiting backends."""

    @abc.abstractmethod
    def is_locked(self, identifier: str, max_attempts: int, window_seconds: int) -> Tuple[bool, str]:
        pass

    @abc.abstractmethod
    def record_failure(self, identifier: str, window_seconds: int) -> None:
        pass

    @abc.abstractmethod
    def reset(self, identifier: str) -> None:
        pass


class InMemoryRateLimiterBackend(BaseRateLimiterBackend):
    """
    Thread-safe in-memory rate limiter backend using a local dictionary.
    Suitable for local development and single-process unit testing.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._attempts: dict[str, list[float]] = {}

    def _clean(self, identifier: str, now: float, window_seconds: int) -> list[float]:
        recent = [t for t in self._attempts.get(identifier, []) if now - t < window_seconds]
        self._attempts[identifier] = recent
        return recent

    def is_locked(self, identifier: str, max_attempts: int, window_seconds: int) -> Tuple[bool, str]:
        with self._lock:
            now = time.time()
            recent = self._clean(identifier, now, window_seconds)
            if len(recent) >= max_attempts:
                oldest = min(recent)
                wait_secs = int(window_seconds - (now - oldest))
                minutes = max(1, wait_secs // 60)
                return True, (
                    f"Too many failed login attempts. "
                    f"Please wait {minutes} minute(s) before trying again."
                )
        return False, ""

    def record_failure(self, identifier: str, window_seconds: int) -> None:
        with self._lock:
            now = time.time()
            self._clean(identifier, now, window_seconds)
            self._attempts.setdefault(identifier, []).append(now)

    def reset(self, identifier: str) -> None:
        with self._lock:
            self._attempts.pop(identifier, None)


class SQLiteRateLimiterBackend(BaseRateLimiterBackend):
    """
    Thread-safe and process-safe rate limiter backend backed by SQLite.
    Survives application restarts and coordinates rate limits across multiple
    Streamlit worker processes sharing the database.
    """

    def __init__(self):
        self._table_ensured = False
        self._in_memory_fallback = InMemoryRateLimiterBackend()

    def _ensure_table(self):
        if self._table_ensured:
            return
        try:
            from database.connection import get_db_cursor
            with get_db_cursor() as cursor:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS rate_limits (
                        identifier TEXT NOT NULL,
                        attempt_timestamp REAL NOT NULL
                    );
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_rate_limits_id_time
                    ON rate_limits (identifier, attempt_timestamp);
                """)
            self._table_ensured = True
        except Exception as e:
            _sec_logger.warning(f"Could not initialize rate_limits table in SQLite: {e}")

    def is_locked(self, identifier: str, max_attempts: int, window_seconds: int) -> Tuple[bool, str]:
        self._ensure_table()
        now = time.time()
        cutoff = now - window_seconds
        try:
            from database.connection import get_db_cursor
            with get_db_cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*), MIN(attempt_timestamp) FROM rate_limits WHERE identifier = ? AND attempt_timestamp >= ?",
                    (identifier, cutoff),
                )
                row = cursor.fetchone()
                if row and row[0] >= max_attempts:
                    oldest = row[1] if row[1] is not None else cutoff
                    wait_secs = int(window_seconds - (now - oldest))
                    minutes = max(1, wait_secs // 60)
                    return True, (
                        f"Too many failed login attempts. "
                        f"Please wait {minutes} minute(s) before trying again."
                    )
            return False, ""
        except Exception as e:
            _sec_logger.error(f"SQLiteRateLimiter error in is_locked for {identifier}: {e}; falling back to memory")
            return self._in_memory_fallback.is_locked(identifier, max_attempts, window_seconds)

    def record_failure(self, identifier: str, window_seconds: int) -> None:
        self._ensure_table()
        now = time.time()
        try:
            from database.connection import get_db_cursor
            with get_db_cursor() as cursor:
                cursor.execute(
                    "INSERT INTO rate_limits (identifier, attempt_timestamp) VALUES (?, ?)",
                    (identifier, now),
                )
                # Opportunistic maintenance cleanup of stale records
                cursor.execute(
                    "DELETE FROM rate_limits WHERE attempt_timestamp < ?",
                    (now - (window_seconds * 2),),
                )
            self._in_memory_fallback.record_failure(identifier, window_seconds)
        except Exception as e:
            _sec_logger.error(f"SQLiteRateLimiter error recording failure: {e}; falling back to memory")
            self._in_memory_fallback.record_failure(identifier, window_seconds)

    def reset(self, identifier: str) -> None:
        self._ensure_table()
        try:
            from database.connection import get_db_cursor
            with get_db_cursor() as cursor:
                cursor.execute("DELETE FROM rate_limits WHERE identifier = ?", (identifier,))
            self._in_memory_fallback.reset(identifier)
        except Exception as e:
            _sec_logger.error(f"SQLiteRateLimiter error resetting identifier: {e}")
            self._in_memory_fallback.reset(identifier)


class RedisRateLimiterBackend(BaseRateLimiterBackend):
    """
    Centralized distributed rate limiter backend using Redis atomic sliding-window.
    If Redis is unavailable or unconfigured, securely falls back to SQLiteRateLimiterBackend.
    """

    def __init__(self, redis_url: str):
        self._redis_url = redis_url
        self._client = None
        self._sqlite_fallback = SQLiteRateLimiterBackend()
        self._init_client()

    def _init_client(self):
        try:
            import redis  # type: ignore[import-not-found] # pyright: ignore[reportMissingImports]
            self._client = redis.Redis.from_url(self._redis_url, socket_connect_timeout=2.0)
            self._client.ping()
            _sec_logger.info("RedisRateLimiterBackend connected successfully.")
        except Exception:
            _sec_logger.warning("RedisRateLimiter initialization failed or unavailable; falling back to SQLite backend.")
            self._client = None

    def is_locked(self, identifier: str, max_attempts: int, window_seconds: int) -> Tuple[bool, str]:
        if not self._client:
            return self._sqlite_fallback.is_locked(identifier, max_attempts, window_seconds)
        try:
            now = time.time()
            cutoff = now - window_seconds
            key = f"ftw_ratelimit:{identifier}"
            pipe = self._client.pipeline()
            pipe.zremrangebyscore(key, 0, cutoff)
            pipe.zcard(key)
            pipe.zrange(key, 0, 0, withscores=True)
            res = pipe.execute()
            count = res[1]
            if count >= max_attempts:
                oldest_score = res[2][0][1] if res[2] else cutoff
                wait_secs = int(window_seconds - (now - oldest_score))
                minutes = max(1, wait_secs // 60)
                return True, (
                    f"Too many failed login attempts. "
                    f"Please wait {minutes} minute(s) before trying again."
                )
            return False, ""
        except Exception as e:
            _sec_logger.warning(f"RedisRateLimiter error during is_locked: {e}; falling back to SQLite")
            return self._sqlite_fallback.is_locked(identifier, max_attempts, window_seconds)

    def record_failure(self, identifier: str, window_seconds: int) -> None:
        if not self._client:
            self._sqlite_fallback.record_failure(identifier, window_seconds)
            return
        try:
            now = time.time()
            cutoff = now - window_seconds
            key = f"ftw_ratelimit:{identifier}"
            pipe = self._client.pipeline()
            pipe.zremrangebyscore(key, 0, cutoff)
            pipe.zadd(key, {str(now): now})
            pipe.expire(key, window_seconds * 2)
            pipe.execute()
        except Exception as e:
            _sec_logger.warning(f"RedisRateLimiter error during record_failure: {e}; falling back to SQLite")
            self._sqlite_fallback.record_failure(identifier, window_seconds)

    def reset(self, identifier: str) -> None:
        if not self._client:
            self._sqlite_fallback.reset(identifier)
            return
        try:
            key = f"ftw_ratelimit:{identifier}"
            self._client.delete(key)
        except Exception as e:
            _sec_logger.warning(f"RedisRateLimiter error during reset: {e}; falling back to SQLite")
            self._sqlite_fallback.reset(identifier)


class RateLimiter:
    """
    Unified rate limiter interface for login brute-force protection.
    Configurable via RATE_LIMIT_BACKEND ('sqlite', 'memory', or 'redis').
    Defaults to 'sqlite' for process-safe and restart-persistent protection.
    """

    _instance: "RateLimiter | None" = None
    _lock = threading.Lock()

    def __init__(self, backend: BaseRateLimiterBackend | None = None):
        if backend is not None:
            self._backend = backend
        else:
            self._backend = self._create_default_backend()

    @classmethod
    def _create_default_backend(cls) -> BaseRateLimiterBackend:
        backend_type = os.environ.get("RATE_LIMIT_BACKEND", "sqlite").strip().lower()
        redis_url = os.environ.get("REDIS_URL", "").strip()

        if backend_type == "memory":
            return InMemoryRateLimiterBackend()
        elif backend_type == "redis" or (redis_url and backend_type != "sqlite"):
            return RedisRateLimiterBackend(redis_url or "redis://localhost:6379/0")
        else:
            return SQLiteRateLimiterBackend()

    @classmethod
    def get(cls) -> "RateLimiter":
        """Singleton accessor."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def set_backend(self, backend: BaseRateLimiterBackend) -> None:
        """Sets the active rate limiter backend (e.g., for testing or reconfiguration)."""
        self._backend = backend

    def get_backend(self) -> BaseRateLimiterBackend:
        return self._backend

    def is_locked(self, identifier: str) -> Tuple[bool, str]:
        """Check if identifier is currently rate-limited."""
        return self._backend.is_locked(identifier, _RATE_MAX_ATTEMPTS, _RATE_LOCK_WINDOW)

    def record_failure(self, identifier: str) -> None:
        """Record a failed login attempt for the given identifier."""
        self._backend.record_failure(identifier, _RATE_LOCK_WINDOW)

    def reset(self, identifier: str) -> None:
        """Clear all recorded failures for the identifier (on successful login)."""
        self._backend.reset(identifier)


# ── Session helpers ───────────────────────────────────────────────────────────

def session_touch(session_state) -> None:
    """Update the last-active timestamp for the current session."""
    session_state["_session_last_active"] = time.time()


def session_is_expired(session_state) -> bool:
    """
    Return True if the session has been inactive beyond SESSION_TIMEOUT_SECONDS.
    Also returns True if no timestamp has ever been recorded.
    """
    last = session_state.get("_session_last_active")
    if last is None:
        return False  # First page load — don't evict immediately
    return (time.time() - last) > SESSION_TIMEOUT_SECONDS
