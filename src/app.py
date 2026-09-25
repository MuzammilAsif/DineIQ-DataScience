"""DineIQ Analytics web app. Run from the project root: .venv/bin/streamlit run src/app.py"""
import streamlit as st

import auth
import data_loader as dl

st.set_page_config(page_title="DineIQ Analytics", layout="wide")

if "user" not in st.session_state:
    st.title("DineIQ Analytics")
    st.caption("Restaurant intelligence for the DineIQ chain. Please sign in.")
    with st.form("login"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign in")
    if submitted:
        try:
            ok = auth.login(st.session_state, username, password)
        except Exception as e:  # noqa: BLE001
            st.error(f"Login is unavailable: the user database could not be read ({type(e).__name__}). "
                     "Run database/init_db.py.")
            st.stop()
        if ok:
            st.rerun()
        st.error("Incorrect username or password.")
    st.stop()

user = st.session_state["user"]
st.title("DineIQ Analytics")
st.write(f"Signed in as **{user['full_name'] or user['username']}** ({user['role']}). "
         f"Data covers 1 Jan to 31 Dec 2025; snapshot tables are as of {dl.as_of()}.")
if st.button("Log out"):
    auth.logout(st.session_state)
    st.rerun()

PAGES = [
    ("pages/1_Executive_Dashboard.py", "Executive Dashboard", "Revenue, profit, customers, wastage, forecast and critical actions", auth.ALL_ROLES),
    ("pages/2_Menu_Dashboard.py", "Menu Dashboard", "Menu performance classes, margins, ratings, slow movers", auth.ALL_ROLES),
    ("pages/3_Customer_Dashboard.py", "Customer Dashboard", "Segments, RFM, high-value, at-risk and promotion-sensitive customers", auth.ALL_ROLES),
    ("pages/4_Wastage_Dashboard.py", "Wastage Dashboard", "Wastage cost, trends, worst items and locations, risk predictions", auth.ALL_ROLES),
    ("pages/5_Forecast_Dashboard.py", "Forecast Dashboard", "Demand forecast vs actual, accuracy against the baseline", auth.ALL_ROLES),
    ("pages/6_DualPipeline_Dashboard.py", "Dual-Pipeline Dashboard", "Spark vs Python results and agreement", auth.MANAGERS_AND_ANALYSTS),
    ("pages/7_Recommendations.py", "Recommendations", "Prioritised actions with evidence", auth.ALL_ROLES),
    ("pages/8_WhatIf_Simulator.py", "What-If Simulator", "Estimate the effect of price, promotion, prep and demand changes", auth.ALL_ROLES),
    ("pages/9_Admin.py", "Admin", "Users, master data, model registry, audit log, job monitoring", ["Administrator"]),
]
for path, label, desc, roles in PAGES:
    if user["role"] in roles:
        st.page_link(path, label=label)
        st.caption(desc)
