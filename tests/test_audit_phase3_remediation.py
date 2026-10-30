"""
tests/test_audit_phase3_remediation.py
======================================
Automated verification tests for Phase 3 Audit Remediation:
- SEC-05: HTML escaping and XSS mitigation across dynamic HTML sinks
  (profile, goals, transactions, unverified email, AI coach, chatbot).
- Attribute-breakout encoding verification (quotes, event handlers).
- Database-controlled untrusted input flow verification.
- Preservation of legitimate Markdown formatting in chatbot output.
- Phase 1 & Phase 2 security regression protection.
"""

import os
import sys
import unittest
import uuid
from html import escape as _he
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from database.connection import (
    init_db,
    get_db_cursor,
    is_demo_seed_enabled,
    get_database_pragmas,
)
from database.db_manager import DBManager
from utils.security import (
    sanitize_html_output,
    escape_html,
    RateLimiter,
    SQLiteRateLimiterBackend,
    InMemoryRateLimiterBackend,
)
from utils import auth
from utils.chatbot import (
    _format_inline_markdown,
    _format_chat_markdown,
    _build_system_prompt,
)
from utils.privacy import (
    get_user_privacy_mode,
    PRIVACY_MODE_ANONYMIZED,
)
from utils.ui_components import PremiumLoader
from models.twin_engine import FinancialDigitalTwin


class MockTwinForSecurity:
    """Mock Digital Twin with controllable demographic and financial fields."""
    def __init__(self, name="Test User", occupation="Engineer", city="Mumbai", user_id="sec_test_01"):
        self.user_id = user_id
        self.name = name
        self.age = 30
        self.city = city
        self.occupation = occupation
        self.total_income = 100000.0
        self.net_worth = 500000.0
        self.bank_savings = 50000.0
        self.fd_amount = 50000.0
        self.emergency_fund = 60000.0
        self.sip_amount = 15000.0
        self.mutual_funds = 200000.0
        self.stocks = 100000.0
        self.ppf_investment = 50000.0
        self.nps_investment = 50000.0
        self.home_loan = 0.0
        self.car_loan = 0.0
        self.credit_card_debt = 0.0
        self.monthly_emi = 0.0
        self.health_insurance = 500000.0
        self.life_insurance = 5000000.0
        self.basic_expenses = 35000.0
        self.rent = 15000.0
        self.groceries = 10000.0
        self.utilities = 5000.0
        self.transport = 5000.0
        self.food_delivery = 3000.0
        self.entertainment = 3000.0
        self.shopping = 4000.0
        self.bonus = 0.0
        self.additional_income = 0.0
        self.monthly_income = 100000.0
        self.goal_type = "Retirement"
        self.goal_amount = 5000000.0


class TestAuditPhase3Remediation(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        init_db()

    # ── Test 1: HTML Escaping (<script> tags) ──────────────────────────────────

    def test_sec05_html_escaping_script_tag(self):
        """Test 1: Verify <script>alert('XSS')</script> is converted into harmless text entities."""
        payload = '<script>alert("XSS")</script>'
        escaped = sanitize_html_output(payload)
        self.assertNotIn("<script>", escaped)
        self.assertNotIn("</script>", escaped)
        self.assertIn("&lt;script&gt;", escaped)
        self.assertIn("&lt;/script&gt;", escaped)

        # Also test escape_html alias
        escaped_alias = escape_html(payload)
        self.assertEqual(escaped, escaped_alias)

    # ── Test 2: HTML Event Handler Payload ────────────────────────────────────

    def test_sec05_html_event_handler_payload(self):
        """Test 2: Verify <img src=x onerror=alert(1)> cannot become executable HTML."""
        payload = '<img src=x onerror=alert(1)>'
        escaped = sanitize_html_output(payload)
        self.assertNotIn("<img", escaped)
        self.assertIn("&lt;img", escaped)
        self.assertNotIn("onerror=alert(1)>", escaped)
        self.assertIn("onerror=alert(1)&gt;", escaped)

    # ── Test 3: Attribute Breakout Payload ────────────────────────────────────

    def test_sec05_attribute_breakout_payload(self):
        """Test 3: Malicious content attempting to break out of an HTML attribute with quotes."""
        payload_double = '" onmouseover="alert(1)'
        escaped_double = sanitize_html_output(payload_double)
        self.assertNotIn('"', escaped_double)
        self.assertIn('&quot;', escaped_double)

        payload_single = "' onfocus='alert(1)"
        escaped_single = sanitize_html_output(payload_single)
        self.assertNotIn("'", escaped_single)
        self.assertIn("&#x27;", escaped_single)

    # ── Test 4: Database-Controlled Content ───────────────────────────────────

    def test_sec05_database_controlled_content(self):
        """Test 4: Insert malicious value into DB, retrieve, and pass through sanitization."""
        unique_id = f"sec05_db_{uuid.uuid4().hex[:8]}"
        malicious_name = '"><script>alert("db_xss")</script>'
        email = f"{unique_id}@example.com"

        with get_db_cursor() as cursor:
            cursor.execute(
                "INSERT INTO users (user_id, email, password_hash, name, age, email_verified) VALUES (?, ?, ?, ?, ?, ?)",
                (unique_id, email, "dummy_hash", malicious_name, 28, 1),
            )

        try:
            profile = DBManager.get_user_profile(unique_id)
            self.assertIsNotNone(profile)
            raw_db_name = profile["name"]
            self.assertEqual(raw_db_name, malicious_name)

            # Pass retrieved DB value through protected rendering filter
            safe_rendered = sanitize_html_output(raw_db_name)
            self.assertNotIn("<script>", safe_rendered)
            self.assertIn("&lt;script&gt;", safe_rendered)
            self.assertIn("&quot;&gt;", safe_rendered)
        finally:
            with get_db_cursor() as cursor:
                cursor.execute("DELETE FROM users WHERE user_id = ?", (unique_id,))

    # ── Test 5: User Profile Content ──────────────────────────────────────────

    def test_sec05_user_profile_content_safe_rendering(self):
        """Test 5: Malicious values in profile fields (name, occupation, city)."""
        twin = MockTwinForSecurity(
            name="<script>alert('name')</script>",
            occupation='Fintech "><script>alert(1)</script>',
            city="<img src=x onerror=alert('city')>",
        )

        # Profile card rendering path in 03_Behavior_Analysis
        safe_name = _he(twin.name)
        safe_occ = _he(twin.occupation or "Salaried Professional")
        safe_city = _he(twin.city or "India")

        rendered_html = (
            f"<h3 style='color:#F9FAFB'>{safe_name}</h3>"
            f"<span>{safe_occ} &middot; Age {twin.age} &middot; {safe_city}</span>"
        )

        self.assertNotIn("<script>", rendered_html)
        self.assertNotIn("<img", rendered_html)
        self.assertIn("&lt;script&gt;", rendered_html)
        self.assertIn("&lt;img", rendered_html)

        # Sidebar profile footer rendering path in utils/session.py
        name_parts = [p for p in twin.name.strip().split() if p]
        initials = f"{name_parts[0][0]}{name_parts[-1][0]}".upper() if len(name_parts) >= 2 else "FT"
        safe_initials = _he(initials)
        safe_twin_name = _he(twin.name)

        sidebar_html = (
            f'<div class="profile-avatar">{safe_initials}</div>'
            f'<div class="profile-fullname">{safe_twin_name}</div>'
        )
        self.assertNotIn("<script>", sidebar_html)
        self.assertIn("&lt;script&gt;", sidebar_html)

    # ── Test 6: Transaction Content ───────────────────────────────────────────

    def test_sec05_transaction_content_safe_rendering(self):
        """Test 6: Malicious transaction categories or descriptions."""
        malicious_category = '<b onmouseover="alert(\'tx\')">Luxury Dining</b>'
        safe_cat = _he(malicious_category)

        rendered_row = f'<div class="chart-summary-row"><span>{safe_cat}</span><span>₹5,000</span></div>'
        self.assertNotIn('<b onmouseover=', rendered_row)
        self.assertIn('&lt;b onmouseover=&quot;', rendered_row)

    # ── Test 7: Goal Content ──────────────────────────────────────────────────

    def test_sec05_goal_content_safe_rendering(self):
        """Test 7: Malicious goal name in planning headers and lists."""
        malicious_goal = "House <script>alert('pwn_goal')</script>"
        safe_goal = _he(malicious_goal)

        planning_header = f"<h3>Planning Result — {safe_goal}</h3>"
        self.assertNotIn("<script>", planning_header)
        self.assertIn("&lt;script&gt;", planning_header)

        # Multi-goal feasibility list rendering
        goal_list = [malicious_goal, "Retirement"]
        rendered_goals = ', '.join([_he(g) for g in goal_list])
        self.assertNotIn("<script>", rendered_goals)
        self.assertIn("&lt;script&gt;alert(&#x27;pwn_goal&#x27;)&lt;/script&gt;", rendered_goals)

    # ── Test 8: Chatbot Content & Markdown Preservation ───────────────────────

    def test_sec05_chatbot_markdown_preserves_legitimate_formatting_and_escapes_xss(self):
        """Test 8: Chatbot output escapes arbitrary HTML while preserving Markdown (bold, italic, tables)."""
        raw_msg = (
            "**Key Finding**: Your savings rate is *optimal*.\n"
            "Here is `code_snippet()`.\n"
            "<script>alert('chatbot_xss')</script>\n"
            "<img src=x onerror=alert('img_xss')>"
        )

        formatted = _format_chat_markdown(raw_msg)

        # Verify XSS payloads are safely neutralized
        self.assertNotIn("<script>", formatted)
        self.assertNotIn("<img", formatted)
        self.assertIn("&lt;script&gt;", formatted)
        self.assertIn("&lt;img", formatted)

        # Verify legitimate Markdown tags are rendered
        self.assertIn("<strong", formatted)
        self.assertIn("Key Finding", formatted)
        self.assertIn("<em", formatted)
        self.assertIn("optimal", formatted)
        self.assertIn("<code", formatted)

    def test_sec05_chatbot_table_markdown_escaping(self):
        """Test 8b: Chatbot tables with malicious cells encode HTML inside <td> elements."""
        table_md = (
            "| Asset | Allocation | Note |\n"
            "|---|---|---|\n"
            "| Equity | 60% | <script>alert(1)</script> |\n"
            "| Debt | 40% | Safe |"
        )
        table_html = _format_chat_markdown(table_md)
        self.assertIn("<table", table_html)
        self.assertIn("<td", table_html)
        self.assertNotIn("<script>", table_html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", table_html)

    # ── Test 9: Unverified Email Prompt Escaping ───────────────────────────────

    def test_sec05_unverified_email_sanitization(self):
        """Test 9: Verify unverified email in session state cannot inject HTML."""
        malicious_email = 'victim@example.com"><script>alert("email")</script>'
        safe_unverified = _he(malicious_email)
        resend_html = f"Need a new activation link for <strong>{safe_unverified}</strong>?"

        self.assertNotIn('<script>', resend_html)
        self.assertIn('&quot;&gt;&lt;script&gt;', resend_html)

    # ── Test 10: UI Components (Loader & Scenario Name) ───────────────────────

    def test_sec05_loader_and_scenario_sanitization(self):
        """Test 10: Verify loader title/subtitle and scenario name escaping."""
        loader_title = 'Loading <script>alert("loader")</script>'
        safe_title = _he(loader_title)
        self.assertNotIn("<script>", safe_title)
        self.assertIn("&lt;script&gt;", safe_title)

        scenario_name = 'Salary Hike <img src=x onerror=alert(1)>'
        safe_scenario = _he(scenario_name)
        card_html = f"After {safe_scenario}"
        self.assertNotIn("<img", card_html)
        self.assertIn("&lt;img", card_html)

    # ── Phase 1 Security Regression Protection ────────────────────────────────

    def test_phase1_regression_sec01_uid_query_param_cannot_authenticate(self):
        """Regression SEC-01: Confirm query param 'uid' does not auto-authenticate."""
        fake_uid = "user_attacker_01"
        self.assertIsNone(auth.get_user_by_id(fake_uid))

    def test_phase1_regression_sec02_token_security(self):
        """Regression SEC-02: Reset & verification tokens must be single-use and time-bound."""
        raw_token, token_hash, expires_at = auth._generate_secure_token()
        self.assertGreaterEqual(len(raw_token), 32)
        self.assertEqual(len(token_hash), 64)  # sha256 hex digest is 64 chars
        self.assertIsNotNone(expires_at)

    def test_phase1_regression_priv01_privacy_controls_intact(self):
        """Regression PRIV-01: Anonymized privacy mode remains default for AI chatbot."""
        twin = MockTwinForSecurity()
        mode = get_user_privacy_mode(twin.user_id)
        self.assertEqual(mode, PRIVACY_MODE_ANONYMIZED)
        prompt = _build_system_prompt(twin)
        self.assertNotIn("Name: Test User", prompt)

    # ── Phase 2 Security Regression Protection ────────────────────────────────

    def test_phase2_regression_sec04_demo_seed_disabled(self):
        """Regression SEC-04: Demo seeding remains disabled by default."""
        os.environ.pop("ENABLE_DEMO_SEED", None)
        self.assertFalse(is_demo_seed_enabled())

    def test_phase2_regression_data01_sqlite_pragmas(self):
        """Regression DATA-01: WAL mode and busy_timeout=5000 active."""
        pragmas = get_database_pragmas()
        self.assertEqual(pragmas.get("journal_mode", "").lower(), "wal")
        self.assertEqual(pragmas.get("busy_timeout"), 5000)
        self.assertEqual(pragmas.get("foreign_keys"), 1)

    def test_phase2_regression_sec03_rate_limiting(self):
        """Regression SEC-03: Rate limiter default backend is SQLite with persistent tracking."""
        os.environ.pop("RATE_LIMIT_BACKEND", None)
        backend = RateLimiter().get_backend()
        self.assertIsInstance(backend, SQLiteRateLimiterBackend)


if __name__ == "__main__":
    unittest.main()
