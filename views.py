"""views.py: the seven RouteIQ pages."""
from datetime import date

import numpy as np
import plotly.graph_objects as go
import streamlit as st

import core as C
from core import (ACC, AMB, BLUE, CRIT, DEADLINE_MULT, GREEN, HUB_COL, HUB_FEE, MONTHS, PORTS, PRESETS, RED,
                  STATUS_KIND, VIOLET, WEIGHTS, badge, bar, dark, kpi, page_head, show, table)

ACTIVE = ("Packed", "In transit", "At hub", "Delayed")


def _items(t):
    return [(b, C.status_of(b, t), C.position(b, t)) for b in st.session_state["bookings"] if b["ship_date"] <= t]


def _stat_card(title, value, caption):
    with st.container(border=True):
        st.markdown(f'<div class="card-t">{title}</div>', unsafe_allow_html=True)
        st.markdown(f"<div style='font-size:1.6rem;font-weight:700;color:#fff'>{value}</div>", unsafe_allow_html=True)
        st.caption(caption)


# ----------------------------------------------------------------------------
# 1. Dashboard
# ----------------------------------------------------------------------------
def dashboard():
    t, bks = C.today(), st.session_state["bookings"]
    page_head(f"Welcome, {st.session_state['cfg_name']} 👋",
              f"Operations overview · demo date {t:%d %b %Y} · all data is synthetic")
    tot, act, dlv, rev = C.daily_series(bks, t)
    items = _items(t)
    stat = [s for _, s, _ in items]

    k = st.columns(4)
    with k[0]:
        kpi("📦", "Total shipments", f"{tot[-1]}", f"+{tot[-1] - tot[-8]} this week", "ok", tot, ACC)
    with k[1]:
        kpi("🚢", "In transit", f"{act[-1]}", f"{stat.count('Delayed')} delayed",
            "bad" if stat.count("Delayed") else "ok", act, BLUE)
    with k[2]:
        kpi("✅", "Delivered", f"{dlv[-1]}", f"+{dlv[-1] - dlv[-8]} this week", "ok", dlv, GREEN)
    with k[3]:
        kpi("⚠️", "Needs review", f"{rev[-1]}", f"near-ties (gap < {C.review_gap():.2f})", "warn", rev, AMB)
    st.write("")

    a, b = st.columns([1.8, 1])
    with a, st.container(border=True):
        st.markdown('<div class="card-t">Live shipment map</div>', unsafe_allow_html=True)
        C.fleet_map(items)
        st.caption("Each dot is a booked shipment at its simulated position. Move the demo clock on the Tracking page.")
    with b, st.container(border=True):
        st.markdown('<div class="card-t">Shipment status</div>', unsafe_allow_html=True)
        order = ["In transit", "At hub", "Delayed", "Packed", "Delivered"]
        vals = [stat.count(s) for s in order]
        C.donut(order, vals, [BLUE, ACC, RED, "#8FB3B0", GREEN], str(len(items)), "shipments", h=300)
    st.write("")

    a, b = st.columns([1, 1.6])
    with a, st.container(border=True):
        st.markdown('<div class="card-t">Fleet · MV RouteIQ</div>', unsafe_allow_html=True)
        C.ship3d("MV RouteIQ", f"{len(items)} bookings · {sum(1 for s in stat if s in ACTIVE)} at sea", height=300)
    with b, st.container(border=True):
        st.markdown('<div class="card-t">Delivery schedule</div>', unsafe_allow_html=True)
        rows = []
        live = [x for x in items if x[1] in ACTIVE]
        for bk, s, _ in sorted(live, key=lambda x: C.eta(x[0]))[:6]:
            pg = C.progress(bk, t) * 100
            rows.append([bk["id"], bk["route"], bar(pg) + f"{pg:.0f}%", f"{C.eta(bk):%d %b}",
                         badge(s, STATUS_KIND[s]), f"{bk['on_time'] * 100:.0f}%"])
        if rows:
            table(["ID", "Route", "Progress", "ETA", "Status", "On-time chance"], rows)
        else:
            st.info("No active shipments.")
    st.write("")

    st.markdown('<div class="card-t">RouteIQ vs simple rules (60 demo shipments, USD)</div>', unsafe_allow_html=True)
    ships, strat = C.portfolio_eval(C.wkey(), C.review_gap())
    s = strat.groupby("strategy")[["cost", "expected_days", "on_time"]].mean()
    cols = st.columns(4)
    for col, name, ic, colr in zip(cols, ["Always cheapest", "Always fastest", "Weighted score", "TOPSIS"],
                                   ["💲", "⚡", "🏆", "🎯"], ["#8FB3B0", "#8FB3B0", ACC, VIOLET]):
        with col:
            r = s.loc[name]
            kind = "ok" if r.on_time >= 85 else "warn" if r.on_time >= 70 else "bad"
            kpi(ic, name, f"${r.cost:,.0f}", f"{r.expected_days:.1f} days · {r.on_time:.0f}% on time", kind, None, colr)
    st.write("")

    m = st.columns(3)
    with m[0]:
        _stat_card("Weighted vs TOPSIS agreement", f"{ships.agree.mean() * 100:.0f}%",
                   "Share of shipments where both methods pick the same hub.")
    with m[1]:
        _stat_card("Flagged for human review", f"{ships.flagged.mean() * 100:.0f}%",
                   f"Score gap between top two routes is below {C.review_gap():.2f}.")
    with m[2]:
        _stat_card("Decision stability", f"{ships.stability.mean() * 100:.0f}%",
                   "Same recommendation when priority weights change by ±20%.")


# ----------------------------------------------------------------------------
# 2. Shipping (route recommendation + booking)
# ----------------------------------------------------------------------------
def shipping():
    page_head("Shipping", "Choose a lane and priority to get a recommended route")
    names = list(PORTS)
    with st.container(border=True):
        a, b, c, d = st.columns([1.2, 1.2, 1, 1])
        o_name = a.selectbox("Origin", names, index=names.index("Mumbai, India"), key="sh_o")
        d_name = b.selectbox("Destination", names, index=names.index("New York, USA"), key="sh_d")
        pr = c.radio("Priority", list(WEIGHTS), index=1, horizontal=True, key="sh_pr")
        mo = d.selectbox("Ship month", MONTHS, index=date.today().month - 1, key="sh_mo")
        cargo = st.number_input("Cargo value (USD)", min_value=1000, max_value=5_000_000, value=250_000,
                                step=10_000, key="sh_cargo")
    if o_name == d_name:
        st.warning("Origin and destination must be different.")
        return
    o, d = PORTS[o_name], PORTS[d_name]
    g, base = C.build_options(o_name, o, d_name, d, MONTHS.index(mo) + 1)
    if g is None:
        st.warning(base)
        return

    deadline = base * DEADLINE_MULT[pr]
    r = C.simulate(C.score(g, C.weights_for(pr)), deadline)
    best = r.iloc[0]
    gap = r.score.iloc[1] - best.score
    review = gap < C.review_gap()

    k = st.columns(4)
    with k[0]:
        kpi("🏆", "Recommended hub", best.hub, "needs review" if review else "high confidence", "warn" if review else "ok")
    with k[1]:
        parts = C.money_list(best.cost, o_name, d_name)
        kpi("💲", "Cost", parts[0], "≈ " + " · ".join(parts[1:]) + f" · hub fee ${C.HUB_FEE[best.hub]}", "info")
    with k[2]:
        kpi("⏱️", "Expected days", f"{best.expected_days:.1f}", f"P90: {best.p90:.1f} days", "info")
    with k[3]:
        kpi("🎯", "On-time chance", f"{best.on_time * 100:.0f}%", f"deadline {deadline:.0f} days",
            "ok" if best.on_time >= .85 else "warn" if best.on_time >= .7 else "bad")
    st.write("")

    a, b = st.columns([1.6, 1])
    with a, st.container(border=True):
        st.markdown('<div class="card-t">Route options</div>', unsafe_allow_html=True)
        C.route_map(r, o_name, o, d_name, d)
    with b:
        with st.container(border=True):
            st.markdown('<div class="card-t">Why this route?</div>', unsafe_allow_html=True)
            for line in C.explain(r):
                st.markdown(f"<div style='font-size:.84rem;margin:4px 0'>• {line}</div>", unsafe_allow_html=True)
            if review:
                st.warning(f"Top two routes are almost tied (gap {gap:.2f}). Please review manually.")
        with st.container(border=True):
            C.gauge(best.on_time * 100, deadline)
    st.write("")

    with st.container(border=True):
        st.markdown('<div class="card-t">All options ranked (lower score = better)</div>', unsafe_allow_html=True)
        rows = [[x.route, C.money(x.cost, o_name, d_name), f"{x.expected_days:.1f}", f"{x.delay_p * 100:.1f}%",
                 f"{x.congestion:.0f}", f"{x.geo:.0f}", f"{x.on_time * 100:.0f}%", f"{x.score:.3f}"]
                for x in r.itertuples()]
        table(["Route", "Cost", "Expected days", "Delay chance", "Congestion", "Geopolitical", "On-time", "Score"],
              rows, hl=0)
        st.caption("Costs are shown in the origin and destination currencies using assumed demo exchange rates.")
    st.write("")

    if st.button("📦 Book this shipment"):
        bk = C.add_booking(r, base, o_name, o, d_name, d, pr, cargo)
        st.success(f"Booked {bk['id']} via {bk['hub']}. See it on the Tracking and Invoice pages.")


# ----------------------------------------------------------------------------
# 3. Tracking
# ----------------------------------------------------------------------------
def tracking():
    page_head("Tracking", "Follow a booked shipment on the map")
    bks = st.session_state["bookings"]
    with st.container(border=True):
        a, b = st.columns([1.6, 1])
        pick = a.selectbox("Shipment", list(reversed(bks)), format_func=lambda x: f"{x['id']} · {x['route']}", key="trk_pick")
        b.slider("Demo clock (days ahead)", min_value=0, max_value=60, key="sim_days")
    t = C.today()
    status, pos, pg = C.status_of(pick, t), C.position(pick, t), C.progress(pick, t)

    k = st.columns(4)
    with k[0]:
        kpi("📍", "Status", status, "", STATUS_KIND[status])
    with k[1]:
        kpi("📈", "Progress", f"{pg * 100:.0f}%", f"ETA {C.eta(pick):%d %b %Y}", "info")
    with k[2]:
        kpi("🎯", "On-time chance", f"{pick['on_time'] * 100:.0f}%", f"deadline {pick['deadline']:.0f} days", "info")
    with k[3]:
        parts = C.money_list(pick["cost"], pick["origin"], pick["dest"])
        kpi("💲", "Freight cost", parts[0], "≈ " + " · ".join(parts[1:]) + f" · {pick['priority']}", "mute")
    st.write("")

    a, b = st.columns([1.8, 1])
    with a, st.container(border=True):
        st.markdown('<div class="card-t">Ship position</div>', unsafe_allow_html=True)
        C.track_map(pick, pos)
    with b, st.container(border=True):
        st.markdown('<div class="card-t">Journey</div>', unsafe_allow_html=True)
        stages = [(f"Booked · {pick['origin'].split(',')[0]}", f"{pick['ship_date']:%d %b %Y}", True),
                  ("Left origin port", "", pg >= 0.06),
                  (f"Reached hub · {pick['hub']}", "", pg >= pick["leg_share"]),
                  (f"Delivered · {pick['dest'].split(',')[0]}", f"ETA {C.eta(pick):%d %b}", pg >= 1)]
        html, now_set = "", False
        for title, sub, done in stages:
            cls = "done" if done else ("now" if not now_set else "")
            if not done:
                now_set = True
            html += f'<div class="step {cls}"><span class="pt"></span><div><b>{title}</b><small>{sub}</small></div></div>'
        st.markdown(f'<div class="steps">{html}</div>', unsafe_allow_html=True)


# ----------------------------------------------------------------------------
# 4. Invoice
# ----------------------------------------------------------------------------
def invoice():
    page_head("Invoice", "Cost breakdown for a booked shipment")
    bks = st.session_state["bookings"]
    pick = st.selectbox("Shipment", list(reversed(bks)), format_func=lambda x: f"{x['id']} · {x['route']}", key="inv_pick")
    freight = pick["cost"]
    fee = HUB_FEE[pick["hub"]]
    insurance = pick["cargo"] * 0.003                       # assumed 0.3% of cargo value
    holding = pick["cargo"] * C.holding() * pick["planned"]  # holding cost per day x planned days
    total = freight + fee + insurance + holding
    delivered = C.status_of(pick, C.today()) == "Delivered"
    o, dn = pick["origin"], pick["dest"]

    with st.container(border=True):
        stamp = '<span class="stamp">PAID</span>' if delivered else '<span class="stamp">DUE</span>'
        rows = [("Ocean freight", freight), (f"Hub handling fee ({pick['hub']})", fee),
                ("Cargo insurance (0.3% assumed)", insurance),
                (f"Inventory holding ({st.session_state['cfg_holding']}%/day × {pick['planned']:.1f} days)", holding)]
        body = "".join(f"<tr><td>{n}</td><td style='text-align:right'>{C.money(v, o, dn)}</td></tr>" for n, v in rows)
        st.markdown(
            f"""<div class="inv">
            <div style="display:flex;justify-content:space-between"><div><b style="font-size:1.1rem">Invoice {pick['id']}</b><br>
            <small>{st.session_state['cfg_company']}</small></div>{stamp}</div><br>
            <div style="font-size:.84rem">Route: <b>{pick['route']}</b><br>Priority: {pick['priority']} ·
            Cargo value: ${pick['cargo']:,.0f} · Shipped {pick['ship_date']:%d %b %Y}</div><br>
            <table class="rt">{body}<tr class="tot"><td>Total</td><td style="text-align:right">{C.money(total, o, dn)}</td></tr></table>
            </div>""", unsafe_allow_html=True)
        st.caption("Demo invoice. Fees, insurance rate, holding cost and exchange rates are assumptions.")


# ----------------------------------------------------------------------------
# 5. Compare scenarios
# ----------------------------------------------------------------------------
def compare_scenarios():
    page_head("Compare", "Same lane, three priorities: see how the recommendation changes")
    names = list(PORTS)
    with st.container(border=True):
        a, b, c = st.columns(3)
        o_name = a.selectbox("Origin", names, index=names.index("Shanghai, China"), key="cmp_o")
        d_name = b.selectbox("Destination", names, index=names.index("Hamburg, Germany"), key="cmp_d")
        mo = c.selectbox("Ship month", MONTHS, index=date.today().month - 1, key="cmp_mo")
    if o_name == d_name:
        st.warning("Origin and destination must be different.")
        return
    o, d = PORTS[o_name], PORTS[d_name]
    g, base = C.build_options(o_name, o, d_name, d, MONTHS.index(mo) + 1)
    if g is None:
        st.warning(base)
        return

    cols = st.columns(3)
    results = {}
    for col, pr in zip(cols, WEIGHTS):
        W = C.weights_for(pr)
        r = C.simulate(C.score(g, W), base * DEADLINE_MULT[pr])
        tp = C.topsis(r, W)
        results[pr] = r
        best, t_hub = r.iloc[0], r.iloc[int(np.argmax(tp))].hub
        with col, st.container(border=True):
            st.markdown(f'<div class="card-t">{pr}</div>', unsafe_allow_html=True)
            st.markdown(f"<div style='font-size:1.5rem;font-weight:700;color:{HUB_COL[best.hub]}'>{best.hub}</div>",
                        unsafe_allow_html=True)
            st.caption(f"{C.money(best.cost, o_name, d_name)} · {best.expected_days:.1f} days · {best.on_time * 100:.0f}% on time")
            st.caption(f"TOPSIS pick: {t_hub} ({'agrees' if t_hub == best.hub else 'differs'})")
    st.write("")

    a, b = st.columns(2)
    with a, st.container(border=True):
        st.markdown('<div class="card-t">Cost by hub (USD)</div>', unsafe_allow_html=True)
        r = results["Standard"]
        fig = go.Figure(go.Bar(x=r.hub, y=r.cost, marker_color=[HUB_COL[h] for h in r.hub], text=r.cost.round(0),
                               textposition="outside"))
        show(dark(fig, 300))
    with b, st.container(border=True):
        st.markdown('<div class="card-t">Expected days by hub</div>', unsafe_allow_html=True)
        fig = go.Figure(go.Bar(x=r.hub, y=r.expected_days, marker_color=[HUB_COL[h] for h in r.hub],
                               text=r.expected_days.round(1), textposition="outside"))
        show(dark(fig, 300))


# ----------------------------------------------------------------------------
# 6. Reports
# ----------------------------------------------------------------------------
def reports():
    page_head("Reports", "How RouteIQ performs across 60 demo shipments")
    ships, strat = C.portfolio_eval(C.wkey(), C.review_gap())
    s = strat.groupby("strategy")[["cost", "expected_days", "on_time"]].mean().round(2)

    k = st.columns(4)
    with k[0]:
        kpi("📦", "Shipments evaluated", f"{len(ships)}", "", "info")
    with k[1]:
        kpi("🤝", "Methods agree", f"{ships.agree.mean() * 100:.0f}%", "Weighted vs TOPSIS", "ok")
    with k[2]:
        kpi("⚠️", "Flagged", f"{ships.flagged.mean() * 100:.0f}%", f"gap < {C.review_gap():.2f}", "warn")
    with k[3]:
        kpi("🛡️", "Avg stability", f"{ships.stability.mean() * 100:.0f}%", "weights ±20%", "ok")
    st.write("")

    a, b = st.columns(2)
    with a, st.container(border=True):
        st.markdown('<div class="card-t">On-time % by strategy</div>', unsafe_allow_html=True)
        fig = go.Figure(go.Bar(x=s.index, y=s.on_time, marker_color=["#8FB3B0", "#8FB3B0", ACC, VIOLET],
                               text=s.on_time.round(0), textposition="outside"))
        show(dark(fig, 300))
    with b, st.container(border=True):
        st.markdown('<div class="card-t">Average cost by strategy (USD)</div>', unsafe_allow_html=True)
        fig = go.Figure(go.Bar(x=s.index, y=s.cost, marker_color=["#8FB3B0", "#8FB3B0", ACC, VIOLET],
                               text=s.cost.round(0), textposition="outside"))
        show(dark(fig, 300))
    st.write("")

    a, b = st.columns(2)
    with a, st.container(border=True):
        st.markdown('<div class="card-t">Results by priority (Weighted score)</div>', unsafe_allow_html=True)
        w = strat[strat.strategy == "Weighted score"].groupby("priority")[["cost", "expected_days", "on_time"]].mean()
        table(["Priority", "Avg cost", "Avg days", "On-time"],
              [[p, f"${r.cost:,.0f}", f"{r.expected_days:.1f}", f"{r.on_time:.0f}%"] for p, r in w.iterrows()])
    with b, st.container(border=True):
        st.markdown('<div class="card-t">Decision stability (1.0 = never changes)</div>', unsafe_allow_html=True)
        fig = go.Figure(go.Histogram(x=ships.stability, nbinsx=10, marker_color=ACC))
        show(dark(fig, 240))
    st.write("")

    with st.container(border=True):
        st.markdown('<div class="card-t">Most fragile decisions: review these manually</div>', unsafe_allow_html=True)
        frag = ships.sort_values("stability").head(6)
        table(["Lane", "Priority", "Month", "Weighted", "TOPSIS", "Score gap", "Stability"],
              [[x.lane, x.priority, x.month, x.weighted, x.topsis, f"{x.gap:.2f}", f"{x.stability * 100:.0f}%"]
               for x in frag.itertuples()])


# ----------------------------------------------------------------------------
# 7. Settings
# ----------------------------------------------------------------------------
def settings():
    page_head("Settings", "Profile, decision weights and demo controls")
    with st.container(border=True):
        st.markdown('<div class="card-t">Profile</div>', unsafe_allow_html=True)
        a, b, c = st.columns(3)
        a.text_input("Name", key="cfg_name")
        b.text_input("Role", key="cfg_role")
        c.text_input("Company", key="cfg_company")
    st.write("")

    with st.container(border=True):
        st.markdown('<div class="card-t">Decision weights (relative; they are normalised automatically)</div>',
                    unsafe_allow_html=True)
        cols = st.columns(3)
        for col, p in zip(cols, WEIGHTS):
            with col:
                st.markdown(f"**{p}**")
                for kx in CRIT:
                    st.slider(kx.capitalize(), min_value=0, max_value=100, key=f"w_{p}_{kx}")
    st.write("")

    with st.container(border=True):
        st.markdown('<div class="card-t">Business rules</div>', unsafe_allow_html=True)
        a, b, c = st.columns(3)
        a.number_input("Holding cost (% of cargo value per day)", min_value=0.0, max_value=1.0, step=0.01,
                       format="%.2f", key="cfg_holding")
        b.number_input("Review gap (flag when top-two score gap is below)", min_value=0.0, max_value=0.5, step=0.01,
                       format="%.2f", key="cfg_gap")
        c.number_input("USD → INR rate (demo)", min_value=50.0, max_value=150.0, step=0.5, format="%.1f", key="cfg_inr")
    st.write("")

    c1, c2 = st.columns(2)
    if c1.button("↺ Reset demo clock"):
        st.session_state["sim_days"] = 0
        st.rerun()
    if c2.button("🗑️ Reset demo bookings"):
        st.session_state["bookings"] = C.seed_bookings()
        st.rerun()
