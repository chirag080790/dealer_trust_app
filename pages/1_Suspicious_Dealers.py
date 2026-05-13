import streamlit as st
import pandas as pd
import os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from utils.flags import load_data, get_suspicious_dealers, FLAG_COLS, FLAG_LABELS, CACHE_VERSION

st.set_page_config(page_title="Suspicious Dealers", page_icon="🚨", layout="wide")
st.title("Suspicious Dealers")
st.caption("Dealers with >= 5 listings and > 75% flagged")

@st.cache_data(show_spinner="Loading data...")
def get_df(_version=None):
    return load_data()

df = get_df(CACHE_VERSION)

# ── Sidebar controls ─────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Filters")
    min_listings = st.slider("Min listings", 1, 20, 5)
    threshold = st.slider("Issue rate threshold", 0.5, 1.0, 0.75, step=0.05,
                           format="%.0f%%")
    states = ["All"] + sorted(df["state_dealer"].dropna().unique().tolist())
    sel_state = st.selectbox("State", states)

suspicious = get_suspicious_dealers(df, min_listings=min_listings, threshold=threshold)
if sel_state != "All":
    suspicious = suspicious[suspicious["state"] == sel_state]

suspicious_ids = set(suspicious["cte_dealer_id"])

# ── Summary ──────────────────────────────────────────────────────────────────
c1, c2, c3 = st.columns(3)
c1.metric("Suspicious dealers", len(suspicious))
c2.metric("Listings affected", int(suspicious["flagged"].sum()))
c3.metric("Avg issue rate", f"{suspicious['issue_rate'].mean()*100:.1f}%" if len(suspicious) else "—")

st.divider()

# ── Dealer table ─────────────────────────────────────────────────────────────
st.subheader("Dealer list")
disp = suspicious[["cte_dealer_id", "dealer_name", "city", "state", "plan",
                    "total_listings", "flagged", "issue_rate"]].copy()
disp["issue_rate"] = (disp["issue_rate"] * 100).round(1).astype(str) + "%"
disp = disp.sort_values("flagged", ascending=False).reset_index(drop=True)
st.dataframe(disp, use_container_width=True, hide_index=True)

st.divider()

# ── Drill-down ───────────────────────────────────────────────────────────────
st.subheader("Drill down into a dealer")
dealer_options = suspicious.sort_values("flagged", ascending=False)[["cte_dealer_id", "dealer_name"]].apply(
    lambda r: f"{r['cte_dealer_id']} — {r['dealer_name']}", axis=1
).tolist()

if dealer_options:
    sel = st.selectbox("Select dealer", dealer_options)
    sel_id = sel.split(" — ")[0]
    dealer_df = df[df["cte_dealer_id"] == sel_id]

    st.markdown(f"**{len(dealer_df)} listings** | flagged: **{int(dealer_df['any_issue'].sum())}**")

    # Flag breakdown for this dealer
    flag_rows = []
    for col, label in FLAG_LABELS.items():
        n = int(dealer_df[col].sum())
        if n > 0:
            flag_rows.append({"Flag": label, "Count": n})
    if flag_rows:
        st.dataframe(pd.DataFrame(flag_rows), use_container_width=True, hide_index=True)

    show_cols = ["stockid", "make", "model", "mfgyear", "kilometers", "price",
                 "listing_city", "image_count", "any_issue"] + FLAG_COLS
    st.dataframe(dealer_df[show_cols], use_container_width=True, hide_index=True)
else:
    st.info("No suspicious dealers found with current filters.")
