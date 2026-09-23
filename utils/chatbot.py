"""
Floating AI Chatbot Widget  (FinBot)
─────────────────────────────────────────────────────────────────────────────
A Gemini-powered assistant that floats bottom-right on every page of the app,
with a large, expressive animated "face" orb (idle blink + glance + breathing
glow, in the spirit of modern AI-assistant launchers). Clicking it opens a
roomy chat panel. Logged-in users get answers grounded in their own Financial
Digital Twin data (income, spending, investments, debt, goals) plus a digest
from the app's own rule-based AI Coach engine, so FinBot's advice matches
what the rest of the app already tells them. A daily message limit is
enforced per user (persisted in the DB) to protect API usage.

Wire-up: call render_chatbot(twin) once per page, after the user/twin has
been resolved (see utils/session.py -> render_sidebar_user_selector()).

API key resolution order:
  1. st.secrets["GEMINI_API_KEY"]           (.streamlit/secrets.toml)
  2. environment variable GEMINI_API_KEY
"""

from __future__ import annotations

import datetime
import os
import re
from html import escape as _he
import requests
import streamlit as st

from database.db_manager import DBManager
from utils.security import sanitize_chat_message


def _format_inline_markdown(text: str) -> str:
    """Escapes HTML and applies inline bold, italic, code formatting."""
    escaped = _he(text)
    # Bold: **text** or __text__
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong style='color: #F8FAFC; font-weight: 600;'>\1</strong>", escaped)
    escaped = re.sub(r"__(.+?)__", r"<strong style='color: #F8FAFC; font-weight: 600;'>\1</strong>", escaped)
    # Italic: *text* or _text_ (single asterisk or underscore)
    escaped = re.sub(r"(?<!\*)\*([^*]+?)\*(?!\*)", r"<em style='color: #94A3B8;'>\1</em>", escaped)
    escaped = re.sub(r"(?<!\w)_([^_]+?)_(?!\w)", r"<em style='color: #94A3B8;'>\1</em>", escaped)
    # Inline code: `text`
    escaped = re.sub(r"`(.+?)`", r"<code style='background: rgba(255,255,255,0.08); padding: 1px 5px; border-radius: 4px; font-size: 0.86em; color: #38BDF8;'>\1</code>", escaped)
    # Remove any stray unparsed markdown markers
    escaped = escaped.replace("**", "").replace("###", "").replace("##", "")
    return escaped


def _is_table_row(line: str) -> bool:
    s = line.strip()
    return s.startswith("|") and s.endswith("|") and s.count("|") >= 2


def _is_table_delimiter(line: str) -> bool:
    s = line.strip()
    if not _is_table_row(s):
        return False
    cells = [c.strip() for c in s.strip("|").split("|")]
    return len(cells) > 0 and all(re.match(r"^:?-+:?$", c) for c in cells if c)


def _render_table_html(table_rows: list[str]) -> str:
    cleaned_rows = [r.strip() for r in table_rows if r.strip() and _is_table_row(r)]
    if not cleaned_rows:
        return ""

    has_delimiter = False
    delimiter_idx = -1

    for idx, row in enumerate(cleaned_rows):
        if _is_table_delimiter(row):
            has_delimiter = True
            delimiter_idx = idx
            break

    html = [
        '<div style="overflow-x: auto; margin: 10px 0 12px 0; border-radius: 8px; border: 1px solid rgba(255, 255, 255, 0.12); background: rgba(15, 23, 42, 0.7);">'
        '<table style="width: 100%; border-collapse: collapse; font-family: \'Inter\', sans-serif; font-size: 0.83rem; text-align: left;">'
    ]

    if has_delimiter and delimiter_idx > 0:
        header_cells = [c.strip() for c in cleaned_rows[0].strip("|").split("|")]
        html.append('<thead><tr style="background: rgba(30, 41, 59, 0.95); border-bottom: 1px solid rgba(255, 255, 255, 0.15);">')
        for c in header_cells:
            formatted_c = _format_inline_markdown(c)
            html.append(f'<th style="padding: 8px 10px; color: #F8FAFC; font-weight: 700; white-space: nowrap;">{formatted_c}</th>')
        html.append('</tr></thead><tbody>')

        body_rows = [r for idx, r in enumerate(cleaned_rows) if idx != 0 and idx != delimiter_idx]
        for r_idx, b_row in enumerate(body_rows):
            b_cells = [c.strip() for c in b_row.strip("|").split("|")]
            bg = "background: rgba(255, 255, 255, 0.025);" if r_idx % 2 == 1 else ""
            html.append(f'<tr style="border-bottom: 1px solid rgba(255, 255, 255, 0.05); {bg}">')
            for c in b_cells:
                formatted_c = _format_inline_markdown(c)
                html.append(f'<td style="padding: 7px 10px; color: #CBD5E1; vertical-align: top; line-height: 1.45;">{formatted_c}</td>')
            html.append('</tr>')
        html.append('</tbody>')
    else:
        html.append('<tbody>')
        for r_idx, row in enumerate(cleaned_rows):
            cells = [c.strip() for c in row.strip("|").split("|")]
            bg = "background: rgba(255, 255, 255, 0.025);" if r_idx % 2 == 1 else ""
            html.append(f'<tr style="border-bottom: 1px solid rgba(255, 255, 255, 0.05); {bg}">')
            for c in cells:
                formatted_c = _format_inline_markdown(c)
                html.append(f'<td style="padding: 7px 10px; color: #CBD5E1; vertical-align: top; line-height: 1.45;">{formatted_c}</td>')
            html.append('</tr>')
        html.append('</tbody>')

    html.append('</table></div>')
    return "".join(html)


def _format_chat_markdown(text: str) -> str:
    """Converts Markdown (headers, bold, italic, bullet lists, numbered lists, tables, HRs)
    into clean, formatted HTML while escaping any unsafe user/model input."""
    if not text:
        return ""

    raw_lines = text.strip().split("\n")
    html_lines = []
    in_ul = False
    in_ol = False

    i = 0
    n = len(raw_lines)

    while i < n:
        raw_line = raw_lines[i]
        line = raw_line.strip()

        # Check for table block
        if _is_table_row(line):
            if in_ul:
                html_lines.append("</ul>")
                in_ul = False
            if in_ol:
                html_lines.append("</ol>")
                in_ol = False

            table_lines = []
            while i < n:
                curr_line = raw_lines[i].strip()
                if _is_table_row(curr_line):
                    table_lines.append(curr_line)
                    i += 1
                elif not curr_line and i + 1 < n and _is_table_row(raw_lines[i + 1].strip()):
                    # Empty line inside table
                    i += 1
                else:
                    break
            html_lines.append(_render_table_html(table_lines))
            continue

        if not line:
            if in_ul:
                html_lines.append("</ul>")
                in_ul = False
            if in_ol:
                html_lines.append("</ol>")
                in_ol = False
            html_lines.append("<div style='height: 6px;'></div>")
            i += 1
            continue

        # Check for Horizontal Rules: ---, ***, ___
        if re.match(r"^(\-{3,}|\*{3,}|_{3,})$", line):
            if in_ul:
                html_lines.append("</ul>")
                in_ul = False
            if in_ol:
                html_lines.append("</ol>")
                in_ol = False
            html_lines.append("<div style='height: 1px; background: rgba(255, 255, 255, 0.1); margin: 12px 0;'></div>")
            i += 1
            continue

        # Check for headings: ### or ## or #
        h_match = re.match(r"^(#{1,6})\s+(.*)$", line)
        if h_match:
            if in_ul:
                html_lines.append("</ul>")
                in_ul = False
            if in_ol:
                html_lines.append("</ol>")
                in_ol = False
            level = len(h_match.group(1))
            h_content = _format_inline_markdown(h_match.group(2))
            font_size = "1rem" if level <= 3 else "0.92rem"
            html_lines.append(
                f'<div style="font-family: \'Plus Jakarta Sans\', sans-serif; font-weight: 700; font-size: {font_size}; color: #F8FAFC; margin: 10px 0 4px 0;">{h_content}</div>'
            )
            i += 1
            continue

        # Check for unordered list item: * or -
        ul_match = re.match(r"^[\*\-]\s+(.*)$", line)
        if ul_match:
            if in_ol:
                html_lines.append("</ol>")
                in_ol = False
            if not in_ul:
                html_lines.append("<ul style='margin: 4px 0 6px 0; padding-left: 18px; list-style-type: disc;'>")
                in_ul = True
            item_content = _format_inline_markdown(ul_match.group(1))
            html_lines.append(f"<li style='margin-bottom: 5px; color: #CBD5E1; line-height: 1.5;'>{item_content}</li>")
            i += 1
            continue

        # Check for ordered list item: 1. 2. etc.
        ol_match = re.match(r"^(\d+)\.\s+(.*)$", line)
        if ol_match:
            if in_ul:
                html_lines.append("</ul>")
                in_ul = False
            if not in_ol:
                html_lines.append("<ol style='margin: 4px 0 6px 0; padding-left: 18px;'>")
                in_ol = True
            item_content = _format_inline_markdown(ol_match.group(2))
            html_lines.append(f"<li style='margin-bottom: 5px; color: #CBD5E1; line-height: 1.5;'>{item_content}</li>")
            i += 1
            continue

        # Normal text line
        if in_ul:
            html_lines.append("</ul>")
            in_ul = False
        if in_ol:
            html_lines.append("</ol>")
            in_ol = False

        content = _format_inline_markdown(line)
        html_lines.append(f"<p style='margin: 0 0 6px 0; color: #CBD5E1; line-height: 1.55;'>{content}</p>")
        i += 1

    if in_ul:
        html_lines.append("</ul>")
    if in_ol:
        html_lines.append("</ol>")

    return "".join(html_lines)


def _safe_html(text: str) -> str:
    """HTML-escape user-supplied text and convert newlines to <br> tags."""
    return _he(text).replace("\n", "<br>")

# ══════════════════════════════════════════════════════════════════════════
# Config
# ══════════════════════════════════════════════════════════════════════════

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODELS = [
    "qwen/qwen3.8-27b",
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "groq/compound-mini",
    "allam-2-7b",
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
]

GEMINI_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-1.5-flash-latest",
]

HISTORY_KEY = "ftw_chat_history"     # list[{"role": "user"|"model", "text": str}]
OPEN_KEY = "ftw_chat_open"           # bool
ANON_USAGE_KEY = "ftw_anon_usage"    # {"date": iso, "count": int}  (guest fallback, session-only)

DAILY_LIMIT_LOGGED_IN = 40
DAILY_LIMIT_GUEST = 12
MAX_HISTORY = 50  # Maximum stored turns to prevent memory exhaustion and excessive API tokens


def _get_groq_api_key() -> str | None:
    try:
        if "GROQ_API_KEY" in st.secrets:
            return st.secrets["GROQ_API_KEY"]
    except Exception:
        pass
    return os.environ.get("GROQ_API_KEY")


def _get_api_key() -> str | None:
    groq_key = _get_groq_api_key()
    if groq_key:
        return groq_key
    try:
        if "GEMINI_API_KEY" in st.secrets:
            return st.secrets["GEMINI_API_KEY"]
    except Exception:
        pass
    return os.environ.get("GEMINI_API_KEY")



# ══════════════════════════════════════════════════════════════════════════
# Daily usage limit
# ══════════════════════════════════════════════════════════════════════════

def _usage_today(twin) -> tuple[int, int]:
    """Returns (used_today, daily_limit) for the current user (or guest)."""
    if twin is not None:
        used = DBManager.get_chat_usage_today(twin.user_id)
        return used, DAILY_LIMIT_LOGGED_IN

    today = datetime.date.today().isoformat()
    rec = st.session_state.get(ANON_USAGE_KEY)
    if not rec or rec.get("date") != today:
        rec = {"date": today, "count": 0}
        st.session_state[ANON_USAGE_KEY] = rec
    return rec["count"], DAILY_LIMIT_GUEST


def _record_usage(twin) -> int:
    """Increments and returns the new used-today count."""
    if twin is not None:
        return DBManager.increment_chat_usage(twin.user_id)

    today = datetime.date.today().isoformat()
    rec = st.session_state.get(ANON_USAGE_KEY)
    if not rec or rec.get("date") != today:
        rec = {"date": today, "count": 0}
    rec["count"] += 1
    st.session_state[ANON_USAGE_KEY] = rec
    return rec["count"]


# ══════════════════════════════════════════════════════════════════════════
# Context building
# ══════════════════════════════════════════════════════════════════════════

def _coach_digest(twin) -> str:
    """Pulls a short digest from the app's own rule-based AI Coach engine so
    FinBot's answers stay consistent with what the AI Coach page tells the
    user. Fails silently (returns "") if the twin's data can't be analysed."""
    try:
        from utils.coach import FinancialCoach
        report = FinancialCoach(twin).generate_report()
        lines = [
            f"Overall financial health score (per app's rule engine): {report.overall_score:.0f}/100, "
            f"risk level: {report.risk_level}.",
            f"Top priority action: {report.top_action}",
        ]
        top_recs = report.recommendations[:4]
        if top_recs:
            lines.append("Other flagged recommendations:")
            for r in top_recs:
                lines.append(f"- [{r.domain.value} / {r.severity.value}] {r.title}: {r.action}")
        return "\n".join(lines)
    except Exception:
        return ""


def _build_predictions_and_scenarios_context(twin) -> str:
    """Computes ML predictions (6M and 12M) and standard Scenario simulations
    for the active user, and formats them into a compact text block for the system prompt
    to allow the chatbot to predict future decisions / outcomes for all financial aspects."""
    if twin is None:
        return ""
    
    lines = []
    
    # 1. Machine Learning Predictions
    try:
        from models.predictor import FinancialPredictor
        predictor = FinancialPredictor()
        predictor.load_only(horizon=6)
        pred_6 = predictor.predict(twin, horizon_months=6)
        pred_12 = predictor.predict(twin, horizon_months=12)
        lines.extend([
            "== Machine Learning Predictions (XGBoost) ==",
            f"- Predicted Monthly Savings (6M): \u20b9{pred_6['predicted_savings']:,.0f}",
            f"- Predicted Net Worth (6M): \u20b9{pred_6['predicted_net_worth']:,.0f}",
            f"- Predicted Monthly Savings (12M): \u20b9{pred_12['predicted_savings']:,.0f}",
            f"- Predicted Net Worth (12M): \u20b9{pred_12['predicted_net_worth']:,.0f}",
            ""
        ])
    except Exception:
        pass

    # 2. Life Event Scenario Simulations
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
        
        lines.append("== Simulated Life Decisions & Scenarios (Before vs After) ==")
        for name, params in scenarios:
            res = sim.run_scenario(name, **params)
            b = res.before
            a = res.after
            lines.extend([
                f"- Scenario: {name} (Params: {params})",
                f"  * Monthly Surplus: \u20b9{b.monthly_surplus:,.0f} -> \u20b9{a.monthly_surplus:,.0f} (Delta: \u20b9{a.monthly_surplus - b.monthly_surplus:,.0f})",
                f"  * Health Score: {b.health_score:.1f}/100 -> {a.health_score:.1f}/100 (Delta: {a.health_score - b.health_score:+.1f})",
                f"  * 12M Future Savings: \u20b9{b.future_savings_12m:,.0f} -> \u20b9{a.future_savings_12m:,.0f}",
                f"  * 5Y Projected Net Worth: \u20b9{b.future_net_worth_5y:,.0f} -> \u20b9{a.future_net_worth_5y:,.0f}",
                f"  * Risk Level: {b.risk_level} -> {a.risk_level}"
            ])
        lines.append("")
    except Exception:
        pass

    return "\n".join(lines)


def _build_system_prompt(twin) -> str:
    base = (
        "You are FinBot, the built-in AI assistant of FinTwin AI \u2014 an AI-powered "
        "personal finance \"digital twin\" web app for Indian users aged 22-40. "
        "Your job is to answer ALL personal-finance questions the active user has: "
        "budgeting, saving, spending habits, investing (SIP/mutual funds/stocks/PPF/NPS), "
        "debt and EMIs, insurance adequacy, emergency funds, Indian income tax (old vs new "
        "regime, 80C/80D/NPS deductions), retirement and goal planning \u2014 as well as "
        "questions about how to use the app's own features (Digital Twin, Financial Health "
        "Score, Behavior Analysis, Financial Personality, Forecasting, Scenario Simulator, "
        "Tax Intelligence, AI Coach, Goal Planner, Explainable AI). "
        "Stay strictly on personal-finance and app-usage topics; if asked something "
        "unrelated, gently steer back. "
        "Reply in clear, friendly paragraphs or bullet points with complete, thorough explanations. "
        "Use \u20b9 for currency. Never claim to "
        "move money, place trades, or change account settings \u2014 you only inform and advise. "
        "If you don't have a number you need, say so instead of inventing one."
    )

    if twin is None:
        return base + (
            "\n\nThe current visitor is NOT logged in, so you have no personal financial "
            "data for them. Answer general questions helpfully, and suggest they log in "
            "(or try the demo account) from the sidebar to unlock personalised answers "
            "grounded in their own numbers."
        )

    instructions = (
        "\n\nYou also have access to predictive models and scenario simulations for the user's financial profile. "
        "Use the provided predictions and scenario results to answer questions about the future impact of their decisions. "
        "For example, if they ask about a salary hike, job loss, buying a car, buying a home, marriage, or increasing their SIP, "
        "refer to the simulated scenario data and explain the specific before/after changes in monthly surplus, "
        "financial health score, projected savings, and risk level. Cite these metrics directly."
    )

    profile = f"""

You ARE currently chatting with a logged-in, active user. Use the data below to fully
personalise every answer. Do not invent figures that aren't listed here or derivable
from them.

Name: {twin.name} | Age: {twin.age} | Occupation: {twin.occupation} | City: {twin.city}
Monthly income (incl. extra income): \u20b9{twin.total_income:,.0f}
Net worth: \u20b9{twin.net_worth:,.0f}
Bank savings: \u20b9{twin.bank_savings:,.0f} | Fixed deposits: \u20b9{twin.fd_amount:,.0f} | Emergency fund: \u20b9{twin.emergency_fund:,.0f}
Investments \u2014 SIP: \u20b9{twin.sip_amount:,.0f}/mo, Mutual funds: \u20b9{twin.mutual_funds:,.0f}, Stocks: \u20b9{twin.stocks:,.0f}, PPF: \u20b9{twin.ppf_investment:,.0f}, NPS: \u20b9{twin.nps_investment:,.0f}
Debt \u2014 Home loan: \u20b9{twin.home_loan:,.0f}, Car loan: \u20b9{twin.car_loan:,.0f}, Credit card debt: \u20b9{twin.credit_card_debt:,.0f}, Monthly EMI: \u20b9{twin.monthly_emi:,.0f}
Insurance \u2014 Health: \u20b9{twin.health_insurance:,.0f}, Life: \u20b9{twin.life_insurance:,.0f}
Monthly essential expenses (rent, groceries, utilities, transport, food delivery, entertainment, shopping): \u20b9{twin.basic_expenses:,.0f}
Goal: {twin.goal_type or 'Not set'} (target \u20b9{twin.goal_amount:,.0f})
"""

    pred_context = _build_predictions_and_scenarios_context(twin)
    if pred_context:
        profile += f"\n{pred_context}\n"

    digest = _coach_digest(twin)
    if digest:
        profile += f"\nApp's own AI Coach analysis (use this to stay consistent, but explain in your own words):\n{digest}\n"

    return base + instructions + profile


def _get_available_gemini_models(api_key: str) -> list[str]:
    """Dynamically queries Gemini's ModelService to find models that support generateContent."""
    cache_key = "ftw_discovered_gemini_models"
    if cache_key in st.session_state and st.session_state[cache_key]:
        return st.session_state[cache_key]

    default_models = [
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-1.5-flash",
        "gemini-1.5-flash-latest",
        "gemini-1.5-flash-8b",
        "gemini-pro",
    ]
    try:
        url = "https://generativelanguage.googleapis.com/v1beta/models"
        resp = requests.get(url, params={"key": api_key}, timeout=8)
        if resp.status_code == 200:
            data = resp.json()
            models = []
            for m in data.get("models", []):
                methods = m.get("supportedGenerationMethods", [])
                name = m.get("name", "")
                if "generateContent" in methods and "gemini" in name.lower():
                    clean_name = name.replace("models/", "")
                    models.append(clean_name)
            if models:
                def _sort_key(m_name: str) -> int:
                    if "2.5-flash" in m_name:
                        return 0
                    if "2.0-flash" in m_name:
                        return 1
                    if "1.5-flash" in m_name and "8b" not in m_name:
                        return 2
                    if "1.5-flash-8b" in m_name:
                        return 3
                    if "flash" in m_name:
                        return 4
                    return 10
                models.sort(key=_sort_key)
                st.session_state[cache_key] = models
                return models
    except Exception:
        pass

    return default_models


def _call_groq(twin, history: list[dict], api_key: str) -> str:
    """Calls Groq's high-speed OpenAI-compatible API with multi-model fallback."""
    system_prompt = _build_system_prompt(twin)
    messages = [{"role": "system", "content": system_prompt}]
    for m in history:
        role = "user" if m.get("role") == "user" else "assistant"
        messages.append({"role": role, "content": m.get("text", "")})

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    last_error_detail = ""
    for model in GROQ_MODELS:
        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.6,
            "max_tokens": 8192,
        }
        try:
            resp = requests.post(GROQ_URL, headers=headers, json=payload, timeout=25)
            if resp.status_code == 200:
                data = resp.json()
                choices = data.get("choices", [])
                if choices:
                    content = choices[0].get("message", {}).get("content", "").strip()
                    if content:
                        return content
            else:
                try:
                    last_error_detail = resp.json().get("error", {}).get("message", "")
                except Exception:
                    last_error_detail = f"HTTP {resp.status_code}"
                # If model not found or rate limited, try next Groq model
                if resp.status_code in (400, 404, 429, 500, 503):
                    continue
                else:
                    break
        except (requests.exceptions.Timeout, requests.exceptions.RequestException):
            continue

    if last_error_detail:
        return f"FinBot hit an API error: {last_error_detail}. Please try again shortly."
    return "FinBot couldn't reach the AI service right now. Please check your connection or try again in a moment."


def _call_gemini_backend(twin, history: list[dict], api_key: str) -> str:
    contents = [{"role": m["role"], "parts": [{"text": m["text"]}]} for m in history]

    payload = {
        "contents": contents,
        "systemInstruction": {"parts": [{"text": _build_system_prompt(twin)}]},
        "generationConfig": {"temperature": 0.6, "maxOutputTokens": 8192},
    }

    models_to_try = _get_available_gemini_models(api_key)
    last_error_detail = ""

    for model in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        try:
            resp = requests.post(url, params={"key": api_key}, json=payload, timeout=25)
            if resp.status_code == 200:
                data = resp.json()
                candidates = data.get("candidates", [])
                if not candidates:
                    reason = data.get("promptFeedback", {}).get("blockReason", "unknown reason")
                    return f"FinBot couldn't generate a reply ({reason}). Please rephrase your question."
                parts = candidates[0].get("content", {}).get("parts", [])
                text = "".join(p.get("text", "") for p in parts).strip()
                if text:
                    return text
            else:
                try:
                    last_error_detail = resp.json().get("error", {}).get("message", "")
                except Exception:
                    last_error_detail = f"HTTP {resp.status_code}"
                # If high demand (503), rate limit (429), model not found (404), or server error (500), try next available model
                if resp.status_code in (404, 429, 500, 503):
                    continue
                else:
                    break
        except (requests.exceptions.Timeout, requests.exceptions.RequestException):
            continue

    if last_error_detail:
        return f"FinBot hit an API error: {last_error_detail}. Please try again shortly."
    return "FinBot couldn't reach the AI service right now. Please check your connection or try again in a moment."


def _call_llm(twin, history: list[dict]) -> str:
    """Dispatches chat completions to Groq (primary) or Gemini (fallback)."""
    groq_key = _get_groq_api_key()
    if groq_key:
        return _call_groq(twin, history, groq_key)

    gemini_key = os.environ.get("GEMINI_API_KEY")
    if not gemini_key:
        try:
            if "GEMINI_API_KEY" in st.secrets:
                gemini_key = st.secrets["GEMINI_API_KEY"]
        except Exception:
            pass

    if gemini_key:
        return _call_gemini_backend(twin, history, gemini_key)

    return (
        "FinBot isn't fully set up yet — no AI API key was found. "
        "Add `GROQ_API_KEY` to `.streamlit/secrets.toml` (or as an environment "
        "variable) and reload the app."
    )


# Backward-compatibility alias
_call_gemini = _call_llm


# ══════════════════════════════════════════════════════════════════════════
# CSS (shared, injected once per page run)
# ══════════════════════════════════════════════════════════════════════════

def _inject_css():
    st.markdown("""
    <style>
    /* ---- Professional Fintech Floating AI Coach Launcher Orb ---- */
    .ftw-orb-wrap {
        position: fixed;
        bottom: 26px;
        right: 26px;
        width: 60px;
        height: 60px;
        z-index: 999998;
        pointer-events: none;
    }
    .ftw-orb {
        width: 100%;
        height: 100%;
        border-radius: 50%;
        background: linear-gradient(135deg, #2563EB 0%, #1D4ED8 100%);
        border: 1px solid rgba(255, 255, 255, 0.2);
        box-shadow: 0 8px 26px rgba(37, 99, 235, 0.4), 0 0 0 1px rgba(255, 255, 255, 0.1);
        position: relative;
        display: flex;
        align-items: center;
        justify-content: center;
        transition: transform 0.25s cubic-bezier(0.16, 1, 0.3, 1), box-shadow 0.25s ease;
    }
    .ftw-orb-icon {
        display: flex;
        align-items: center;
        justify-content: center;
        color: #FFFFFF;
    }
    .ftw-badge {
        position: absolute;
        bottom: 2px;
        right: 2px;
        width: 13px;
        height: 13px;
        border-radius: 50%;
        background: #10B981;
        border: 2px solid #0F172A;
        box-shadow: 0 0 6px rgba(16, 185, 129, 0.6);
    }
    .ftw-ping {
        position: absolute;
        inset: -2px;
        border-radius: 50%;
        border: 1.5px solid rgba(16, 185, 129, 0.6);
        animation: ftw-ping 2.5s cubic-bezier(0, 0.5, 0.5, 1) infinite;
    }
    @keyframes ftw-ping {
        0% { transform: scale(0.9); opacity: 0.7; }
        100% { transform: scale(1.35); opacity: 0; }
    }

    /* ---- Invisible clickable button placed exactly over the launcher orb ---- */
    .st-key-ftw_toggle_btn {
        position: fixed !important;
        bottom: 26px !important;
        right: 26px !important;
        width: 60px !important;
        height: 60px !important;
        z-index: 999999 !important;
    }
    .st-key-ftw_toggle_btn > div { height: 100%; }
    .st-key-ftw_toggle_btn button {
        width: 100% !important;
        height: 100% !important;
        border-radius: 50% !important;
        background: transparent !important;
        border: none !important;
        opacity: 0 !important;
        cursor: pointer !important;
        padding: 0 !important;
    }

    /* ---- Chat panel: Institutional Dark Fintech, right-anchored ---- */
    .st-key-ftw_panel {
        position: fixed !important;
        bottom: 18px !important;
        right: 20px !important;
        width: 32vw !important;
        min-width: 440px !important;
        max-width: 530px !important;
        height: min(84vh, calc(100vh - 36px)) !important;
        max-height: calc(100vh - 36px) !important;
        z-index: 999999 !important;
        background: rgba(15, 23, 42, 0.97) !important;
        backdrop-filter: blur(20px) !important;
        -webkit-backdrop-filter: blur(20px) !important;
        border: 1px solid rgba(255, 255, 255, 0.1) !important;
        border-radius: 20px !important;
        box-shadow: 0 24px 60px rgba(0, 0, 0, 0.6), 0 0 0 1px rgba(255, 255, 255, 0.06) !important;
        padding: 14px 18px 10px 18px !important;
        overflow-y: auto !important;
        overflow-x: hidden !important;
        display: flex !important;
        flex-direction: column !important;
        animation: ftw-pop 0.26s cubic-bezier(0.16, 1, 0.3, 1);
    }
    @media (max-width: 900px) {
        .st-key-ftw_panel {
            width: calc(100vw - 32px) !important;
            min-width: 0 !important;
            right: 16px !important;
            bottom: 16px !important;
            height: calc(100vh - 32px) !important;
            max-height: calc(100vh - 32px) !important;
        }
        .ftw-orb-wrap, .st-key-ftw_toggle_btn { right: 16px !important; bottom: 16px !important; }
    }
    @keyframes ftw-pop {
        0% { opacity: 0; transform: translateY(16px) scale(0.95); }
        100% { opacity: 1; transform: translateY(0) scale(1); }
    }

    /* Clean custom scrollbar */
    .st-key-ftw_panel::-webkit-scrollbar,
    .ftw-msgs::-webkit-scrollbar,
    .ftw-empty-card::-webkit-scrollbar {
        width: 5px;
    }
    .st-key-ftw_panel::-webkit-scrollbar-track,
    .ftw-msgs::-webkit-scrollbar-track,
    .ftw-empty-card::-webkit-scrollbar-track {
        background: transparent;
    }
    .st-key-ftw_panel::-webkit-scrollbar-thumb,
    .ftw-msgs::-webkit-scrollbar-thumb,
    .ftw-empty-card::-webkit-scrollbar-thumb {
        background: rgba(255, 255, 255, 0.12);
        border-radius: 99px;
    }
    .st-key-ftw_panel::-webkit-scrollbar-thumb:hover,
    .ftw-msgs::-webkit-scrollbar-thumb:hover,
    .ftw-empty-card::-webkit-scrollbar-thumb:hover {
        background: rgba(255, 255, 255, 0.22);
    }

    /* ---- Header Layout & Vertical Alignment ---- */
    .st-key-ftw_panel [data-testid="stHorizontalBlock"]:first-of-type {
        height: 44px !important;
        min-height: 44px !important;
        max-height: 44px !important;
        display: flex !important;
        flex-direction: row !important;
        align-items: center !important;
        justify-content: space-between !important;
        margin-bottom: 8px !important;
        padding-bottom: 8px !important;
        border-bottom: 1px solid rgba(255, 255, 255, 0.08) !important;
    }
    .st-key-ftw_panel [data-testid="stHorizontalBlock"]:first-of-type > [data-testid="stColumn"] {
        display: flex !important;
        flex-direction: row !important;
        align-items: center !important;
        height: 100% !important;
    }
    .st-key-ftw_panel [data-testid="stHorizontalBlock"]:first-of-type > [data-testid="stColumn"]:nth-child(1) {
        justify-content: flex-start !important;
    }
    .st-key-ftw_panel [data-testid="stHorizontalBlock"]:first-of-type > [data-testid="stColumn"]:nth-child(2) {
        justify-content: center !important;
    }
    .st-key-ftw_panel [data-testid="stHorizontalBlock"]:first-of-type > [data-testid="stColumn"]:nth-child(3) {
        justify-content: flex-end !important;
    }
    .st-key-ftw_panel [data-testid="stHorizontalBlock"]:first-of-type [data-testid="stVerticalBlock"] {
        height: 100% !important;
        display: flex !important;
        flex-direction: row !important;
        align-items: center !important;
        justify-content: center !important;
        gap: 6px !important;
        margin: 0 !important;
        padding: 0 !important;
    }
    .st-key-ftw_panel [data-testid="stHorizontalBlock"]:first-of-type > [data-testid="stColumn"]:first-child [data-testid="stVerticalBlock"] {
        justify-content: flex-start !important;
    }
    .st-key-ftw_panel [data-testid="stHorizontalBlock"]:first-of-type > [data-testid="stColumn"]:last-child [data-testid="stVerticalBlock"] {
        justify-content: flex-end !important;
    }
    .st-key-ftw_panel [data-testid="stHorizontalBlock"]:first-of-type [data-testid="stHorizontalBlock"] {
        height: 100% !important;
        min-height: 0 !important;
        margin: 0 !important;
        padding: 0 !important;
        border-bottom: none !important;
        display: flex !important;
        flex-direction: row !important;
        align-items: center !important;
        justify-content: flex-end !important;
        gap: 6px !important;
    }
    .st-key-ftw_panel [data-testid="stHorizontalBlock"]:first-of-type [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        height: 100% !important;
        width: auto !important;
        flex: 0 0 auto !important;
    }

    .ftw-panel-title {
        display: flex;
        align-items: center;
        gap: 10px;
        height: 38px;
    }
    .ftw-mini-orb {
        width: 36px;
        height: 36px;
        border-radius: 50%;
        flex-shrink: 0;
        background: linear-gradient(135deg, #2563EB 0%, #1D4ED8 100%);
        border: 1px solid rgba(255, 255, 255, 0.18);
        box-shadow: 0 4px 12px rgba(37, 99, 235, 0.3);
        position: relative;
        display: flex;
        align-items: center;
        justify-content: center;
        color: #FFFFFF;
    }
    .ftw-mini-badge {
        position: absolute;
        bottom: 0px;
        right: 0px;
        width: 9px;
        height: 9px;
        border-radius: 50%;
        background: #10B981;
        border: 1.5px solid #0F172A;
    }
    @keyframes ftw-dot-pulse {
        0%, 100% { opacity: 1; transform: scale(1); }
        50% { opacity: 0.4; transform: scale(0.85); }
    }
    .ftw-pulse-dot {
        display: inline-block;
        color: #10B981;
        text-shadow: 0 0 6px #10B981;
        animation: ftw-dot-pulse 2s ease-in-out infinite;
        margin-right: 3px;
    }
    .ftw-title-text {
        font-family: 'Plus Jakarta Sans', sans-serif;
        font-weight: 800;
        color: #F8FAFC;
        font-size: 1.02rem;
        letter-spacing: -0.02em;
        line-height: 1.15;
        margin: 0;
    }
    .ftw-intel-badge {
        font-family: 'Inter', sans-serif;
        font-size: 0.62rem;
        font-weight: 600;
        color: #38BDF8;
        background: rgba(56, 189, 248, 0.12);
        border: 1px solid rgba(56, 189, 248, 0.28);
        border-radius: 999px;
        padding: 1px 7px;
        white-space: nowrap;
        display: inline-flex;
        align-items: center;
        gap: 3px;
        letter-spacing: 0.02em;
        line-height: 1.3;
    }
    .ftw-subtitle {
        font-family: 'Inter', sans-serif;
        font-size: 0.72rem;
        color: #94A3B8;
        display: flex;
        align-items: center;
        gap: 4px;
        line-height: 1;
        margin-top: 2px;
    }
    .ftw-usage-pill {
        font-family: 'Inter', sans-serif;
        font-size: 0.74rem;
        font-weight: 600;
        color: #94A3B8;
        background: rgba(30, 41, 59, 0.9);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 999px;
        padding: 0 12px;
        height: 28px;
        white-space: nowrap;
        text-align: center;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        box-sizing: border-box;
        line-height: 28px;
        margin: 0 !important;
    }
    .ftw-usage-pill.low { color: #F59E0B; border-color: rgba(245, 158, 11, 0.3); }
    .ftw-usage-pill.zero { color: #EF4444; border-color: rgba(239, 68, 68, 0.3); }

    .st-key-ftw_close_btn,
    .st-key-ftw_clear_hdr_btn {
        display: inline-flex !important;
        align-items: center !important;
        justify-content: center !important;
        margin: 0 !important;
        padding: 0 !important;
        height: 32px !important;
    }
    .st-key-ftw_close_btn button,
    .st-key-ftw_clear_hdr_btn button {
        background: rgba(255, 255, 255, 0.08) !important;
        border: 1px solid rgba(255, 255, 255, 0.15) !important;
        border-radius: 8px !important;
        color: #F8FAFC !important;
        width: 32px !important;
        height: 32px !important;
        min-height: 32px !important;
        max-height: 32px !important;
        padding: 0 !important;
        display: inline-flex !important;
        align-items: center !important;
        justify-content: center !important;
        transition: all 0.15s ease !important;
        margin: 0 !important;
    }
    .st-key-ftw_close_btn button:hover,
    .st-key-ftw_clear_hdr_btn button:hover {
        background: rgba(255, 255, 255, 0.2) !important;
        color: #FFFFFF !important;
        border-color: rgba(255, 255, 255, 0.3) !important;
    }
    .st-key-ftw_close_btn button [data-testid="stIconMaterial"],
    .st-key-ftw_clear_hdr_btn button [data-testid="stIconMaterial"],
    .st-key-ftw_close_btn button span,
    .st-key-ftw_clear_hdr_btn button span {
        color: #F8FAFC !important;
        font-size: 1.15rem !important;
    }

    /* ---- Messages Feed ---- */
    .ftw-msgs {
        flex: 1 1 auto !important;
        overflow-y: auto !important;
        display: flex;
        flex-direction: column;
        gap: 12px;
        padding: 6px 4px 10px 2px;
        margin-bottom: 6px;
        max-height: calc(84vh - 165px) !important;
    }
    @media (min-height: 1000px) {
        .ftw-msgs {
            max-height: 640px !important;
        }
    }
    @media (max-width: 900px) {
        .ftw-msgs {
            max-height: calc(80vh - 165px) !important;
        }
    }

    /* ---- Professional Chat Bubbles ---- */
    .ftw-bubble {
        max-width: 94%;
        padding: 12px 16px;
        border-radius: 14px;
        font-family: 'Inter', sans-serif;
        font-size: 0.89rem;
        line-height: 1.55;
        white-space: normal;
        word-wrap: break-word;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
        animation: ftw-bubble-in 0.22s ease-out;
    }
    @keyframes ftw-bubble-in {
        0% { opacity: 0; transform: translateY(6px); }
        100% { opacity: 1; transform: translateY(0); }
    }
    .ftw-bubble.user {
        align-self: flex-end;
        background: linear-gradient(135deg, #2563EB 0%, #1D4ED8 100%) !important;
        color: #FFFFFF !important;
        border-bottom-right-radius: 4px;
        font-weight: 500;
        max-width: 85%;
    }
    .ftw-bubble.model {
        align-self: flex-start;
        background: rgba(30, 41, 59, 0.85) !important;
        color: #E2E8F0 !important;
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
        border-bottom-left-radius: 4px;
        box-shadow: 0 4px 14px rgba(0, 0, 0, 0.25) !important;
    }
    .ftw-bubble table {
        width: 100%;
        border-collapse: collapse;
        font-family: 'Inter', sans-serif;
    }

    /* ---- Bubble Footer & Copy Action ---- */
    .ftw-bubble-footer {
        display: flex;
        align-items: center;
        justify-content: flex-start;
        margin-top: 8px;
        padding-top: 6px;
        border-top: 1px solid rgba(255, 255, 255, 0.08);
    }
    .ftw-copy-btn {
        background: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(255, 255, 255, 0.1);
        color: #94A3B8;
        font-family: 'Inter', sans-serif;
        font-size: 0.72rem;
        font-weight: 500;
        padding: 3px 8px;
        border-radius: 6px;
        display: inline-flex;
        align-items: center;
        gap: 5px;
        cursor: pointer;
        transition: all 0.15s ease;
        user-select: none;
    }
    .ftw-copy-btn:hover {
        color: #F8FAFC;
        background: rgba(255, 255, 255, 0.12);
        border-color: rgba(255, 255, 255, 0.2);
    }
    .ftw-copy-btn .ftw-check-icon {
        display: none;
    }
    .ftw-copy-btn.copied {
        color: #10B981 !important;
        background: rgba(16, 185, 129, 0.15) !important;
        border-color: rgba(16, 185, 129, 0.3) !important;
    }
    .ftw-copy-btn.copied .ftw-copy-icon {
        display: none;
    }
    .ftw-copy-btn.copied .ftw-check-icon {
        display: inline-block;
    }

    /* ---- Structured Empty State (Balanced Onboarding & Suggestion Chips) ---- */
    .ftw-empty-card {
        flex: 1 1 auto;
        overflow-y: auto;
        display: flex;
        flex-direction: column;
        justify-content: center;
        padding: 4px 4px 4px 4px;
        max-height: calc(84vh - 165px);
    }
    .ftw-welcome-badge {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        background: rgba(37, 99, 235, 0.12);
        border: 1px solid rgba(37, 99, 235, 0.25);
        border-radius: 999px;
        padding: 4px 12px;
        color: #60A5FA;
        font-family: 'Inter', sans-serif;
        font-size: 0.74rem;
        font-weight: 600;
        letter-spacing: 0.02em;
        margin-bottom: 8px;
        width: fit-content;
    }
    .ftw-welcome-title {
        font-family: 'Plus Jakarta Sans', sans-serif;
        font-size: 1.15rem;
        font-weight: 800;
        color: #F8FAFC;
        margin: 0 0 4px 0;
        letter-spacing: -0.02em;
    }
    .ftw-welcome-desc {
        font-family: 'Inter', sans-serif;
        font-size: 0.83rem;
        color: #94A3B8;
        line-height: 1.45;
        margin: 0 0 6px 0;
    }
    .ftw-suggestion-label {
        font-family: 'Inter', sans-serif;
        font-size: 0.70rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        color: #64748B;
        margin-bottom: 4px;
        display: flex;
        align-items: center;
        gap: 6px;
    }

    /* Suggestion Buttons in Streamlit */
    div[class*="st-key-ftw_sugg_"] {
        margin-bottom: 3px !important;
    }
    div[class*="st-key-ftw_sugg_"] button {
        background: rgba(30, 41, 59, 0.65) !important;
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
        border-radius: 10px !important;
        color: #CBD5E1 !important;
        font-family: 'Inter', sans-serif !important;
        font-size: 0.82rem !important;
        font-weight: 500 !important;
        text-align: left !important;
        padding: 6px 12px !important;
        height: 34px !important;
        min-height: 34px !important;
        justify-content: flex-start !important;
        transition: all 0.15s ease !important;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1) !important;
    }
    div[class*="st-key-ftw_sugg_"] button:hover {
        background: rgba(59, 130, 246, 0.15) !important;
        border-color: rgba(59, 130, 246, 0.45) !important;
        color: #60A5FA !important;
        transform: translateX(2px) !important;
    }

    /* ---- Typing & Limit Banners ---- */
    .ftw-limit-banner {
        font-family: 'Inter', sans-serif;
        font-size: 0.80rem;
        color: #F59E0B;
        background: rgba(245, 158, 11, 0.1);
        border: 1px solid rgba(245, 158, 11, 0.25);
        border-radius: 12px;
        padding: 8px 12px;
        margin-bottom: 6px;
        line-height: 1.4;
    }

    /* ---- Input Form & Controls ---- */
    .st-key-ftw_panel form {
        background: transparent !important;
        border: none !important;
        padding: 0 !important;
        margin-top: 4px !important;
        margin-bottom: 2px !important;
    }
    .st-key-ftw_panel input {
        background-color: rgba(30, 41, 59, 0.85) !important;
        border: 1px solid rgba(255, 255, 255, 0.1) !important;
        border-radius: 12px !important;
        color: #F8FAFC !important;
        font-family: 'Inter', sans-serif !important;
        font-size: 0.88rem !important;
        padding: 8px 14px !important;
        height: 38px !important;
        line-height: 1.4 !important;
        transition: all 0.2s ease !important;
    }
    .st-key-ftw_panel input:focus {
        border-color: #3B82F6 !important;
        box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.25) !important;
        background-color: rgba(30, 41, 59, 0.98) !important;
    }
    .st-key-ftw_panel input::placeholder,
    .st-key-ftw_panel input::-webkit-input-placeholder,
    .st-key-ftw_panel input::-moz-placeholder,
    .st-key-ftw_panel input:-ms-input-placeholder {
        color: #64748B !important;
        font-size: 0.88rem !important;
        opacity: 1 !important;
    }
    .st-key-ftw_panel [data-baseweb="input"] {
        border: none !important;
        background: transparent !important;
    }

    /* Hide Streamlit form input instructions and character count overlay */
    .st-key-ftw_panel [data-testid="stInputInstructions"],
    .st-key-ftw_panel [data-testid="InputInstructions"],
    .st-key-ftw_panel small,
    .st-key-ftw_panel .st-emotion-cache-16idsys,
    .st-key-ftw_panel div:has(> [data-testid="stInputInstructions"]) {
        display: none !important;
        visibility: hidden !important;
        height: 0 !important;
        padding: 0 !important;
        margin: 0 !important;
    }

    /* Form Submit Button */
    .st-key-ftw_panel button[type="submit"] {
        background: linear-gradient(135deg, #2563EB 0%, #1D4ED8 100%) !important;
        color: #FFFFFF !important;
        border: none !important;
        border-radius: 12px !important;
        font-weight: 600 !important;
        font-size: 0.98rem !important;
        height: 38px !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        transition: all 0.18s ease !important;
        cursor: pointer !important;
        box-shadow: 0 4px 12px rgba(37, 99, 235, 0.25) !important;
    }
    .st-key-ftw_panel button[type="submit"]:hover {
        background: linear-gradient(135deg, #3B82F6 0%, #2563EB 100%) !important;
        transform: translateY(-1px) !important;
        box-shadow: 0 6px 16px rgba(37, 99, 235, 0.38) !important;
    }
    .st-key-ftw_panel button[type="submit"]:active {
        transform: translateY(1px) !important;
    }

    /* Trust Disclaimer */
    .ftw-disclaimer {
        font-family: 'Inter', sans-serif;
        font-size: 0.68rem;
        color: #64748B;
        text-align: center;
        margin-top: 2px;
        margin-bottom: 2px;
        line-height: 1.25;
    }

    /* Flex structure to prevent bottom clipping */
    .st-key-ftw_panel > div,
    .st-key-ftw_panel [data-testid="stVerticalBlock"] {
        height: 100% !important;
        display: flex !important;
        flex-direction: column !important;
    }
    .st-key-ftw_panel [data-testid="stVerticalBlock"] > div {
        flex-shrink: 0 !important;
    }
    .st-key-ftw_panel [data-testid="stVerticalBlock"] > div:has(.ftw-msgs),
    .st-key-ftw_panel [data-testid="stVerticalBlock"] > div:has(.ftw-msgs) > div,
    .st-key-ftw_panel [data-testid="stVerticalBlock"] > div:has(.ftw-msgs) [data-testid="stMarkdownContainer"],
    .st-key-ftw_panel [data-testid="stVerticalBlock"] > div:has(.ftw-empty-card),
    .st-key-ftw_panel [data-testid="stVerticalBlock"] > div:has(.ftw-empty-card) > div,
    .st-key-ftw_panel [data-testid="stVerticalBlock"] > div:has(.ftw-empty-card) [data-testid="stMarkdownContainer"] {
        flex: 1 1 auto !important;
        flex-shrink: 1 !important;
        overflow: hidden !important;
        display: flex !important;
        flex-direction: column !important;
    }
    </style>
    <script>
    if (typeof window.ftwCopy === 'undefined') {
        window.ftwCopy = function(btn) {
            try {
                const bubble = btn.closest('.ftw-bubble');
                if (!bubble) return;
                const source = bubble.querySelector('.ftw-copy-source');
                if (!source) return;
                const text = source.textContent;

                const onDone = () => {
                    const lbl = btn.querySelector('.ftw-copy-text');
                    btn.classList.add('copied');
                    if (lbl) lbl.textContent = 'Copied!';
                    setTimeout(() => {
                        btn.classList.remove('copied');
                        if (lbl) lbl.textContent = 'Copy';
                    }, 2000);
                };

                if (navigator.clipboard && window.isSecureContext) {
                    navigator.clipboard.writeText(text).then(onDone).catch(() => fallback(text, onDone));
                } else {
                    fallback(text, onDone);
                }

                function fallback(txt, cb) {
                    const t = document.createElement('textarea');
                    t.value = txt;
                    t.style.position = 'fixed';
                    t.style.left = '-999999px';
                    document.body.appendChild(t);
                    t.focus();
                    t.select();
                    try { document.execCommand('copy'); } catch(e) {}
                    document.body.removeChild(t);
                    cb();
                }
            } catch(e) {
                console.error(e);
            }
        };
    }
    </script>
    """, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════
# Single Source of Truth Message Handler
# ══════════════════════════════════════════════════════════════════════════

def _process_user_message(msg_text: str, twin, remaining: int):
    """Processes message submission from either manual text input or suggestion chips.
    Preserves all existing logic: sanitization, usage recording, API call, and history capping."""
    if not msg_text or not msg_text.strip() or remaining <= 0:
        return
    safe_msg = sanitize_chat_message(msg_text.strip())
    if safe_msg:
        st.session_state[HISTORY_KEY].append({"role": "user", "text": safe_msg})
        _record_usage(twin)
        with st.spinner("FinBot is analyzing..."):
            reply = _call_gemini(twin, st.session_state[HISTORY_KEY])
        st.session_state[HISTORY_KEY].append({"role": "model", "text": reply})
        if len(st.session_state[HISTORY_KEY]) > MAX_HISTORY:
            st.session_state[HISTORY_KEY] = st.session_state[HISTORY_KEY][-MAX_HISTORY:]
        st.rerun()


# ══════════════════════════════════════════════════════════════════════════
# Public entry point
# ══════════════════════════════════════════════════════════════════════════

def render_chatbot(twin=None):
    """Renders the floating FinBot widget. Call once per page."""
    # Check if the user has changed to clear chat history from previous user
    curr_user_id = twin.user_id if twin is not None else "guest"
    last_user_id = st.session_state.get("ftw_last_user_id")
    if last_user_id is not None and last_user_id != curr_user_id:
        st.session_state[HISTORY_KEY] = []
        st.session_state[OPEN_KEY] = False
    st.session_state["ftw_last_user_id"] = curr_user_id

    if HISTORY_KEY not in st.session_state:
        st.session_state[HISTORY_KEY] = []
    if OPEN_KEY not in st.session_state:
        st.session_state[OPEN_KEY] = False

    _inject_css()
    used, limit = _usage_today(twin)
    remaining = max(0, limit - used)

    if not st.session_state[OPEN_KEY]:
        st.markdown("""
        <div class="ftw-orb-wrap" title="AI Financial Coach">
            <div class="ftw-orb">
                <div class="ftw-ping"></div>
                <div class="ftw-orb-icon">
                    <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/>
                    </svg>
                </div>
                <div class="ftw-badge"></div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        if st.button(" ", key="ftw_toggle_btn", help="Open AI Financial Assistant"):
            st.session_state[OPEN_KEY] = True
            st.rerun()
        return

    # ── Open panel ──────────────────────────────────────────────────────
    with st.container(key="ftw_panel"):
        history = st.session_state[HISTORY_KEY]

        header_l, header_m, header_r = st.columns([0.56, 0.26, 0.18], vertical_alignment="center")
        with header_l:
            st.markdown("""
            <div class="ftw-panel-title">
                <div class="ftw-mini-orb">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/>
                    </svg>
                    <div class="ftw-mini-badge"></div>
                </div>
                <div>
                    <div style="display: flex; align-items: center; gap: 6px;">
                        <div class="ftw-title-text">FinBot</div>
                        <span class="ftw-intel-badge"><i class="fa-solid fa-sparkles" style="font-size: 0.55rem;"></i> FinTwin Intelligence</span>
                    </div>
                    <div class="ftw-subtitle"><span class="ftw-pulse-dot">●</span> Online</div>
                </div>
            </div>
            """, unsafe_allow_html=True)
        with header_m:
            pill_class = "zero" if remaining == 0 else ("low" if remaining <= max(3, limit // 5) else "")
            st.markdown(
                f'<div class="ftw-usage-pill {pill_class}" title="{remaining} messages remaining today">{used}/{limit} today</div>',
                unsafe_allow_html=True,
            )
        with header_r:
            if history:
                act_c1, act_c2 = st.columns([1, 1], gap="small", vertical_alignment="center")
                with act_c1:
                    if st.button("", icon=":material/delete:", key="ftw_clear_hdr_btn", help="Clear conversation"):
                        st.session_state[HISTORY_KEY] = []
                        st.rerun()
                with act_c2:
                    if st.button("", icon=":material/close:", key="ftw_close_btn", help="Close Assistant"):
                        st.session_state[OPEN_KEY] = False
                        st.rerun()
            else:
                if st.button("", icon=":material/close:", key="ftw_close_btn", help="Close Assistant"):
                    st.session_state[OPEN_KEY] = False
                    st.rerun()

        if not history:
            user_first_name = _he(twin.name.split()[0]) if (twin is not None and getattr(twin, "name", None)) else None
            greeting_title = f"Hi {user_first_name} \U0001f44b" if user_first_name else "Hi there \U0001f44b"
            greeting_desc = (
                "I'm your FinTwin financial assistant. Ask me about your savings, spending, "
                "investments, debt, taxes, or financial goals."
            )
            st.markdown(f"""
            <div class="ftw-empty-card">
                <h4 class="ftw-welcome-title">{greeting_title}</h4>
                <p class="ftw-welcome-desc">{greeting_desc}</p>
                <div class="ftw-suggestion-label">
                    <i class="fa-regular fa-lightbulb"></i> Suggested Questions
                </div>
            </div>
            """, unsafe_allow_html=True)

            suggestions = [
                "Analyze my savings & budget",
                "How is my spending?",
                "Review my investments",
                "How am I doing toward my goals?",
            ]
            for idx, prompt_text in enumerate(suggestions):
                if st.button(prompt_text, key=f"ftw_sugg_{idx}", use_container_width=True, disabled=(remaining == 0)):
                    _process_user_message(prompt_text, twin, remaining)
        else:
            bubble_items = []
            for m in history:
                if m["role"] == "user":
                    bubble_items.append(f'<div class="ftw-bubble user">{_format_inline_markdown(m["text"])}</div>')
                else:
                    raw_text_escaped = _he(m["text"])
                    formatted_content = _format_chat_markdown(m["text"])
                    bubble_items.append(
                        f'<div class="ftw-bubble model">'
                        f'{formatted_content}'
                        f'<div class="ftw-bubble-footer">'
                        f'<button class="ftw-copy-btn" type="button" onclick="ftwCopy(this)" title="Copy response">'
                        f'<svg class="ftw-copy-icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
                        f'<rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>'
                        f'<path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>'
                        f'</svg>'
                        f'<svg class="ftw-check-icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">'
                        f'<polyline points="20 6 9 17 4 12"></polyline>'
                        f'</svg>'
                        f'<span class="ftw-copy-text">Copy</span>'
                        f'</button>'
                        f'<span class="ftw-copy-source" style="display:none;">{raw_text_escaped}</span>'
                        f'</div>'
                        f'</div>'
                    )
            bubbles_html = "".join(bubble_items)
            st.markdown(f'<div class="ftw-msgs">{bubbles_html}</div>', unsafe_allow_html=True)

        if remaining == 0:
            who = "You've" if twin is not None else "This browser session has"
            st.markdown(
                f'<div class="ftw-limit-banner"><i class="fa-solid fa-circle-exclamation"></i> {who} reached today\u2019s limit of '
                f'{limit} FinBot messages. '
                f'{"Please come back tomorrow." if twin is not None else "Log in for a higher daily limit, or come back tomorrow."}'
                f'</div>',
                unsafe_allow_html=True,
            )

        with st.form("ftw_input_form", clear_on_submit=True, border=False):
            c1, c2 = st.columns([0.83, 0.17], vertical_alignment="center")
            with c1:
                user_msg = st.text_input(
                    "Message", key="ftw_user_msg", label_visibility="collapsed",
                    placeholder="Ask FinBot about your finances...",
                    disabled=(remaining == 0),
                )
            with c2:
                sent = st.form_submit_button(
                    "\u27a4", use_container_width=True, disabled=(remaining == 0),
                    help="Send message"
                )

        st.markdown("""
        <div class="ftw-disclaimer">
            <i class="fa-solid fa-shield-halved" style="font-size: 0.68rem; margin-right: 3px; opacity: 0.7;"></i>
            FinBot can make mistakes. Verify important financial decisions.
        </div>
        """, unsafe_allow_html=True)

        if sent and user_msg.strip() and remaining > 0:
            _process_user_message(user_msg.strip(), twin, remaining)
