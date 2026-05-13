import pandas as pd
import os
import io
import requests
from datetime import datetime

GDRIVE_FILE_ID = "1HL6GKc3_l4xeQruV4GCbPgcZZ7hUtVJM"
LOCAL_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "dealer_listings.csv")

PLACEHOLDER_REGNOS = {"XXXX", "0000", "NAN", "NEWDELHI", ""}

# Flags in display/severity order
FLAG_COLS = [
    "f_same_dealer_dup",
    "f_cross_dealer_same_city",
    "f_cross_dealer_diff_city",
    "f_price_abnormal",
    "f_km_abnormal",
    "f_stale",
]

FLAG_LABELS = {
    "f_same_dealer_dup":        "Same listing, same dealer",
    "f_cross_dealer_same_city": "Same listing, diff dealers, same city",
    "f_cross_dealer_diff_city": "Same listing, diff dealers, diff cities",
    "f_price_abnormal":         "Price abnormal",
    "f_km_abnormal":            "KMs abnormal",
    "f_stale":                  "Stale listing (>180 days)",
}

FLAG_DEFN = {
    "f_price_abnormal": "Price > Rs 4cr or < Rs 1L",
    "f_km_abnormal":    "KM driven < 500 × car age (yrs) or > 75,000 × car age (yrs)",
}


def _read_csv_from_drive() -> pd.DataFrame:
    session = requests.Session()
    url = f"https://drive.google.com/uc?export=download&id={GDRIVE_FILE_ID}"
    response = session.get(url, stream=True)
    token = None
    for key, value in response.cookies.items():
        if key.startswith("download_warning"):
            token = value
            break
    if token is None and b"confirm=" in response.content:
        import re
        match = re.search(rb"confirm=([0-9A-Za-z_\-]+)", response.content)
        if match:
            token = match.group(1).decode()
    if token:
        response = session.get(url, params={"confirm": token}, stream=True)
    content = b"".join(response.iter_content(chunk_size=32768))
    return pd.read_csv(io.BytesIO(content), low_memory=False)


CACHE_VERSION = "v3"  # bump this whenever FLAG_COLS change to bust Streamlit cache


def load_data(cache_version: str = CACHE_VERSION) -> pd.DataFrame:
    local = os.path.abspath(LOCAL_PATH)
    if os.path.exists(local):
        df = pd.read_csv(local, low_memory=False)
    else:
        df = _read_csv_from_drive()
    return compute_flags(df)


def compute_flags(df: pd.DataFrame) -> pd.DataFrame:
    for col in ["kilometers", "price", "mfgyear", "image_count",
                "all_leads", "last_month_lead", "current_month_lead",
                "lead_before_certification", "lead_after_certification",
                "impressions", "engagements"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Derived fields
    df["km_bucket"] = (df["kilometers"] // 1000).fillna(-1).astype(int)
    df["regno_clean"] = df["regno"].astype(str).str.strip().str.upper()
    valid_mask = ~df["regno_clean"].isin(PLACEHOLDER_REGNOS)

    current_year = datetime.now().year
    df["car_age"] = current_year - df["mfgyear"]

    # Initialize all flags to 0
    for col in FLAG_COLS:
        df[col] = 0

    v_idx = df.index[valid_mask]
    p_idx = df.index[~valid_mask]
    v = df.loc[valid_mask]
    p = df.loc[~valid_mask]

    # ── f_same_dealer_dup ──────────────────────────────────────────────────────
    # Valid regno: same dealer + regno + city appears 2+ times
    if len(v):
        cnt = v.groupby(["cte_dealer_id", "regno_clean", "listing_city"])["stockid"].transform("count")
        df.loc[v_idx, "f_same_dealer_dup"] = (cnt.fillna(0) >= 2).astype(int)

    # Placeholder: same dealer + model + city + km_bucket + year appears 2+ times
    if len(p):
        cnt = p.groupby(["cte_dealer_id", "cw_modelid", "listing_city", "km_bucket", "mfgyear"])["stockid"].transform("count")
        df.loc[p_idx, "f_same_dealer_dup"] = (cnt.fillna(0) >= 2).astype(int)

    # ── f_cross_dealer_same_city ───────────────────────────────────────────────
    # Valid: same regno + city at 2+ different dealer IDs
    if len(v):
        nu = v.groupby(["regno_clean", "listing_city"])["cte_dealer_id"].transform("nunique")
        df.loc[v_idx, "f_cross_dealer_same_city"] = (nu.fillna(0) >= 2).astype(int)

    # Placeholder: same model + city + km_bucket + year at 2+ different dealer IDs
    if len(p):
        nu = p.groupby(["cw_modelid", "listing_city", "km_bucket", "mfgyear"])["cte_dealer_id"].transform("nunique")
        df.loc[p_idx, "f_cross_dealer_same_city"] = (nu.fillna(0) >= 2).astype(int)

    # ── f_cross_dealer_diff_city ───────────────────────────────────────────────
    # Valid: same regno appears in 2+ different cities (implies different dealers)
    if len(v):
        nu = v.groupby("regno_clean")["listing_city"].transform("nunique")
        df.loc[v_idx, "f_cross_dealer_diff_city"] = (nu.fillna(0) >= 2).astype(int)

    # Placeholder: same model + km_bucket + year appears in 2+ different cities
    if len(p):
        nu = p.groupby(["cw_modelid", "km_bucket", "mfgyear"])["listing_city"].transform("nunique")
        df.loc[p_idx, "f_cross_dealer_diff_city"] = (nu.fillna(0) >= 2).astype(int)

    # ── f_price_abnormal ──────────────────────────────────────────────────────
    price_ok = df["price"].notna()
    df.loc[price_ok, "f_price_abnormal"] = (
        (df.loc[price_ok, "price"] > 4_00_00_000) |
        (df.loc[price_ok, "price"] < 1_00_000)
    ).astype(int)

    # ── f_km_abnormal ─────────────────────────────────────────────────────────
    valid_age = df["car_age"].notna() & (df["car_age"] > 0) & df["kilometers"].notna()
    df.loc[valid_age, "f_km_abnormal"] = (
        (df.loc[valid_age, "kilometers"] < 500  * df.loc[valid_age, "car_age"]) |
        (df.loc[valid_age, "kilometers"] > 75000 * df.loc[valid_age, "car_age"])
    ).astype(int)

    # ── f_stale ───────────────────────────────────────────────────────────────
    df["postingdate_dt"] = pd.to_datetime(df["postingdate"], errors="coerce")
    cutoff = pd.Timestamp.now() - pd.Timedelta(days=180)
    df["f_stale"] = (df["postingdate_dt"] < cutoff).fillna(0).astype(int)

    # ── any_issue & primary_flag ──────────────────────────────────────────────
    df["any_issue"] = df[FLAG_COLS].max(axis=1)
    df["primary_flag"] = df[FLAG_COLS].apply(
        lambda row: next((FLAG_LABELS[c] for c in FLAG_COLS if row[c] == 1), "—"),
        axis=1,
    )

    return df


def get_suspicious_dealers(df: pd.DataFrame, min_listings: int = 5, threshold: float = 0.75):
    stats = df.groupby("cte_dealer_id").agg(
        dealer_name=("dealer_name", "first"),
        total_listings=("stockid", "count"),
        flagged=("any_issue", "sum"),
        city=("city_dealer", "first"),
        state=("state_dealer", "first"),
        plan=("plan", "first"),
    ).reset_index()
    stats["issue_rate"] = stats["flagged"] / stats["total_listings"]
    return stats[
        (stats["total_listings"] >= min_listings) & (stats["issue_rate"] > threshold)
    ].copy()


def get_benchmark_cohort(df: pd.DataFrame, city: str, plan: str,
                          exclude_dealer: str = None, suspicious_ids: set = None):
    mask = (df["listing_city"] == city) & (df["plan"] == plan)
    if suspicious_ids:
        mask &= ~df["cte_dealer_id"].isin(suspicious_ids)
    if exclude_dealer:
        mask &= df["cte_dealer_id"] != exclude_dealer
    return df[mask]
