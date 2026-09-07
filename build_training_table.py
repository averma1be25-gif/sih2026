"""
SIH26192 - Track 1: Feature engineering + merge
=================================================
Builds one combined training table for flood severity prediction from:
  1. hilly_indofloods_combined.csv   -> 208 events, full catchment/climate features, NO raw hourly series
  2. cwc_derived_flood_events.csv    -> 8,481 events (249 CWC stations), NO catchment features
  3. cwc_hilly_water_levels.csv      -> 3.76M raw hourly readings, used ONLY to derive time-series
                                        features per CWC event (rate of rise, volatility, season)

Output: combined_training_table.csv
  - one row per flood event (~8,689 rows)
  - common columns: identifiers, peak/danger/warning levels, severity_ratio (target), dates
  - time-series features: populated for CWC rows, NaN for INDOFLOODS rows (no hourly data exists for them)
  - catchment/climate features: populated for INDOFLOODS rows, NaN for CWC rows (known gap, by design)
  - a `source` and `threshold_source` column so Track 2 can report metrics split by group
"""

import pandas as pd
import numpy as np

UPLOAD_DIR = "/mnt/user-data/uploads"
OUT_PATH = "/mnt/user-data/outputs/combined_training_table.csv"

# ---------------------------------------------------------------------------
# 1. Load INDOFLOODS (old stations, full catchment features, no raw series)
# ---------------------------------------------------------------------------
print("Loading INDOFLOODS...")
indo = pd.read_csv(f"{UPLOAD_DIR}/hilly_indofloods_combined.csv")

# Columns that are NOT catchment/climate features -> keep as identifiers/metadata
indo_meta_cols = [
    "EventID", "Start Date", "End Date", "Peak Flood Level (m)", "Peak FL Date",
    "GaugeID", "Warning Level", "Danger Level", "Station", "Latitude", "Longitude",
    "River Name/ Tributory/ SubTributory", "Basin", "State",
]
# Everything else in the file is a catchment/climate/socioeconomic feature -> carry through as-is
catchment_cols = [c for c in indo.columns if c not in indo_meta_cols]

indo_out = pd.DataFrame({
    "event_id": indo["EventID"],
    "source": "INDOFLOODS",
    "threshold_source": "official",
    "station_id": indo["GaugeID"],
    "station_name": indo["Station"],
    "state_or_region": indo["State"],
    "latitude": indo["Latitude"],
    "longitude": indo["Longitude"],
    "peak_date": pd.to_datetime(indo["Peak FL Date"], errors="coerce"),
    "peak_level": indo["Peak Flood Level (m)"],
    "warning_level": indo["Warning Level"],
    "danger_level": indo["Danger Level"],
})
# severity ratio = target variable for Track 2
indo_out["severity_ratio"] = indo_out["peak_level"] / indo_out["danger_level"]

# time-series features: not derivable for INDOFLOODS (no hourly readings for these gauges) -> NaN
ts_feature_names = [
    "rate_of_rise_6h", "rate_of_rise_24h", "rate_of_rise_48h",
    "volatility_48h", "month", "season",
]
for col in ts_feature_names:
    indo_out[col] = np.nan

# attach catchment/climate features as-is (prefixed so Track 2 knows what they are)
catchment_block = indo[catchment_cols].copy()
catchment_block.columns = [f"catchment__{c}" for c in catchment_cols]
indo_out = pd.concat([indo_out.reset_index(drop=True), catchment_block.reset_index(drop=True)], axis=1)

print(f"  INDOFLOODS -> {len(indo_out)} rows")

# ---------------------------------------------------------------------------
# 2. Load CWC derived flood events (new stations, no catchment features)
# ---------------------------------------------------------------------------
print("Loading CWC derived flood events...")
cwc_events = pd.read_csv(f"{UPLOAD_DIR}/cwc_derived_flood_events.csv")
cwc_events["peak_date"] = pd.to_datetime(cwc_events["peak_date"], errors="coerce")
cwc_events["start_date"] = pd.to_datetime(cwc_events["start_date"], errors="coerce")

cwc_out = pd.DataFrame({
    "event_id": [f"CWC-{i}" for i in cwc_events.index],
    "source": "CWC",
    "threshold_source": cwc_events["threshold_source"],  # "official" or "percentile_proxy"
    "station_id": cwc_events["GaugeID"],
    "station_name": cwc_events["station_name"],
    "state_or_region": cwc_events["region"],
    "latitude": np.nan,   # not present in this file
    "longitude": np.nan,
    "peak_date": cwc_events["peak_date"],
    "peak_level": cwc_events["peak_level"],
    "warning_level": cwc_events["warning_level_used"],
    "danger_level": cwc_events["danger_level_used"],
})
cwc_out["severity_ratio"] = cwc_out["peak_level"] / cwc_out["danger_level"]

# catchment features: unavailable for CWC stations -> NaN (known gap, documented in shared context)
for col in catchment_cols:
    cwc_out[f"catchment__{col}"] = np.nan

print(f"  CWC events -> {len(cwc_out)} rows")

# ---------------------------------------------------------------------------
# 3. Derive time-series features for CWC events from raw hourly readings
# ---------------------------------------------------------------------------
print("Loading raw CWC hourly water levels (this is the big file, may take a bit)...")
readings = pd.read_csv(
    f"{UPLOAD_DIR}/cwc_hilly_water_levels.csv",
    usecols=["station_code", "datetime", "water_level"],
    parse_dates=["datetime"],
)
readings = readings.sort_values(["station_code", "datetime"])

# Split into per-station frames with a datetime index for fast windowed lookups
print("Indexing readings per station...")
station_groups = {
    station: g.set_index("datetime")["water_level"]
    for station, g in readings.groupby("station_code", sort=False)
}
del readings  # free memory, we don't need the flat frame anymore

def season_for_month(m):
    if pd.isna(m):
        return np.nan
    m = int(m)
    if m in (3, 4, 5):
        return "pre_monsoon"
    if m in (6, 7, 8, 9):
        return "monsoon"
    if m in (10, 11):
        return "post_monsoon"
    return "winter"

def compute_ts_features(station_id, peak_date):
    """Look back from peak_date within this station's own series and derive
    rate-of-rise over 3 windows, a volatility measure, and month/season."""
    empty = dict(rate_of_rise_6h=np.nan, rate_of_rise_24h=np.nan,
                 rate_of_rise_48h=np.nan, volatility_48h=np.nan,
                 month=np.nan, season=np.nan)
    if pd.isna(peak_date) or station_id not in station_groups:
        return empty

    series = station_groups[station_id]
    window_start = peak_date - pd.Timedelta(hours=48)
    window = series.loc[window_start:peak_date]
    if window.empty or len(window) < 2:
        return empty

    peak_level = window.iloc[-1]

    def rate_over(hours):
        w_start = peak_date - pd.Timedelta(hours=hours)
        w = series.loc[w_start:peak_date]
        if len(w) < 2:
            return np.nan
        elapsed_h = (w.index[-1] - w.index[0]).total_seconds() / 3600
        if elapsed_h == 0:
            return np.nan
        return (w.iloc[-1] - w.iloc[0]) / elapsed_h

    return dict(
        rate_of_rise_6h=rate_over(6),
        rate_of_rise_24h=rate_over(24),
        rate_of_rise_48h=rate_over(48),
        volatility_48h=window.std(),
        month=peak_date.month,
        season=season_for_month(peak_date.month),
    )

print(f"Computing time-series features for {len(cwc_out)} CWC events...")
feat_rows = [
    compute_ts_features(sid, pdate)
    for sid, pdate in zip(cwc_out["station_id"], cwc_out["peak_date"])
]
feat_df = pd.DataFrame(feat_rows)
for col in ts_feature_names:
    cwc_out[col] = feat_df[col].values

n_missing = cwc_out["rate_of_rise_24h"].isna().sum()
print(f"  Done. {n_missing}/{len(cwc_out)} CWC events ended up with no usable window "
      f"(station missing from readings file or <2 points in the 48h window before peak).")

# ---------------------------------------------------------------------------
# 4. Combine and save
# ---------------------------------------------------------------------------
# align column order: common cols, then ts features, then catchment features
common_cols = ["event_id", "source", "threshold_source", "station_id", "station_name",
               "state_or_region", "latitude", "longitude", "peak_date",
               "peak_level", "warning_level", "danger_level", "severity_ratio"]
final_cols = common_cols + ts_feature_names + [f"catchment__{c}" for c in catchment_cols]

combined = pd.concat([indo_out[final_cols], cwc_out[final_cols]], axis=0, ignore_index=True)

print(f"\nCombined table: {combined.shape[0]} rows x {combined.shape[1]} cols")
print(combined["source"].value_counts())
print(combined["threshold_source"].value_counts())
print("\nRows with a usable severity_ratio target:", combined["severity_ratio"].notna().sum())

combined.to_csv(OUT_PATH, index=False)
print(f"\nSaved to {OUT_PATH}")
