"""
tests/test_audit_phase2_remediation.py
======================================
Automated verification tests for Phase 2 Audit Remediation:
- SEC-04: Opt-in demo account seeding (ENABLE_DEMO_SEED=true).
- DATA-01: SQLite WAL mode, busy_timeout=5000, and concurrency handling.
- SEC-03: Multi-backend RateLimiter (SQLite persistence, In-Memory, Redis fallback).
"""

import os
import sys
import time
import unittest
import sqlite3
import threading
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from database.connection import (
    init_db,
    get_connection,
    get_db_cursor,
    is_demo_seed_enabled,
    ensure_demo_user_seeded,
    get_database_pragmas,
)
from database.db_manager import DBManager
from utils.security import (
    RateLimiter,
    InMemoryRateLimiterBackend,
    SQLiteRateLimiterBackend,
    RedisRateLimiterBackend,
)
from utils import auth


class TestAuditPhase2Remediation(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        # Ensure clean environment
        os.environ.pop("ENABLE_DEMO_SEED", None)
        os.environ.pop("RATE_LIMIT_BACKEND", None)

    # ── SEC-04: Demo Account Auto-Seeding Tests ──────────────────────────────

    def test_sec04_demo_seed_disabled_by_default(self):
        """SEC-04: is_demo_seed_enabled() must return False when variable is absent."""
        os.environ.pop("ENABLE_DEMO_SEED", None)
        self.assertFalse(is_demo_seed_enabled())

    def test_sec04_demo_seed_disabled_when_explicitly_false(self):
        """SEC-04: is_demo_seed_enabled() must return False when set to 'false' or '0'."""
        os.environ["ENABLE_DEMO_SEED"] = "false"
        self.assertFalse(is_demo_seed_enabled())
        os.environ["ENABLE_DEMO_SEED"] = "0"
        self.assertFalse(is_demo_seed_enabled())

    def test_sec04_demo_seed_enabled_explicitly(self):
        """SEC-04: is_demo_seed_enabled() returns True only when set to 'true', '1', or 'yes'."""
        os.environ["ENABLE_DEMO_SEED"] = "true"
        self.assertTrue(is_demo_seed_enabled())
        os.environ["ENABLE_DEMO_SEED"] = "1"
        self.assertTrue(is_demo_seed_enabled())
        os.environ["ENABLE_DEMO_SEED"] = "yes"
        self.assertTrue(is_demo_seed_enabled())

    def test_sec04_demo_user_password_is_hashed(self):
        """SEC-04: Demo account must NEVER store plaintext password."""
        with get_db_cursor() as cursor:
            ensure_demo_user_seeded(cursor)
            cursor.execute("SELECT password_hash, password_salt FROM users WHERE user_id = 'demo_user'")
            row = cursor.fetchone()
            self.assertIsNotNone(row)
            pw_hash, salt = row[0], row[1]
            self.assertNotEqual(pw_hash, "Demo@123", "Demo password must not be stored in plaintext")
            self.assertTrue(
                pw_hash.startswith("$argon2") or (len(pw_hash) == 64 and salt is not None),
                "Password must be hashed with Argon2id or PBKDF2-HMAC-SHA256"
            )

    def test_sec04_demo_user_idempotency_no_duplicates(self):
        """SEC-04: Seeding demo user multiple times does not duplicate records."""
        with get_db_cursor() as cursor:
            ensure_demo_user_seeded(cursor)
            ensure_demo_user_seeded(cursor)
            cursor.execute("SELECT COUNT(*) FROM users WHERE user_id = 'demo_user'")
            count = cursor.fetchone()[0]
            self.assertEqual(count, 1)

    def test_sec04_existing_users_preserved_during_demo_seed(self):
        """SEC-04: Seeding demo account does not touch or overwrite existing users."""
        test_uid = "sec04_regular_user"
        test_email = "regular.user@example.com"
        with get_db_cursor() as cursor:
            cursor.execute("DELETE FROM users WHERE user_id = ?", (test_uid,))
            cursor.execute(
                "INSERT INTO users (user_id, email, name, age, monthly_income, email_verified) VALUES (?, ?, ?, ?, ?, 1)",
                (test_uid, test_email, "Regular User", 30, 80000.0),
            )
            # Re-seed demo
            ensure_demo_user_seeded(cursor)

            cursor.execute("SELECT name, email FROM users WHERE user_id = ?", (test_uid,))
            row = cursor.fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row[0], "Regular User")
            self.assertEqual(row[1], test_email)

            # Cleanup
            cursor.execute("DELETE FROM users WHERE user_id = ?", (test_uid,))

    # ── DATA-01: SQLite WAL & Concurrency Tests ──────────────────────────────

    def test_data01_wal_mode_and_pragmas_enabled(self):
        """DATA-01: Verify that SQLite journal mode is WAL and busy timeout is 5000ms."""
        pragmas = get_database_pragmas()
        self.assertEqual(pragmas["journal_mode"], "wal", "SQLite should operate in WAL mode")
        self.assertEqual(pragmas["busy_timeout"], 5000, "Busy timeout should be configured to 5000ms")
        self.assertEqual(pragmas["foreign_keys"], 1, "Foreign keys must be enabled")

    def test_data01_database_initialization_idempotent(self):
        """DATA-01: init_db() can be called repeatedly without schema conflicts or errors."""
        try:
            init_db()
            init_db()
        except Exception as e:
            self.fail(f"init_db() raised unexpected exception on re-run: {e}")

    def test_data01_concurrent_connections_and_reads(self):
        """DATA-01: Multiple connections can read concurrently under WAL mode without blocking."""
        errors = []

        def reader_task(reader_id: int):
            try:
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM users")
                _ = cursor.fetchone()[0]
                cursor.close()
                conn.close()
            except Exception as e:
                errors.append((reader_id, str(e)))

        threads = [threading.Thread(target=reader_task, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"Concurrent reader errors: {errors}")

    def test_data01_concurrent_reads_during_write(self):
        """DATA-01: WAL mode allows concurrent readers while a write transaction is in progress."""
        write_started = threading.Event()
        write_finished = threading.Event()
        read_success = []

        def writer():
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO chat_usage (user_id, usage_date, message_count) VALUES ('wal_test', '2026-09-24', 1)")
            write_started.set()
            time.sleep(0.1)  # Hold write lock briefly
            conn.commit()
            cursor.close()
            conn.close()
            write_finished.set()

        def reader():
            write_started.wait()
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM users")
            _ = cursor.fetchone()
            read_success.append(True)
            cursor.close()
            conn.close()

        w_thread = threading.Thread(target=writer)
        r_thread = threading.Thread(target=reader)

        w_thread.start()
        r_thread.start()

        w_thread.join()
        r_thread.join()

        self.assertTrue(read_success, "Reader must succeed concurrently during WAL write")

        # Cleanup
        with get_db_cursor() as cursor:
            cursor.execute("DELETE FROM chat_usage WHERE user_id = 'wal_test'")

    # ── SEC-03: Rate Limiting & Persistence Tests ────────────────────────────

    def test_sec03_in_memory_backend(self):
        """SEC-03: InMemoryRateLimiterBackend blocks after threshold and resets."""
        backend = InMemoryRateLimiterBackend()
        ident = "test_mem_rate@example.com"
        backend.reset(ident)

        is_locked, _ = backend.is_locked(ident, max_attempts=3, window_seconds=60)
        self.assertFalse(is_locked)

        backend.record_failure(ident, window_seconds=60)
        backend.record_failure(ident, window_seconds=60)
        self.assertFalse(backend.is_locked(ident, max_attempts=3, window_seconds=60)[0])

        backend.record_failure(ident, window_seconds=60)
        is_locked, msg = backend.is_locked(ident, max_attempts=3, window_seconds=60)
        self.assertTrue(is_locked)
        self.assertIn("Too many failed login attempts", msg)

        backend.reset(ident)
        self.assertFalse(backend.is_locked(ident, max_attempts=3, window_seconds=60)[0])

    def test_sec03_sqlite_backend_persistence_across_instances(self):
        """SEC-03: SQLiteRateLimiterBackend persists attempts across separate backend instances (simulating process restart)."""
        ident = "test_sqlite_restart@example.com"
        backend1 = SQLiteRateLimiterBackend()
        backend1.reset(ident)

        # Record 5 failures on instance 1
        for _ in range(5):
            backend1.record_failure(ident, window_seconds=300)

        self.assertTrue(backend1.is_locked(ident, max_attempts=5, window_seconds=300)[0])

        # Simulate fresh process restart / new worker instance
        backend2 = SQLiteRateLimiterBackend()
        is_locked, msg = backend2.is_locked(ident, max_attempts=5, window_seconds=300)
        self.assertTrue(is_locked, "Lockout state must survive process restart in SQLite backend")
        self.assertIn("Too many failed login attempts", msg)

        # Reset on instance 2
        backend2.reset(ident)
        self.assertFalse(backend1.is_locked(ident, max_attempts=5, window_seconds=300)[0])

    def test_sec03_rate_limiter_identity_isolation(self):
        """SEC-03: Separate identifiers have isolated failure counters."""
        backend = SQLiteRateLimiterBackend()
        id_a = "user_a_rate@example.com"
        id_b = "user_b_rate@example.com"
        backend.reset(id_a)
        backend.reset(id_b)

        for _ in range(5):
            backend.record_failure(id_a, window_seconds=300)

        self.assertTrue(backend.is_locked(id_a, max_attempts=5, window_seconds=300)[0])
        self.assertFalse(backend.is_locked(id_b, max_attempts=5, window_seconds=300)[0])

        backend.reset(id_a)
        backend.reset(id_b)

    def test_sec03_redis_backend_fallback_on_unreachable(self):
        """SEC-03: Redis backend gracefully falls back to SQLite when Redis is unavailable."""
        redis_backend = RedisRateLimiterBackend("redis://nonexistent_host_12345:6379/0")
        ident = "test_redis_fallback@example.com"
        redis_backend.reset(ident)

        # Should fall back cleanly without raising unhandled exception
        is_locked, _ = redis_backend.is_locked(ident, max_attempts=5, window_seconds=300)
        self.assertFalse(is_locked)

        for _ in range(5):
            redis_backend.record_failure(ident, window_seconds=300)

        is_locked, msg = redis_backend.is_locked(ident, max_attempts=5, window_seconds=300)
        self.assertTrue(is_locked, "Fallback backend must enforce rate limits when Redis is down")
        redis_backend.reset(ident)

    def test_sec03_unified_rate_limiter_interface(self):
        """SEC-03: Unified RateLimiter.get() functions with default SQLite backend."""
        limiter = RateLimiter.get()
        ident = "test_unified_rate@example.com"
        limiter.reset(ident)

        self.assertFalse(limiter.is_locked(ident)[0])
        for _ in range(5):
            limiter.record_failure(ident)

        self.assertTrue(limiter.is_locked(ident)[0])
        limiter.reset(ident)
        self.assertFalse(limiter.is_locked(ident)[0])


if __name__ == "__main__":
    unittest.main()
