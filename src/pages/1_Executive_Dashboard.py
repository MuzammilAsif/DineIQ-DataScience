import plotly.express as px
import streamlit as st

import data_loader as dl
import db
import ui

user, f = ui.page("Executive Dashboard")

with ui.guard("Could not load order data."):
    o = ui.filter_df(dl.orders(), f, date_col="date", loc_col="location_id")
done = o[o.order_status != dl.CANCELLED]
if done.empty:
    st.warning("No completed orders match the current filters.")
    st.stop()

revenue = (done.subtotal - done.discount_amount).sum()
profit = done.margin.sum()
n_orders = len(done)
per_cust = done.groupby("customer_id").size()
active, repeat = len(per_cust), int((per_cust >= 2).sum())

with ui.guard("Could not load wastage data."):
    w = ui.filter_df(dl.wastage(), f, date_col="date", loc_col="location_id")
waste = w.cost_of_waste.sum()

ui.applied(f, ["date", "location"])
c = st.columns(4)
c[0].metric("Net sales", ui.money_short(revenue))
c[1].metric("Gross profit", ui.money_short(profit), f"{profit / revenue:.1%} margin", delta_color="off")
c[2].metric("Completed orders", f"{n_orders:,}")
c[3].metric("Average order value", ui.money_short(revenue / n_orders))
c = st.columns(4)
c[0].metric("Active customers", f"{active:,}")
c[1].metric("Repeat customers", f"{repeat:,}", f"{repeat / active:.1%} of active", delta_color="off")
c[2].metric("Wastage cost", ui.money_short(waste), f"{waste / revenue:.1%} of net sales", delta_color="off")
c[3].metric("Cancellation rate", f"{(o.order_status == dl.CANCELLED).mean():.1%}")

st.subheader("Sales trend")
daily = (done.assign(net=done.subtotal - done.discount_amount)
         .groupby("date", as_index=False).agg(net_sales=("net", "sum"), orders=("order_id", "count")))
daily["7-day average"] = daily.net_sales.rolling(7, min_periods=1).mean()
fig = px.line(daily, x="date", y=["net_sales", "7-day average"],
              labels={"value": "Net sales (PKR)", "date": "", "variable": ""})
ui.chart(fig, width="stretch")
monthly = daily.groupby(daily.date.dt.to_period("M").dt.to_timestamp()).net_sales.sum()
if len(monthly) >= 2:
    best = monthly.idxmax()
    ui.takeaway(f"Net sales went from {ui.money(monthly.iloc[0])} in {monthly.index[0]:%b} to "
                f"{ui.money(monthly.iloc[-1])} in {monthly.index[-1]:%b} "
                f"({monthly.iloc[-1] / monthly.iloc[0] - 1:+.0%}). The best month was {best:%B} "
                f"({ui.money(monthly.max())}). Gross margin over the period is {profit / revenue:.1%}, "
                f"and {repeat / active:.0%} of active customers ordered more than once.")

if not f["locations"] or len(f["locations"]) > 1:
    by_loc = (done.assign(net=done.subtotal - done.discount_amount)
              .groupby("location_id", as_index=False).net.sum().sort_values("net", ascending=False))
    by_loc["location"] = by_loc.location_id.map(f["location_names"])
    st.subheader("Net sales by location")
    ui.chart(px.bar(by_loc, x="location", y="net", labels={"net": "Net sales (PKR)",
                                                                  "location": ""}),
                    width="stretch")
    top, low = by_loc.iloc[0], by_loc.iloc[-1]
    ui.takeaway(f"{top.location} leads with {ui.money(top.net)}, {top.net / low.net:.1f}x "
                f"{low.location} ({ui.money(low.net)}).")

st.subheader("Demand forecast")
with ui.guard("Could not load the demand forecast."):
    level = "location_day" if f["locations"] else "overall_day"
    fc = dl.forecast(level)
    if f["locations"]:
        fc = fc[fc.location_id.isin(f["locations"])]
    fc = fc.groupby("target_date", as_index=False)[["forecast", "actual", "recent_average"]].sum()
days = len(fc)
c = st.columns(3)
c[0].metric("Forecast units, latest window", f"{fc.forecast.sum():,.0f}",
            f"{fc.target_date.min():%d %b} to {fc.target_date.max():%d %b}", delta_color="off")
c[1].metric("Recent level over the same days", f"{fc.recent_average.sum():,.0f}")
c[2].metric("Actual units sold", f"{fc.actual.sum():,.0f}")
ui.takeaway(f"The model forecasts {fc.forecast.sum():,.0f} units over the {days}-day window, "
            f"{fc.forecast.sum() / fc.recent_average.sum() - 1:+.0%} against the recent daily level, "
            f"and actual sales came to {fc.actual.sum():,.0f} "
            f"({fc.forecast.sum() / fc.actual.sum() - 1:+.1%} forecast error). This window is the "
            "held-out test period of the forecast model (see the Forecast Dashboard).")

left, right = st.columns(2)
with left:
    st.subheader("Critical recommendations")
    with ui.guard("Could not load recommendations."):
        recs = dl.recommendations()
    crit = recs[recs.priority == "Critical"]
    ui.takeaway(f"{len(crit)} of {len(recs)} recommendations are Critical: "
                + ", ".join(f"{v} {k.lower()}" for k, v in crit.type.value_counts().items()) + ".")
    for r in crit.head(8).itertuples():
        st.markdown(f"**{r.action}**  \n" + "  \n".join(f"- {e}" for e in r.evidence[:2]))
with right:
    st.subheader("Recent anomalies")
    with ui.guard("Could not load anomalies."):
        a = dl.anomalies()
    a = a[a.anomaly_type.isin(["location_sales_z", "high_order_value", "rating_z"])]
    a = ui.filter_df(a, f, date_col="period_start")
    if f["locations"]:
        a = a[a.location_id.isin(f["locations"])]
    a = a.sort_values("period_start", ascending=False)
    a = a.assign(period_start=a.period_start.dt.date)
    st.dataframe(a[["period_start", "anomaly_type", "entity_id", "location_id", "metric", "value",
                    "score"]].head(15), hide_index=True, width="stretch")
    if len(a):
        ui.takeaway(f"{len(a):,} anomalies in the selected range; the most recent was "
                    f"{a.iloc[0].anomaly_type.replace('_', ' ')} on {a.iloc[0].period_start:%d %b}.")

st.subheader("Download reports")
files = dl.report_files()
choice = st.selectbox("Report", files, format_func=lambda p: p.name)
st.download_button("Download report", choice.read_bytes(), file_name=choice.name,
                   mime="text/markdown", on_click=db.log,
                   args=(user["id"], "export_report", choice.name))
