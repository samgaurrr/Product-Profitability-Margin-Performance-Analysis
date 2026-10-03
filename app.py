import glob
import os

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(
    page_title="Nassau Candy - Product Profitability",
    page_icon="🍬",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Reference data taken from the project brief
# ---------------------------------------------------------------------------
FACTORY_COORDS = {
    "Lot's O' Nuts": (32.881893, -111.768036),
    "Wicked Choccy's": (32.076176, -81.088371),
    "Sugar Shack": (48.11914, -96.18115),
    "Secret Factory": (41.446333, -90.565487),
    "The Other Factory": (35.1175, -89.971107),
}

PRODUCT_FACTORY = {
    "Wonka Bar - Nutty Crunch Surprise": "Lot's O' Nuts",
    "Wonka Bar - Fudge Mallows": "Lot's O' Nuts",
    "Wonka Bar -Scrumdiddlyumptious": "Lot's O' Nuts",
    "Wonka Bar - Milk Chocolate": "Wicked Choccy's",
    "Wonka Bar - Triple Dazzle Caramel": "Wicked Choccy's",
    "Laffy Taffy": "Sugar Shack",
    "SweeTARTS": "Sugar Shack",
    "Nerds": "Sugar Shack",
    "Fun Dip": "Sugar Shack",
    "Fizzy Lifting Drinks": "Sugar Shack",
    "Everlasting Gobstopper": "Secret Factory",
    "Lickable Wallpaper": "Secret Factory",
    "Wonka Gum": "Secret Factory",
    "Hair Toffee": "The Other Factory",
    "Kazookles": "The Other Factory",
}

REQUIRED_COLUMNS = [
    "Order Date", "Division", "Region", "State/Province", "Product Name",
    "Sales", "Units", "Gross Profit", "Cost",
]


# ---------------------------------------------------------------------------
# Data loading and cleaning
# ---------------------------------------------------------------------------
def read_any(source):
    name = getattr(source, "name", str(source)).lower()
    if name.endswith((".xlsx", ".xls")):
        return pd.read_excel(source)
    try:
        return pd.read_csv(source)
    except UnicodeDecodeError:
        if hasattr(source, "seek"):
            source.seek(0)
        return pd.read_csv(source, encoding="latin-1")


@st.cache_data(show_spinner="Loading and cleaning data...")
def load_and_clean(source):
    df = read_any(source)
    df.columns = [str(c).strip() for c in df.columns]

    # Case-insensitive column matching
    lower_map = {c.lower(): c for c in df.columns}
    rename = {}
    for col in REQUIRED_COLUMNS + ["Ship Date", "Ship Mode", "Country/Region", "City"]:
        if col.lower() in lower_map and lower_map[col.lower()] != col:
            rename[lower_map[col.lower()]] = col
    df = df.rename(columns=rename)

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    # Types
    df["Order Date"] = pd.to_datetime(df["Order Date"], dayfirst=True, errors="coerce")
    for col in ["Sales", "Units", "Gross Profit", "Cost"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Standardise labels
    for col in ["Division", "Region", "State/Province", "Product Name"]:
        df[col] = df[col].astype(str).str.strip()
    df["Division"] = df["Division"].str.title()

    # Validation: remove invalid records
    before = len(df)
    df = df.dropna(subset=["Order Date", "Sales", "Cost", "Gross Profit", "Units"])
    df = df[(df["Sales"] > 0) & (df["Cost"] >= 0) & (df["Units"] > 0)]
    # Recompute gross profit so it is consistent with Sales - Cost
    df["Gross Profit"] = df["Sales"] - df["Cost"]
    removed = before - len(df)

    df["Factory"] = df["Product Name"].map(PRODUCT_FACTORY).fillna("Unknown")
    return df.reset_index(drop=True), removed


def product_summary(d):
    g = d.groupby(["Product Name", "Division", "Factory"], as_index=False).agg(
        Sales=("Sales", "sum"),
        Cost=("Cost", "sum"),
        Units=("Units", "sum"),
        Gross_Profit=("Gross Profit", "sum"),
    )
    g["Gross Margin %"] = g["Gross_Profit"] / g["Sales"] * 100
    g["Profit per Unit"] = g["Gross_Profit"] / g["Units"]
    g["Revenue Contribution %"] = g["Sales"] / g["Sales"].sum() * 100
    g["Profit Contribution %"] = g["Gross_Profit"] / g["Gross_Profit"].sum() * 100
    g["Cost Ratio %"] = g["Cost"] / g["Sales"] * 100
    return g.sort_values("Gross_Profit", ascending=False).reset_index(drop=True)


def division_summary(d):
    g = d.groupby("Division", as_index=False).agg(
        Sales=("Sales", "sum"),
        Cost=("Cost", "sum"),
        Units=("Units", "sum"),
        Gross_Profit=("Gross Profit", "sum"),
    )
    g["Gross Margin %"] = g["Gross_Profit"] / g["Sales"] * 100
    g["Revenue Share %"] = g["Sales"] / g["Sales"].sum() * 100
    g["Profit Share %"] = g["Gross_Profit"] / g["Gross_Profit"].sum() * 100
    g["Share Gap (pp)"] = g["Revenue Share %"] - g["Profit Share %"]
    return g


def pareto_frame(df, value_col, label_col):
    p = df.groupby(label_col, as_index=False)[value_col].sum()
    p = p[p[value_col] > 0].sort_values(value_col, ascending=False).reset_index(drop=True)
    p["Cumulative %"] = p[value_col].cumsum() / p[value_col].sum() * 100
    return p


def n_to_reach(p, threshold=80):
    hit = p[p["Cumulative %"] >= threshold]
    return int(hit.index[0]) + 1 if len(hit) else len(p)


# ---------------------------------------------------------------------------
# Sidebar: data source
# ---------------------------------------------------------------------------
st.title("🍬 Product Line Profitability & Margin Performance")
st.caption("Nassau Candy Distributor - gross margin, cost structure and profit concentration")

st.sidebar.header("Data")
uploaded = st.sidebar.file_uploader("Upload dataset (CSV or Excel)", type=["csv", "xlsx", "xls"])

source = uploaded
if source is None:
    local = sorted(glob.glob("*.csv") + glob.glob("*.xlsx") + glob.glob("*.xls"))
    if local:
        source = local[0]
        st.sidebar.info(f"Using local file: {os.path.basename(source)}")

if source is None:
    st.warning("Upload the dataset in the sidebar, or put the CSV/Excel file in the same folder as app.py.")
    st.stop()

try:
    data, removed_rows = load_and_clean(source)
except Exception as e:
    st.error(f"Could not load the dataset: {e}")
    st.stop()

# ---------------------------------------------------------------------------
# Sidebar: filters (user capabilities from the brief)
# ---------------------------------------------------------------------------
st.sidebar.header("Filters")
min_d, max_d = data["Order Date"].min().date(), data["Order Date"].max().date()
date_range = st.sidebar.date_input("Date range", value=(min_d, max_d), min_value=min_d, max_value=max_d)
if isinstance(date_range, tuple) and len(date_range) == 2:
    start, end = date_range
else:
    start, end = min_d, max_d

divisions = sorted(data["Division"].unique())
sel_div = st.sidebar.multiselect("Division", divisions, default=divisions)
margin_threshold = st.sidebar.slider("Margin threshold (%)", 0, 100, 30, help="Products below this gross margin are flagged as margin risks.")
search = st.sidebar.text_input("Product search")

mask = (
    (data["Order Date"].dt.date >= start)
    & (data["Order Date"].dt.date <= end)
    & (data["Division"].isin(sel_div))
)
if search:
    mask &= data["Product Name"].str.contains(search, case=False, na=False)
df = data[mask]

st.sidebar.caption(f"{removed_rows:,} invalid rows removed during cleaning")

if df.empty:
    st.warning("No data for the selected filters.")
    st.stop()

prod = product_summary(df)
div = division_summary(df)

# ---------------------------------------------------------------------------
# Headline KPIs
# ---------------------------------------------------------------------------
total_sales = df["Sales"].sum()
total_profit = df["Gross Profit"].sum()
overall_margin = total_profit / total_sales * 100
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Total Sales", f"${total_sales:,.0f}")
c2.metric("Gross Profit", f"${total_profit:,.0f}")
c3.metric("Gross Margin", f"{overall_margin:.1f}%")
c4.metric("Units Sold", f"{df['Units'].sum():,.0f}")
c5.metric("Products", f"{prod.shape[0]}")

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "Product Profitability",
    "Division Performance",
    "Cost vs Margin",
    "Profit Concentration",
    "Factories & Regions",
    "Data",
])

# ---------------------------------------------------------------------------
# Tab 1: Product profitability overview
# ---------------------------------------------------------------------------
with tab1:
    st.subheader("Product-level margin leaderboard")
    metric = st.radio("Rank by", ["Gross Margin %", "Gross_Profit", "Profit per Unit"], horizontal=True)
    board = prod.sort_values(metric, ascending=False)
    fig = px.bar(
        board, x=metric, y="Product Name", color="Division", orientation="h",
        title=f"Products ranked by {metric.replace('_', ' ')}",
    )
    fig.update_layout(yaxis={"categoryorder": "total ascending"}, height=520)
    st.plotly_chart(fig)

    st.subheader("Profit contribution")
    left, right = st.columns(2)
    with left:
        st.plotly_chart(
            px.pie(prod, names="Product Name", values="Gross_Profit", title="Share of gross profit by product"),
        )
    with right:
        st.plotly_chart(
            px.pie(prod, names="Product Name", values="Sales", title="Share of revenue by product"),
        )

    st.subheader("Product quadrants")
    med_sales, med_margin = prod["Sales"].median(), prod["Gross Margin %"].median()

    def quadrant(r):
        if r["Sales"] >= med_sales and r["Gross Margin %"] >= med_margin:
            return "High sales / high margin"
        if r["Sales"] >= med_sales:
            return "High sales / low margin"
        if r["Gross Margin %"] >= med_margin:
            return "Low sales / high margin"
        return "Low sales / low margin"

    prod["Quadrant"] = prod.apply(quadrant, axis=1)
    st.dataframe(
        prod[["Product Name", "Division", "Sales", "Gross_Profit", "Gross Margin %", "Quadrant"]].round(2), hide_index=True,
    )

# ---------------------------------------------------------------------------
# Tab 2: Division performance
# ---------------------------------------------------------------------------
with tab2:
    st.subheader("Revenue vs profit by division")
    melt = div.melt(id_vars="Division", value_vars=["Sales", "Gross_Profit"], var_name="Metric", value_name="Amount")
    st.plotly_chart(
        px.bar(melt, x="Division", y="Amount", color="Metric", barmode="group"),
    )

    l, r = st.columns(2)
    with l:
        st.plotly_chart(
            px.bar(div, x="Division", y="Gross Margin %", color="Division", title="Average gross margin by division"),
        )
    with r:
        st.plotly_chart(
            px.box(df.assign(**{"Order Margin %": df["Gross Profit"] / df["Sales"] * 100}),
                   x="Division", y="Order Margin %", color="Division", title="Margin distribution by division"),
        )

    st.subheader("Revenue vs profit imbalance")
    st.caption("Positive gap = division brings more of the revenue than of the profit (structural margin issue).")
    st.dataframe(div.round(2), hide_index=True)

# ---------------------------------------------------------------------------
# Tab 3: Cost vs margin diagnostics
# ---------------------------------------------------------------------------
with tab3:
    st.subheader("Cost vs sales")
    st.plotly_chart(
        px.scatter(
            prod, x="Sales", y="Cost", size="Units", color="Division", hover_name="Product Name",
            title="Cost vs sales by product (bubble size = units)",
        ).add_shape(
            type="line", x0=0, y0=0, x1=prod["Sales"].max(), y1=prod["Sales"].max(),
            line=dict(dash="dash", color="grey"),
        ),
    )
    st.caption("Points close to the dashed break-even line have thin margins.")

    st.subheader("Margin risk flags")
    prod["Flag"] = "OK"
    prod.loc[prod["Gross Margin %"] < margin_threshold, "Flag"] = "Margin risk"
    prod.loc[(prod["Gross Margin %"] < margin_threshold) & (prod["Sales"] >= prod["Sales"].median()), "Flag"] = "High sales, low margin"

    def action(r):
        if r["Flag"] == "OK":
            return "Maintain"
        if r["Flag"] == "High sales, low margin":
            return "Reprice / renegotiate cost"
        return "Cost renegotiation / discontinuation review"

    prod["Suggested Action"] = prod.apply(action, axis=1)
    flagged = prod[prod["Flag"] != "OK"]
    st.metric("Products below threshold", f"{len(flagged)} of {len(prod)}")
    st.dataframe(
        prod[["Product Name", "Division", "Gross Margin %", "Cost Ratio %", "Profit per Unit", "Flag", "Suggested Action"]].round(2), hide_index=True,
    )

# ---------------------------------------------------------------------------
# Tab 4: Profit concentration (Pareto)
# ---------------------------------------------------------------------------
with tab4:
    st.subheader("Pareto analysis")
    for value_col, title in [("Sales", "Revenue"), ("Gross Profit", "Gross profit")]:
        p = pareto_frame(df, value_col, "Product Name")
        n80 = n_to_reach(p, 80)
        fig = go.Figure()
        fig.add_bar(x=p["Product Name"], y=p[value_col], name=title)
        fig.add_scatter(x=p["Product Name"], y=p["Cumulative %"], name="Cumulative %", yaxis="y2", mode="lines+markers")
        fig.add_scatter(x=p["Product Name"], y=[80] * len(p), name="80% line", yaxis="y2", mode="lines", line=dict(dash="dash", color="red"))
        fig.update_layout(
            title=f"{title} Pareto: {n80} of {len(p)} products ({n80 / len(p) * 100:.0f}%) make 80% of {title.lower()}",
            yaxis2=dict(overlaying="y", side="right", range=[0, 105], title="Cumulative %"),
            height=480,
        )
        st.plotly_chart(fig)

    st.subheader("Dependency indicators")
    top_prod_share = prod["Profit Contribution %"].iloc[0]
    st.metric("Top product's share of profit", f"{top_prod_share:.1f}%", help=prod["Product Name"].iloc[0])
    by_state = pareto_frame(df, "Gross Profit", "State/Province")
    by_region = pareto_frame(df, "Gross Profit", "Region")
    a, b = st.columns(2)
    with a:
        st.plotly_chart(
            px.bar(by_state.head(10), x="State/Province", y="Gross Profit", title="Top 10 states by gross profit"),
        )
        st.caption(f"Top 5 states hold {by_state['Gross Profit'].head(5).sum() / by_state['Gross Profit'].sum() * 100:.1f}% of profit.")
    with b:
        st.plotly_chart(
            px.pie(by_region, names="Region", values="Gross Profit", title="Gross profit by region"),
        )

# ---------------------------------------------------------------------------
# Tab 5: Factories and regions
# ---------------------------------------------------------------------------
with tab5:
    st.subheader("Factory profitability")
    fac = df.groupby("Factory", as_index=False).agg(
        Sales=("Sales", "sum"), Gross_Profit=("Gross Profit", "sum"), Units=("Units", "sum")
    )
    fac["Gross Margin %"] = fac["Gross_Profit"] / fac["Sales"] * 100
    fac["Latitude"] = fac["Factory"].map(lambda f: FACTORY_COORDS.get(f, (None, None))[0])
    fac["Longitude"] = fac["Factory"].map(lambda f: FACTORY_COORDS.get(f, (None, None))[1])
    mapped = fac.dropna(subset=["Latitude"])
    if not mapped.empty:
        fig = px.scatter_geo(
            mapped, lat="Latitude", lon="Longitude", size="Sales", color="Gross Margin %",
            hover_name="Factory", scope="north america", title="Factories (size = sales, colour = margin)",
            color_continuous_scale="RdYlGn",
        )
        st.plotly_chart(fig)
    st.dataframe(fac.drop(columns=["Latitude", "Longitude"]).round(2), hide_index=True)

    st.subheader("Product to factory mapping")
    st.dataframe(
        prod[["Division", "Product Name", "Factory"]].sort_values(["Division", "Factory"]), hide_index=True,
    )

# ---------------------------------------------------------------------------
# Tab 6: Data
# ---------------------------------------------------------------------------
with tab6:
    st.subheader("Product summary (filtered)")
    st.dataframe(prod.round(2), hide_index=True)
    st.download_button(
        "Download product summary as CSV",
        prod.round(2).to_csv(index=False).encode("utf-8"),
        "product_summary.csv",
        "text/csv",
    )
    with st.expander("Cleaned raw data preview"):
        st.dataframe(df.head(500))
