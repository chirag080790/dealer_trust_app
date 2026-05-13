import streamlit as st
import pandas as pd
import os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from utils.flags import load_data, get_suspicious_dealers, get_benchmark_cohort, FLAG_COLS, FLAG_LABELS

st.set_page_config(page_title="Dealer Health Card", page_icon="📋", layout="wide")
st.title("Dealer Health Card")
st.caption("Per-dealer scorecard with benchmark comparison")

@st.cache_data(show_spinner="Loading data...")
def get_df():
    return load_data()

df = get_df()
suspicious = get_suspicious_dealers(df)
suspicious_ids = set(suspicious["cte_dealer_id"])

# ── Dealer search ─────────────────────────────────────────────────────────────
dealer_list = (df.groupby("cte_dealer_id")["dealer_name"]
               .first().reset_index()
               .apply(lambda r: f"{r['cte_dealer_id']} — {r['dealer_name']}", axis=1)
               .sort_values().tolist())

sel = st.selectbox("Search dealer (ID or name)", dealer_list)
sel_id = sel.split(" — ")[0]
sel_name = sel.split(" — ", 1)[1]

dealer_df = df[df["cte_dealer_id"] == sel_id]

if dealer_df.empty:
    st.warning("No listings found.")
    st.stop()

city = dealer_df["listing_city"].mode()[0] if not dealer_df["listing_city"].isna().all() else None
plan = dealer_df["plan"].mode()[0] if not dealer_df["plan"].isna().all() else None

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown(f"## {sel_name} `{sel_id}`")
is_suspicious = sel_id in suspicious_ids

col_info = st.columns(7)
col_info[0].metric("City", city or "—")
col_info[1].metric("Plan", plan or "—")
col_info[2].metric("Total listings", len(dealer_df))
col_info[3].metric("Suspicious?", "YES 🚨" if is_suspicious else "No ✅")

def first_val(col):
    return dealer_df[col].dropna().iloc[0] if col in dealer_df.columns and not dealer_df[col].dropna().empty else "—"

col_info[4].metric("Zonal Manager", first_val("zonal_manager"))
col_info[5].metric("State Head", first_val("state_head"))
col_info[6].metric("Area Manager", first_val("area_manager"))

st.divider()

# ── Listing quality ───────────────────────────────────────────────────────────
st.subheader("Listing quality")
total = len(dealer_df)
flagged = int(dealer_df["any_issue"].sum())
issue_rate = flagged / total * 100 if total else 0

q1, q2, q3 = st.columns(3)
q1.metric("Flagged listings", f"{flagged} / {total}", f"{issue_rate:.1f}% issue rate")

flag_rows = []
for col, label in FLAG_LABELS.items():
    n = int(dealer_df[col].sum())
    flag_rows.append({"Flag": label, "Count": n, "% of listings": f"{n/total*100:.1f}%"})
flag_df = pd.DataFrame(flag_rows).sort_values("Count", ascending=False)
st.dataframe(flag_df, use_container_width=True, hide_index=True)

st.divider()

# ── Performance vs benchmark ──────────────────────────────────────────────────
st.subheader(f"Performance vs benchmark ({city} · {plan})")

bench_df = get_benchmark_cohort(df, city=city, plan=plan,
                                 exclude_dealer=sel_id, suspicious_ids=suspicious_ids)

metrics = {
    "Avg leads / listing": ("all_leads", "mean"),
    "Avg leads last month": ("last_month_lead", "mean"),
    "Avg leads this month": ("current_month_lead", "mean"),
    "Avg impressions": ("impressions", "mean"),
    "Avg engagements": ("engagements", "mean"),
    "Avg images": ("image_count", "mean"),
}

rows = []
for label, (col, agg) in metrics.items():
    if col not in df.columns:
        continue
    dealer_val = dealer_df[col].mean() if agg == "mean" else dealer_df[col].sum()
    bench_val = bench_df[col].mean() if (len(bench_df) > 0 and agg == "mean") else None
    delta = ((dealer_val - bench_val) / bench_val * 100) if bench_val else None
    rows.append({
        "Metric": label,
        "Dealer": round(dealer_val, 1) if pd.notna(dealer_val) else "—",
        "Benchmark (avg)": round(bench_val, 1) if bench_val and pd.notna(bench_val) else "—",
        "vs Benchmark": f"{delta:+.1f}%" if delta is not None else "—",
    })

perf_df = pd.DataFrame(rows)
st.dataframe(perf_df, use_container_width=True, hide_index=True)

if len(bench_df) > 0:
    st.caption(f"Benchmark: {len(bench_df['cte_dealer_id'].unique())} dealers, "
               f"{len(bench_df):,} listings in {city} on {plan} plan (excl. suspicious)")
else:
    st.caption("No benchmark cohort found for this city + plan combination.")

# Funnel ratios
st.subheader("Funnel ratios")
def funnel(d):
    imp = d["impressions"].sum()
    eng = d["engagements"].sum()
    leads = d["all_leads"].sum()
    return {
        "Engagement rate (eng/imp)": f"{eng/imp*100:.2f}%" if imp else "—",
        "Lead conversion (leads/imp)": f"{leads/imp*100:.3f}%" if imp else "—",
    }

d_funnel = funnel(dealer_df)
b_funnel = funnel(bench_df) if len(bench_df) > 0 else {}

funnel_rows = []
for k, v in d_funnel.items():
    funnel_rows.append({"Metric": k, "Dealer": v, "Benchmark": b_funnel.get(k, "—")})
st.dataframe(pd.DataFrame(funnel_rows), use_container_width=True, hide_index=True)

st.divider()

# ── Listing detail ────────────────────────────────────────────────────────────
st.subheader("All listings")
show_cols = ["stockid", "olx_listing_id", "make", "model", "mfgyear", "kilometers",
             "price", "image_count", "postingdate", "status",
             "all_leads", "impressions", "engagements", "any_issue"] + FLAG_COLS
available = [c for c in show_cols if c in dealer_df.columns]
st.dataframe(dealer_df[available], use_container_width=True, hide_index=True)
