"""
Session & Authentication UI

Replaces the old sidebar logic with a premium fintech navigation system
featuring custom CSS, grouped links, active indicators, financial status, and modal authentication.
"""
import time
import streamlit as st
from database.connection import init_db, get_db_cursor
from database.db_manager import DBManager
from models.twin_engine import FinancialDigitalTwin, HealthScoreEngine
from utils import auth
from utils.chatbot import render_chatbot
from utils.security import (
    session_is_expired,
    session_touch,
    validate_name,
    validate_email,
    MAX_NAME_LEN,
    MAX_EMAIL_LEN,
)
from typing import Optional
import logging

logger = logging.getLogger(__name__)

def _init_db_once():
    if not st.session_state.get("_db_initialized"):
        try:
            init_db()
            st.session_state["_db_initialized"] = True
        except Exception as e:
            logger.error(f"Error initializing database: {e}", exc_info=True)
            st.error("A database error occurred. Please try again later.")

def load_css():
    """Injects premium CSS for the fintech sidebar redesign and global spacing system."""
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=Outfit:wght@300;400;500;600;700;800&family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200&display=swap');
        @import url('https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css');

        :root {
            --space-2xs: 4px;
            --space-xs: 8px;
            --space-sm: 12px;
            --space-md: 16px;
            --space-lg: 24px;
            --space-xl: 32px;
            --space-2xl: 48px;
            --space-3xl: 64px;
            --radius-sm: 6px;
            --radius-md: 10px;
            --radius-lg: 14px;
            --radius-xl: 18px;
            --card-bg: #1F2937;
            --card-border: rgba(255, 255, 255, 0.06);
        }

        /* Prevent horizontal scroll in the sidebar */
        section[data-testid="stSidebar"] {
            overflow-x: hidden !important;
        }
        section[data-testid="stSidebar"] div[data-testid="stSidebarUserContent"] {
            overflow-x: hidden !important;
        }

        /* Global Page Container Standardization */
        .main .block-container,
        [data-testid="stMainBlockContainer"],
        div[data-testid="stAppViewBlockContainer"] {
            max-width: 1340px !important;
            padding-top: 1.75rem !important;
            padding-bottom: 4rem !important;
            padding-left: 2rem !important;
            padding-right: 2rem !important;
        }
        @media (max-width: 768px) {
            .main .block-container,
            [data-testid="stMainBlockContainer"],
            div[data-testid="stAppViewBlockContainer"] {
                padding-left: 1.15rem !important;
                padding-right: 1.15rem !important;
                padding-top: 1.25rem !important;
                padding-bottom: 3.5rem !important;
            }
        }

        /* Global Font Override */
        html, body, [data-testid="stAppViewContainer"], .stApp, p, li, label, input, select, textarea {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif !important;
        }

        /* App Background Styling (Matching Dashboard across all pages) */
        .stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] {
            background-color: #0B1220 !important;
            background-image: radial-gradient(circle at 50% 0%, rgba(79, 140, 255, 0.08) 0%, transparent 60%),
                              radial-gradient(circle at 100% 100%, rgba(0, 212, 255, 0.04) 0%, transparent 40%) !important;
            background-attachment: fixed !important;
        }

        /* Restore Material Icons Font Family for Streamlit native icons */
        .material-icons,
        [data-testid="stIcon"],
        [class*="Icon"],
        [class*="icon"],
        button[data-testid="stSidebarCollapseButton"] *,
        div[data-testid="collapsedControl"] * {
            font-family: 'Material Icons', 'Material Symbols Outlined', 'Material Symbols Rounded', sans-serif !important;
        }

        /* Titles and Headers */
        h1, [data-testid="stMarkdownContainer"] h1, .hero-title {
            font-family: 'Plus Jakarta Sans', sans-serif !important;
            font-size: 2.35rem !important;
            font-weight: 800 !important;
            letter-spacing: -0.03em !important;
            line-height: 1.2 !important;
            color: #F8FAFC !important;
            margin-bottom: 0.35rem !important;
        }
        
        h2, [data-testid="stMarkdownContainer"] h2 {
            font-family: 'Plus Jakarta Sans', sans-serif !important;
            font-size: 1.6rem !important;
            font-weight: 700 !important;
            letter-spacing: -0.02em !important;
            line-height: 1.25 !important;
            color: #F8FAFC !important;
            margin-top: 1.75rem !important;
            margin-bottom: 0.5rem !important;
        }
        
        h3, [data-testid="stMarkdownContainer"] h3, .module-title, .feature-title {
            font-family: 'Plus Jakarta Sans', sans-serif !important;
            font-size: 1.2rem !important;
            font-weight: 700 !important;
            letter-spacing: -0.015em !important;
            line-height: 1.3 !important;
            color: #F8FAFC !important;
            margin-bottom: 0.35rem !important;
        }
        
        h4, h5, h6, [data-testid="stMarkdownContainer"] h4, [data-testid="stMarkdownContainer"] h5, [data-testid="stMarkdownContainer"] h6 {
            font-family: 'Plus Jakarta Sans', sans-serif !important;
            font-size: 1.05rem !important;
            font-weight: 600 !important;
            letter-spacing: -0.01em !important;
            color: #E2E8F0 !important;
        }

        /* Financial Figures & Metrics */
        [data-testid="stMetricValue"], .kpi-value, .financial-number, .metric-value, .score-value {
            font-family: 'Outfit', sans-serif !important;
            font-size: 1.75rem !important;
            font-weight: 700 !important;
            letter-spacing: -0.01em !important;
            color: #F8FAFC !important;
        }

        /* Metric Labels */
        [data-testid="stMetricLabel"], .kpi-label {
            font-family: 'Inter', sans-serif !important;
            font-size: 0.78rem !important;
            font-weight: 600 !important;
            color: #94A3B8 !important;
            text-transform: uppercase !important;
            letter-spacing: 0.05em !important;
        }

        /* Widget inputs, sliders, select boxes */
        [data-testid="stWidgetLabel"] p, label, .stWidgetLabel {
            font-family: 'Inter', sans-serif !important;
            font-size: 0.88rem !important;
            font-weight: 500 !important;
            color: #CBD5E1 !important;
            margin-bottom: 0.3rem !important;
        }
        
        /* Selectbox / dropdown options */
        div[data-baseweb="select"] * {
            font-family: 'Inter', sans-serif !important;
            font-size: 0.92rem !important;
        }

        /* Native Streamlit Buttons */
        button[data-testid="stBaseButton-secondary"], 
        button[data-testid="stBaseButton-primary"],
        .stButton > button {
            font-family: 'Plus Jakarta Sans', sans-serif !important;
            font-size: 0.9rem !important;
            font-weight: 600 !important;
            letter-spacing: -0.01em !important;
            border-radius: 8px !important;
            padding: 0.55rem 1.25rem !important;
            min-height: 42px !important;
        }

        /* Standardize Tabs */
        div[data-testid="stTabs"] [data-baseweb="tab-list"] {
            gap: 8px !important;
            border-bottom: 1px solid rgba(255, 255, 255, 0.08) !important;
            margin-bottom: 1.5rem !important;
        }
        div[data-testid="stTabs"] [data-baseweb="tab"] {
            font-family: 'Plus Jakarta Sans', sans-serif !important;
            font-size: 0.9rem !important;
            font-weight: 600 !important;
            padding: 0.6rem 1rem !important;
            border-radius: 6px 6px 0 0 !important;
        }

        /* Standardize Expanders */
        div[data-testid="stExpander"] {
            border: 1px solid rgba(255, 255, 255, 0.06) !important;
            border-radius: 10px !important;
            background: #1F2937 !important;
            margin-bottom: 0.75rem !important;
        }

        /* Hide default auto sidebar navigation */
        div[data-testid="stSidebarNav"] {
            display: none !important;
        }
        
        /* Transparent Streamlit Header */
        header[data-testid="stHeader"] {
            background-color: transparent !important;
            background: transparent !important;
            border-bottom: none !important;
        }
        
        /* Sidebar background & border */
        section[data-testid="stSidebar"] {
            background-color: #111827 !important;
            border-right: 1px solid rgba(255, 255, 255, 0.06) !important;
        }
        
        /* Sidebar layout padding adjustments */
        div[data-testid="stSidebarUserContent"] {
            padding-top: 0.85rem !important;
            padding-left: 1.15rem !important;
            padding-right: 1.15rem !important;
            padding-bottom: 2rem !important;
        }
        
        /* Sidebar Navigation Item Links */
        div[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"] {
            color: #94A3B8 !important;
            background-color: transparent !important;
            border: 1px solid transparent !important;
            border-left: 3px solid transparent !important;
            border-radius: 8px !important;
            padding: 0.5rem 0.75rem !important;
            min-height: 38px !important;
            transition: all 0.18s cubic-bezier(0.16, 1, 0.3, 1) !important;
            font-weight: 500 !important;
            text-decoration: none !important;
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 3px;
        }
        
        div[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"]:hover {
            background-color: rgba(255, 255, 255, 0.04) !important;
            border-color: rgba(255, 255, 255, 0.06) !important;
            border-left: 3px solid rgba(79, 140, 255, 0.4) !important;
            color: #F8FAFC !important;
        }

        div[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"] p {
            color: #94A3B8 !important;
            font-size: 0.88rem !important;
            font-weight: 500 !important;
            transition: color 0.18s ease !important;
            margin: 0 !important;
        }
        
        div[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"]:hover p {
            color: #F8FAFC !important;
        }
        
        /* Active Page Highlighting via aria-current */
        div[data-testid="stSidebar"] a[aria-current="page"] {
            background: rgba(79, 140, 255, 0.10) !important;
            border: 1px solid rgba(79, 140, 255, 0.22) !important;
            border-left: 3px solid #4F8CFF !important;
            border-radius: 8px !important;
        }

        div[data-testid="stSidebar"] a[aria-current="page"] p {
            color: #FFFFFF !important;
            font-weight: 600 !important;
        }

        /* Modernized Sidebar Collapse Arrow Styling */
        div[data-testid="stSidebarCollapseButton"] {
            top: 0.75rem !important;
            right: 0.5rem !important;
        }
        
        div[data-testid="stSidebarCollapseButton"] button {
            background-color: rgba(255, 255, 255, 0.03) !important;
            border: 1px solid rgba(255, 255, 255, 0.06) !important;
            border-radius: 8px !important;
            color: #94A3B8 !important;
            transition: all 0.2s ease-in-out !important;
        }
        
        div[data-testid="stSidebarCollapseButton"] button:hover {
            background-color: #1F2937 !important;
            color: #4F8CFF !important;
            border-color: rgba(79, 140, 255, 0.25) !important;
        }

        /* Modernized Sidebar Expand Arrow Styling (when collapsed) */
        div[data-testid="collapsedControl"] button {
            background-color: #111827 !important;
            border: 1px solid rgba(255, 255, 255, 0.06) !important;
            border-radius: 8px !important;
            color: #94A3B8 !important;
            transition: all 0.2s ease-in-out !important;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4) !important;
        }
        
        div[data-testid="collapsedControl"] button:hover {
            background-color: #1F2937 !important;
            color: #4F8CFF !important;
            border-color: rgba(79, 140, 255, 0.25) !important;
        }
        
        /* Section Headers for Link Groups */
        .sidebar-header {
            font-family: 'Plus Jakarta Sans', sans-serif;
            font-size: 0.70rem;
            text-transform: uppercase;
            letter-spacing: 0.09em;
            color: #64748B;
            margin-top: 1.15rem;
            margin-bottom: 0.35rem;
            padding-left: 0.5rem;
            font-weight: 700;
        }

        /* Load Font Awesome font family for sidebar icons with consistent size and alignment */
        [data-testid="stSidebar"] .stPageLink a [data-testid="stIcon"],
        [data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"] [data-testid="stIcon"] {
            font-family: "Font Awesome 6 Free" !important;
            font-weight: 900 !important;
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
            text-rendering: auto !important;
            -webkit-font-smoothing: antialiased !important;
            font-size: 0 !important;
            width: 1.25rem !important;
            height: 1.25rem !important;
            text-align: center !important;
            flex-shrink: 0 !important;
        }

        /* Colorize & Inject Clean Font Awesome Unicode Glyphs for Sidebar Icons */
        [data-testid="stSidebar"] a[href="/"] [data-testid="stIcon"]::before,
        [data-testid="stSidebar"] a[href*="app"] [data-testid="stIcon"]::before {
            content: "\\f009" !important; /* LayoutDashboard */
            font-size: 1.05rem !important;
        }
        [data-testid="stSidebar"] a[href="/"] [data-testid="stIcon"],
        [data-testid="stSidebar"] a[href*="app"] [data-testid="stIcon"] { color: #4F8CFF !important; }

        [data-testid="stSidebar"] a[href*="Digital_Twin"] [data-testid="stIcon"]::before {
            content: "\\f2bd" !important; /* UserRound */
            font-size: 1.05rem !important;
        }
        [data-testid="stSidebar"] a[href*="Digital_Twin"] [data-testid="stIcon"] { color: #3B82F6 !important; }

        [data-testid="stSidebar"] a[href*="Financial_Health"] [data-testid="stIcon"]::before {
            content: "\\f625" !important; /* Gauge */
            font-size: 1.05rem !important;
        }
        [data-testid="stSidebar"] a[href*="Financial_Health"] [data-testid="stIcon"] { color: #10B981 !important; }

        [data-testid="stSidebar"] a[href*="Behavior_Analysis"] [data-testid="stIcon"]::before {
            content: "\\f080" !important; /* ChartNoAxesCombined */
            font-size: 1.05rem !important;
        }
        [data-testid="stSidebar"] a[href*="Behavior_Analysis"] [data-testid="stIcon"] { color: #00D4FF !important; }

        [data-testid="stSidebar"] a[href*="Financial_Personality"] [data-testid="stIcon"]::before {
            content: "\\f577" !important; /* Fingerprint */
            font-size: 1.05rem !important;
        }
        [data-testid="stSidebar"] a[href*="Financial_Personality"] [data-testid="stIcon"] { color: #A855F7 !important; }

        [data-testid="stSidebar"] a[href*="Forecasting"] [data-testid="stIcon"]::before {
            content: "\\f201" !important; /* TrendingUp */
            font-size: 1.05rem !important;
        }
        [data-testid="stSidebar"] a[href*="Forecasting"] [data-testid="stIcon"] { color: #EC4899 !important; }

        [data-testid="stSidebar"] a[href*="Scenario_Simulator"] [data-testid="stIcon"]::before {
            content: "\\f1de" !important; /* SlidersHorizontal */
            font-size: 1.05rem !important;
        }
        [data-testid="stSidebar"] a[href*="Scenario_Simulator"] [data-testid="stIcon"] { color: #EF4444 !important; }

        [data-testid="stSidebar"] a[href*="Tax_Intelligence"] [data-testid="stIcon"]::before {
            content: "\\f543" !important; /* ReceiptText */
            font-size: 1.05rem !important;
        }
        [data-testid="stSidebar"] a[href*="Tax_Intelligence"] [data-testid="stIcon"] { color: #10B981 !important; }

        [data-testid="stSidebar"] a[href*="Goal_Planner"] [data-testid="stIcon"]::before {
            content: "\\f140" !important; /* Target */
            font-size: 1.05rem !important;
        }
        [data-testid="stSidebar"] a[href*="Goal_Planner"] [data-testid="stIcon"] { color: #6366F1 !important; }

        [data-testid="stSidebar"] a[href*="AI_Coach"] [data-testid="stIcon"]::before {
            content: "\\f27a" !important; /* MessageCircle */
            font-size: 1.05rem !important;
        }
        [data-testid="stSidebar"] a[href*="AI_Coach"] [data-testid="stIcon"] { color: #F59E0B !important; }

        [data-testid="stSidebar"] a[href*="Explainable_AI"] [data-testid="stIcon"]::before {
            content: "\\f5dc" !important; /* BrainCircuit */
            font-size: 1.05rem !important;
        }
        [data-testid="stSidebar"] a[href*="Explainable_AI"] [data-testid="stIcon"] { color: #E2E8F0 !important; }

        [data-testid="stSidebar"] a[href*="Settings"] [data-testid="stIcon"]::before {
            content: "\\f013" !important; /* Settings2 */
            font-size: 1.05rem !important;
        }
        [data-testid="stSidebar"] a[href*="Settings"] [data-testid="stIcon"] { color: #38BDF8 !important; }

        /* Dark Theme Subtle Custom Scrollbar */
        section[data-testid="stSidebar"] div[data-testid="stSidebarContent"]::-webkit-scrollbar,
        section[data-testid="stSidebar"] ::-webkit-scrollbar {
            width: 5px;
            height: 5px;
        }
        section[data-testid="stSidebar"] ::-webkit-scrollbar-track {
            background: transparent;
        }
        section[data-testid="stSidebar"] ::-webkit-scrollbar-thumb {
            background: rgba(255, 255, 255, 0.12);
            border-radius: 99px;
        }
        section[data-testid="stSidebar"] ::-webkit-scrollbar-thumb:hover {
            background: rgba(79, 140, 255, 0.35);
        }

        /* Financial Status Compact Card */
        .sidebar-status-card {
            background: #1F2937;
            border: 1px solid rgba(255, 255, 255, 0.06);
            border-radius: 10px;
            padding: 0.85rem 0.95rem;
            margin-top: 1.25rem;
            margin-bottom: 0.75rem;
            box-shadow: 0 4px 10px rgba(0, 0, 0, 0.2);
        }
        .sidebar-status-card.incomplete {
            border-style: dashed;
            border-color: rgba(79, 140, 255, 0.25);
            background: rgba(79, 140, 255, 0.04);
        }
        .status-card-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 0.35rem;
        }
        .status-card-title {
            font-size: 0.68rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            color: #94A3B8;
        }
        .status-grade-tag {
            font-size: 0.72rem;
            font-weight: 700;
            padding: 0.15rem 0.45rem;
            border-radius: 4px;
        }
        .status-score-line {
            display: flex;
            justify-content: space-between;
            align-items: baseline;
            margin-bottom: 0.4rem;
        }
        .status-score-num {
            font-family: 'Outfit', sans-serif;
            font-size: 1.15rem;
            font-weight: 700;
            color: #F8FAFC;
        }
        .status-score-denom {
            font-size: 0.78rem;
            font-weight: 500;
            color: #64748B;
        }
        .status-score-text {
            font-size: 0.8rem;
            font-weight: 600;
        }
        .status-bar-track {
            width: 100%;
            height: 5px;
            background: rgba(255, 255, 255, 0.08);
            border-radius: 99px;
            overflow: hidden;
        }
        .status-bar-thumb {
            height: 100%;
            border-radius: 99px;
            transition: width 0.6s ease;
        }
        .status-incomplete-msg {
            color: #94A3B8;
            font-size: 0.82rem;
            margin: 0.25rem 0 0.45rem 0;
        }
        .status-incomplete-action {
            display: inline-flex;
            align-items: center;
            gap: 4px;
            color: #4F8CFF !important;
            text-decoration: none !important;
            font-size: 0.78rem;
            font-weight: 600;
            transition: transform 0.15s ease;
        }
        .status-incomplete-action:hover {
            color: #60A5FA !important;
            transform: translateX(2px);
        }

        /* User Profile Footer Section */
        .sidebar-profile-box {
            background: #1F2937;
            border: 1px solid rgba(255, 255, 255, 0.06);
            border-radius: 12px;
            padding: 0.75rem 0.85rem;
            margin-top: 1rem;
            margin-bottom: 0.75rem;
            box-shadow: 0 4px 10px rgba(0, 0, 0, 0.15);
        }
        .profile-user-row {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 8px;
            width: 100%;
        }
        .profile-user-left {
            display: flex;
            align-items: center;
            gap: 10px;
            min-width: 0;
            flex: 1;
        }
        .profile-avatar {
            width: 34px;
            height: 34px;
            border-radius: 50%;
            background: linear-gradient(135deg, #2563EB, #1D4ED8);
            border: 1.5px solid rgba(255, 255, 255, 0.15);
            display: flex;
            justify-content: center;
            align-items: center;
            font-weight: 700;
            color: #FFFFFF;
            font-size: 0.82rem;
            letter-spacing: 0.02em;
            flex-shrink: 0;
        }
        .profile-meta {
            flex: 1;
            min-width: 0;
        }
        .profile-fullname {
            font-size: 0.88rem;
            font-weight: 600;
            color: #F8FAFC;
            line-height: 1.2;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .profile-tagline {
            font-size: 0.72rem;
            color: #94A3B8;
            margin-top: 2px;
        }
        .profile-settings-btn {
            color: #94A3B8 !important;
            text-decoration: none !important;
            width: 32px;
            height: 32px;
            border-radius: 8px;
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid rgba(255, 255, 255, 0.06);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 0.95rem;
            flex-shrink: 0;
            transition: background 0.2s ease, border-color 0.2s ease, color 0.2s ease;
        }
        .profile-settings-btn i {
            transition: transform 0.35s cubic-bezier(0.34, 1.56, 0.64, 1);
            display: inline-block;
        }
        .profile-settings-btn:hover {
            color: #4F8CFF !important;
            background: rgba(79, 140, 255, 0.15) !important;
            border-color: rgba(79, 140, 255, 0.35) !important;
        }
        .profile-settings-btn:hover i {
            transform: rotate(90deg);
        }
        .profile-settings-btn:active i {
            transform: rotate(180deg) scale(0.9);
        }

        /* Streamlit Toast Notification Popup */
        div[data-testid="stToast"] {
            background-color: #111827 !important;
            background: linear-gradient(135deg, rgba(16, 185, 129, 0.12) 0%, #111827 100%) !important;
            border: 1px solid rgba(16, 185, 129, 0.4) !important;
            border-left: 4px solid #10B981 !important;
            border-radius: 8px !important;
            box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.6), 0 0 15px rgba(16, 185, 129, 0.2) !important;
        }

        div[data-testid="stToast"] [data-testid="stIcon"],
        div[data-testid="stToast"] .material-symbols-rounded,
        div[data-testid="stToast"] [class*="Icon"] {
            color: #10B981 !important;
            font-size: 1.35rem !important;
        }

        div[data-testid="stToast"] [data-testid="stMarkdownContainer"] p {
            color: #F8FAFC !important;
            font-weight: 500 !important;
        }

        div[data-testid="stToast"] button {
            color: #94A3B8 !important;
        }
        div[data-testid="stToast"] button:hover {
            color: #10B981 !important;
        }
        </style>
    """, unsafe_allow_html=True)

# Try to use st.dialog if available, fallback to experimental
try:
    dialog_decorator = st.dialog
except AttributeError:
    try:
        dialog_decorator = st.experimental_dialog
    except AttributeError:
        # Dummy decorator if neither exists (fallback mechanism)
        def dialog_decorator(title):
            def decorator(func):
                return func
            return decorator


@dialog_decorator("Reset Your Password")
def reset_password_modal(raw_token: str):
    """Modal dialog for resetting password via secure email link."""
    st.write("Enter a strong new password for your FinTwin AI account.")
    is_valid, msg, email = auth.validate_reset_token(raw_token)
    if not is_valid:
        st.error(msg)
        if st.button("Close", use_container_width=True):
            if "reset_password_token" in st.query_params:
                del st.query_params["reset_password_token"]
            st.rerun()
        return

    if email:
        st.caption(f"Account: **{email}**")

    with st.form("reset_password_form"):
        new_pw = st.text_input("New Password", type="password", max_chars=64)
        confirm_pw = st.text_input("Confirm New Password", type="password", max_chars=64)
        st.caption("Must be at least 8 characters, with uppercase, lowercase, and a number or symbol.")
        submitted = st.form_submit_button("Reset Password", use_container_width=True, type="primary")
        if submitted:
            success, reset_msg = auth.reset_password_with_token(raw_token, new_pw, confirm_pw)
            if success:
                st.success(reset_msg)
                if "reset_password_token" in st.query_params:
                    del st.query_params["reset_password_token"]
                st.info("You can now close this window and log in with your new password.")
            else:
                st.error(reset_msg)


@dialog_decorator("Welcome to FinTwin AI")
def login_modal():
    st.write("Log in to your own Financial Twin, or create a free account.")

    # Global feedback from previous actions (e.g. email verified)
    if "_auth_success_msg" in st.session_state:
        st.success(st.session_state.pop("_auth_success_msg"))

    tab_login, tab_register, tab_forgot = st.tabs([
        ":material/login: Log In",
        ":material/person_add: Register",
        ":material/lock_reset: Forgot Password",
    ])

    with tab_login:
        with st.form("login_form"):
            email = st.text_input("Email Address", key="login_email", max_chars=MAX_EMAIL_LEN)
            password = st.text_input("Password", type="password", key="login_password", max_chars=64)
            submitted = st.form_submit_button("Log In", use_container_width=True, type="primary")
            if submitted:
                ok, status_code, user = auth.login_user(email, password)
                if ok:
                    st.session_state["user_id"] = user["user_id"]
                    st.query_params["uid"] = user["user_id"]
                    session_touch(st.session_state)
                    st.session_state["_auth_success_msg"] = f"Welcome back, {user.get('name', 'User')}!"
                    st.rerun()
                else:
                    if status_code == "UNVERIFIED_EMAIL":
                        st.session_state["_unverified_email"] = email
                        st.error(user)
                    else:
                        st.error(user)

        if st.session_state.get("_unverified_email"):
            unverified = st.session_state["_unverified_email"]
            st.markdown("---")
            st.markdown(
                f"<div style='font-size: 0.9rem; color: #94A3B8; margin-bottom: 0.5rem;'>"
                f"Need a new activation link for <strong>{unverified}</strong>?</div>",
                unsafe_allow_html=True,
            )
            if st.button("Resend Verification Email", use_container_width=True, type="secondary"):
                resend_ok, resend_msg = auth.resend_verification_email(unverified)
                if resend_ok:
                    st.success(resend_msg)
                else:
                    st.error(resend_msg)

    with tab_register:
        with st.form("register_form"):
            r_name = st.text_input("Full Name", key="register_name", max_chars=MAX_NAME_LEN)
            r_email = st.text_input("Email Address", key="register_email", max_chars=MAX_EMAIL_LEN)
            r_age = st.number_input("Age", min_value=18, max_value=100, value=25, key="register_age")
            r_password = st.text_input(
                "Password",
                type="password",
                help="At least 8 characters, with uppercase, lowercase, and a number or symbol.",
                key="register_password",
                max_chars=64,
            )
            r_confirm = st.text_input(
                "Confirm Password",
                type="password", key="register_confirm_password", max_chars=64
            )
            submitted = st.form_submit_button("Create Account", use_container_width=True, type="primary")
            if submitted:
                ok, status_code, result = auth.register_user(
                    email=r_email,
                    password=r_password,
                    name=r_name,
                    age=r_age,
                    confirm_password=r_confirm,
                )
                if ok:
                    if status_code == "SUCCESS":
                        st.success(
                            f"Account created successfully for {r_name}.\n\n"
                            f"We have sent a verification email to **{r_email}** with an activation link.\n\n"
                            "Please click the link in your email to verify your account, then switch to the **Log In** tab to access your Digital Twin."
                        )
                    else:
                        st.warning(
                            "Your account was created successfully, but we couldn't send the verification email. "
                            "Please try logging in and requesting a new verification link."
                        )
                else:
                    st.error(result)

    with tab_forgot:
        st.write("Enter your registered email address and we'll send you a secure password reset link.")
        with st.form("forgot_password_form"):
            f_email = st.text_input("Registered Email", key="forgot_email", max_chars=MAX_EMAIL_LEN)
            f_submitted = st.form_submit_button("Send Password Reset Link", use_container_width=True, type="primary")
            if f_submitted:
                ok, msg = auth.request_password_reset(f_email)
                if ok:
                    st.success(
                        "If an account exists for this email address, a password reset link has been sent to your inbox. "
                        "The link will expire in 30 minutes."
                    )
                else:
                    st.error(msg)


def render_sidebar_user_selector() -> Optional[FinancialDigitalTwin]:
    """
    Renders custom sidebar navigation, authentication modal overlay,
    query parameter token handling, and returns the active account's FinancialDigitalTwin.
    """
    _init_db_once()
    load_css()

    # ── Handle Global Auth Success Feedback ──────────────────────────────
    if "_auth_success_msg" in st.session_state:
        st.toast(st.session_state.pop("_auth_success_msg"), icon=":material/check_circle:")

    # ── Handle Query Parameter Actions (Email Verification & Password Reset) ──
    params = st.query_params
    if "verify_email_token" in params:
        raw_token = params.get("verify_email_token")
        ok, msg = auth.verify_email_token(raw_token)
        if ok:
            st.toast("Email verified! Please log in to your account.", icon=":material/check_circle:")
            st.session_state["_auth_success_msg"] = msg
        else:
            st.toast(f"Verification failed: {msg}", icon=":material/error:")
        del st.query_params["verify_email_token"]
        st.rerun()

    if "reset_password_token" in params:
        raw_token = params.get("reset_password_token")
        reset_password_modal(raw_token)

    # ── Session restoration & timeout enforcement ────────────────────────
    if "user_id" not in st.session_state:
        candidate_uid = st.query_params.get("uid")
        if candidate_uid and DBManager.get_user_profile(candidate_uid):
            st.session_state["user_id"] = candidate_uid
            session_touch(st.session_state)

    if "user_id" in st.session_state:
        if session_is_expired(st.session_state):
            del st.session_state["user_id"]
            st.session_state.pop("_session_last_active", None)
            if "uid" in st.query_params:
                del st.query_params["uid"]
            st.warning("Your session expired due to inactivity. Please log in again.")
            st.rerun()
        else:
            session_touch(st.session_state)

    # Render Custom Top Header (SVG Logo)
    st.sidebar.markdown("""<svg width="100%" viewBox="0 0 320 100" xmlns="http://www.w3.org/2000/svg" style="margin-bottom: 1.5rem; margin-top: 0.25rem; display: block; overflow: hidden;">
<defs>
    <linearGradient id="gradBlueLogo" x1="0%" y1="100%" x2="100%" y2="0%">
        <stop offset="0%" stop-color="#4F8CFF" />
        <stop offset="100%" stop-color="#00D4FF" />
    </linearGradient>
    <linearGradient id="gradCyanLogo" x1="0%" y1="100%" x2="100%" y2="0%">
        <stop offset="0%" stop-color="#00D4FF" />
        <stop offset="100%" stop-color="#22C55E" />
    </linearGradient>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;700;800&amp;display=swap');
        .logo-text-fin { font-family: 'Outfit', sans-serif; font-weight: 800; font-size: 46px; }
        .logo-text-twin { font-family: 'Outfit', sans-serif; font-weight: 700; font-size: 46px; }
        .logo-text-ai { font-family: 'Outfit', sans-serif; font-weight: 300; font-size: 46px; }
    </style>
</defs>
<g transform="translate(-5, 8) scale(1.05)">
    <rect x="20" y="20" width="40" height="40" rx="12" fill="url(#gradBlueLogo)" opacity="0.85" transform="rotate(45, 40, 40)"/>
    <rect x="45" y="20" width="40" height="40" rx="12" fill="url(#gradCyanLogo)" opacity="0.85" transform="rotate(45, 65, 40)"/>
    <path d="M 30 55 L 50 35 L 60 45 L 85 20" fill="none" stroke="#F8FAFC" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
    <circle cx="85" cy="20" r="4" fill="#F8FAFC"/>
    <circle cx="30" cy="55" r="4" fill="#F8FAFC"/>
</g>
<text x="95" y="62" class="logo-text-fin" fill="#F8FAFC">Fin<tspan class="logo-text-twin" fill="#4F8CFF">Twin</tspan> <tspan class="logo-text-ai" fill="#00D4FF">AI</tspan></text>
<rect x="99" y="72" width="85" height="18" rx="4" fill="rgba(79, 140, 255, 0.15)" stroke="rgba(79,140,255,0.3)"/>
<text x="105" y="84" font-family="'Outfit', sans-serif" font-weight="700" font-size="10" fill="#4F8CFF" letter-spacing="1">AI POWERED</text>
</svg>""", unsafe_allow_html=True)

    # ── Grouped Navigation ──
    st.sidebar.markdown('<div class="sidebar-header">Overview</div>', unsafe_allow_html=True)
    st.sidebar.page_link("app.py", label="Home Dashboard", icon=":material/dashboard:")
    st.sidebar.page_link("pages/01_Digital_Twin.py", label="Digital Twin", icon=":material/account_circle:")
    st.sidebar.page_link("pages/02_Financial_Health.py", label="Financial Health", icon=":material/speed:")

    st.sidebar.markdown('<div class="sidebar-header">Analysis</div>', unsafe_allow_html=True)
    st.sidebar.page_link("pages/03_Behavior_Analysis.py", label="Behavior Analysis", icon=":material/query_stats:")
    st.sidebar.page_link("pages/04_Financial_Personality.py", label="Financial Personality", icon=":material/fingerprint:")
    st.sidebar.page_link("pages/05_Forecasting.py", label="Forecasting", icon=":material/trending_up:")
    st.sidebar.page_link("pages/06_Scenario_Simulator.py", label="Scenario Simulator", icon=":material/tune:")

    st.sidebar.markdown('<div class="sidebar-header">Financial Tools</div>', unsafe_allow_html=True)
    st.sidebar.page_link("pages/07_Tax_Intelligence.py", label="Tax Intelligence", icon=":material/receipt_long:")
    st.sidebar.page_link("pages/09_Goal_Planner.py", label="Goal Planner", icon=":material/track_changes:")

    st.sidebar.markdown('<div class="sidebar-header">AI Features</div>', unsafe_allow_html=True)
    st.sidebar.page_link("pages/08_AI_Coach.py", label="AI Coach", icon=":material/forum:")
    st.sidebar.page_link("pages/10_Explainable_AI.py", label="Explainable AI", icon=":material/psychology:")

    # ── Authentication Check ──
    if "user_id" not in st.session_state:
        st.sidebar.markdown('<div class="sidebar-header">Account</div>', unsafe_allow_html=True)
        if st.sidebar.button("Log In / Register", use_container_width=True, type="primary"):
            login_modal()
        render_chatbot(None)
        return None

    user_id = st.session_state["user_id"]
    demographics = DBManager.get_user_profile(user_id)
    if not demographics:
        st.sidebar.error("Could not load your account.")
        del st.session_state["user_id"]
        return None

    balance_sheet = DBManager.get_digital_twin(user_id)
    if balance_sheet is None:
        try:
            with get_db_cursor() as cursor:
                cursor.execute("INSERT OR IGNORE INTO digital_twins (user_id) VALUES (?)", (user_id,))
            balance_sheet = DBManager.get_digital_twin(user_id) or {"user_id": user_id}
        except Exception:
            balance_sheet = {"user_id": user_id}

    twin = FinancialDigitalTwin(user_id, demographics, balance_sheet)

    # ── Financial Status Block (Readily available data) ──
    has_profile_data = (twin.total_income > 0 or twin.net_worth != 0 or twin.bank_savings > 0 or twin.basic_expenses > 0)
    if has_profile_data:
        try:
            score_data = HealthScoreEngine(twin).compute_overall_health_score()
            h_score = score_data["overall_score"]
            h_grade = score_data["financial_grade"]
            grade_color = "#10B981" if h_score >= 75 else ("#F59E0B" if h_score >= 55 else "#EF4444")
            grade_bg = "rgba(16, 185, 129, 0.15)" if h_score >= 75 else ("rgba(245, 158, 11, 0.15)" if h_score >= 55 else "rgba(239, 68, 68, 0.15)")

            st.sidebar.markdown(f"""<div class="sidebar-status-card">
<div class="status-card-header">
<span class="status-card-title">FINANCIAL STATUS</span>
<span class="status-grade-tag" style="background: {grade_bg}; color: {grade_color};">{h_grade}</span>
</div>
<div class="status-score-line">
<span class="status-score-num">{h_score} <span class="status-score-denom">/ 100</span></span>
<span class="status-score-text" style="color: {grade_color};">{h_grade}</span>
</div>
<div class="status-bar-track">
<div class="status-bar-thumb" style="width: {h_score}%; background: {grade_color};"></div>
</div>
</div>""", unsafe_allow_html=True)
        except Exception:
            pass
    else:
        st.sidebar.markdown("""<div class="sidebar-status-card incomplete">
<div class="status-card-header"><span class="status-card-title">FINANCIAL PROFILE</span></div>
<div class="status-incomplete-msg">Profile incomplete</div>
<a href="/Digital_Twin" target="_self" class="status-incomplete-action"><span>Complete Profile</span> <i class="fa-solid fa-arrow-right"></i></a>
</div>""", unsafe_allow_html=True)

    # ── User Profile Initials & Name ──
    name_parts = [p for p in twin.name.strip().split() if p]
    if len(name_parts) >= 2:
        initials = f"{name_parts[0][0]}{name_parts[-1][0]}".upper()
    elif len(name_parts) == 1 and name_parts[0]:
        initials = name_parts[0][:2].upper()
    else:
        initials = "FT"

    # ── Compact Bottom Profile Footer ──
    st.sidebar.markdown(f"""<div class="sidebar-profile-box">
<div class="profile-user-row">
<div class="profile-user-left">
<div class="profile-avatar">{initials}</div>
<div class="profile-meta">
<div class="profile-fullname">{twin.name}</div>
<div class="profile-tagline">Financial Profile</div>
</div>
</div>
<a href="/Settings?uid={twin.user_id}" target="_self" class="profile-settings-btn" title="Settings & Privacy">
<i class="fa-solid fa-gear"></i>
</a>
</div>
</div>""", unsafe_allow_html=True)

    if st.sidebar.button("Log Out", icon=":material/logout:", use_container_width=True):
        st.session_state.pop("user_id", None)
        st.session_state.pop("_session_last_active", None)
        st.session_state.pop("_master_pdf_bytes", None)
        st.session_state.pop("_master_pdf_uid", None)
        st.session_state.pop("_reg_success_data", None)
        st.session_state.pop("_unverified_email", None)
        if "uid" in st.query_params:
            del st.query_params["uid"]
        st.rerun()

    render_chatbot(twin)
    return twin
