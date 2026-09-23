# Software Requirements Specification (SRS)
## Project Name: FinTwin AI
### Document Identifier: SRS-FTW-2026-V1.0 | Status: Baseline Approved

---

## 1. Introduction

### 1.1 Purpose
This document provides a complete and formal specification of the software requirements for **FinTwin AI**, an AI-powered financial digital twin platform. It details functional and non-functional requirements, data schemas, business rules, validation constraints, security mechanisms, and testable acceptance criteria for engineering, quality assurance, and product validation.

### 1.2 Scope of the System
FinTwin AI captures a user's complete financial profile (income, expenditure, debt obligations, liquid reserves, mutual fund investments, and insurance policies), computes an explainable 0–100 Financial Health Score, executes machine learning-based 10-year wealth forecasting (XGBoost), conducts peer cohort behavioral segmentation (K-Means), compares Indian tax regimes (Old vs. New Section 115BAC), runs what-if economic scenario simulations, and offers conversational behavioral coaching via LLM integrations.

### 1.3 Definitions, Acronyms, and Abbreviations
- **SRS:** Software Requirements Specification
- **DTI:** Debt-to-Income Ratio
- **EMI:** Equated Monthly Installment
- **SIP:** Systematic Investment Plan
- **SHAP:** SHapley Additive exPlanations
- **XAI:** Explainable Artificial Intelligence
- **XGBoost:** eXtreme Gradient Boosting
- **HRA:** House Rent Allowance
- **Section 115BAC:** New Default Tax Regime under Indian Income Tax Act, 1961

---

## 2. User Roles & Access Permissions

| Role | Role Description | Permissions & Boundaries |
|---|---|---|
| **Visitor / Guest** | Unauthenticated user visiting landing page | Can view landing page, high-level feature overviews, and sample screenshots. Cannot view or create financial data. |
| **Demo User** | User logging in via pre-seeded demo credentials (`demo@fintwin.app`) | Has full read-write access to a persistent sandbox profile. Can modify profile numbers, run simulations, view scores, and execute coaching. |
| **Registered User** | Authenticated salaried professional | Isolated access strictly to their own user profile, financial records, goals, and simulation history. Zero cross-tenant data leakage. |
| **System / Admin** | Backend runtime operator | CLI access for model training (`train_offline.py`), database migrations, synthetic data generation, and environment configuration. |

---

## 3. Business Rules & Computational Models

### 3.1 BR-01: Financial Health Score Formulation
The composite Financial Health Score is computed on a scale of **0 to 100**, aggregated through six weighted sub-metrics:

$$\text{Health Score} = \sum_{i=1}^{6} (S_i \times W_i)$$

Where each component score $S_i \in [0, 100]$ is computed against benchmark thresholds:

| Component Metric | Calculation Formula | Benchmark Threshold | Weight ($W_i$) |
|---|---|---|---|
| **Savings Rate Score** | $\min(100, \frac{\text{Monthly Savings}}{\text{Monthly Income}} \times \frac{100}{30\%})$ | Savings Rate $\ge 30\%$ of Gross Income | **25%** |
| **EMI Burden Score** | $\max(0, 100 - \frac{\text{Total Monthly EMIs}}{\text{Monthly Income}} \times \frac{100}{35\%})$ | EMI Burden $\le 35\%$ of Gross Income | **20%** |
| **Emergency Fund Score**| $\min(100, \frac{\text{Liquid Savings}}{\text{Monthly Expenses}} \times \frac{100}{6})$ | Liquid Funds $\ge 6$ months of Expenses | **20%** |
| **SIP Allocation Score**| $\min(100, \frac{\text{Monthly SIP}}{\text{Monthly Income}} \times \frac{100}{15\%})$ | Monthly SIP $\ge 15\%$ of Gross Income | **15%** |
| **Insurance Score** | $50 \times \text{TermFlag} + 50 \times \text{HealthFlag}$ | Term Life $\ge 120\times$ monthly salary; Health $\ge ₹5,00,000$ | **10%** |
| **Debt-to-Income Score**| $\max(0, 100 - \frac{\text{Total Outstanding Debt}}{\text{Annual Income} \times 1.5} \times 100)$ | Total Debt $\le 1.5\times$ Annual Gross Income | **10%** |

#### Grade Boundaries:
- **Grade A (80.0 – 100.0):** Excellent financial health and resilient safety net.
- **Grade B (60.0 – 79.9):** Good health; moderate improvements needed in insurance or investments.
- **Grade C (40.0 – 59.9):** Vulnerable; excessive debt or inadequate liquid emergency cushion.
- **Grade D (0.0 – 39.9):** Critical stress; urgent debt restructuring or budget reduction needed.

### 3.2 BR-02: Indian Income Tax Engine (Old vs. New Regime)
The tax engine evaluates annual tax liability under both Indian tax frameworks:
- **New Tax Regime (Section 115BAC, FY 2024-25 / 2025-26):**
  - Standard deduction of ₹75,000 for salaried employees.
  - Slabs: Up to ₹3L: 0%; ₹3L–₹7L: 5%; ₹7L–₹10L: 10%; ₹10L–₹12L: 15%; ₹12L–₹15L: 20%; Above ₹15L: 30%.
  - Full tax rebate under Section 87A if taxable income does not exceed ₹7,00,000.
  - Health & Education Cess: 4% applied to net computed tax.
- **Old Tax Regime:**
  - Standard deduction of ₹50,000.
  - Slabs: Up to ₹2.5L: 0%; ₹2.5L–₹5L: 5%; ₹5L–₹10L: 20%; Above ₹10L: 30%.
  - Deductions supported: Section 80C (max ₹1.5L), Section 80D (Health Insurance max ₹25,000/₹50,000), Section 24(b) (Home loan interest max ₹2L), Section 80CCD(1B) (NPS max ₹50,000), Section 10(13A) (HRA exemption).
  - Rebate under Section 87A if taxable income $\le ₹5,00,000$.

### 3.3 BR-03: Multi-Year Wealth Forecasting Formula
Projections use XGBoost regression models trained on multi-decade trajectories with macroeconomic parameters:
- Baseline annual salary escalation: default 8% p.a.
- Consumer Price Index (CPI) inflation: default 6% p.a.
- Equity/SIP compounded return: default 12% p.a.
- Debt/Liquid interest return: default 6.5% p.a.

---

## 4. Functional Requirements

### 4.1 Module 1: User Authentication & Profile (FR-AUTH)
- **FR-AUTH-01:** System shall permit users to register with an email address and strong password (minimum 8 characters with at least one number and special character).
- **FR-AUTH-02:** System shall securely hash passwords using PBKDF2/SHA256 with per-user cryptographic salts prior to database storage.
- **FR-AUTH-03:** System shall provide one-click login for pre-seeded demo user (`demo@fintwin.app`).
- **FR-AUTH-04:** System shall maintain session state in `st.session_state` preventing unauthenticated access to pages `01_Digital_Twin.py` through `11_Settings.py`.

### 4.2 Module 2: Digital Twin Profile Management (FR-TWIN)
- **FR-TWIN-01:** System shall record and update user financial parameters:
  - Monthly Gross Salary (INR)
  - Monthly Mandatory Expenses (Rent, Utilities, Food)
  - Discretionary Expenses (Dining, Entertainment, Shopping)
  - Active Monthly EMIs (Home loan, Auto loan, Personal loan)
  - Total Liquid Savings (Savings bank, Liquid Mutual Funds, FDs)
  - Total Outstanding Debt Principle
  - Monthly SIP Investments
  - Term Life Coverage Sum Assured (INR)
  - Health Insurance Policy Sum Insured (INR)
- **FR-TWIN-02:** When saving profile updates, the database record shall update immediately and trigger recalculation of the 0–100 health score.

### 4.3 Module 3: Financial Health & Explainability (FR-HLTH & FR-XAI)
- **FR-HLTH-01:** System shall compute the 0–100 score and assign grade A, B, C, or D in accordance with BR-01.
- **FR-HLTH-02:** System shall render visual gauge charts with color-coded status bands (Green: A, Blue: B, Yellow: C, Red: D).
- **FR-XAI-01:** System shall utilize TreeSHAP algorithms against pre-trained score models to compute SHAP values for each input metric.
- **FR-XAI-02:** System shall render a Waterfall Plot indicating the base value, positive metric lifts, and negative drags.
- **FR-XAI-03:** System shall generate natural-language bullet points translating SHAP values (e.g., *"Your high EMI burden of 42% reduced your score by 14 points"*).

### 4.4 Module 4: 10-Year Wealth Forecast & Simulation (FR-SIM)
- **FR-SIM-01:** System shall load pre-trained XGBoost regression artifacts (`data/models/forecast_model.json`) at runtime without reading training raw data.
- **FR-SIM-02:** System shall forecast year-by-year net worth for years $t \in [1, 10]$.
- **FR-SIM-03:** System shall provide interactive sliders allowing users to simulate:
  - Annual salary increment (0% to 25%)
  - Planned additional monthly EMI (₹0 to ₹1,50,000)
  - Expected market equity returns (6% to 18%)
  - Inflation rate fluctuations (4% to 10%)
- **FR-SIM-04:** System shall render side-by-side Plotly line charts displaying "Baseline Net Worth" vs. "Simulated Net Worth".

### 4.5 Module 5: Spending Behavior & Peer Clustering (FR-CLUST)
- **FR-CLUST-01:** System shall load pre-trained K-Means clustering artifacts (`data/models/cluster_model.json`) and scaler.
- **FR-CLUST-02:** System shall map user spending and saving ratios to the closest centroid and assign one of four archetypes:
  1. *Disciplined Accumulator* (High savings, balanced debt)
  2. *Over-Leveraged Spender* (High EMIs, low emergency runway)
  3. *Conservative Stagnator* (High cash savings, low equity investment)
  4. *Lifestyle Inflator* (High discretionary expenses, volatile savings)
- **FR-CLUST-03:** System shall present a Radar Chart benchmarking the user against their demographic cohort average.

### 4.6 Module 6: Indian Tax Intelligence (FR-TAX)
- **FR-TAX-01:** System shall take user inputs for gross annual income, 80C investments, 80D health premiums, 24(b) home loan interest, and NPS contributions.
- **FR-TAX-02:** System shall compute net tax liability under both Old and New Tax Regimes according to BR-02.
- **FR-TAX-03:** System shall compute difference $\Delta_{\text{tax}} = \text{Tax}_{\text{Old}} - \text{Tax}_{\text{New}}$ and output a explicit badge: `"Switch to New Regime — Save ₹X"` or `"Retain Old Regime — Save ₹Y"`.

### 4.7 Module 7: AI Behavioral Coach (FR-COACH)
- **FR-COACH-01:** System shall integrate with Groq Cloud API using model `llama-3-70b-versatile` or `llama3-8b-8192`.
- **FR-COACH-02:** System shall construct prompts incorporating the user's financial archetype, health score, and top 2 weakness metrics without exposing personally identifiable information (PII).
- **FR-COACH-03:** System shall enforce a maximum response length of 150 words per coaching tip to maintain conciseness.
- **FR-COACH-04:** If Groq API key is missing or calls time out (>4 seconds), the system shall trigger the local rule-based fallback coaching module seamlessly.

### 4.8 Module 8: Goal Milestone Planner (FR-GOAL)
- **FR-GOAL-01:** System shall permit users to create financial goals (Goal Name, Target Amount, Target Year).
- **FR-GOAL-02:** System shall calculate required monthly SIP assuming standard 12% compound annual growth rate (CAGR).
- **FR-GOAL-03:** System shall mark goal status as:
  - *On Track:* Required monthly SIP $\le$ current monthly savings.
  - *At Risk:* Required monthly SIP exceeds current savings by $<30\%$.
  - *Off Track:* Required monthly SIP exceeds current savings by $\ge 30\%$.

---

## 5. Data Requirements & Database Schema

### 5.1 Relational Schema (SQLite 3)
```sql
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS profiles (
    user_id INTEGER PRIMARY KEY,
    full_name TEXT,
    age INTEGER CHECK(age >= 18 AND age <= 75),
    occupation TEXT,
    monthly_income REAL CHECK(monthly_income > 0),
    living_expenses REAL DEFAULT 0,
    discretionary_expenses REAL DEFAULT 0,
    monthly_emi REAL DEFAULT 0,
    liquid_savings REAL DEFAULT 0,
    total_debt REAL DEFAULT 0,
    monthly_sip REAL DEFAULT 0,
    term_insurance_cover REAL DEFAULT 0,
    health_insurance_cover REAL DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS goals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    goal_name TEXT NOT NULL,
    target_amount REAL NOT NULL CHECK(target_amount > 0),
    target_years INTEGER NOT NULL CHECK(target_years >= 1),
    priority TEXT CHECK(priority IN ('High', 'Medium', 'Low')),
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS simulation_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    simulation_name TEXT,
    parameters_json TEXT NOT NULL,
    projected_net_worth_10y REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
```

### 5.2 Input Validation Rules & Boundary Conditions

| Field | Minimum Value | Maximum Value | Constraint / Validation Rule |
|---|---|---|---|
| `monthly_income` | ₹10,000 | ₹50,00,000 | Must be positive non-zero |
| `living_expenses` | ₹0 | `monthly_income` | Cannot exceed gross monthly income |
| `monthly_emi` | ₹0 | `monthly_income` | Warning triggered if $\text{EMI} > 50\%$ income |
| `liquid_savings` | ₹0 | ₹10,00,00,000 | Non-negative numeric float |
| `total_debt` | ₹0 | ₹50,00,00,000 | Non-negative numeric float |
| `monthly_sip` | ₹0 | `monthly_income` | Cannot exceed net savings capacity |
| `age` | 18 | 75 | Enforced integer range |

---

## 6. Non-Functional Requirements (NFR)

### 6.1 Performance Requirements
- **NFR-PERF-01:** Digital Twin health score and SHAP recalculations must execute within **400ms**.
- **NFR-PERF-02:** Local Streamlit page re-render latency shall not exceed **1.2 seconds**.
- **NFR-PERF-03:** Database reads and updates against SQLite must complete in under **30ms**.

### 6.2 Security & Data Privacy
- **NFR-SEC-01:** Passwords stored must never be in plaintext. Passwords must be hashed using salt + hash algorithms.
- **NFR-SEC-02:** Multi-tenant data isolation: all SQL queries must filter strictly on `session_state.user_id`.
- **NFR-SEC-03:** AI Coaching calls to Groq API must strictly exclude user email, name, phone, or raw account IDs. Only sanitized ratios and metric differentials are transmitted.
- **NFR-SEC-04:** API keys (`GROQ_API_KEY`) must be loaded strictly from local `.env` or system environment variables, never hardcoded into source repositories.

### 6.3 Reliability & Fault Tolerance
- **NFR-REL-01:** If machine learning model artifacts are absent, the system shall fail gracefully with a descriptive error prompt directing the administrator to run `training/train_offline.py`.
- **NFR-REL-02:** In the event of network disruption or Groq API quota exhaustion, the chatbot must fall back to the built-in rule-based heuristics engine without unhandled exceptions.

### 6.4 Maintainability & Extensibility
- **NFR-MNT-01:** Modular codebase architecture: all tax constants, tax slabs, and scoring weights must be centralized in `config.py`.
- **NFR-MNT-02:** Machine learning models must be serialized in human-readable JSON formats (`.json`) for cross-platform compatibility and zero binary pickle deserialization vulnerabilities.

---

## 7. Edge Cases & Exception Handling

| Edge Case Scenario | Expected System Behavior |
|---|---|
| **Zero Income Entered** | Form validation halts submission with inline prompt: *"Monthly gross income must be greater than zero."* |
| **Zero Expenses & Zero EMI** | Health score calculates savings rate at 100%; division-by-zero guard returns emergency fund adequacy capped at 100%. |
| **Total Debt Exceeds 10x Annual Income** | Debt-to-Income sub-score evaluates to 0.0; warning banner flags high bankruptcy vulnerability. |
| **Groq API Rate Limit (HTTP 429)** | Catch block intercepts error, logs warning, and delivers immediate rule-based coaching recommendation with an offline indicator. |
| **Negative Input Values** | Client-side and database-level `CHECK` constraints prevent negative values, auto-resetting input fields to zero. |

---

## 8. Verification & Acceptance Criteria Matrix

| Requirement ID | Verification Method | Pass Criteria |
|---|---|---|
| **FR-AUTH-01 / 03** | Automated integration test | Demo login succeeds; unauthorized page view redirects to login prompt. |
| **FR-HLTH-01 / BR-01** | Unit test with known vectors | Given known income/expense profile, Health Score matches expected integer within $\pm 0.1$. |
| **FR-TAX-01 / 02** | Unit test with tax cases | Old vs. New tax calculations match official Income Tax Department utility numbers for test incomes (₹7.5L, ₹15L, ₹25L). |
| **FR-SIM-01 / 02** | End-to-end regression test | 10-year array returns exactly 10 positive floating-point values without NaN or infinite values. |
| **NFR-SEC-03** | Payload inspection test | Groq outbound request JSON contains no occurrences of `user_id`, `email`, or `full_name`. |
