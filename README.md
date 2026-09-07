<div align="center">

<img src="assets/logos/1_horizontal.svg" alt="FinTwin AI" width="360"/>

# FinTwin AI
### Your Financial Life, Simulated.

**An AI-powered financial digital twin that scores your financial health, forecasts your wealth, optimizes your taxes, and coaches your behavior — purpose-built for Indian salaried professionals aged 22–40.**

[![Python](https://img.shields.io/badge/Python-3.9+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.35+-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white)](https://streamlit.io)
[![XGBoost](https://img.shields.io/badge/XGBoost-ML%20Engine-F7931E?style=for-the-badge)](https://xgboost.readthedocs.io)
[![SHAP](https://img.shields.io/badge/SHAP-Explainable%20AI-7C3AED?style=for-the-badge)](https://shap.readthedocs.io)
[![SQLite](https://img.shields.io/badge/SQLite-Database-003B57?style=for-the-badge&logo=sqlite&logoColor=white)](https://sqlite.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-00A86B?style=for-the-badge)](LICENSE)
[![Status](https://img.shields.io/badge/Status-In%20Progress-F59E0B?style=for-the-badge)](#)

[Overview](#overview) • [Features](#dashboard-modules) • [How It Works](#how-it-works) • [Getting Started](#getting-started) • [Demo](#demo-login) • [Roadmap](#roadmap)

</div>

---

## Overview

FinTwin AI builds a living, data-driven model — a **digital twin** — of a user's financial life. It combines gradient-boosted forecasting, unsupervised behavior clustering, and explainable AI to turn raw income, expense, debt, and goal data into a single, actionable financial health picture.

Instead of static budgeting spreadsheets, FinTwin AI answers the questions people actually ask:

- *"How financially healthy am I, really?"*
- *"What happens to my net worth if I switch jobs, take a loan, or have a child?"*
- *"Old tax regime or new — which saves me more this year?"*
- *"Am I spending more than people like me?"*

---

## How It Works

FinTwin AI runs in two clearly separated phases, so the live app never touches raw training data — only pre-trained, versioned model artifacts.

### Phase 1 — Offline Training *(run once)*
Synthetic profiles are generated, engineered into features, and used to train the forecasting, clustering, and explainability models. Outputs are serialized to `data/models/`.

<p align="center">
  <img src="assets/phase1_training_diagram.png" alt="Phase 1 — Offline Training Pipeline" width="720"/>
</p>

### Phase 2 — Live Dashboard *(runtime)*
The Streamlit app loads only the pre-trained model artifacts to score, forecast, and coach in real time — no raw data dependency, fast cold starts, and reproducible results.

<p align="center">
  <img src="assets/phase2_live_dashboard_diagram.png" alt="Phase 2 — Live Dashboard Runtime" width="720"/>
</p>

> **Note:** Raw training data is never accessed by the live app. Only pre-trained JSON model files are loaded at runtime.

---

## Dashboard Modules

| Module | What it does |
|---|---|
| **Digital Twin** | Builds a structured financial profile — income, assets, debts, and goals |
| **Financial Health** | Produces a 0–100 health score with SHAP-powered, human-readable explanations |
| **Forecast & Simulation** | Runs 10-year what-if projections using XGBoost-based forecasting models |
| **Spending Behavior** | Benchmarks spending patterns against occupation-matched peer cohorts |
| **Tax Intelligence** | Instantly compares Old vs. New tax regimes to find the optimal choice |
| **Goal Planner** | Tracks progress toward milestones — home, education, retirement |
| **AI Behavioral Coach** | Delivers advice tailored to the user's detected financial personality type |

---

## Financial Health Score

The headline **0–100 score** is a weighted composite of six underlying financial metrics:

| Metric | Benchmark | Weight |
|---|---|---|
| Savings Rate | ≥ 30% of income | 25% |
| EMI Burden | ≤ 35% of income | 20% |
| Emergency Fund | ≥ 6 months of expenses | 20% |
| SIP Investment | ≥ 15% of income | 15% |
| Insurance Coverage | Life ≥ 120× salary · Health ≥ ₹5L | 10% |
| Debt-to-Income Ratio | Total debt ≤ 1.5× annual income | 10% |

**Grade scale:** `A` 80–100 &nbsp;·&nbsp; `B` 60–79 &nbsp;·&nbsp; `C` 40–59 &nbsp;·&nbsp; `D` below 40

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend / App | Streamlit |
| ML — Forecasting | XGBoost |
| ML — Explainability | SHAP |
| ML — Behavior Segmentation | K-Means Clustering |
| Data Layer | SQLite |
| Visualization | Plotly |
| LLM / Coaching | Groq API |

---

## Project Structure

```
FinTwin_AI/
├── app.py                    # Streamlit entry point & dashboard landing page
├── config.py                 # Tax slabs, economic constants, score weights
├── requirements.txt          # Python dependencies
│
├── training/
│   └── train_offline.py      # Run this FIRST — trains all ML models
│
├── data/
│   ├── generator.py          # Generates 10,000 synthetic Indian profiles
│   ├── preprocessor.py       # Feature engineering pipeline
│   └── models/                # Saved model artifacts (.json)
│
├── models/
│   ├── twin_engine.py        # Digital Twin object model + health score formulas
│   ├── predictor.py          # XGBoost savings & net worth forecaster
│   ├── clustering.py         # K-Means financial personality detector
│   └── explainability.py     # SHAP explainer computations
│
├── utils/
│   ├── tax_calculator.py     # Indian tax engine (Old vs. New regime)
│   ├── simulator.py          # What-if scenario simulation engine
│   ├── coach.py              # Personality-driven AI recommendations
│   └── visualizer.py         # Plotly chart template builders
│
├── database/
│   ├── schema.sql            # Table & constraint definitions
│   ├── db_manager.py         # CRUD operations (profiles, goals, ledger)
│   └── financial_twin.db     # SQLite database file
│
└── pages/
    ├── 01_Digital_Twin.py
    ├── 02_Financial_Health.py
    ├── 03_Behavior_Analysis.py
    ├── 04_Financial_Personality.py
    ├── 05_Forecasting.py
    ├── 06_Scenario_Simulator.py
    ├── 07_Tax_Intelligence.py
    ├── 08_AI_Coach.py
    ├── 09_Goal_Planner.py
    ├── 10_Explainable_AI.py
    └── 11_Settings.py
```

---

## Getting Started

### Prerequisites
- Python 3.9+
- A [Groq API key](https://console.groq.com) for the AI coaching module

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/AlokRana01/FinTwin-AI.git
cd FinTwin-AI

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment variables
cp .env.example .env
# Add your GROQ_API_KEY (and optional SMTP credentials) to .env

# 4. (Optional) Retrain models — pre-trained weights are already included
# python data/generator.py
# python training/train_offline.py

# 5. Launch the dashboard
streamlit run app.py
```

The app will be available at `http://localhost:8501`.

---

## Demo Login

Try FinTwin AI instantly with the pre-seeded demo account:

| Field | Value |
|---|---|
| Email | `demo@fintwin.app` |
| Password | `Demo@123` |

---

## Roadmap

- [ ] Multi-currency support beyond INR
- [ ] Mobile-responsive dashboard layout
- [ ] Bank statement auto-import (PDF/CSV parsing)
- [ ] Portfolio-level investment tracking
- [ ] Exportable PDF financial health reports

---

## Contributing

Contributions, issues, and feature requests are welcome. If you'd like to contribute:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/your-feature`)
3. Commit your changes
4. Open a pull request

---

## License

This project is licensed under the **MIT License** — see [LICENSE](LICENSE) for details.

<div align="center">

Copyright © 2026 **Alok Rana**

<sub>Built for a smarter, more transparent approach to personal finance.</sub>

</div>
