"""
SIH26192 - Track 2: Model training + evaluation
=================================================
Input:  combined_training_table.csv (from Track 1)
Target: severity_ratio = peak_level / danger_level
Model:  XGBoost regression

Non-negotiables from the shared team context:
  - Group-aware CV by station_id (this is what caught the earlier fake R²=+ result;
    a random split leaks station identity and looks great for the wrong reason)
  - Report MAE vs. a "predict the mean" baseline, and R²
  - Report metrics SEPARATELY for official-threshold stations vs. percentile-proxy stations,
    since those two groups are not measuring severity against the same kind of yardstick

Output:
  - printed honest metrics report (overall + split by threshold_source)
  - flood_model.joblib: model refit on ALL data, for Track 4 to load
  - feature_importance.csv
"""

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold
from sklearn.metrics import mean_absolute_error, r2_score
from xgboost import XGBRegressor
import joblib

IN_PATH = "/mnt/user-data/outputs/combined_training_table.csv"
MODEL_OUT = "/mnt/user-data/outputs/flood_model.joblib"
IMPORTANCE_OUT = "/mnt/user-data/outputs/feature_importance.csv"

# ---------------------------------------------------------------------------
# 1. Load + define target / leakage exclusions
# ---------------------------------------------------------------------------
df = pd.read_csv(IN_PATH, low_memory=False)

TARGET = "severity_ratio"

# Columns that must NOT be features: identifiers, dates, reporting-only columns,
# and anything that peak_level/danger_level were literally computed from (pure leakage).
EXCLUDE = {
    "event_id", "source", "threshold_source", "station_id", "station_name",
    "state_or_region", "peak_date", TARGET,
    "peak_level", "danger_level",              # target = peak_level / danger_level -> leakage if kept
    "catchment__Start_date", "catchment__End_date",  # dataset coverage metadata, not per-event
}

feature_cols = [c for c in df.columns if c not in EXCLUDE]

X = df[feature_cols].copy()
y = df[TARGET].copy()
groups = df["station_id"].copy()

# XGBoost's native categorical support handles the remaining object columns
# (season, warning_level is numeric already, catchment__KoppenGeiger, Land cover,
# Soil type, lithology type, Flood Type, Privacy, Reliability, etc.)
cat_cols = X.select_dtypes(include=["object"]).columns.tolist()
for c in cat_cols:
    X[c] = X[c].astype("category")

print(f"Rows: {len(X)} | Features: {len(feature_cols)} | Categorical: {len(cat_cols)}")
print(f"Stations (groups): {groups.nunique()}")

# Diagnosis (see conversation): the earlier deeper model didn't overfit broadly -
# individual unseen stations in each fold got wildly extrapolated predictions
# (e.g. one station predicted ~1.6 when every event there was ~1.0), which
# dominates R2 even though most predictions were fine. Fix: heavier regularization
# so trees can't carve out narrow leaves that misfire on unfamiliar stations, plus
# a physically-sane clip on the output as a safety net against extrapolation blowups.
MODEL_PARAMS = dict(
    n_estimators=300,
    max_depth=3,
    learning_rate=0.03,
    subsample=0.7,
    colsample_bytree=0.6,
    min_child_weight=15,
    reg_lambda=8.0,
    reg_alpha=1.0,
    tree_method="hist",
    enable_categorical=True,
    random_state=42,
)
# clip bounds from the 1st/99th percentile of observed severity_ratio - a model
# predicting outside this range for a "typical" flood event is extrapolating, not learning
CLIP_LO, CLIP_HI = y.quantile(0.01), y.quantile(0.99)
print(f"Prediction clip bounds: [{CLIP_LO:.3f}, {CLIP_HI:.3f}]")

# ---------------------------------------------------------------------------
# 2. Group-aware cross-validation
# ---------------------------------------------------------------------------
N_SPLITS = 5
gkf = GroupKFold(n_splits=N_SPLITS)

fold_rows = []
oof_pred = np.full(len(X), np.nan)

for fold, (train_idx, test_idx) in enumerate(gkf.split(X, y, groups)):
    X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
    y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]

    model = XGBRegressor(**MODEL_PARAMS)
    model.fit(X_train, y_train)
    preds = np.clip(model.predict(X_test), CLIP_LO, CLIP_HI)
    oof_pred[test_idx] = preds

    baseline_pred = np.full_like(y_test, fill_value=y_train.mean(), dtype=float)

    mae_model = mean_absolute_error(y_test, preds)
    mae_baseline = mean_absolute_error(y_test, baseline_pred)
    r2_model = r2_score(y_test, preds)

    fold_rows.append(dict(
        fold=fold, n_test=len(test_idx),
        n_stations_test=groups.iloc[test_idx].nunique(),
        mae_model=mae_model, mae_baseline=mae_baseline, r2_model=r2_model,
    ))
    print(f"Fold {fold}: n_test={len(test_idx)} stations_test={groups.iloc[test_idx].nunique()} "
          f"MAE_model={mae_model:.4f} MAE_baseline={mae_baseline:.4f} R2={r2_model:.4f}")

fold_df = pd.DataFrame(fold_rows)

print("\n=== OVERALL (mean across folds) ===")
print(fold_df[["mae_model", "mae_baseline", "r2_model"]].mean().to_string())

# ---------------------------------------------------------------------------
# 3. Honest metrics split by threshold_source, using out-of-fold predictions
# ---------------------------------------------------------------------------
print("\n=== SPLIT BY THRESHOLD SOURCE (out-of-fold predictions) ===")
report_df = df[["threshold_source"]].copy()
report_df["y_true"] = y.values
report_df["y_pred"] = oof_pred
report_df["y_pred_baseline"] = y.mean()  # global mean baseline for comparison here

for group_name, sub in report_df.groupby("threshold_source"):
    sub = sub.dropna(subset=["y_pred"])
    if len(sub) == 0:
        continue
    mae_m = mean_absolute_error(sub["y_true"], sub["y_pred"])
    mae_b = mean_absolute_error(sub["y_true"], sub["y_pred_baseline"])
    r2_m = r2_score(sub["y_true"], sub["y_pred"])
    print(f"  {group_name:20s} n={len(sub):5d}  MAE_model={mae_m:.4f}  "
          f"MAE_baseline={mae_b:.4f}  R2={r2_m:.4f}")

# Also split by source (INDOFLOODS vs CWC) since they differ in which features are populated
print("\n=== SPLIT BY DATA SOURCE (out-of-fold predictions) ===")
report_df["source"] = df["source"].values
for group_name, sub in report_df.groupby("source"):
    sub = sub.dropna(subset=["y_pred"])
    if len(sub) == 0:
        continue
    mae_m = mean_absolute_error(sub["y_true"], sub["y_pred"])
    mae_b = mean_absolute_error(sub["y_true"], sub["y_pred_baseline"])
    r2_m = r2_score(sub["y_true"], sub["y_pred"])
    print(f"  {group_name:20s} n={len(sub):5d}  MAE_model={mae_m:.4f}  "
          f"MAE_baseline={mae_b:.4f}  R2={r2_m:.4f}")

# ---------------------------------------------------------------------------
# 4. Refit on ALL data for deployment, save model + feature importance
# ---------------------------------------------------------------------------
final_model = XGBRegressor(**MODEL_PARAMS)
final_model.fit(X, y)
joblib.dump({
    "model": final_model, "feature_cols": feature_cols, "cat_cols": cat_cols,
    "clip_lo": CLIP_LO, "clip_hi": CLIP_HI,  # Track 4: clip predictions to this range too
}, MODEL_OUT)
print(f"\nSaved final model (fit on all {len(X)} rows) to {MODEL_OUT}")

importance = pd.Series(final_model.feature_importances_, index=feature_cols).sort_values(ascending=False)
importance.to_csv(IMPORTANCE_OUT, header=["importance"])
print(f"Saved feature importance to {IMPORTANCE_OUT}")
print("\nTop 15 features:")
print(importance.head(15).to_string())
