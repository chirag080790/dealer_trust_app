import streamlit as st
import pandas as pd
import os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from utils.flags import load_data, get_suspicious_dealers

st.set_page_config(page_title="City Benchmarks", page_icon="📊", layout="wide")
st.title("City Benchmarks")
st.caption("Aggregate performance by city and plan (suspicious dealers excluded)")

@st.cache_data(show_spinner="Loading data...")
def get_df():
    return load_data()

df = get_df()
suspicious = get_suspicious_dealers(df)
suspicious_ids = set(suspicious["cte_dealer_id"])
clean_df = df[~df["cte_dealer_id"].isin(suspicious_ids)]

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Filters")
    states = ["All"] + sorted(clean_df["state_dealer"].dropna().unique().tolist())
    sel_state = st.selectbox("State", states)
    plans = ["All"] + sorted(clean_df["plan"].dropna().unique().tolist())
    sel_plan = st.selectbox("Plan", plans)

filtered = clean_df.copy()
if sel_state != "All":
    filtered = filtered[filtered["state_dealer"] == sel_state]
if sel_plan != "All":
    filtered = filtered[filtered["plan"] == sel_plan]

# ── City-level summary ────────────────────────────────────────────────────────
st.subheader("City-level summary")

city_stats = (filtered.groupby("listing_city")
              .agg(
                  state=("state_dealer", "first"),
                  dealers=("cte_dealer_id", "nunique"),
                  listings=("stockid", "count"),
                  flagged=("any_issue", "sum"),
                  avg_leads=("all_leads", "mean"),
                  avg_impressions=("impressions", "mean"),
                  avg_engagements=("engagements", "mean"),
                  avg_images=("image_count", "mean"),
              )
              .reset_index()
              .rename(columns={"listing_city": "City"}))

city_stats["issue_rate"] = (city_stats["flagged"] / city_stats["listings"] * 100).round(1)
city_stats["eng_rate"] = (city_stats["avg_engagements"] / city_stats["avg_impressions"] * 100).round(2)
city_stats["avg_leads"] = city_stats["avg_leads"].round(2)
city_stats["avg_impressions"] = city_stats["avg_impressions"].round(0).astype("Int64")
city_stats["avg_images"] = city_stats["avg_images"].round(1)

city_stats = city_stats.sort_values("listings", ascending=False)

st.dataframe(
    city_stats[["City", "state", "dealers", "listings", "flagged", "issue_rate",
                "avg_leads", "avg_impressions", "eng_rate", "avg_images"]],
    use_container_width=True, hide_index=True
)

st.divider()

# ── Plan-level summary ────────────────────────────────────────────────────────
st.subheader("Plan-level summary")

plan_stats = (filtered.groupby("plan")
              .agg(
                  dealers=("cte_dealer_id", "nunique"),
                  listings=("stockid", "count"),
                  flagged=("any_issue", "sum"),
                  avg_leads=("all_leads", "mean"),
                  avg_impressions=("impressions", "mean"),
                  avg_engagements=("engagements", "mean"),
                  avg_images=("image_count", "mean"),
              )
              .reset_index())

plan_stats["issue_rate"] = (plan_stats["flagged"] / plan_stats["listings"] * 100).round(1)
plan_stats["eng_rate"] = (plan_stats["avg_engagements"] / plan_stats["avg_impressions"] * 100).round(2)
plan_stats["avg_leads"] = plan_stats["avg_leads"].round(2)
plan_stats["avg_impressions"] = plan_stats["avg_impressions"].round(0).astype("Int64")
plan_stats["avg_images"] = plan_stats["avg_images"].round(1)
plan_stats = plan_stats.sort_values("listings", ascending=False)

st.dataframe(
    plan_stats[["plan", "dealers", "listings", "flagged", "issue_rate",
                "avg_leads", "avg_impressions", "eng_rate", "avg_images"]],
    use_container_width=True, hide_index=True
)

st.divider()

# ── City × Plan benchmark table ───────────────────────────────────────────────
st.subheader("City x Plan benchmark")
st.caption("Use this to find the benchmark for a specific dealer's cohort")

cp_stats = (filtered.groupby(["listing_city", "plan"])
            .agg(
                dealers=("cte_dealer_id", "nunique"),
                listings=("stockid", "count"),
                avg_leads=("all_leads", "mean"),
                avg_last_month=("last_month_lead", "mean"),
                avg_this_month=("current_month_lead", "mean"),
                avg_impressions=("impressions", "mean"),
                avg_engagements=("engagements", "mean"),
                avg_images=("image_count", "mean"),
            )
            .reset_index()
            .rename(columns={"listing_city": "City"}))

for c in ["avg_leads", "avg_last_month", "avg_this_month", "avg_images"]:
    cp_stats[c] = cp_stats[c].round(2)
cp_stats["avg_impressions"] = cp_stats["avg_impressions"].round(0).astype("Int64")
cp_stats["avg_engagements"] = cp_stats["avg_engagements"].round(0).astype("Int64")
cp_stats = cp_stats.sort_values(["City", "listings"], ascending=[True, False])

st.dataframe(cp_stats, use_container_width=True, hide_index=True)
