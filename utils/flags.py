import pandas as pd
import os
import io
import gdown

# Google Drive file ID — update this if the file is replaced
GDRIVE_FILE_ID = "1HL6GKc3_l4xeQruV4GCbPgcZZ7hUtVJM"
GDRIVE_URL = f"https://drive.google.com/uc?id={GDRIVE_FILE_ID}"

# Local fallback path (for development)
LOCAL_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "dealer_listings.csv")

PLACEHOLDER_REGNOS = {"XXXX", "0000", "NaN", "nan", "NEWDELHI", ""}

FLAG_COLS = ["f_suspicious", "f_km_low", "f_km_high", "f_km_age_high",
             "f_no_image", "f_dealer_dup", "f_cross_dealer"]

FLAG_LABELS = {
    "f_suspicious": "Suspicious",
    "f_km_low": "KM too low",
    "f_km_high": "KM > 2.5L",
    "f_km_age_high": "KM high for age",
    "f_no_image": "No images",
    "f_dealer_dup": "Dealer duplicate",
    "f_cross_dealer": "Cross-dealer",
}


def _read_csv_from_drive() -> pd.DataFrame:
    """Download CSV from Google Drive into memory."""
    out = io.BytesIO()
    gdown.download(GDRIVE_URL, out, quiet=True, fuzzy=True)
    out.seek(0)
    return pd.read_csv(out, low_memory=False)


def load_data() -> pd.DataFrame:
    """Load data from Google Drive, fall back to local file if available."""
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

    df["f_suspicious"] = (df["suspicious listing"] == 1).astype(int)
    df["f_km_low"] = (df["km driven < age*1000"] == 1).astype(int)
    df["f_km_high"] = (df["km driven > 250000km"] == 1).astype(int)
    df["f_km_age_high"] = (df["km driven > age*75000"] == 1).astype(int)
    df["f_no_image"] = (df["image_count"] == 0).astype(int)

    df["km_bucket"] = (df["kilometers"] // 1000).fillna(-1).astype(int)
    dup_key = ["cte_dealer_id", "make", "model", "mfgyear", "km_bucket", "listing_city"]
    dup_counts = df.groupby(dup_key)["stockid"].transform("count")
    df["f_dealer_dup"] = (dup_counts >= 2).astype(int)

    df["regno_clean"] = df["regno"].astype(str).str.strip().str.upper()
    valid_regno = ~df["regno_clean"].isin(PLACEHOLDER_REGNOS)
    cross = df[valid_regno].groupby("regno_clean")["cte_dealer_id"].transform("nunique")
    df["f_cross_dealer"] = 0
    df.loc[valid_regno, "f_cross_dealer"] = (cross >= 2).astype(int)

    df["any_issue"] = df[FLAG_COLS].max(axis=1)
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
    return stats[(stats["total_listings"] >= min_listings) & (stats["issue_rate"] > threshold)].copy()


def get_benchmark_cohort(df: pd.DataFrame, city: str, plan: str,
                          exclude_dealer: str = None, suspicious_ids: set = None):
    mask = (df["listing_city"] == city) & (df["plan"] == plan)
    if suspicious_ids:
        mask &= ~df["cte_dealer_id"].isin(suspicious_ids)
    if exclude_dealer:
        mask &= df["cte_dealer_id"] != exclude_dealer
    return df[mask]
