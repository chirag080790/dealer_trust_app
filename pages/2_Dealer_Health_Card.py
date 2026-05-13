import streamlit as st
import pandas as pd
import os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from utils.flags import load_data, get_suspicious_dealers, get_benchmark_cohort, FLAG_COLS, FLAG_LABELS, FLAG_DEFN, CACHE_VERSION

st.set_page_config(page_title="Dealer Health Card", page_icon="📋", layout="wide")

@st.cache_data(show_spinner="Loading data...")
def get_df(_version=None):
    return load_data()

df = get_df(CACHE_VERSION)
suspicious = get_suspicious_dealers(df)
suspicious_ids = set(suspicious["cte_dealer_id"])

# ── Title + search bar ────────────────────────────────────────────────────────
col_title, col_search = st.columns([3, 1])
with col_title:
    st.title("Dealer Health Card")
    st.caption("Per-dealer scorecard with benchmark comparison")
with col_search:
    dealer_list = (
        df.groupby("cte_dealer_id")["dealer_name"]
        .first().reset_index()
        .apply(lambda r: f"{r['cte_dealer_id']} — {r['dealer_name']}", axis=1)
        .sort_values().tolist()
    )
    st.markdown("<br>", unsafe_allow_html=True)
    sel = st.selectbox("Search dealer", dealer_list, label_visibility="collapsed",
                       placeholder="Search by ID or name…")

sel_id   = sel.split(" — ")[0]
sel_name = sel.split(" — ", 1)[1]
dealer_df = df[df["cte_dealer_id"] == sel_id]

if dealer_df.empty:
    st.warning("No listings found for this dealer.")
    st.stop()

def first_val(col):
    return (
        dealer_df[col].dropna().iloc[0]
        if col in dealer_df.columns and not dealer_df[col].dropna().empty
        else "—"
    )

city  = dealer_df["listing_city"].mode()[0] if not dealer_df["listing_city"].isna().all() else None
plan  = dealer_df["plan"].mode()[0]          if not dealer_df["plan"].isna().all()         else None

# ── Dealer header ─────────────────────────────────────────────────────────────
is_suspicious = sel_id in suspicious_ids
if is_suspicious:
    st.warning(f"⚠️ {sel_name} is flagged as a suspicious dealer (>75% listings flagged)")

st.subheader(sel_name)

# Row 1: core metrics
def fmt_date(val):
    if val == "—" or pd.isna(val):
        return "—"
    try:
        return pd.to_datetime(val).strftime("%d %b %Y")
    except Exception:
        return str(val)

plan_start = fmt_date(first_val("plan_start_date"))
plan_end   = fmt_date(first_val("plan_end_date"))
period     = f"{plan_start} – {plan_end}" if plan_start != "—" and plan_end != "—" else "—"
city_label = f"{city} ({sel_id})" if city else sel_id

m1, m2, m3, m4 = st.columns(4)
m1.metric("City (CTE ID)",  city_label)
m2.metric("Plan",           plan or "—")
m3.metric("Plan Period",    period)
m4.metric("Live Listings",  len(dealer_df))

# Row 2: org hierarchy — compact single line
zm = first_val("zonal_manager")
sh = first_val("state_head")
am = first_val("area_manager")
st.markdown(f"**Zonal Manager:** {zm} &nbsp;·&nbsp; **State Head:** {sh} &nbsp;·&nbsp; **Area Manager:** {am}")

st.divider()

# ── Listing quality ───────────────────────────────────────────────────────────
st.subheader("Listing quality")
total    = len(dealer_df)
flagged  = int(dealer_df["any_issue"].sum())
issue_pct = flagged / total * 100 if total else 0

st.metric("Flagged listings", f"{flagged} / {total}", f"{issue_pct:.1f}% flagged")

rows_html = ""
for col in FLAG_COLS:
    flagged_rows = dealer_df[dealer_df[col] == 1]
    n = len(flagged_rows)
    pct = f"{n / total * 100:.1f}%"
    defn = FLAG_DEFN.get(col, "")

    links = []
    if "url" in flagged_rows.columns and n > 0:
        sample = flagged_rows[["url", "make", "model", "mfgyear"]].dropna(subset=["url"]).head(5)
        for _, r in sample.iterrows():
            year = int(r["mfgyear"]) if pd.notna(r["mfgyear"]) else ""
            label = f"{year} {r['make']} {r['model']}".strip()
            links.append(f'<a href="{r["url"]}" target="_blank">{label}</a>')
    links_cell = " &nbsp;·&nbsp; ".join(links) if links else "—"

    rows_html += f"""
    <tr>
      <td style="padding:8px 12px;border-bottom:1px solid #eee">{FLAG_LABELS[col]}</td>
      <td style="padding:8px 12px;border-bottom:1px solid #eee;color:#888;font-size:0.82em">{defn}</td>
      <td style="padding:8px 12px;border-bottom:1px solid #eee;text-align:right">{n}</td>
      <td style="padding:8px 12px;border-bottom:1px solid #eee;text-align:right">{pct}</td>
      <td style="padding:8px 12px;border-bottom:1px solid #eee;font-size:0.88em">{links_cell}</td>
    </tr>"""

st.markdown(f"""
<table style="width:100%;border-collapse:collapse;font-size:0.9em">
  <thead>
    <tr style="border-bottom:2px solid #ddd;text-align:left">
      <th style="padding:8px 12px">Flag</th>
      <th style="padding:8px 12px">Definition</th>
      <th style="padding:8px 12px;text-align:right">Count</th>
      <th style="padding:8px 12px;text-align:right">% of listings</th>
      <th style="padding:8px 12px">Sample listings (up to 5)</th>
    </tr>
  </thead>
  <tbody>{rows_html}</tbody>
</table>
""", unsafe_allow_html=True)

st.divider()

# ── Performance vs benchmark ──────────────────────────────────────────────────
bench_df = get_benchmark_cohort(df, city=city, plan=plan,
                                 exclude_dealer=sel_id, suspicious_ids=suspicious_ids)

st.subheader(f"Performance vs benchmark ({city} · {plan})")

metrics = {
    "Avg leads / listing":    ("all_leads",           "mean"),
    "Avg leads last month":   ("last_month_lead",     "mean"),
    "Avg leads this month":   ("current_month_lead",  "mean"),
    "Avg impressions":        ("impressions",         "mean"),
    "Avg engagements":        ("engagements",         "mean"),
    "Avg images":             ("image_count",         "mean"),
}

rows = []
for label, (col, _) in metrics.items():
    if col not in df.columns:
        continue
    dealer_val = dealer_df[col].mean()
    bench_val  = bench_df[col].mean() if len(bench_df) > 0 else None
    delta      = ((dealer_val - bench_val) / bench_val * 100) if bench_val else None
    rows.append({
        "Metric":          label,
        "Dealer":          round(dealer_val, 1) if pd.notna(dealer_val) else "—",
        "Benchmark (avg)": round(bench_val,  1) if bench_val and pd.notna(bench_val) else "—",
        "vs Benchmark":    f"{delta:+.1f}%" if delta is not None else "—",
    })

st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
if len(bench_df) > 0:
    st.caption(
        f"Benchmark: {bench_df['cte_dealer_id'].nunique()} dealers, "
        f"{len(bench_df):,} listings in {city} on {plan} plan (excl. suspicious)"
    )
else:
    st.caption("No benchmark cohort found for this city + plan combination.")

# Funnel ratios
st.subheader("Funnel ratios")

def funnel(d):
    imp   = d["impressions"].sum()
    eng   = d["engagements"].sum()
    leads = d["all_leads"].sum()
    return {
        "Engagement rate (eng/imp)":   f"{eng/imp*100:.2f}%"   if imp else "—",
        "Lead conversion (leads/imp)": f"{leads/imp*100:.3f}%" if imp else "—",
    }

d_funnel = funnel(dealer_df)
b_funnel = funnel(bench_df) if len(bench_df) > 0 else {}
funnel_rows = [
    {"Metric": k, "Dealer": v, "Benchmark": b_funnel.get(k, "—")}
    for k, v in d_funnel.items()
]
st.dataframe(pd.DataFrame(funnel_rows), use_container_width=True, hide_index=True)

st.divider()

# ── All listings ──────────────────────────────────────────────────────────────
st.subheader("All listings")
show_cols = [
    "stockid", "olx_listing_id", "make", "model", "mfgyear", "kilometers",
    "price", "image_count", "postingdate", "listing_city",
    "all_leads", "impressions", "engagements",
    "any_issue", "primary_flag",
] + FLAG_COLS
available = [c for c in show_cols if c in dealer_df.columns]
st.dataframe(dealer_df[available], use_container_width=True, hide_index=True)
