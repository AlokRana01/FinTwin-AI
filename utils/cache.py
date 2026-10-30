"""
utils/cache.py
==============
Centralized Caching Architecture for FinTwin AI.
Consolidates long-lived resource initialization, pre-trained ML models,
SHAP explainers, and static/reference benchmarks using Streamlit's caching primitives.

Design Principles:
  1. st.cache_resource:
     - Long-lived shared objects: ML models, SHAP explainers, database schema initialization.
  2. st.cache_data:
     - Static reference datasets and anonymous cohort benchmarks.
  3. User Data Safety:
     - Never globally cache private, user-specific financial information.
     - Cache keys for reference benchmarks explicitly depend on non-sensitive parameters (e.g., occupation).
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple
import pandas as pd
import streamlit as st


# ══════════════════════════════════════════════════════════════════════════════
# 1. Database Initialization (Global, run once per application process)
# ══════════════════════════════════════════════════════════════════════════════

@st.cache_resource(show_spinner=False)
def get_initialized_db() -> bool:
    """
    Ensures the SQLite database schema, migrations, and demo user are initialized
    exactly once for the server process, avoiding repetitive schema checks on reruns.
    """
    from database.connection import init_db
    init_db()
    return True


# ══════════════════════════════════════════════════════════════════════════════
# 2. Pretrained Machine Learning Models (st.cache_resource)
# ══════════════════════════════════════════════════════════════════════════════

@st.cache_resource(show_spinner=False)
def get_cached_predictor(horizon: int = 6) -> Tuple[Any, bool]:
    """
    Loads and caches the XGBoost FinancialPredictor models (savings + net worth)
    for the requested horizon. Reused across Forecasting, Explainable AI,
    FinBot chatbot, and Master Report without re-reading large JSON models from disk.
    """
    from models.predictor import FinancialPredictor
    predictor = FinancialPredictor()
    loaded = predictor.load_only(horizon=horizon)
    return predictor, loaded


@st.cache_resource(show_spinner=False)
def get_cached_clusterer() -> Any:
    """
    Loads and caches the pretrained FinancialPersonalityClusterer.
    Reused across the Financial Personality module and Master Report.
    """
    from models.clustering import FinancialPersonalityClusterer
    return FinancialPersonalityClusterer.load()


# ══════════════════════════════════════════════════════════════════════════════
# 3. Explainability Resources (st.cache_resource)
# ══════════════════════════════════════════════════════════════════════════════

@st.cache_resource(show_spinner=False)
def get_cached_tree_explainer(_model: Any) -> Any:
    """
    Caches the SHAP TreeExplainer for an XGBoost booster model.
    The leading underscore on `_model` prevents Streamlit from attempting
    to hash the unhashable XGBRegressor instance.
    """
    import shap
    return shap.TreeExplainer(_model)


# ══════════════════════════════════════════════════════════════════════════════
# 4. Static & Reference Benchmarks (st.cache_data)
# ══════════════════════════════════════════════════════════════════════════════

@st.cache_data(show_spinner=False)
def get_cached_cohort_averages(occupation: str) -> Dict[str, float]:
    """
    Caches aggregate, anonymous cohort spending averages by occupation.
    Safe: aggregate statistics only, key explicitly depends on occupation string.
    """
    from database.db_manager import DBManager
    return DBManager.get_cohort_averages(occupation)


@st.cache_data(show_spinner=False)
def get_cached_cluster_benchmarks() -> pd.DataFrame:
    """
    Caches the aggregate cluster benchmarks table from cluster_benchmarks.json.
    """
    from models.clustering import FinancialPersonalityClusterer
    return FinancialPersonalityClusterer.load_saved_cluster_benchmarks()
