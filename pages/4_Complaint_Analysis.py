import streamlit as st
import pandas as pd
import os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from utils.flags import load_data, get_suspicious_dealers, get_benchmark_cohort, FLAG_LABELS

st.set_page_config(page_title="Complaint Analysis", page_icon="📝", layout="wide")
st.title("Complaint Analysis")
st.caption("Structured deep-dive for a dealer complaint — benchmarked against cohort")

@st.cache_data(show_spinner="Loading data...")
def get_df():
    return load_data()

df = get_df()
suspicious = get_suspicious_dealers(df)
suspicious_ids = set(suspicious["cte_dealer_id"])

# ── Dealer selector ───────────────────────────────────────────────────────────
dealer_list = (df.groupby("cte_dealer_id")["dealer_name"]
               .first().reset_index()
               .apply(lambda r: f"{r['cte_dealer_id']} — {r['dealer_name']}", axis=1)
               .sort_values().tolist())

col_sel, col_complaint = st.columns([2, 2])
with col_sel:
    sel = st.selectbox("Select dealer", dealer_list)
with col_complaint:
    complaint_text = st.text_area("Complaint summary (optional)", height=80,
                                   placeholder="e.g. Low lead volume despite high impressions")

sel_id = sel.split(" — ")[0]
sel_name = sel.split(" — ", 1)[1]
dealer_df = df[df["cte_dealer_id"] == sel_id]

if dealer_df.empty:
    st.warning("No data for this dealer.")
    st.stop()

city = dealer_df["listing_city"].mode()[0] if not dealer_df["listing_city"].isna().all() else None
plan = dealer_df["plan"].mode()[0] if not dealer_df["plan"].isna().all() else None
bench_df = get_benchmark_cohort(df, city=city, plan=plan,
                                 exclude_dealer=sel_id, suspicious_ids=suspicious_ids)

st.divider()

# ── Section 1: Who is the dealer ─────────────────────────────────────────────
st.subheader("1. Dealer profile")
h = dealer_df.iloc[0]
cols = st.columns(5)
cols[0].metric("Dealer", sel_name)
cols[1].metric("City", city or "—")
cols[2].metric("Plan", plan or "—")
cols[3].metric("Total listings", len(dealer_df))
cols[4].metric("Suspicious?", "YES 🚨" if sel_id in suspicious_ids else "No ✅")

# ── Section 2: Listing health ─────────────────────────────────────────────────
st.subheader("2. Listing health")
total = len(dealer_df)
flagged = int(dealer_df["any_issue"].sum())

h1, h2 = st.columns(2)
h1.metric("Flagged listings", f"{flagged}/{total}", f"{flagged/total*100:.1f}%")

flag_rows = [{"Flag": FLAG_LABELS[c], "Count": int(dealer_df[c].sum())}
             for c in FLAG_LABELS if int(dealer_df[c].sum()) > 0]
if flag_rows:
    st.dataframe(pd.DataFrame(flag_rows), use_container_width=True, hide_index=True)
else:
    st.success("No flags on any listings.")

# ── Section 3: Performance vs benchmark ──────────────────────────────────────
st.subheader(f"3. Performance vs benchmark ({city} · {plan})")

def safe_mean(series):
    v = series.mean()
    return round(v, 2) if pd.notna(v) else None

metrics_map = [
    ("All-time leads / listing", "all_leads"),
    ("Last month leads / listing", "last_month_lead"),
    ("This month leads / listing", "current_month_lead"),
    ("Impressions / listing", "impressions"),
    ("Engagements / listing", "engagements"),
    ("Images / listing", "image_count"),
]

perf_rows = []
for label, col in metrics_map:
    if col not in df.columns:
        continue
    dv = safe_mean(dealer_df[col])
    bv = safe_mean(bench_df[col]) if len(bench_df) > 0 else None
    delta = f"{(dv - bv)/bv*100:+.1f}%" if (dv is not None and bv) else "—"
    perf_rows.append({
        "Metric": label,
        "Dealer": dv if dv is not None else "—",
        "Benchmark": bv if bv is not None else "—",
        "vs Benchmark": delta,
    })

st.dataframe(pd.DataFrame(perf_rows), use_container_width=True, hide_index=True)

if len(bench_df) > 0:
    st.caption(f"Benchmark: {bench_df['cte_dealer_id'].nunique()} dealers, "
               f"{len(bench_df):,} listings in {city} on {plan} (excl. suspicious)")

# ── Section 4: Funnel ─────────────────────────────────────────────────────────
st.subheader("4. Funnel analysis")
imp_d = dealer_df["impressions"].sum()
eng_d = dealer_df["engagements"].sum()
leads_d = dealer_df["all_leads"].sum()
imp_b = bench_df["impressions"].sum() if len(bench_df) else 0
eng_b = bench_df["engagements"].sum() if len(bench_df) else 0
leads_b = bench_df["all_leads"].sum() if len(bench_df) else 0

funnel_rows = [
    {"Stage": "Impressions (total)", "Dealer": int(imp_d), "Benchmark total": int(imp_b)},
    {"Stage": "Engagement rate", "Dealer": f"{eng_d/imp_d*100:.2f}%" if imp_d else "—",
     "Benchmark total": f"{eng_b/imp_b*100:.2f}%" if imp_b else "—"},
    {"Stage": "Lead conversion rate", "Dealer": f"{leads_d/imp_d*100:.3f}%" if imp_d else "—",
     "Benchmark total": f"{leads_b/imp_b*100:.3f}%" if imp_b else "—"},
]
st.dataframe(pd.DataFrame(funnel_rows), use_container_width=True, hide_index=True)

# ── Section 5: Image analysis ─────────────────────────────────────────────────
st.subheader("5. Image distribution")
bins = [0, 1, 6, 11, 16, 21, 26, 999]
labels = ["0", "1-5", "6-10", "11-15", "16-20", "21-25", "26+"]

def image_dist(d):
    d = d.copy()
    d["img_bucket"] = pd.cut(d["image_count"], bins=bins, labels=labels, right=False)
    return d.groupby("img_bucket", observed=True).size().reset_index(name="count")

img_dealer = image_dist(dealer_df).rename(columns={"count": "Dealer"})
img_bench = image_dist(bench_df).rename(columns={"count": "Benchmark"}) if len(bench_df) > 0 else None

if img_bench is not None:
    img_merged = img_dealer.merge(img_bench, on="img_bucket", how="left")
    img_merged.columns = ["Images", "Dealer", "Benchmark"]
else:
    img_merged = img_dealer.rename(columns={"img_bucket": "Images", "Dealer": "Dealer"})

st.dataframe(img_merged, use_container_width=True, hide_index=True)

# ── Section 6: Listing age ────────────────────────────────────────────────────
st.subheader("6. Listing age breakdown")
if "listing-age-bucket" in dealer_df.columns:
    age_dist = dealer_df["listing-age-bucket"].value_counts().reset_index()
    age_dist.columns = ["Age bucket", "Count"]
    st.dataframe(age_dist, use_container_width=True, hide_index=True)
else:
    st.info("Listing age bucket column not available.")

# ── Section 7: Recommendations ───────────────────────────────────────────────
st.subheader("7. Potential issues & recommendations")
issues = []

if flagged / total > 0.3:
    issues.append(f"High flag rate ({flagged/total*100:.0f}%) — review flagged listings with dealer")

if dealer_df["image_count"].mean() < 5:
    issues.append("Low average image count — advise dealer to upload more photos per listing")

if len(perf_rows) >= 4:
    eng_row = next((r for r in perf_rows if "Engagement" in r["Metric"]), None)
    if eng_row and eng_row["vs Benchmark"] not in ("—", None):
        try:
            delta_val = float(eng_row["vs Benchmark"].replace("%", "").replace("+", ""))
            if delta_val < -20:
                issues.append("Engagement rate significantly below benchmark — check listing quality, photos, pricing")
        except Exception:
            pass

if dealer_df["postingdate"].notna().any():
    try:
        dealer_df2 = dealer_df.copy()
        dealer_df2["postingdate"] = pd.to_datetime(dealer_df2["postingdate"], errors="coerce")
        fresh = (dealer_df2["postingdate"] > pd.Timestamp.now() - pd.Timedelta(days=30)).sum()
        if fresh / total > 0.7:
            issues.append(f"{fresh}/{total} listings are <30 days old — leads may not have accumulated yet")
    except Exception:
        pass

if issues:
    for i in issues:
        st.warning(i)
else:
    st.success("No automatic issues detected. Review metrics above for manual assessment.")
