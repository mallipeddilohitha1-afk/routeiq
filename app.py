"""RouteIQ: shipment route recommender. Run with:  streamlit run app.py"""
import streamlit as st

st.set_page_config(page_title="RouteIQ · Shipment Route Recommender", page_icon="🚢", layout="wide",
                   initial_sidebar_state="collapsed")

import core  # noqa: E402
import views  # noqa: E402

core.inject_css()
core.init_state()

PAGES = {
    "dashboard": st.Page(views.dashboard, title="Dashboard", icon="📊", url_path="dashboard", default=True),
    "shipping": st.Page(views.shipping, title="Shipping", icon="🚢", url_path="shipping"),
    "tracking": st.Page(views.tracking, title="Tracking", icon="📍", url_path="tracking"),
    "invoice": st.Page(views.invoice, title="Invoice", icon="🧾", url_path="invoice"),
    "compare": st.Page(views.compare_scenarios, title="Compare", icon="⚖️", url_path="compare"),
    "reports": st.Page(views.reports, title="Reports", icon="📈", url_path="reports"),
    "settings": st.Page(views.settings, title="Settings", icon="⚙️", url_path="settings"),
}
st.session_state["_pages"] = PAGES
st.navigation(list(PAGES.values()), position="top").run()