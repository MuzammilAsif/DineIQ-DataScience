import plotly.express as px
import streamlit as st

import data_loader as dl
import ui

user, f = ui.page("Wastage Dashboard")

with ui.guard("Could not load wastage data."):
    w = ui.filter_df(dl.wastage(), f, date_col="date", loc_col="location_id",
                     cat_col="category_name", cls_col="category")
    sales = ui.filter_df(dl.daily_item_sales(), f, date_col="date", loc_col="location_id",
                         cat_col="category_name")
ui.applied(f, ["date", "location", "category", "class"])
if w.empty:
    st.warning("No wastage records match the current filters.")
    st.stop()

cost, revenue = w.cost_of_waste.sum(), sales.revenue.sum()
c = st.columns(4)
c[0].metric("Wastage cost", ui.money_short(cost))
c[1].metric("As share of sales", f"{cost / revenue:.1%}" if revenue else "n/a")
c[2].metric("Wastage records", f"{len(w):,}")
c[3].metric("Items affected", f"{w.item_id.nunique():,}")

st.subheader("Weekly trend")
weekly = w.set_index("date").resample("W").cost_of_waste.sum().reset_index()
ui.chart(px.line(weekly, x="date", y="cost_of_waste",
                        labels={"cost_of_waste": "Wastage cost (PKR)", "date": ""}),
                width="stretch")
peak = weekly.loc[weekly.cost_of_waste.idxmax()]
ui.takeaway(f"The worst week began {peak.date:%d %b} ({ui.money(peak.cost_of_waste)}), "
            f"{peak.cost_of_waste / weekly.cost_of_waste.median():.1f}x the median week.")

left, right = st.columns(2)
items = (w.groupby(["item_name", "category_name"], as_index=False).cost_of_waste.sum()
         .sort_values("cost_of_waste", ascending=False))
with left:
    st.subheader("Highest-wastage items")
    ui.chart(px.bar(items.head(10), x="cost_of_waste", y="item_name", orientation="h",
                           labels={"cost_of_waste": "PKR", "item_name": ""}).update_yaxes(
        autorange="reversed"), width="stretch")
    top3 = items.head(3).cost_of_waste.sum() / cost
    ui.takeaway(f"The top 3 items ({', '.join(items.head(3).item_name)}) account for {top3:.0%} "
                "of wastage cost.")
with right:
    st.subheader("Highest-wastage locations")
    locs = w.groupby("location_id", as_index=False).cost_of_waste.sum()
    loc_sales = sales.groupby("location_id", as_index=False).revenue.sum()
    locs = locs.merge(loc_sales, on="location_id", how="left")
    locs["wastage_rate"] = locs.cost_of_waste / locs.revenue
    locs["location"] = locs.location_id.map(f["location_names"])
    locs = locs.sort_values("wastage_rate", ascending=False)
    st.dataframe(locs[["location", "cost_of_waste", "revenue", "wastage_rate"]].head(10),
                 hide_index=True, width="stretch",
                 column_config={"wastage_rate": st.column_config.NumberColumn(format="percent")})
    if len(locs) > 1:
        ui.takeaway(f"{locs.iloc[0].location} wastes the most relative to sales "
                    f"({locs.iloc[0].wastage_rate:.1%}), against {locs.iloc[-1].wastage_rate:.1%} at "
                    f"{locs.iloc[-1].location}.")

st.subheader("Reasons")
reasons = w.groupby("reason", as_index=False).cost_of_waste.sum().sort_values("cost_of_waste",
                                                                              ascending=False)
ui.chart(px.bar(reasons, x="reason", y="cost_of_waste",
                       labels={"cost_of_waste": "PKR", "reason": ""}), width="stretch")
top_reason = reasons.iloc[0].reason
cause = {"Overproduction": "preparation planning", "PrepError": "kitchen process",
         "Spoilage": "storage", "Expired": "stock rotation",
         "CustomerReturn": "dish quality"}.get(top_reason, "operations")
ui.takeaway(f"{top_reason} is the largest cause ({reasons.iloc[0].cost_of_waste / cost:.0%} of "
            f"cost), so the first fix is in {cause}.")

st.subheader("Wastage-risk predictions")
with ui.guard("Could not load wastage-risk predictions."):
    r = ui.filter_df(dl.wastage_risk(), f, date_col="date", loc_col="location_id")
    r = r.merge(dl.classification()[["item_id", "item_name", "category_name"]], on="item_id")
    r = ui.filter_df(r, f, cat_col="category_name")
if r.empty:
    st.caption(f"Risk predictions cover the model's test period ({dl.wastage_risk().date.min():%d %b} "
               f"to {dl.wastage_risk().date.max():%d %b}); widen the date range to see them.")
else:
    flagged = r[r.predicted_risk == 1]
    hit = (flagged.high_wastage_risk == 1).mean() if len(flagged) else 0
    c = st.columns(3)
    c[0].metric("Item-days predicted high risk", f"{len(flagged):,}", f"of {len(r):,}",
                delta_color="off")
    c[1].metric("Of those, actually high wastage", f"{hit:.0%}")
    c[2].metric("High-wastage days caught",
                f"{(r[r.high_wastage_risk == 1].predicted_risk == 1).mean():.0%}")
    pairs = (r.groupby(["item_name", "location_id"], as_index=False)
             .agg(avg_risk=("risk_probability", "mean"), predicted_days=("predicted_risk", "sum"))
             .sort_values("avg_risk", ascending=False))
    st.dataframe(pairs.head(15), hide_index=True, width="stretch")
    ui.download_df(pairs, "wastage_risk_pairs")
    ui.takeaway(f"The model flags {len(flagged):,} item-days as high risk. {hit:.0%} of those "
                "really wasted more than 10% of the day's preparation, against a "
                f"{(r.high_wastage_risk == 1).mean():.1%} base rate. Watch the pairs at the top of "
                "this list when planning prep.")
