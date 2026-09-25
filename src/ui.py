"""Shared page setup: access check, global sidebar filters, takeaways, downloads, errors."""
import datetime as dt
from contextlib import contextmanager

import pandas as pd
import plotly.express as px
import streamlit as st

import auth
import data_loader as dl
import db

CLASSES = ["Profit Driver", "Volume Driver", "Hidden Opportunity", "Low Performer",
           "Insufficient History"]
DATA_START, DATA_END = dt.date(2025, 1, 1), dt.date(2025, 12, 31)
PALETTE = ["#C8102E", "#1A1A1A", "#8C8C8C", "#E8707F", "#5C0613", "#BDBDBD", "#F2B8C0"]

px.defaults.color_discrete_sequence = PALETTE
px.defaults.color_continuous_scale = ["#FBE7EA", "#C8102E"]


def page(title, allowed=auth.ALL_ROLES):
    st.set_page_config(page_title=f"DineIQ · {title}", layout="wide")
    user = auth.require(allowed)
    st.title(title)
    filters = sidebar(user)
    return user, filters


def _persisted(key, default):
    return st.session_state.get(f"flt_{key}", default)


def _keep(key):
    st.session_state[f"flt_{key}"] = st.session_state[f"w_{key}"]


def sidebar(user):
    with st.sidebar:
        st.markdown(f"**{user['full_name'] or user['username']}**  \n{user['role']}")
        if st.button("Log out"):
            db.log(user["id"], "logout")
            auth.logout(st.session_state)
            st.rerun()
        st.divider()
        st.subheader("Filters")
        with guard("Could not load filter options."):
            locs = dl.locations()[["location_id", "location_name"]].sort_values("location_id")
            names = dict(zip(locs.location_id, locs.location_name))
            cats = sorted(dl.classification().category_name.dropna().unique())
        dates = st.date_input("Date range", _persisted("dates", (DATA_START, DATA_END)),
                              min_value=DATA_START, max_value=DATA_END, key="w_dates",
                              on_change=_keep, args=("dates",))
        if user["role"] == "Restaurant Manager" and user.get("assigned_location_id"):
            loc = [user["assigned_location_id"]]
            st.caption(f"Location: {names.get(loc[0], loc[0])} (your assigned restaurant)")
        else:
            loc = st.multiselect("Location", list(names), _persisted("loc", []),
                                 format_func=lambda x: f"{x} · {names[x]}", key="w_loc",
                                 on_change=_keep, args=("loc",))
        cat = st.multiselect("Menu category", cats, _persisted("cat", []), key="w_cat",
                             on_change=_keep, args=("cat",))
        cls = st.multiselect("Performance class", CLASSES, _persisted("cls", []), key="w_cls",
                             on_change=_keep, args=("cls",))
    start, end = (dates if isinstance(dates, (tuple, list)) and len(dates) == 2
                  else (DATA_START, DATA_END))
    return dict(start=pd.Timestamp(start), end=pd.Timestamp(end), locations=loc,
                categories=cat, classes=cls, location_names=names)


def filter_df(df, f, date_col=None, loc_col=None, cat_col=None, cls_col=None):
    if date_col:
        df = df[(df[date_col] >= f["start"]) & (df[date_col] <= f["end"])]
    if loc_col and f["locations"]:
        df = df[df[loc_col].isin(f["locations"])]
    if cat_col and f["categories"]:
        df = df[df[cat_col].isin(f["categories"])]
    if cls_col and f["classes"]:
        df = df[df[cls_col].isin(f["classes"])]
    return df


def applied(f, used):
    """Caption listing which of the global filters this section applies."""
    parts = []
    if "date" in used:
        parts.append(f"{f['start']:%d %b %Y} to {f['end']:%d %b %Y}")
    if "location" in used:
        parts.append(f"{len(f['locations'])} location(s)" if f["locations"] else "all locations")
    if "category" in used:
        parts.append(", ".join(f["categories"]) if f["categories"] else "all categories")
    if "class" in used:
        parts.append(", ".join(f["classes"]) if f["classes"] else "all classes")
    st.caption("Filters applied: " + "; ".join(parts) if parts else "Global filters do not apply here.")


def chart(fig, container=None, **kw):
    fig.update_layout(template="plotly_white", plot_bgcolor="#FFFFFF", paper_bgcolor="#FFFFFF",
                      colorway=PALETTE, piecolorway=PALETTE)
    fig.update_xaxes(gridcolor="#EAEAEA")
    fig.update_yaxes(gridcolor="#EAEAEA")
    kw.setdefault("width", "stretch")
    (container or st).plotly_chart(fig, theme=None, **kw)


def takeaway(text):
    st.info(text)


def download_df(df, name, label="Download CSV"):
    user = st.session_state.get("user", {})
    st.download_button(label, df.to_csv(index=False).encode(), file_name=f"{name}.csv",
                       mime="text/csv", key=f"dl_{name}",
                       on_click=db.log, args=(user.get("id"), "export_csv", name))


@contextmanager
def guard(message):
    """Shows a plain error instead of a stack trace and stops the page."""
    try:
        yield
    except Exception as e:  # noqa: BLE001
        st.error(f"{message} ({type(e).__name__})")
        st.stop()


def money(v):
    return f"PKR {v:,.0f}"


def money_short(v):
    """For KPI tiles, where long numbers get cut off."""
    for div, unit in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(v) >= div:
            return f"PKR {v / div:,.1f}{unit}"
    return f"PKR {v:,.0f}"


def pct(v):
    return f"{v:.1%}"
