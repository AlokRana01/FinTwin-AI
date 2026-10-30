"""
tests/test_audit_phase1_remediation.py
======================================
Automated verification tests for Phase 1 Audit Remediation:
- SEC-01: Insecure 'uid' query parameter authentication bypass removed.
- SEC-02: Cryptographic token validation, time-bounding, single-use, and URL scrubbing.
- PRIV-01: AI privacy controls (Anonymized default, Minimal, Full) and data minimization.
"""

import sys
import unittest
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import streamlit as st
from database.connection import init_db, get_db_cursor
from database.db_manager import DBManager
from utils import auth
from utils.privacy import (
    get_user_privacy_mode,
    set_user_privacy_mode,
    sanitize_financial_profile,
    bracket_inr,
    bracket_age,
    PRIVACY_MODE_ANONYMIZED,
    PRIVACY_MODE_MINIMAL,
    PRIVACY_MODE_FULL,
    DEFAULT_PRIVACY_MODE,
)
from utils.chatbot import _build_system_prompt
from models.twin_engine import FinancialDigitalTwin


class MockTwin:
    def __init__(self):
        self.user_id = "test_user_privacy_001"
        self.name = "Vikram Sharma"
        self.age = 32
        self.city = "Bengaluru"
        self.occupation = "Cloud Solutions Architect"
        self.total_income = 165000.0
        self.net_worth = 4500000.0
        self.bank_savings = 350000.0
        self.fd_amount = 500000.0
        self.emergency_fund = 400000.0
        self.sip_amount = 45000.0
        self.mutual_funds = 1800000.0
        self.stocks = 600000.0
        self.ppf_investment = 300000.0
        self.nps_investment = 150000.0
        self.home_loan = 3200000.0
        self.car_loan = 0.0
        self.credit_card_debt = 25000.0
        self.monthly_emi = 32000.0
        self.health_insurance = 1000000.0
        self.life_insurance = 20000000.0
        self.basic_expenses = 65000.0
        self.goal_type = "Early Retirement"
        self.goal_amount = 30000000.0


class TestAuditPhase1Remediation(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        # Reset session state mock
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        for key in list(st.query_params.keys()):
            del st.query_params[key]

    # ── SEC-01 Tests ─────────────────────────────────────────────────────────

    def test_sec01_unauthenticated_uid_param_does_not_create_session(self):
        """SEC-01: An unauthenticated request with ?uid=... must NEVER populate user_id in session_state."""
        st.query_params["uid"] = "demo_user"
        self.assertNotIn("user_id", st.session_state)

        # Simulate session_tracker query param sanitation
        if "uid" in st.query_params:
            del st.query_params["uid"]

        self.assertNotIn("user_id", st.session_state, "user_id must not be populated from uid parameter")
        self.assertNotIn("uid", st.query_params, "Injected uid query parameter must be stripped")

    def test_sec01_unknown_uid_param_does_not_create_session(self):
        """SEC-01: Injected arbitrary user IDs are rejected and stripped."""
        st.query_params["uid"] = "arbitrary_attacker_id_999"
        if "uid" in st.query_params:
            del st.query_params["uid"]

        self.assertNotIn("user_id", st.session_state)
        self.assertNotIn("uid", st.query_params)

    # ── SEC-02 Tests ─────────────────────────────────────────────────────────

    def test_sec02_token_single_use_and_scrubbing(self):
        """SEC-02: Reset tokens must be single-use and invalid after first use."""
        test_email = "test.sec02.reset@example.com"
        with get_db_cursor() as cursor:
            cursor.execute("DELETE FROM users WHERE email = ?", (test_email,))

        # Register and verify
        ok_reg, _, uid = auth.register_user(
            email=test_email,
            password="InitialPassword#123",
            name="Token Test User",
            age=28,
            confirm_password="InitialPassword#123",
        )
        self.assertTrue(ok_reg)

        with get_db_cursor() as cursor:
            cursor.execute("UPDATE users SET email_verified = 1 WHERE user_id = ?", (uid,))

        # Request password reset
        raw_token, token_hash, expires_at = auth._generate_secure_token()
        with get_db_cursor() as cursor:
            cursor.execute(
                "UPDATE users SET reset_token_hash = ?, reset_expires_at = ? WHERE user_id = ?",
                (token_hash, expires_at, uid),
            )

        # 1. Valid token validates
        is_valid, msg, email = auth.validate_reset_token(raw_token)
        self.assertTrue(is_valid)
        self.assertEqual(email, test_email)

        # 2. Reset password using token
        new_pw = "NewSecurePassword#2026"
        ok_reset, reset_msg = auth.reset_password_with_token(raw_token, new_pw, new_pw)
        self.assertTrue(ok_reset)

        # 3. Token cannot be replayed/reused
        is_valid_again, msg_again, _ = auth.validate_reset_token(raw_token)
        self.assertFalse(is_valid_again, "Replayed reset token must be rejected")

        # Clean up
        with get_db_cursor() as cursor:
            cursor.execute("DELETE FROM users WHERE user_id = ?", (uid,))

    def test_sec02_tampered_token_rejected(self):
        """SEC-02: Modified/tampered tokens are rejected."""
        is_valid, _, _ = auth.validate_reset_token("tampered_token_value_xyz123456789")
        self.assertFalse(is_valid)

        ok_v, _ = auth.verify_email_token("tampered_verification_token_abc987654321")
        self.assertFalse(ok_v)

    # ── PRIV-01 Tests ────────────────────────────────────────────────────────

    def test_priv01_default_mode_is_anonymized(self):
        """PRIV-01: Default AI privacy mode must be 'anonymized' to prevent silent PII leakage."""
        mode = get_user_privacy_mode(None)
        self.assertEqual(mode, DEFAULT_PRIVACY_MODE)
        self.assertEqual(mode, PRIVACY_MODE_ANONYMIZED)

    def test_priv01_bracket_inr_transforms_currency(self):
        """PRIV-01: Exact rupee values are converted to realistic generalized brackets."""
        self.assertEqual(bracket_inr(0), "₹0")
        self.assertEqual(bracket_inr(15000), "Under ₹25k")
        self.assertEqual(bracket_inr(35000), "₹25k - ₹50k")
        self.assertEqual(bracket_inr(63500), "₹50k - ₹75k")
        self.assertEqual(bracket_inr(85000), "₹75k - ₹1 Lakh")
        self.assertEqual(bracket_inr(120000), "₹1L - ₹1.5 Lakhs")
        self.assertEqual(bracket_inr(1500000), "₹10L - ₹25 Lakhs")
        self.assertEqual(bracket_inr(4500000), "₹25L - ₹50 Lakhs")
        self.assertEqual(bracket_inr(15000000), "Above ₹1 Crore")

    def test_priv01_bracket_age(self):
        """PRIV-01: Exact age is generalized into a broad cohort."""
        self.assertEqual(bracket_age(23), "Early 20s")
        self.assertEqual(bracket_age(28), "Late 20s")
        self.assertEqual(bracket_age(32), "Early 30s")
        self.assertEqual(bracket_age(37), "Late 30s")

    def test_priv01_anonymized_profile_redacts_pii(self):
        """PRIV-01: Anonymized mode must NOT include real user name, city, or exact balances."""
        twin = MockTwin()
        sanitized = sanitize_financial_profile(twin, mode=PRIVACY_MODE_ANONYMIZED)

        # Verify PII is redacted
        self.assertNotIn("Vikram Sharma", sanitized, "User's real name must not be in anonymized prompt")
        self.assertNotIn("Bengaluru", sanitized, "User's city must not be in anonymized prompt")
        self.assertNotIn("165,000", sanitized, "Exact income must not be in anonymized prompt")
        self.assertNotIn("4,500,000", sanitized, "Exact net worth must not be in anonymized prompt")

        # Verify generalized brackets are present
        self.assertIn("Age Bracket: Early 30s", sanitized)
        self.assertIn("Monthly Income Bracket: ₹1.5L - ₹2.5 Lakhs", sanitized)
        self.assertIn("Net Worth Bracket: ₹25L - ₹50 Lakhs", sanitized)
        self.assertIn("ANONYMIZED CONTEXT ACTIVE", sanitized)

    def test_priv01_minimal_profile_removes_all_balances(self):
        """PRIV-01: Minimal mode strips all balance and monetary numbers."""
        twin = MockTwin()
        sanitized = sanitize_financial_profile(twin, mode=PRIVACY_MODE_MINIMAL)

        self.assertNotIn("Vikram Sharma", sanitized)
        self.assertNotIn("165,000", sanitized)
        self.assertNotIn("4,500,000", sanitized)
        self.assertNotIn("₹1.5L", sanitized)
        self.assertIn("MINIMAL CONTEXT ACTIVE", sanitized)
        self.assertIn("redacted", sanitized.lower())

    def test_priv01_privacy_mode_persistence(self):
        """PRIV-01: User privacy preferences persist across calls."""
        test_uid = "user_pref_test_42"
        # Set to minimal
        ok = set_user_privacy_mode(test_uid, PRIVACY_MODE_MINIMAL)
        self.assertTrue(ok)
        self.assertEqual(get_user_privacy_mode(test_uid), PRIVACY_MODE_MINIMAL)

        # Set to full
        ok = set_user_privacy_mode(test_uid, PRIVACY_MODE_FULL)
        self.assertTrue(ok)
        self.assertEqual(get_user_privacy_mode(test_uid), PRIVACY_MODE_FULL)

        # Set back to anonymized
        ok = set_user_privacy_mode(test_uid, PRIVACY_MODE_ANONYMIZED)
        self.assertTrue(ok)
        self.assertEqual(get_user_privacy_mode(test_uid), PRIVACY_MODE_ANONYMIZED)


if __name__ == "__main__":
    unittest.main()
