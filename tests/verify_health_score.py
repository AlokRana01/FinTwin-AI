import os
import sys
from pathlib import Path

# Configure utf-8 output for Windows console
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Add project root directory to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from database.connection import init_db
from database.db_manager import DBManager
from models.twin_engine import FinancialDigitalTwin, HealthScoreEngine

def main():
    print("=== RUNNING HEALTH SCORE ENGINE VERIFICATION ===")
    
    # 1. Initialize and seed DB
    print("Initializing and seeding SQLite database...")
    init_db()
    
    # 2. Query all users and get sample user ID
    users = DBManager.get_all_users()
    assert len(users) > 0, "No users found in database after seeding!"
    print(f"Loaded {len(users)} users successfully from DB.")
    
    sample_user = users[0]
    sample_user_id = sample_user["user_id"]
    print(f"Sample User: {sample_user['name']} ({sample_user_id})")
    
    # 3. Load twin
    demographics = DBManager.get_user_profile(sample_user_id)
    balance_sheet = DBManager.get_digital_twin(sample_user_id)
    
    assert demographics is not None, "Demographics failed to load!"
    assert balance_sheet is not None, "Balance sheet failed to load!"
    print("[PASS] User demographics and balance sheet loaded.")
    
    # 4. Construct twin and compute score
    twin = FinancialDigitalTwin(sample_user_id, demographics, balance_sheet)
    engine = HealthScoreEngine(twin)
    score_data = engine.compute_overall_health_score()
    
    print("\nScore Results:")
    print(f"Overall Score: {score_data['overall_score']}")
    print(f"Grade: {score_data['financial_grade']}")
    print("Components:")
    for k, v in score_data["components"].items():
        print(f" - {k}: Score={v['score']}, Raw={v['raw_value']}{v['unit']}, Benchmark={v['benchmark']}")
        
    assert 0 <= score_data["overall_score"] <= 100, f"Score {score_data['overall_score']} out of bounds!"
    assert score_data["financial_grade"] in ["A", "B", "C", "D"], f"Invalid grade {score_data['financial_grade']}!"
    
    # 5. Cohort verification
    cohort = DBManager.get_cohort_averages(twin.occupation)
    assert len(cohort) > 0, "Cohort averages failed to load!"
    print(f"\nCohort Averages for {twin.occupation}:")
    for k, v in cohort.items():
        if v is not None:
            print(f" - Average {k}: ₹{v:,.2f}")
        else:
            print(f" - Average {k}: None")
        
    print("\n[SUCCESS] Health Score Engine verified successfully!")

if __name__ == "__main__":
    main()
