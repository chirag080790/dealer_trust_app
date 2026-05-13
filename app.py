import streamlit as st
import pandas as pd
import os, sys

sys.path.insert(0, os.path.dirname(__file__))
from utils.flags import load_data, get_suspicious_dealers, FLAG_COLS, FLAG_LABELS

st.set_page_config(page_title="Dealer Trust & Safety", page_icon="🚗", layout="wide")

st.title("Dealer Listings — Trust & Safety")
st.caption("Internal ops tool · CarWale")

@st.cache_data(show_spinner="Loading data...", ttl=3600)
def get_df():
    return load_data()

df = get_df()
suspicious = get_suspicious_dealers(df)
suspicious_ids = set(suspicious["cte_dealer_id"])

# ── Top-level KPIs ──────────────────────────────────────────────────────────
total = len(df)
flagged = int(df["any_issue"].sum())
susp_dealers = len(suspicious)
susp_listings = int(suspicious["flagged"].sum())

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Total listings", f"{total:,}")
c2.metric("Flagged listings", f"{flagged:,}", f"{flagged/total*100:.1f}%")
c3.metric("Clean listings", f"{total-flagged:,}", f"{(total-flagged)/total*100:.1f}%")
c4.metric("Suspicious dealers", f"{susp_dealers}")
c5.metric("Listings on suspicious dealers", f"{susp_listings:,}")

st.divider()

# ── Flag breakdown ───────────────────────────────────────────────────────────
st.subheader("Flag breakdown")
rows = []
for col, label in FLAG_LABELS.items():
    n = int(df[col].sum())
    rows.append({"Flag": label, "Listings affected": n, "% of total": f"{n/total*100:.1f}%"})
flag_df = pd.DataFrame(rows).sort_values("Listings affected", ascending=False)
st.dataframe(flag_df, use_container_width=True, hide_index=True)

st.divider()

# ── Quick filters ────────────────────────────────────────────────────────────
st.subheader("Browse listings")
col1, col2, col3 = st.columns(3)
with col1:
    show_only_flagged = st.checkbox("Show only flagged listings", value=True)
with col2:
    states = ["All"] + sorted(df["state_dealer"].dropna().unique().tolist())
    sel_state = st.selectbox("State", states)
with col3:
    flag_filter = st.multiselect("Filter by flag", list(FLAG_LABELS.values()))

view = df.copy()
if show_only_flagged:
    view = view[view["any_issue"] == 1]
if sel_state != "All":
    view = view[view["state_dealer"] == sel_state]
if flag_filter:
    inv_labels = {v: k for k, v in FLAG_LABELS.items()}
    cols_selected = [inv_labels[f] for f in flag_filter]
    mask = view[cols_selected].max(axis=1) == 1
    view = view[mask]

display_cols = ["cte_dealer_id", "dealer_name", "city_dealer", "state_dealer", "plan",
                "make", "model", "mfgyear", "kilometers", "price", "image_count",
                "any_issue"] + FLAG_COLS
st.dataframe(view[display_cols].head(500), use_container_width=True, hide_index=True)
st.caption(f"Showing {min(len(view), 500):,} of {len(view):,} rows")
