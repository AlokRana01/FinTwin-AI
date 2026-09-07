"""
utils/master_report.py
========================
Builds ONE consolidated, professional PDF report spanning every module of
FinTwin AI (User Profile, Financial Health Score, Income/Expense/Savings/
Investment Analysis, Net Worth, Financial Risk Assessment, Tax Intelligence,
AI Coach Recommendations, Financial Personality, Behaviour Analysis,
Forecasting, and Explainable AI).

Design principles (matching the per-page PDF exports):
  * Every number is produced by calling the SAME engines the Streamlit pages
    already use (HealthScoreEngine, IndianTaxCalculator, FinancialCoach,
    FinancialPersonalityClusterer, FinancialPredictor, ExplainableAI). No
    financial calculation is duplicated or re-derived here.
  * Each section is wrapped in its own try/except so that a missing model
    artifact (e.g. clusterer not yet trained) or an edge-case input simply
    skips that ONE section rather than failing the whole report — matching
    the "only include sections that contain data" requirement.
"""

from __future__ import annotations

import pandas as pd

import uuid
from utils.pdf_report import FinTwinPDFReport
from utils.visualizer import PlotlyVisualizer
from models.twin_engine import HealthScoreEngine


def build_master_report(twin) -> bytes:
    random_id = uuid.uuid4().hex[:8].upper()
    report = FinTwinPDFReport(
        report_title="FinTwin AI — Complete Financial Report",
        user_id=twin.user_id,
        report_id=f"MASTER-{random_id}",
        subtitle="Consolidated Digital Twin, Health Score, Forecasting, Tax, Coaching & AI Explainability",
    )

    # ---------------------------------------------------------------- #
    # 1. User Profile
    # ---------------------------------------------------------------- #
    try:
        payload = twin.export_twin()
        report.add_section("1. User Profile")
        report.add_key_value_grid({
            "User ID": twin.user_id,
            "Name": getattr(twin, "name", "—"),
            "Occupation": getattr(twin, "occupation", "—"),
            "Risk Level": payload.get("risk_level"),
        })
    except Exception:
        payload = {}

    # ---------------------------------------------------------------- #
    # 2. Financial Health Score
    # ---------------------------------------------------------------- #
    try:
        engine = HealthScoreEngine(twin)
        score_data = engine.compute_overall_health_score()
        report.add_section("2. Financial Health Score")
        report.add_key_value_grid({
            "Overall Score": score_data["overall_score"],
            "Financial Grade": score_data["financial_grade"],
        })
        try:
            fig = PlotlyVisualizer.plot_health_score_gauge(score_data["overall_score"])
            report.add_plotly_figure(fig, caption="Financial Health Score Gauge")
        except Exception:
            pass
    except Exception:
        pass

    # ---------------------------------------------------------------- #
    # 3-8. Financial Summary / Income / Expense / Savings / Investment / Net Worth
    # ---------------------------------------------------------------- #
    try:
        income = payload.get("income_profile", {})
        expense = payload.get("expense_profile", {})
        debt = payload.get("debt_profile", {})
        invest = payload.get("investment_profile", {})

        report.add_section("3. Financial Summary")
        report.add_key_value_grid({
            "Total Monthly Income": twin.total_income,
            "Net Worth": twin.net_worth,
            "Monthly Surplus": getattr(twin, "monthly_surplus", None),
        })

        if income:
            report.add_section("4. Income Analysis")
            report.add_key_value_grid(income)

        if expense:
            report.add_section("5. Expense Analysis")
            report.add_key_value_grid(expense)
            try:
                needs = twin.rent + twin.groceries + twin.utilities + twin.transport
                wants = twin.food_delivery + twin.entertainment + twin.shopping
                fig_nw = PlotlyVisualizer.plot_cash_flow_sankey(
                    twin.total_income, expense, max(twin.total_income - needs - wants, 0)
                )
                report.add_plotly_figure(fig_nw, caption="Cash Flow Breakdown")
            except Exception:
                pass

        report.add_section("6. Savings Analysis")
        report.add_key_value_grid({
            "SIP Amount": getattr(twin, "sip_amount", None),
            "Emergency Fund": getattr(twin, "emergency_fund", None),
        })

        if invest:
            report.add_section("7. Investment Analysis")
            report.add_key_value_grid(invest)
            try:
                fig_inv = PlotlyVisualizer.plot_investment_breakdown_bar(invest)
                report.add_plotly_figure(fig_inv, caption="Investment Breakdown")
            except Exception:
                pass

        report.add_section("8. Net Worth")
        report.add_key_value_grid({"Net Worth": twin.net_worth, **({"Total Debt": debt} if isinstance(debt, (int, float)) else {})})
    except Exception:
        pass

    # ---------------------------------------------------------------- #
    # 9. Financial Risk Assessment
    # ---------------------------------------------------------------- #
    try:
        report.add_section("9. Financial Risk Assessment")
        report.add_key_value_grid({"Risk Level": twin.risk_level})
    except Exception:
        pass

    # ---------------------------------------------------------------- #
    # 10. Tax Intelligence
    # ---------------------------------------------------------------- #
    try:
        from utils.tax_calculator import IndianTaxCalculator, DeductionProfile
        annual_income = float(getattr(twin, "monthly_income", 0)) * 12
        deductions = DeductionProfile(
            investment_80c=min(getattr(twin, "sip_amount", 0) * 12, 150000),
            health_insurance_self=getattr(twin, "health_insurance", 0),
            health_insurance_parents=0,
            nps_80ccd1b=0,
            home_loan_interest=0,
            other_deductions=0,
        )
        calc = IndianTaxCalculator()
        result = calc.compare_and_optimize(annual_income, deductions)
        report.add_section("10. Tax Intelligence")
        report.add_key_value_grid({
            "Recommended Regime": result["recommended_regime"],
            "Annual Savings": result["annual_savings"],
            "Old Regime Tax": result["old_regime"].total_tax,
            "New Regime Tax": result["new_regime"].total_tax,
        })
    except Exception:
        pass

    # ---------------------------------------------------------------- #
    # 11. AI Financial Coach Recommendations
    # ---------------------------------------------------------------- #
    try:
        from utils.coach import FinancialCoach
        coach_report = FinancialCoach(twin).generate_report()
        report.add_section("11. AI Financial Coach Recommendations")
        report.add_paragraph(coach_report.narrative)
        if coach_report.recommendations:
            rec_df = pd.DataFrame([
                {"Domain": r.domain.value if hasattr(r.domain, "value") else r.domain,
                 "Title": r.title, "Action": r.action, "Impact": r.impact}
                for r in coach_report.recommendations[:15]
            ])
            report.add_dataframe_table(rec_df)
    except Exception:
        pass

    # ---------------------------------------------------------------- #
    # 12. Financial Personality
    # ---------------------------------------------------------------- #
    try:
        from models.clustering import FinancialPersonalityClusterer
        clusterer = FinancialPersonalityClusterer.load()
        if clusterer.is_fitted():
            personality = clusterer.predict_personality(twin)
            report.add_section("12. Financial Personality")
            report.add_key_value_grid({"Detected Archetype": personality})
    except Exception:
        pass

    # ---------------------------------------------------------------- #
    # 13. Behaviour Analysis (peer comparison, if cohort data exists)
    # ---------------------------------------------------------------- #
    try:
        from database.db_manager import DBManager
        cohort_avg = DBManager.get_cohort_averages(twin.occupation)
        if cohort_avg:
            user_spend = {
                "Rent": twin.rent, "Groceries": twin.groceries, "Utilities": twin.utilities,
                "Transport": twin.transport, "Food Delivery": twin.food_delivery,
                "Entertainment": twin.entertainment, "Shopping": twin.shopping,
            }
            peer_spend = {k: cohort_avg.get(k.lower().replace(" ", "_"), 0.0) for k in user_spend}
            report.add_section("13. Behaviour Analysis")
            fig_peer = PlotlyVisualizer.plot_peer_comparison(user_spend, peer_spend)
            report.add_plotly_figure(fig_peer, caption="Your Spending vs. Peer Average")
    except Exception:
        pass

    # ---------------------------------------------------------------- #
    # 14. Forecasting Results
    # ---------------------------------------------------------------- #
    try:
        from models.predictor import FinancialPredictor
        predictor = FinancialPredictor()
        if predictor.load_only(horizon=6):
            pred_6 = predictor.predict(twin, horizon_months=6)
            report.add_section("14. Forecasting Results")
            report.add_key_value_grid({
                "Predicted Savings (6M)": pred_6["predicted_savings"],
                "Predicted Net Worth (6M)": pred_6["predicted_net_worth"],
            })
            try:
                df_traj = predictor.generate_trajectory(twin, months=12)
                fig_traj = PlotlyVisualizer.plot_forecast_trajectory(df_traj)
                report.add_plotly_figure(fig_traj, caption="12-Month Forecast Trajectory")
            except Exception:
                pass
    except Exception:
        pass

    # ---------------------------------------------------------------- #
    # 15. Explainable AI Summary
    # ---------------------------------------------------------------- #
    try:
        from models.explainability import ExplainableAI
        hs_result = ExplainableAI().explain_health_score(twin)
        report.add_section("15. Explainable AI Summary")
        for line in hs_result.narrative[:6]:
            report.add_paragraph(line)
    except Exception:
        pass

    return report.build()
