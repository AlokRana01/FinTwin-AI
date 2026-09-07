"""
Pipeline Verification Script
Loads the raw dataset, runs it through the preprocessing pipeline, 
and validates that the output matches all requirements.
"""

import os
import sys
from pathlib import Path
import pandas as pd
import numpy as np

# Add project root directory to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from data.preprocessor import DataPreprocessor

def main():
    print("=== Financial Feature Engineering Pipeline Verification ===")
    
    # 1. Load raw dataset
    data_path = BASE_DIR / "data" / "raw" / "indian_salaried_financial_data.csv"
    if not data_path.exists():
        raise FileNotFoundError(f"Raw data file not found at {data_path}")
    
    print(f"Loading raw dataset from {data_path}...")
    df_raw = pd.read_csv(data_path)
    print(f"Raw dataset shape: {df_raw.shape}")
    
    # Intentionally inject some missing values to test the imputer
    print("Injecting sample NaN values for testing imputer...")
    df_raw.loc[0, "Monthly_Income"] = np.nan
    df_raw.loc[1, "City"] = np.nan
    df_raw.loc[2, "Emergency_Fund"] = np.nan
    
    # 2. Build preprocessing pipeline
    print("Building preprocessing pipeline...")
    pipeline = DataPreprocessor.build_preprocessing_pipeline()
    
    # 3. Fit and transform the dataset
    print("Running fit_transform on the raw dataset...")
    df_clean = pipeline.fit_transform(df_raw)
    
    # 4. Perform Verifications
    print("\nRunning validations...")
    
    # Check A: Correct output type
    assert isinstance(df_clean, pd.DataFrame), "Output is not a pandas DataFrame!"
    print("[PASS] Output is a pandas DataFrame.")
    
    # Check B: No missing values
    null_count = df_clean.isnull().sum().sum()
    assert null_count == 0, f"Clean DataFrame contains {null_count} null/missing values!"
    print("[PASS] Zero missing values in the clean DataFrame.")
    
    # Check C: Check shape and columns
    print(f"Clean DataFrame shape: {df_clean.shape}")
    
    # Check D: Engineered features are present and scaled (prefixed by num__)
    expected_engineered_metrics = [
        "num__Savings_Ratio", 
        "num__Expense_Ratio", 
        "num__Debt_To_Income_Ratio", 
        "num__Investment_Ratio",
        "num__Emergency_Fund_Coverage", 
        "num__Net_Worth", 
        "num__Insurance_Coverage_Score"
    ]
    
    for metric in expected_engineered_metrics:
        assert metric in df_clean.columns, f"Engineered metric {metric} is missing from clean columns!"
    print("[PASS] All 7 engineered metrics are present in the output.")
    
    # Check E: No identifier columns like User_ID or Name
    for col in df_clean.columns:
        assert "User_ID" not in col and "Name" not in col, f"Identifier column found in output: {col}"
    print("[PASS] Unique identifiers (User_ID, Name) have been successfully dropped.")
    
    # Check F: One-hot encoded categorical columns are present
    cat_columns = [col for col in df_clean.columns if col.startswith("cat__")]
    assert len(cat_columns) > 0, "No categorical columns were encoded!"
    print(f"[PASS] Found {len(cat_columns)} one-hot encoded categorical features.")
    
    # Check G: Numeric columns are scaled (mean close to 0, std close to 1)
    num_columns = [col for col in df_clean.columns if col.startswith("num__")]
    mean_of_means = df_clean[num_columns].mean().mean()
    mean_of_stds = df_clean[num_columns].std().mean()
    print(f"Average mean of numerical columns: {mean_of_means:.6f}")
    print(f"Average std of numerical columns: {mean_of_stds:.6f}")
    assert abs(mean_of_means) < 0.1, f"Features not scaled to mean=0: {mean_of_means}"
    assert abs(mean_of_stds - 1.0) < 0.1, f"Features not scaled to std=1: {mean_of_stds}"
    print("[PASS] Numeric features are correctly scaled.")
    
    # Check H: Outliers are clipped
    max_val = df_clean[num_columns].max().max()
    min_val = df_clean[num_columns].min().min()
    print(f"Max scaled value: {max_val:.4f}, Min scaled value: {min_val:.4f}")
    assert max_val < 6.0 and min_val > -6.0, "Outliers might not be clipped correctly!"
    print("[PASS] Outlier clipping verifies successfully.")
    
    print("\nSample processed rows (first 3):")
    print(df_clean[expected_engineered_metrics].head(3))
    
    print("\nAll preprocessing pipeline tests passed successfully!")

if __name__ == "__main__":
    main()
