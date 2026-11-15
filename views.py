"""views.py: the seven RouteIQ pages. The Dashboard is built from the notebook's dataset and logic."""
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import core as C
from core import (ACC, AMB, BLUE, CRIT, DEADLINE_MULT, GREEN, HUB_COL, MONTHS, PORTS, RED,
                  STATUS_KIND, VIOLET, WEIGHTS, dark, kpi, page_head, show, table)

# ----------------------------------------------------------------------------
# Notebook assumptions (identical to the notebook)
# ----------------------------------------------------------------------------
CSV = Path(__file__).parent / "shipments.csv"
REVIEW_GAP = 0.05                                    # the notebook's confidence threshold
MUTED = "#8FB3B0"
ROUTE_PROFILES = {
    "Singapore":  {"cost_factor": 1.20, "time_factor": 0.80, "delay": 0.08, "congestion": 25, "geopolitical": 15, "late_days": 2},
    "Dubai":      {"cost_factor": 1.00, "time_factor": 0.90, "delay": 0.16, "congestion": 60, "geopolitical": 45, "late_days": 3},
    "Colombo":    {"cost_factor": 0.85, "time_factor": 1.25, "delay": 0.25, "congestion": 55, "geopolitical": 35, "late_days": 5},
    "Port Klang": {"cost_factor": 1.05, "time_factor": 1.10, "delay": 0.10, "congestion": 20, "geopolitical": 5,  "late_days": 2},
}
SHIPPING_LANES = [("India", "USA", 2000, 30), ("China", "Germany", 2500, 35), ("Japan", "UK", 2300, 32),
                  ("Singapore", "Canada", 2200, 34), ("India", "Australia", 1500, 20)]
PRIORITIES = ["Urgent", "Standard", "Economy"]
STRATS = ["cheapest", "fastest", "lowest_risk", "our_system"]
STRAT_NAME = {"cheapest": "Always cheapest", "fastest": "Always fastest",
              "lowest_risk": "Lowest risk", "our_system": "RouteIQ (weighted)"}
REQUIRED = {"shipment_id", "route_id", "origin", "destination", "intermediate_hub", "priority", "cargo_value_usd",
            "shipping_cost_usd", "estimated_transit_days", "delay_probability", "delay_days_if_late",
            "congestion_risk", "geopolitical_risk"}


# ----------------------------------------------------------------------------
# Notebook data and scoring
# ----------------------------------------------------------------------------
def _generate_dataset(seed=42, n=30):
    """Same generator as the notebook (used only if shipments.csv is missing)."""
    rng = np.random.default_rng(seed)
    rows = []
    for k in range(1, n + 1):
        origin, dest, base_cost, base_days = SHIPPING_LANES[rng.integers(0, len(SHIPPING_LANES))]
        priority = str(rng.choice(PRIORITIES, p=[0.25, 0.5, 0.25]))
        cargo_value = float(round(rng.uniform(20_000, 500_000), -2))
        for hub, p in ROUTE_PROFILES.items():
            if hub in (origin, dest):
                continue
            rows.append({
                "shipment_id": f"SHP{k:03d}", "route_id": f"{origin} → {hub} → {dest}",
                "origin": origin, "destination": dest, "intermediate_hub": hub,
                "priority": priority, "cargo_value_usd": cargo_value,
                "shipping_cost_usd": round(base_cost * p["cost_factor"] * rng.uniform(0.90, 1.10) * rng.uniform(0.96, 1.04), 2),
                "estimated_transit_days": round(base_days * p["time_factor"] * rng.uniform(0.94, 1.06), 2),
                "delay_probability": round(float(np.clip(p["delay"] + rng.normal(0, 0.025), 0.01, 0.60)), 3),
                "delay_days_if_late": round(max(1, p["late_days"] + rng.normal(0, 0.7)), 1),
                "congestion_risk": round(float(np.clip(p["congestion"] + rng.normal(0, 7), 0, 100)), 2),
                "geopolitical_risk": round(float(np.clip(p["geopolitical"] + rng.normal(0, 5), 0, 100)), 2),
            })
    return pd.DataFrame(rows)


@st.cache_data(show_spinner=False)
def _base_data():
    return pd.read_csv(CSV) if CSV.exists() else _generate_dataset()


def _prepare(df):
    df = df.copy()
    grp = df.groupby("shipment_id")
    df["cost_index"] = df.shipping_cost_usd / grp.shipping_cost_usd.transform("mean")
    df["time_index"] = df.estimated_transit_days / grp.estimated_transit_days.transform("mean")
    df["expected_days"] = df.estimated_transit_days + df.delay_probability * df.delay_days_if_late
    return df


def _minmax(s):
    span = s.max() - s.min()
    return (s - s.min()) / span if span > 0 else s * 0


def _score_shipment(g, weights=None):
    g = g.copy()
    w = weights or WEIGHTS[g.priority.iloc[0]]
    n_risk = (_minmax(g.delay_probability) + _minmax(g.congestion_risk) + _minmax(g.geopolitical_risk)) / 3
    g["score"] = (w["cost"] * _minmax(g.shipping_cost_usd) + w["time"] * _minmax(g.expected_days) + w["risk"] * n_risk)
    return g.sort_values("score").reset_index(drop=True)


def _nb_explain(r):
    best, lines = r.iloc[0], []
    for label, ref in (("cheapest", r.loc[r.shipping_cost_usd.idxmin()]), ("fastest", r.loc[r.expected_days.idxmin()]),
                       ("lowest-risk", r.loc[r.delay_probability.idxmin()])):
        if ref.intermediate_hub == best.intermediate_hub:
            lines.append(f"It is also the <b>{label}</b> option.")
        else:
            dc, dd = best.shipping_cost_usd - ref.shipping_cost_usd, best.expected_days - ref.expected_days
            dp = (best.delay_probability - ref.delay_probability) * 100
            lines.append(f"Versus the <b>{label}</b> option ({ref.intermediate_hub}): "
                         f"{'+' if dc >= 0 else '−'}${abs(dc):,.0f}, arrives {abs(dd):.1f} days "
                         f"{'later' if dd > 0 else 'sooner'}, {dp:+.1f} points delay chance.")
    return lines


def _new_shipment(origin, destination, base_cost, base_days, priority, cargo_value=100000, seed=7):
    """Route options for a NEW shipment, same hub profiles as the notebook."""
    r, out = np.random.default_rng(seed), []
    for hub, p in ROUTE_PROFILES.items():
        if hub in (origin, destination):
            continue
        out.append({
            "shipment_id": "NEW", "route_id": f"{origin} → {hub} → {destination}", "origin": origin,
            "destination": destination, "intermediate_hub": hub, "priority": priority, "cargo_value_usd": cargo_value,
            "shipping_cost_usd": round(base_cost * p["cost_factor"] * r.uniform(0.95, 1.05), 2),
            "estimated_transit_days": round(base_days * p["time_factor"] * r.uniform(0.97, 1.03), 2),
            "delay_probability": round(float(np.clip(p["delay"] + r.normal(0, 0.02), 0.01, 0.6)), 3),
            "delay_days_if_late": round(max(1, p["late_days"] + r.normal(0, 0.5)), 1),
            "congestion_risk": round(float(np.clip(p["congestion"] + r.normal(0, 5), 0, 100)), 2),
            "geopolitical_risk": round(float(np.clip(p["geopolitical"] + r.normal(0, 3), 0, 100)), 2)})
    g = pd.DataFrame(out)
    g["expected_days"] = g.estimated_transit_days + g.delay_probability * g.delay_days_if_late
    return g


def _pick(g, how):
    if how == "cheapest":
        return g.loc[g.shipping_cost_usd.idxmin()]
    if how == "fastest":
        return g.loc[g.expected_days.idxmin()]
    if how == "lowest_risk":
        r = _minmax(g.delay_probability) + _minmax(g.congestion_risk) + _minmax(g.geopolitical_risk)
        return g.loc[r.idxmin()]
    return _score_shipment(g).iloc[0]


@st.cache_data(show_spinner=False)
def _evaluate(df):
    rows = []
    for sid, g in df.groupby("shipment_id"):
        for s in STRATS:
            b = _pick(g, s)
            rows.append({"shipment_id": sid, "priority": b.priority, "strategy": s, "hub": b.intermediate_hub,
                         "cost_usd": b.shipping_cost_usd, "expected_days": b.expected_days,
                         "delay_pct": b.delay_probability * 100,
                         "risk_score": (b.congestion_risk + b.geopolitical_risk) / 2})
    return pd.DataFrame(rows)


@st.cache_data(show_spinner=False)
def _stability(df, N=200, seed=1):
    """Exact replica of the notebook's stability test (same seed, same order of random draws)."""
    rng2 = np.random.default_rng(seed)
    info = []
    for sid, g in df.groupby("shipment_id"):
        w0 = [WEIGHTS[g.priority.iloc[0]][k] for k in ("cost", "time", "risk")]
        c = _minmax(g.shipping_cost_usd).to_numpy()
        t = _minmax(g.expected_days).to_numpy()
        cg = _minmax(g.congestion_risk).to_numpy()
        gp = _minmax(g.geopolitical_risk).to_numpy()
        risk = (_minmax(g.delay_probability).to_numpy() + cg + gp) / 3
        base_win = int(np.argmin(w0[0] * c + w0[1] * t + w0[2] * risk))
        info.append((sid, g, w0, c, t, risk, cg, gp, base_win))
    wt = {i[0]: 0 for i in info}
    un = {i[0]: 0 for i in info}
    for _ in range(N):
        for sid, g, w0, c, t, risk, cg, gp, base_win in info:
            v = [x * rng2.uniform(0.8, 1.2) for x in w0]            # weights ±20%
            s = sum(v)
            v = [x / s for x in v]
            wt[sid] += int(np.argmin(v[0] * c + v[1] * t + v[2] * risk) == base_win)
            dl = np.clip(g.delay_probability.to_numpy() * rng2.uniform(0.7, 1.3, len(g)), 0.01, 0.95)   # delay ±30%
            exp = g.estimated_transit_days.to_numpy() + dl * g.delay_days_if_late.to_numpy()
            sc = w0[0] * c + w0[1] * _minmax(pd.Series(exp)).to_numpy() + w0[2] * (_minmax(pd.Series(dl)).to_numpy() + cg + gp) / 3
            un[sid] += int(np.argmin(sc) == base_win)
    out = []
    for sid, g, *_ in info:
        out.append({"shipment_id": sid, "lane": f"{g.origin.iloc[0]} → {g.destination.iloc[0]}",
                    "priority": g.priority.iloc[0], "weight_stability": wt[sid] / N,
                    "uncertainty_stability": un[sid] / N})
    return pd.DataFrame(out)


def _card(title):
    st.markdown(f'<div class="card-t">{title}</div>', unsafe_allow_html=True)


# ----------------------------------------------------------------------------
# 1. Dashboard (from the notebook)
# ----------------------------------------------------------------------------
def dashboard():
    page_head("Shipment Route Dashboard 🚢", "Built from the notebook dataset and scoring logic · all data is synthetic")

    with st.expander("Data source"):
        up = st.file_uploader("Use a different shipments CSV (same columns as shipments.csv)", type="csv")
    raw = pd.read_csv(up) if up is not None else _base_data()
    missing = REQUIRED - set(raw.columns)
    if missing:
        st.error(f"The CSV is missing columns: {', '.join(sorted(missing))}")
        return
    df = _prepare(raw)
    ships = df.drop_duplicates("shipment_id").copy()
    ships["lane"] = ships.origin + " → " + ships.destination
    ev, stab = _evaluate(df), _stability(df)

    k = st.columns(4)
    with k[0]:
        kpi("📦", "Shipments", f"{ships.shipment_id.nunique()}", f"{ships.lane.nunique()} trade lanes", "info")
    with k[1]:
        kpi("🛣️", "Route options", f"{len(df)}", f"{df.route_id.nunique()} unique routes", "info")
    with k[2]:
        kpi("⚓", "Transshipment hubs", f"{df.intermediate_hub.nunique()}", "Singapore, Dubai, Colombo, Port Klang", "mute")
    with k[3]:
        kpi("🛡️", "Decision stability", f"{stab.weight_stability.mean() * 100:.0f}%", "weights ±20%", "ok")
    st.write("")

    t1, t2, t3, t4, t5 = st.tabs(["Overview", "Recommend", "Evaluation", "Sensitivity", "Data & assumptions"])

    # ---------------- Overview ----------------
    with t1:
        hub = df.groupby("intermediate_hub").agg(
            cost=("cost_index", "mean"), time=("time_index", "mean"), late=("delay_probability", "mean"),
            cong=("congestion_risk", "mean"), geo=("geopolitical_risk", "mean"))

        a, b = st.columns([1, 1.6])
        with a, st.container(border=True):
            _card("Shipments by priority")
            pc = ships.priority.value_counts().reindex(PRIORITIES).fillna(0)
            C.donut(PRIORITIES, [int(v) for v in pc.values], [RED, BLUE, GREEN], str(int(pc.sum())), "shipments", h=260)
        with b, st.container(border=True):
            _card("Hub scorecard (vs the average option for the same shipment)")
            rows = [[h, f"{(r.cost - 1) * 100:+.1f}%", f"{(r.time - 1) * 100:+.1f}%", f"{r.late * 100:.0f}",
                     f"{r.cong:.0f}", f"{r.geo:.0f}"] for h, r in hub.iterrows()]
            table(["Hub", "Cost vs avg", "Time vs avg", "Late per 100", "Congestion", "Geopolitical"], rows)
            st.caption("Negative cost or time = better than average. Lower late, congestion and geopolitical = better.")
        st.write("")

        a, b = st.columns(2)
        with a, st.container(border=True):
            _card("Cost and transit time by hub (% vs average)")
            fig = go.Figure()
            fig.add_bar(x=hub.index, y=(hub.cost - 1) * 100, name="Cost", marker_color=ACC)
            fig.add_bar(x=hub.index, y=(hub.time - 1) * 100, name="Time", marker_color=BLUE)
            fig.update_layout(barmode="group", legend=dict(orientation="h", y=1.12))
            show(dark(fig, 300))
        with b, st.container(border=True):
            _card("Risk comparison by hub (darker = riskier)")
            z = np.column_stack([hub.late * 100, hub.cong, hub.geo])
            fig = go.Figure(go.Heatmap(z=z, x=["Late per 100", "Congestion", "Geopolitical"], y=list(hub.index),
                                       colorscale="YlOrRd", text=np.round(z, 0), texttemplate="%{text}", showscale=False))
            show(dark(fig, 300))
        st.write("")

        with st.container(border=True):
            _card("Trade-off map: bottom-left is best, bigger bubble = more delays")
            fig = go.Figure()
            for h, r in hub.iterrows():
                fig.add_trace(go.Scatter(x=[r.cost], y=[r.time], mode="markers+text", text=[h], textposition="middle center",
                                         marker=dict(size=r.late * 380, color=HUB_COL.get(h, MUTED), opacity=0.55),
                                         name=h, showlegend=False))
            fig.add_hline(y=1, line_dash="dash", line_color=MUTED)
            fig.add_vline(x=1, line_dash="dash", line_color=MUTED)
            fig.update_xaxes(title="Cost index (left = cheaper)")
            fig.update_yaxes(title="Time index (down = faster)")
            show(dark(fig, 360))

    # ---------------- Recommend ----------------
    with t2:
        with st.container(border=True):
            _card("Pick a shipment from the dataset")
            lab = {r.shipment_id: f"{r.shipment_id} · {r.origin} → {r.destination} · {r.priority}"
                   for r in ships.itertuples()}
            a, b = st.columns([2, 1])
            sid = a.selectbox("Shipment", list(lab), format_func=lab.get, key="nb_sid")
            custom = b.checkbox("Customise weights", key="nb_custom")
            g = df[df.shipment_id == sid]
            w = dict(WEIGHTS[g.priority.iloc[0]])
            if custom:
                s1, s2, s3 = st.columns(3)
                raw_w = {"cost": s1.slider("Cost", 0, 100, int(w["cost"] * 100), key="nb_wc"),
                         "time": s2.slider("Time", 0, 100, int(w["time"] * 100), key="nb_wt"),
                         "risk": s3.slider("Risk", 0, 100, int(w["risk"] * 100), key="nb_wr")}
                tot = sum(raw_w.values()) or 1
                w = {kx: v / tot for kx, v in raw_w.items()}
        r = _score_shipment(g, w)
        best, gap = r.iloc[0], r.score.iloc[1] - r.score.iloc[0]
        review = gap < REVIEW_GAP
        o, d = best.origin, best.destination

        k = st.columns(4)
        with k[0]:
            kpi("🏆", "Recommended hub", best.intermediate_hub,
                "low confidence: review manually" if review else "high confidence", "warn" if review else "ok")
        with k[1]:
            parts = C.money_list(best.shipping_cost_usd, o, d)
            kpi("💲", "Cost", parts[0], "≈ " + " · ".join(parts[1:]), "info")
        with k[2]:
            kpi("⏱️", "Expected days", f"{best.expected_days:.1f}", f"{best.estimated_transit_days:.1f} planned", "info")
        with k[3]:
            kpi("⚠️", "Delay chance", f"{best.delay_probability * 100:.1f}%", f"score gap {gap:.2f}", "info")
        st.write("")

        a, b = st.columns([1.6, 1])
        with a, st.container(border=True):
            _card("All options ranked (lower score = better)")
            rows = [[x.route_id, C.money(x.shipping_cost_usd, o, d), f"{x.expected_days:.1f}",
                     f"{x.delay_probability * 100:.1f}%", f"{x.congestion_risk:.0f}", f"{x.geopolitical_risk:.0f}",
                     f"{x.score:.3f}"] for x in r.itertuples()]
            table(["Route", "Cost", "Expected days", "Delay chance", "Congestion", "Geopolitical", "Score"], rows, hl=0)
            st.caption(f"Weights used: cost {w['cost']:.2f} · time {w['time']:.2f} · risk {w['risk']:.2f}")
        with b, st.container(border=True):
            _card("Why this route?")
            for line in _nb_explain(r):
                st.markdown(f"<div style='font-size:.84rem;margin:4px 0'>• {line}</div>", unsafe_allow_html=True)
        st.write("")

        c1, c2, c3 = st.columns(3)
        for col, field, title, scale in ((c1, "shipping_cost_usd", "Cost (USD)", 1), (c2, "expected_days", "Expected days", 1),
                                         (c3, "delay_probability", "Chance of delay (%)", 100)):
            with col, st.container(border=True):
                _card(title)
                fig = go.Figure(go.Bar(x=r.intermediate_hub, y=r[field] * scale,
                                       marker_color=[HUB_COL.get(h, MUTED) for h in r.intermediate_hub],
                                       text=(r[field] * scale).round(1), textposition="outside"))
                show(dark(fig, 240))
        st.write("")

        with st.container(border=True):
            _card("New shipment advisor (same hub profiles, same scoring)")
            lanes = {f"{a_} → {b_}": (a_, b_, bc, bd) for a_, b_, bc, bd in SHIPPING_LANES}
            x1, x2 = st.columns([1.5, 1])
            lane = x1.selectbox("Lane", list(lanes), key="nb_lane")
            pri = x2.radio("Priority", PRIORITIES, index=1, horizontal=True, key="nb_pri")
            nr = _score_shipment(_new_shipment(*lanes[lane], pri))
            nb, ngap = nr.iloc[0], nr.score.iloc[1] - nr.score.iloc[0]
            st.markdown(f"**Recommended: {nb.route_id}** · confidence "
                        f"{'HIGH' if ngap >= REVIEW_GAP else 'LOW, please review manually'} (score gap {ngap:.2f})")
            rows = [[x.intermediate_hub, C.money(x.shipping_cost_usd, nb.origin, nb.destination), f"{x.expected_days:.1f}",
                     f"{x.delay_probability * 100:.1f}%", f"{x.score:.3f}"] for x in nr.itertuples()]
            table(["Hub", "Cost", "Expected days", "Delay chance", "Score"], rows, hl=0)
            for line in _nb_explain(nr):
                st.markdown(f"<div style='font-size:.84rem;margin:4px 0'>• {line}</div>", unsafe_allow_html=True)

    # ---------------- Evaluation ----------------
    with t3:
        metrics = ["cost_usd", "expected_days", "delay_pct", "risk_score"]
        overall = ev.groupby("strategy")[metrics].mean().reindex(STRATS)
        a, b = st.columns([1.2, 1])
        with a, st.container(border=True):
            _card("Overall average by strategy")
            rows = [[STRAT_NAME[s], f"${r.cost_usd:,.0f}", f"{r.expected_days:.1f}", f"{r.delay_pct:.1f}%",
                     f"{r.risk_score:.1f}"] for s, r in overall.iterrows()]
            table(["Strategy", "Avg cost", "Avg expected days", "Avg delay chance", "Avg risk score"], rows, hl=3)
        with b, st.container(border=True):
            _card("How often RouteIQ differs from the simple rules")
            sysp = ev[ev.strategy == "our_system"].set_index("shipment_id").hub
            for s in ("cheapest", "fastest", "lowest_risk"):
                same = (ev[ev.strategy == s].set_index("shipment_id").hub == sysp).mean()
                st.markdown(f"<div style='font-size:.86rem;margin:6px 0'>Same hub as <b>{STRAT_NAME[s]}</b>: "
                            f"{same:.0%} of shipments</div>", unsafe_allow_html=True)
            st.caption("A low overlap means the weighted score is making real trade-offs, not copying a single rule.")
        st.write("")

        colors = [MUTED, MUTED, MUTED, ACC]
        grid = st.columns(2)
        for i, (m, title) in enumerate(zip(metrics, ["Average cost (USD)", "Average expected days",
                                                      "Average delay chance (%)", "Average risk score (0-100)"])):
            with grid[i % 2], st.container(border=True):
                _card(title)
                fig = go.Figure(go.Bar(x=[STRAT_NAME[s] for s in STRATS], y=overall[m], marker_color=colors,
                                       text=overall[m].round(1), textposition="outside"))
                show(dark(fig, 260))
        st.write("")

        with st.container(border=True):
            _card("By shipment priority (this is where the weighting should show)")
            byp = ev.groupby(["priority", "strategy"])[metrics].mean()
            rows = []
            for p in PRIORITIES:
                for s in STRATS:
                    if (p, s) in byp.index:
                        r = byp.loc[(p, s)]
                        rows.append([p if s == "cheapest" else "", STRAT_NAME[s], f"${r.cost_usd:,.0f}",
                                     f"{r.expected_days:.1f}", f"{r.delay_pct:.1f}%", f"{r.risk_score:.1f}"])
            table(["Priority", "Strategy", "Avg cost", "Avg expected days", "Avg delay chance", "Avg risk"], rows)

    # ---------------- Sensitivity ----------------
    with t4:
        k = st.columns(3)
        with k[0]:
            kpi("⚖️", "Stable when weights change ±20%", f"{stab.weight_stability.mean() * 100:.0f}%",
                "average over shipments", "ok")
        with k[1]:
            kpi("🎲", "Stable when delay estimates change ±30%", f"{stab.uncertainty_stability.mean() * 100:.0f}%",
                "average over shipments", "ok")
        with k[2]:
            fragile = int((stab.weight_stability < 0.8).sum())
            kpi("🚩", "Fragile decisions", f"{fragile}", "stable in under 80% of simulations", "warn" if fragile else "ok")
        st.write("")

        with st.container(border=True):
            _card("How stable are the recommendations? (1.0 = never changes)")
            fig = go.Figure()
            fig.add_histogram(x=stab.weight_stability, nbinsx=10, name="Weights ±20%", marker_color=ACC, opacity=0.7)
            fig.add_histogram(x=stab.uncertainty_stability, nbinsx=10, name="Delay estimate ±30%", marker_color=AMB, opacity=0.7)
            fig.update_layout(barmode="overlay", legend=dict(orientation="h", y=1.12))
            fig.update_xaxes(title="Share of simulations with the same recommendation")
            show(dark(fig, 300))
        st.write("")

        with st.container(border=True):
            _card("Most fragile decisions: flag these for human review")
            fr = stab.sort_values("weight_stability").head(6)
            table(["Shipment", "Lane", "Priority", "Weight stability", "Delay-estimate stability"],
                  [[x.shipment_id, x.lane, x.priority, f"{x.weight_stability * 100:.0f}%",
                    f"{x.uncertainty_stability * 100:.0f}%"] for x in fr.itertuples()])

    # ---------------- Data & assumptions ----------------
    with t5:
        with st.container(border=True):
            _card("Hub profiles used to build the synthetic data (assumptions)")
            table(["Hub", "Cost factor", "Time factor", "Delay prob.", "Congestion", "Geopolitical", "Days if late"],
                  [[h, p["cost_factor"], p["time_factor"], f"{p['delay'] * 100:.0f}%", p["congestion"],
                    p["geopolitical"], p["late_days"]] for h, p in ROUTE_PROFILES.items()])
        st.write("")
        with st.container(border=True):
            _card("Priority weights (what 'optimal' means)")
            table(["Priority", "Cost", "Time", "Risk"],
                  [[p, f"{wv['cost']:.2f}", f"{wv['time']:.2f}", f"{wv['risk']:.2f}"] for p, wv in WEIGHTS.items()])
            st.caption("Urgent cargo pays for speed, Economy cargo pays for savings. Scores are min-max normalised "
                       "within each shipment, lower = better.")
        st.write("")
        with st.container(border=True):
            _card("Dataset")
            show_cols = ["shipment_id", "route_id", "priority", "shipping_cost_usd", "estimated_transit_days",
                         "delay_probability", "congestion_risk", "geopolitical_risk"]
            st.dataframe(df[show_cols], hide_index=True)
            st.download_button("⬇ Download shipments.csv", raw.to_csv(index=False), "shipments.csv", "text/csv")


# ----------------------------------------------------------------------------
# 2. Shipping (route recommendation + booking)
# ----------------------------------------------------------------------------
def shipping():
    page_head("Shipping", "Choose a lane, priority and parcel weight to get a recommended route")
    names = list(PORTS)
    with st.container(border=True):
        a, b, c, d = st.columns([1.2, 1.2, 1, 1])
        o_name = a.selectbox("Origin", names, index=names.index("Mumbai, India"), key="sh_o")
        d_name = b.selectbox("Destination", names, index=names.index("New York, USA"), key="sh_d")
        pr = c.radio("Priority", list(WEIGHTS), index=1, horizontal=True, key="sh_pr")
        mo = d.selectbox("Ship month", MONTHS, index=date.today().month - 1, key="sh_mo")
        e, f = st.columns(2)
        weight = e.number_input("Parcel weight (kg)", min_value=50, max_value=50_000, value=5_000, step=250, key="sh_wt")
        cargo = f.number_input("Cargo value (USD)", min_value=1000, max_value=5_000_000, value=250_000,
                               step=10_000, key="sh_cargo")
    if o_name == d_name:
        st.warning("Origin and destination must be different.")
        return
    o, d = PORTS[o_name], PORTS[d_name]
    g, base = C.build_options(o_name, o, d_name, d, MONTHS.index(mo) + 1, weight)
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
        kpi("💲", "Freight cost", parts[0],
            "≈ " + " · ".join(parts[1:]) + f" · ${best.cost / weight:.2f}/kg", "info")
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
        rows = [[x.route, C.money(x.cost, o_name, d_name), f"${x.cost / weight:.2f}", f"{x.expected_days:.1f}",
                 f"{x.delay_p * 100:.1f}%", f"{x.congestion:.0f}", f"{x.geo:.0f}", f"{x.on_time * 100:.0f}%",
                 f"{x.score:.3f}"] for x in r.itertuples()]
        table(["Route", "Freight cost", "USD/kg", "Expected days", "Delay chance", "Congestion", "Geopolitical",
               "On-time", "Score"], rows, hl=0)
        st.caption(f"Priced for {weight:,} kg (bulk factor ×{C.weight_tier(weight):.2f}). "
                   "Costs use assumed demo rates and exchange rates.")
    st.write("")

    if st.button("📦 Book this shipment"):
        bk = C.add_booking(r, base, o_name, o, d_name, d, pr, cargo, weight)
        st.success(f"Booked {bk['id']} ({weight:,} kg) via {bk['hub']}. See it on the Tracking and Invoice pages.")


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
        kpi("💲", "Freight cost", parts[0],
            "≈ " + " · ".join(parts[1:]) + f" · {pick.get('weight_kg', 5000):,} kg · {pick['priority']}", "mute")
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
    wt = pick.get("weight_kg", 5000)
    freight = pick["cost"]
    fee = C.hub_fee(pick["hub"], wt)
    insurance = pick["cargo"] * 0.002                          # assumed 0.2% of cargo value
    total = freight + fee + insurance                          # what the carrier bills
    holding = pick["cargo"] * C.holding() * pick["planned"]    # internal cost of capital, not billed
    delivered = C.status_of(pick, C.today()) == "Delivered"
    o, dn = pick["origin"], pick["dest"]

    with st.container(border=True):
        stamp = '<span class="stamp">PAID</span>' if delivered else '<span class="stamp">DUE</span>'
        rows = [(f"Ocean freight ({wt:,} kg)", freight), (f"Hub handling fee ({pick['hub']})", fee),
                ("Cargo insurance (0.2% assumed)", insurance)]
        body = "".join(f"<tr><td>{n}</td><td style='text-align:right'>{C.money(v, o, dn)}</td></tr>" for n, v in rows)
        st.markdown(
            f"""<div class="inv">
            <div style="display:flex;justify-content:space-between"><div><b style="font-size:1.1rem">Invoice {pick['id']}</b><br>
            <small>{st.session_state['cfg_company']}</small></div>{stamp}</div><br>
            <div style="font-size:.84rem">Route: <b>{pick['route']}</b><br>Priority: {pick['priority']} ·
            Weight: {wt:,} kg · Cargo value: ${pick['cargo']:,.0f} · Shipped {pick['ship_date']:%d %b %Y}</div><br>
            <table class="rt">{body}<tr class="tot"><td>Total billed</td><td style="text-align:right">{C.money(total, o, dn)}</td></tr></table>
            <div style="font-size:.78rem;margin-top:10px;color:#8FB3B0">
            Not billed: inventory holding cost ≈ {C.money(holding, o, dn)}
            ({st.session_state['cfg_holding']}%/day × {pick['planned']:.1f} days).<br>
            Landed cost incl. holding: <b>{C.money(total + holding, o, dn)}</b></div>
            </div>""", unsafe_allow_html=True)
        st.caption("Demo invoice. Rates, fees, insurance and exchange rates are assumptions.")


# ----------------------------------------------------------------------------
# 5. Compare scenarios
# ----------------------------------------------------------------------------
def compare_scenarios():
    page_head("Compare", "Same lane and parcel, three priorities: see how the recommendation changes")
    names = list(PORTS)
    with st.container(border=True):
        a, b, c, e = st.columns(4)
        o_name = a.selectbox("Origin", names, index=names.index("Shanghai, China"), key="cmp_o")
        d_name = b.selectbox("Destination", names, index=names.index("Hamburg, Germany"), key="cmp_d")
        mo = c.selectbox("Ship month", MONTHS, index=date.today().month - 1, key="cmp_mo")
        weight = e.number_input("Parcel weight (kg)", min_value=50, max_value=50_000, value=5_000, step=250, key="cmp_wt")
    if o_name == d_name:
        st.warning("Origin and destination must be different.")
        return
    o, d = PORTS[o_name], PORTS[d_name]
    g, base = C.build_options(o_name, o, d_name, d, MONTHS.index(mo) + 1, weight)
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
        st.markdown(f'<div class="card-t">Freight cost by hub (USD, {weight:,} kg)</div>', unsafe_allow_html=True)
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
    page_head("Reports", "How RouteIQ performs across 60 demo shipments (5-tonne reference parcels)")
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
