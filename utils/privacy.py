"""
AI Privacy and Financial Data Minimization Engine
=================================================
Provides configurable privacy modes for external LLM processing (Google Gemini / Groq Cloud).
Anonymizes and sanitizes sensitive user demographics, income, net worth, liabilities,
and scenario simulations to prevent transmission of raw personal financial data (PII).
"""

import logging
import streamlit as st
from typing import Optional
from database.connection import get_db_cursor

logger = logging.getLogger(__name__)

# Privacy Modes
PRIVACY_MODE_ANONYMIZED = "anonymized"  # Default & Recommended: Bracketed ranges, no personal PII
PRIVACY_MODE_MINIMAL    = "minimal"     # High-level financial health tier only, zero balance figures
PRIVACY_MODE_FULL       = "full"        # Explicit opt-in: Unmasked values for granular calculations

ALL_PRIVACY_MODES = [PRIVACY_MODE_ANONYMIZED, PRIVACY_MODE_MINIMAL, PRIVACY_MODE_FULL]
DEFAULT_PRIVACY_MODE = PRIVACY_MODE_ANONYMIZED


def _ensure_preferences_table():
    """Ensures the user_preferences table exists in SQLite."""
    try:
        with get_db_cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS user_preferences (
                    user_id TEXT PRIMARY KEY,
                    ai_privacy_mode TEXT NOT NULL DEFAULT 'anonymized',
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
    except Exception as e:
        logger.warning(f"Could not verify user_preferences table: {e}")


def get_user_privacy_mode(user_id: Optional[str]) -> str:
    """
    Returns the active privacy mode for the specified user.
    Falls back to 'anonymized' if unset or unauthenticated.
    """
    if not user_id:
        return DEFAULT_PRIVACY_MODE

    session_key = f"_ai_privacy_mode_{user_id}"
    if session_key in st.session_state:
        return st.session_state[session_key]

    _ensure_preferences_table()
    try:
        with get_db_cursor() as cursor:
            cursor.execute(
                "SELECT ai_privacy_mode FROM user_preferences WHERE user_id = ?",
                (user_id,),
            )
            row = cursor.fetchone()
            if row and row["ai_privacy_mode"] in ALL_PRIVACY_MODES:
                mode = row["ai_privacy_mode"]
                st.session_state[session_key] = mode
                return mode
    except Exception as e:
        logger.warning(f"Error reading privacy mode from DB for {user_id}: {e}")

    # Default to privacy-preserving anonymized mode
    st.session_state[session_key] = DEFAULT_PRIVACY_MODE
    return DEFAULT_PRIVACY_MODE


def set_user_privacy_mode(user_id: str, mode: str) -> bool:
    """
    Persists the user's chosen privacy preference in SQLite and updates session cache.
    """
    if mode not in ALL_PRIVACY_MODES or not user_id:
        return False

    _ensure_preferences_table()
    try:
        with get_db_cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO user_preferences (user_id, ai_privacy_mode, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id) DO UPDATE SET
                    ai_privacy_mode = excluded.ai_privacy_mode,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (user_id, mode),
            )
        session_key = f"_ai_privacy_mode_{user_id}"
        st.session_state[session_key] = mode
        return True
    except Exception as e:
        logger.error(f"Failed to persist privacy preference for {user_id}: {e}")
        return False


# ── Bracket & Generalization Helpers ─────────────────────────────────────────

def bracket_inr(amount: float) -> str:
    """
    Transforms exact rupee amounts into generalized brackets for data minimization.
    """
    if amount is None or amount <= 0:
        return "₹0"
    if amount < 25000:
        return "Under ₹25k"
    elif amount < 50000:
        return "₹25k - ₹50k"
    elif amount < 75000:
        return "₹50k - ₹75k"
    elif amount < 100000:
        return "₹75k - ₹1 Lakh"
    elif amount < 150000:
        return "₹1L - ₹1.5 Lakhs"
    elif amount < 250000:
        return "₹1.5L - ₹2.5 Lakhs"
    elif amount < 500000:
        return "₹2.5L - ₹5 Lakhs"
    elif amount < 1000000:
        return "₹5L - ₹10 Lakhs"
    elif amount < 2500000:
        return "₹10L - ₹25 Lakhs"
    elif amount < 5000000:
        return "₹25L - ₹50 Lakhs"
    elif amount < 10000000:
        return "₹50L - ₹1 Crore"
    else:
        return "Above ₹1 Crore"


def bracket_age(age: int) -> str:
    """Generalizes exact age into an age bracket to protect identity."""
    if not age or age <= 0:
        return "Adult (20-40)"
    if age < 25:
        return "Early 20s"
    elif age < 30:
        return "Late 20s"
    elif age < 35:
        return "Early 30s"
    elif age < 40:
        return "Late 30s"
    elif age < 50:
        return "40s"
    else:
        return "50+"


def generalize_dti(monthly_emi: float, total_income: float) -> str:
    """Categorizes debt-to-income without exposing exact EMI."""
    if total_income <= 0 or monthly_emi <= 0:
        return "No active EMI burden"
    ratio = monthly_emi / total_income
    if ratio < 0.20:
        return "Low EMI burden (< 20% of income)"
    elif ratio < 0.40:
        return "Moderate EMI burden (20% - 40% of income)"
    else:
        return "High EMI burden (> 40% of income)"


# ── Context Sanitization Engine ──────────────────────────────────────────────

def sanitize_financial_profile(twin, mode: str = PRIVACY_MODE_ANONYMIZED) -> str:
    """
    Produces a sanitized profile string for the LLM system prompt according
    to the active privacy mode (full, anonymized, or minimal).
    """
    if twin is None:
        return ""

    if mode == PRIVACY_MODE_FULL:
        return f"""
[USER CONSENT: FULL CONTEXT ACTIVE]
Name: {twin.name} | Age: {twin.age} | Occupation: {twin.occupation} | City: {twin.city}
Monthly income (incl. extra income): ₹{twin.total_income:,.0f}
Net worth: ₹{twin.net_worth:,.0f}
Bank savings: ₹{twin.bank_savings:,.0f} | Fixed deposits: ₹{twin.fd_amount:,.0f} | Emergency fund: ₹{twin.emergency_fund:,.0f}
Investments — SIP: ₹{twin.sip_amount:,.0f}/mo, Mutual funds: ₹{twin.mutual_funds:,.0f}, Stocks: ₹{twin.stocks:,.0f}, PPF: ₹{twin.ppf_investment:,.0f}, NPS: ₹{twin.nps_investment:,.0f}
Debt — Home loan: ₹{twin.home_loan:,.0f}, Car loan: ₹{twin.car_loan:,.0f}, Credit card debt: ₹{twin.credit_card_debt:,.0f}, Monthly EMI: ₹{twin.monthly_emi:,.0f}
Insurance — Health: ₹{twin.health_insurance:,.0f}, Life: ₹{twin.life_insurance:,.0f}
Monthly essential expenses: ₹{twin.basic_expenses:,.0f}
Goal: {twin.goal_type or 'Not set'} (target ₹{twin.goal_amount:,.0f})
"""

    elif mode == PRIVACY_MODE_MINIMAL:
        # Minimal mode: Zero figures or asset balances; only high-level archetype
        return f"""
[DATA MINIMIZATION: MINIMAL CONTEXT ACTIVE]
User Archetype: Indian Resident (Age Bracket: {bracket_age(twin.age)})
Occupation Sector: {twin.occupation or 'Professional'}
Primary Financial Goal Category: {twin.goal_type or 'General Wealth Accumulation'}
Note: Exact balances, liabilities, and income figures have been redacted per the user's Minimal Privacy Preference. Focus advice on financial principles, strategic ratios, and behavioral rules.
"""

    else:
        # Default: ANONYMIZED (Ranges/Brackets, No Name/City/Direct Identifiers)
        income_b = bracket_inr(twin.total_income)
        net_worth_b = bracket_inr(twin.net_worth)
        savings_b = bracket_inr(twin.bank_savings + twin.fd_amount)
        emergency_b = bracket_inr(twin.emergency_fund)
        invest_b = bracket_inr(twin.mutual_funds + twin.stocks + twin.ppf_investment + twin.nps_investment)
        debt_b = bracket_inr(twin.home_loan + twin.car_loan + twin.credit_card_debt)
        expenses_b = bracket_inr(twin.basic_expenses)
        dti_band = generalize_dti(twin.monthly_emi, twin.total_income)
        goal_b = bracket_inr(twin.goal_amount)

        has_health_ins = "Yes" if twin.health_insurance > 0 else "No"
        has_life_ins = "Yes" if twin.life_insurance > 0 else "No"

        return f"""
[DATA MINIMIZATION: ANONYMIZED CONTEXT ACTIVE (Ranges & Brackets Only)]
Demographics: Age Bracket: {bracket_age(twin.age)} | Occupation Domain: {twin.occupation or 'Salaried Professional'} (Personal Name & City Redacted)
Monthly Income Bracket: {income_b}
Net Worth Bracket: {net_worth_b}
Liquid Savings & FDs: {savings_b} | Emergency Fund: {emergency_b}
Total Investments (SIP, Mutual Funds, Stocks, PPF, NPS): {invest_b}
Total Outstanding Debt: {debt_b} | Debt Burden: {dti_band}
Insurance Coverage Status — Health Insurance: {has_health_ins}, Term Life Insurance: {has_life_ins}
Monthly Essential Expenses Bracket: {expenses_b}
Target Goal: {twin.goal_type or 'Wealth Building'} (Target Bracket: {goal_b})
Note: Exact monetary figures are generalized into brackets per user privacy policy.
"""


def sanitize_predictions_and_scenarios(twin, mode: str = PRIVACY_MODE_ANONYMIZED) -> str:
    """
    Computes ML predictions and life event scenarios, formatting them according to
    the active privacy mode. Redacts raw figures in minimal mode and brackets them in anonymized mode.
    """
    if twin is None or mode == PRIVACY_MODE_MINIMAL:
        # Minimal mode suppresses scenario numbers entirely
        return ""

    if mode == PRIVACY_MODE_FULL:
        # Full mode returns exact before/after numbers
        from utils.chatbot import _build_predictions_and_scenarios_context
        return _build_predictions_and_scenarios_context(twin)

    # Anonymized mode: Use percentage deltas and score changes instead of exact rupee amounts
    lines = []
    try:
        from utils.cache import get_cached_predictor
        predictor, loaded = get_cached_predictor(horizon=6)
        if not loaded:
            predictor.load_only(horizon=6)
        pred_6 = predictor.predict(twin, horizon_months=6)
        pred_12 = predictor.predict(twin, horizon_months=12)

        lines.extend([
            "== Machine Learning Predictions (XGBoost Directional Forecast) ==",
            f"- 6-Month Projected Monthly Savings Bracket: {bracket_inr(pred_6['predicted_savings'])}",
            f"- 6-Month Projected Net Worth Bracket: {bracket_inr(pred_6['predicted_net_worth'])}",
            f"- 12-Month Projected Monthly Savings Bracket: {bracket_inr(pred_12['predicted_savings'])}",
            f"- 12-Month Projected Net Worth Bracket: {bracket_inr(pred_12['predicted_net_worth'])}",
            ""
        ])
    except Exception:
        pass

    try:
        from utils.simulator import ScenarioSimulator
        sim = ScenarioSimulator(twin)
        scenarios = [
            ("Salary Hike", {"hike_percent": 20}),
            ("Job Loss", {"duration_months": 6, "recovery_salary_pct": 100}),
            ("Car Purchase", {"car_price": 800000, "downpayment_pct": 0.20, "loan_rate": 0.085, "tenure_years": 5}),
            ("Home Loan", {"purchase_price": 5000000, "downpayment_pct": 0.20, "home_loan_rate": 0.085, "tenure_years": 20}),
            ("Marriage Expense", {"one_time_cost": 500000, "monthly_expense_hike": 10000}),
            ("Increase SIP", {"sip_increase_pct": 50}),
        ]

        lines.append("== Simulated Life Decisions & Scenarios (Directional & Bracketed Deltas) ==")
        for name, params in scenarios:
            res = sim.run_scenario(name, **params)
            b = res.before
            a = res.after
            surplus_delta = a.monthly_surplus - b.monthly_surplus
            surplus_direction = "Increase" if surplus_delta >= 0 else "Decrease"
            lines.extend([
                f"- Scenario: {name}",
                f"  * Monthly Surplus Impact: {surplus_direction} ({bracket_inr(abs(surplus_delta))})",
                f"  * Health Score: {b.health_score:.0f}/100 -> {a.health_score:.0f}/100 (Delta: {a.health_score - b.health_score:+.1f} pts)",
                f"  * Risk Level Transition: {b.risk_level} -> {a.risk_level}"
            ])
        lines.append("")
    except Exception:
        pass

    return "\n".join(lines)
