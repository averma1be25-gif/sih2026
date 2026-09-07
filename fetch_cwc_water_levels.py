"""
Download real-time/historical water level (WSE) data from CWC's flood
forecasting portal (ffs.india-water.gov.in) for 274 hilly-region stations
identified from the GUARDIAN dataset (Patidar et al. 2024).

Requires: hilly_guardian_stations_final.csv (included alongside this script)
with columns: name, region, code_id, lat, lon.

IMPORTANT -- test this on ONE station first (see main() below, LIMIT=1) to
confirm the endpoint responds correctly on your network before pulling all
274 -- my sandbox couldn't reach ffs.india-water.gov.in to verify end-to-end,
so this needs a real test run before you trust it.

The endpoint/request format is reverse-engineered from GUARDIAN's own public
code (github.com/girishpatidar/discharge_india/codes), not guessed -- but
double-check the response looks sane (see print output) before relying on it.

Run:
    pip install requests pandas --break-system-packages
    python fetch_cwc_water_levels.py
"""

import requests
import pandas as pd
import datetime
import time

STATIONS_CSV = "hilly_guardian_stations_final.csv"
URL = "https://ffs.india-water.gov.in/iam/api/new-entry-data/specification/sorted"
DATATYPE_CODE = "HHS"  # hourly water level (as used in GUARDIAN's own extraction script)
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

# Pull monsoon seasons (when flash floods actually happen) across a few years
# rather than everything -- keeps request count and payload size reasonable
DATE_RANGES = [
    ("2021-05-01", "2021-10-31"),
    ("2022-05-01", "2022-10-31"),
    ("2023-05-01", "2023-10-31"),
    ("2024-05-01", "2024-10-31"),
]

# Set to a small number (e.g. 1 or 3) for your first test run.
# Set to None to pull all stations once you've confirmed it works.
LIMIT = None

# --- Experimental: try to find danger/warning level via the same endpoint ---
# We don't have a confirmed datatype code for these (unlike "HHS" for water
# level), so this tries a few plausible guesses on ONE station. If any of
# them return non-empty data, that's your danger/warning level source.
TEST_THRESHOLD_CODES = ["DL", "WL", "HFL", "DANGER", "WARNING", "DANGERLEVEL", "WARNINGLEVEL"]


def try_threshold_codes(st_code: str):
    print(f"\n--- Testing possible danger/warning-level datatype codes for {st_code} ---")
    for code in TEST_THRESHOLD_CODES:
        specification = (
            '%7B%22where%22:%7B%22where%22:%7B%22where%22:%7B%22expression%22:'
            '%7B%22valueIsRelationField%22:false,%22fieldName%22:%22id.stationCode%22,'
            f'%22operator%22:%22eq%22,%22value%22:%22{st_code}%22%7D%7D,%22and%22:%7B%22expression%22:'
            '%7B%22valueIsRelationField%22:false,%22fieldName%22:%22id.datatypeCode%22,'
            f'%22operator%22:%22eq%22,%22value%22:%22{code}%22%7D%7D%7D,%22and%22:%7B%22expression%22:'
            '%7B%22valueIsRelationField%22:false,%22fieldName%22:%22dataValue%22,'
            '%22operator%22:%22null%22,%22value%22:%22false%22%7D%7D%7D,%22and%22:%7B%22expression%22:'
            '%7B%22valueIsRelationField%22:false,%22fieldName%22:%22id.dataTime%22,'
            '%22operator%22:%22btn%22,%22value%22:%222020-01-01T00:00:00.000,2024-12-31T00:00:00.000%22%7D%7D%7D'
        )
        params = {
            "sort-criteria": "%7B%22sortOrderDtos%22:%5B%7B%22sortDirection%22:%22ASC%22,%22field%22:%22id.dataTime%22%7D%5D%7D",
            "specification": specification,
        }
        try:
            r = requests.get(URL, params=params, headers=HEADERS, timeout=20)
            data = r.json() if r.status_code == 200 else []
            print(f"  code={code!r}: status={r.status_code}, {len(data)} results"
                  + (f" -- SAMPLE: {data[0]}" if data else ""))
        except Exception as e:
            print(f"  code={code!r}: ERROR {e}")


def fetch_station_range(st_code: str, sdate: str, edate: str) -> pd.DataFrame:
    specification = (
        '%7B%22where%22:%7B%22where%22:%7B%22where%22:%7B%22expression%22:'
        '%7B%22valueIsRelationField%22:false,%22fieldName%22:%22id.stationCode%22,'
        f'%22operator%22:%22eq%22,%22value%22:%22{st_code}%22%7D%7D,%22and%22:%7B%22expression%22:'
        '%7B%22valueIsRelationField%22:false,%22fieldName%22:%22id.datatypeCode%22,'
        f'%22operator%22:%22eq%22,%22value%22:%22{DATATYPE_CODE}%22%7D%7D%7D,%22and%22:%7B%22expression%22:'
        '%7B%22valueIsRelationField%22:false,%22fieldName%22:%22dataValue%22,'
        '%22operator%22:%22null%22,%22value%22:%22false%22%7D%7D%7D,%22and%22:%7B%22expression%22:'
        '%7B%22valueIsRelationField%22:false,%22fieldName%22:%22id.dataTime%22,'
        f'%22operator%22:%22btn%22,%22value%22:%22{sdate}T00:00:00.000,{edate}T00:00:00.000%22%7D%7D%7D'
    )
    params = {
        "sort-criteria": "%7B%22sortOrderDtos%22:%5B%7B%22sortDirection%22:%22ASC%22,%22field%22:%22id.dataTime%22%7D%5D%7D",
        "specification": specification,
    }
    r = requests.get(URL, params=params, headers=HEADERS, timeout=30)
    r.raise_for_status()
    data = r.json()

    rows = []
    for item in data:
        try:
            rows.append({
                "station_code": item["stationCode"],
                "datetime": item["id"]["dataTime"],
                "water_level": item["dataValue"],
            })
        except (KeyError, TypeError):
            continue
    return pd.DataFrame(rows)


def main():
    stations = pd.read_csv(STATIONS_CSV)

    # Quick one-time experiment to find a working danger/warning-level code
    try_threshold_codes(stations.iloc[0]["code_id"])

    if LIMIT:
        stations = stations.head(LIMIT)
        print(f"TEST MODE: pulling only {LIMIT} station(s). "
              f"Set LIMIT=None at the top of this script once this works.")

    all_data = []
    for _, row in stations.iterrows():
        code, name = row["code_id"], row["name"]
        print(f"\nFetching {name} ({code})...")
        for sdate, edate in DATE_RANGES:
            try:
                df = fetch_station_range(code, sdate, edate)
                print(f"  {sdate} to {edate}: {len(df)} readings")
                if len(df) > 0:
                    df["station_name"] = name
                    df["region"] = row["region"]
                    all_data.append(df)
            except Exception as e:
                print(f"  ERROR for {sdate}-{edate}: {e}")
            time.sleep(1)  # be polite to the government server

    if not all_data:
        print("\nNo data retrieved. Check the printed errors above -- likely "
              "causes: endpoint changed, station code format issue, or the "
              "site blocking automated requests (check response status/text).")
        return

    combined = pd.concat(all_data, ignore_index=True)
    out_path = "cwc_hilly_water_levels.csv"
    combined.to_csv(out_path, index=False)
    print(f"\nWrote {out_path}: {combined.shape[0]} rows")
    print(combined.head(10))


if __name__ == "__main__":
    main()
