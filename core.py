"""core.py: shared logic, dark-teal theme, 3D ship and chart helpers for RouteIQ.
All data is synthetic. Hub personalities, cost/time formulas and fees are assumptions."""
import base64
import zlib
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

# ----------------------------------------------------------------------------
# Settings and data
# ----------------------------------------------------------------------------
WEIGHTS = {
    "Urgent":   {"cost": 0.15, "time": 0.50, "risk": 0.35},
    "Standard": {"cost": 0.40, "time": 0.30, "risk": 0.30},
    "Economy":  {"cost": 0.65, "time": 0.10, "risk": 0.25},
}
DEADLINE_MULT = {"Urgent": 1.0, "Standard": 1.25, "Economy": 1.5}
HUBS = {  # lat, lon, cost_factor, time_factor, delay, congestion, geopolitical, late_days
    "Singapore":  (1.26, 103.82, 1.20, 0.80, 0.08, 25, 15, 2),
    "Dubai":      (25.01, 55.06, 1.00, 0.90, 0.16, 60, 45, 3),
    "Colombo":    (6.94, 79.85, 0.85, 1.25, 0.25, 55, 35, 5),
    "Port Klang": (3.00, 101.39, 1.05, 1.10, 0.10, 20, 5, 2),
}
HUB_FEE = {"Singapore": 210, "Dubai": 170, "Colombo": 120, "Port Klang": 140}   # USD, assumed
SEASON = {"Colombo": {6: .10, 7: .12, 8: .10, 9: .08, 10: .04},
          "Port Klang": {11: .06, 12: .06, 1: .06}, "Singapore": {1: .04, 2: .06}}
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
PORTS = {
    "Mumbai, India": (18.95, 72.84), "Chennai, India": (13.08, 80.29), "Shanghai, China": (31.23, 121.47),
    "Shenzhen, China": (22.54, 114.06), "Yokohama, Japan": (35.44, 139.64), "Busan, South Korea": (35.10, 129.04),
    "Hamburg, Germany": (53.55, 9.99), "Rotterdam, Netherlands": (51.95, 4.14), "Felixstowe, UK": (51.96, 1.35),
    "New York, USA": (40.67, -74.04), "Los Angeles, USA": (33.74, -118.27), "Vancouver, Canada": (49.29, -123.12),
    "Sydney, Australia": (-33.86, 151.20), "Melbourne, Australia": (-37.81, 144.96), "Santos, Brazil": (-23.96, -46.33),
    "Durban, South Africa": (-29.86, 31.02), "Mombasa, Kenya": (-4.04, 39.67), "Jeddah, Saudi Arabia": (21.48, 39.17),
    "Singapore (port)": (1.26, 103.82), "Dubai (Jebel Ali)": (25.01, 55.06), "Lagos, Nigeria": (6.45, 3.39),
    "Istanbul, Turkey": (41.01, 28.97), "Manila, Philippines": (14.60, 120.97), "Karachi, Pakistan": (24.84, 66.98),
}
PRESETS = {
    "India → USA": ("Mumbai, India", "New York, USA"), "China → Germany": ("Shanghai, China", "Hamburg, Germany"),
    "Japan → UK": ("Yokohama, Japan", "Felixstowe, UK"), "India → Australia": ("Chennai, India", "Sydney, Australia"),
    "Brazil → Kenya": ("Santos, Brazil", "Mombasa, Kenya"),
}
CRIT = ("cost", "time", "risk")
INK, MUTED = "#E6F4F1", "#8FB3B0"
ACC, AMB, RED, BLUE, GREEN, VIOLET = "#2DD4BF", "#F5B942", "#F87171", "#38BDF8", "#4ADE80", "#A78BFA"
HUB_COL = {"Singapore": ACC, "Dubai": AMB, "Colombo": RED, "Port Klang": BLUE}
STATUS_KIND = {"Delivered": "ok", "In transit": "info", "At hub": "info", "Packed": "mute", "Delayed": "bad", "Scheduled": "mute"}

# ---- Currencies (assumed fixed demo rates: units of currency per 1 USD) ----
CUR = {"USD": ("$", 1.0), "INR": ("₹", 88.0), "EUR": ("€", 0.92), "GBP": ("£", 0.78), "CNY": ("¥", 7.2),
       "JPY": ("JP¥", 150.0), "KRW": ("₩", 1380.0), "AUD": ("A$", 1.5), "CAD": ("C$", 1.37), "BRL": ("R$", 5.5),
       "ZAR": ("R", 18.0), "KES": ("KSh", 129.0), "SAR": ("SAR ", 3.75), "AED": ("AED ", 3.67), "NGN": ("₦", 1500.0),
       "TRY": ("₺", 34.0), "PHP": ("₱", 57.0), "PKR": ("Rs ", 280.0), "SGD": ("S$", 1.34)}
COUNTRY_CUR = {"India": "INR", "China": "CNY", "Japan": "JPY", "South Korea": "KRW", "Germany": "EUR",
               "Netherlands": "EUR", "UK": "GBP", "USA": "USD", "Canada": "CAD", "Australia": "AUD",
               "Brazil": "BRL", "South Africa": "ZAR", "Kenya": "KES", "Saudi Arabia": "SAR", "Singapore": "SGD",
               "Dubai": "AED", "Nigeria": "NGN", "Turkey": "TRY", "Philippines": "PHP", "Pakistan": "PKR"}

PERSIST = ["cfg_name", "cfg_role", "cfg_company", "cfg_holding", "cfg_gap", "sim_days", "cfg_inr"] + \
          [f"w_{p}_{k}" for p in WEIGHTS for k in CRIT]


# ----------------------------------------------------------------------------
# Session settings
# ----------------------------------------------------------------------------
def init_state():
    d = {"cfg_name": "Lohitha", "cfg_role": "Logistics Manager", "cfg_company": "Aiqon Demo Co.",
         "cfg_holding": 0.05, "cfg_gap": 0.05, "sim_days": 0, "cfg_inr": 88.0}
    for p, w in WEIGHTS.items():
        for k in CRIT:
            d[f"w_{p}_{k}"] = int(round(w[k] * 100))
    for k, v in d.items():
        st.session_state.setdefault(k, v)
    for k in PERSIST:                      # keep values alive when their widgets are not on screen
        st.session_state[k] = st.session_state[k]
    if "bookings" not in st.session_state:
        st.session_state["bookings"] = seed_bookings()


def weights_for(p):
    w = {k: st.session_state[f"w_{p}_{k}"] for k in CRIT}
    return w if sum(w.values()) > 0 else WEIGHTS[p]


def wkey():
    return tuple((p, tuple(weights_for(p)[k] for k in CRIT)) for p in WEIGHTS)


def review_gap():
    return float(st.session_state["cfg_gap"])


def holding():
    return float(st.session_state["cfg_holding"]) / 100


def today():
    return date.today() + timedelta(days=int(st.session_state["sim_days"]))


# ----------------------------------------------------------------------------
# Currency display (all calculations stay in USD; only the display changes)
# ----------------------------------------------------------------------------
def _country(port_name):
    if "," in port_name:
        return port_name.split(",")[-1].strip()
    return port_name.split(" (")[0].strip()


def _indian_group(n):
    s = str(int(round(n)))
    if len(s) <= 3:
        return s
    head, tail, parts = s[:-3], s[-3:], []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return ",".join(parts + [tail])


def fmt_cur(usd, code):
    sym, rate = CUR[code]
    if code == "INR":
        rate = float(st.session_state.get("cfg_inr", rate))
        return f"{sym}{_indian_group(usd * rate)}"
    return f"{sym}{usd * rate:,.0f}"


def money_list(usd, o_name, d_name):
    """Amounts in the origin and destination currencies (USD added if only one distinct currency)."""
    codes = []
    for n in (o_name, d_name):
        c = COUNTRY_CUR.get(_country(n), "USD")
        if c not in codes:
            codes.append(c)
    if len(codes) == 1 and codes[0] != "USD":
        codes.append("USD")
    return [fmt_cur(usd, c) for c in codes]


def money(usd, o_name, d_name):
    return " · ".join(money_list(usd, o_name, d_name))


# ----------------------------------------------------------------------------
# Decision logic
# ----------------------------------------------------------------------------
def haversine(a, b):
    la1, lo1, la2, lo2 = map(np.radians, (a[0], a[1], b[0], b[1]))
    h = np.sin((la2 - la1) / 2) ** 2 + np.cos(la1) * np.cos(la2) * np.sin((lo2 - lo1) / 2) ** 2
    return float(2 * 6371 * np.arcsin(np.sqrt(h)))


def gc_point(a, b, t):
    """Point at fraction t along the great-circle from a to b -> (lat, lon)."""
    la1, lo1, la2, lo2 = map(np.radians, (a[0], a[1], b[0], b[1]))
    p1 = np.array([np.cos(la1) * np.cos(lo1), np.cos(la1) * np.sin(lo1), np.sin(la1)])
    p2 = np.array([np.cos(la2) * np.cos(lo2), np.cos(la2) * np.sin(lo2), np.sin(la2)])
    om = np.arccos(np.clip(p1 @ p2, -1, 1))
    if om < 1e-9:
        return a
    p = (np.sin((1 - t) * om) * p1 + np.sin(t * om) * p2) / np.sin(om)
    return float(np.degrees(np.arcsin(np.clip(p[2], -1, 1)))), float(np.degrees(np.arctan2(p[1], p[0])))


def minmax(s):
    span = s.max() - s.min()
    return (s - s.min()) / span if span > 0 else s * 0


def build_options(o_name, o, d_name, d, month):
    """One route option per usable hub, for ANY origin/destination."""
    direct = haversine(o, d)
    if direct < 300:
        return None, "Origin and destination are too close for an ocean shipment. Pick places that are further apart."
    base_cost, base_days = 350 + 0.135 * direct, 6 + direct / 650
    rows = []
    for hub, (la, lo, cf, tf, dl, cg, gp, late) in HUBS.items():
        if haversine(o, (la, lo)) < 400 or haversine(d, (la, lo)) < 400:
            continue
        r = np.random.default_rng(zlib.crc32(f"{o_name}|{d_name}|{hub}".encode()))
        l1, l2 = haversine(o, (la, lo)), haversine((la, lo), d)
        detour = max((l1 + l2) / direct, 1.0)
        p = float(np.clip(dl + SEASON.get(hub, {}).get(month, 0) + r.normal(0, 0.02), 0.01, 0.6))
        rows.append({
            "hub": hub, "route": f"{o_name.split(',')[0].split(' (')[0]} → {hub} → {d_name.split(',')[0].split(' (')[0]}",
            "cost": round(base_cost * cf * detour ** 0.9 * r.uniform(0.95, 1.05), 2),
            "days": round(base_days * tf * detour ** 0.9 * r.uniform(0.97, 1.03), 2),
            "delay_p": round(p, 3), "late_days": round(max(1, late + r.normal(0, 0.5)), 1),
            "congestion": round(float(np.clip(cg + r.normal(0, 5), 0, 100)), 1),
            "geo": round(float(np.clip(gp + r.normal(0, 3), 0, 100)), 1),
            "lat": la, "lon": lo, "leg_share": l1 / (l1 + l2)})
    if len(rows) < 2:
        return None, "Fewer than two hub options exist for this lane. Try another origin or destination."
    g = pd.DataFrame(rows)
    g["expected_days"] = g.days + g.delay_p * g.late_days
    return g, base_days


def norm_parts(g):
    """Normalised cost, time, risk (0 best .. 1 worst) as numpy arrays."""
    risk = (minmax(g.delay_p) + minmax(g.congestion) + minmax(g.geo)) / 3
    return minmax(g.cost).to_numpy(), minmax(g.expected_days).to_numpy(), risk.to_numpy()


def score(g, weights):
    g = g.copy()
    tot = sum(weights.values())
    w = {k: v / tot for k, v in weights.items()}
    c, t, r = norm_parts(g)
    g["cost_part"], g["time_part"], g["risk_part"] = w["cost"] * c, w["time"] * t, w["risk"] * r
    g["score"] = g.cost_part + g.time_part + g.risk_part
    return g.sort_values("score").reset_index(drop=True)


def topsis(g, weights):
    """TOPSIS closeness (higher = better). 5 criteria; the risk weight is split over 3 risk indicators."""
    X = g[["cost", "expected_days", "delay_p", "congestion", "geo"]].to_numpy(float)
    X = X / np.sqrt((X ** 2).sum(0))
    tot = sum(weights.values())
    w = np.array([weights["cost"], weights["time"], weights["risk"] / 3, weights["risk"] / 3, weights["risk"] / 3]) / tot
    V = X * w
    d_best, d_worst = np.sqrt(((V - V.min(0)) ** 2).sum(1)), np.sqrt(((V - V.max(0)) ** 2).sum(1))
    return d_worst / (d_best + d_worst + 1e-12)


def simulate(g, deadline, n=4000, seed=1, samples=False):
    """Monte Carlo: P(on time), P90 days (and optionally the raw samples)."""
    r = np.random.default_rng(seed)
    on, p90, raw = [], [], {}
    for row in g.itertuples():
        p = r.beta(row.delay_p * 40, (1 - row.delay_p) * 40, n)
        total = r.normal(row.days, 0.04 * row.days, n) + (r.random(n) < p) * r.gamma(4, row.late_days / 4, n)
        on.append(float((total <= deadline).mean()))
        p90.append(float(np.percentile(total, 90)))
        raw[row.hub] = total
    g = g.copy()
    g["on_time"], g["p90"] = on, p90
    return (g, raw) if samples else g


def explain(r):
    best = r.iloc[0]
    lines = []
    for label, ref in (("cheapest", r.loc[r.cost.idxmin()]), ("fastest", r.loc[r.expected_days.idxmin()]),
                       ("lowest-risk", r.loc[r.delay_p.idxmin()])):
        if ref.hub == best.hub:
            lines.append(f"It is also the <b>{label}</b> option.")
        else:
            dd = best.expected_days - ref.expected_days
            lines.append(f"Versus the <b>{label}</b> option ({ref.hub}): "
                         f"{'+' if best.cost >= ref.cost else '−'}${abs(best.cost - ref.cost):,.0f}, "
                         f"arrives {abs(dd):.1f} days {'later' if dd > 0 else 'sooner'}, "
                         f"{(best.delay_p - ref.delay_p) * 100:+.1f} points delay chance.")
    parts = {"cost": best.cost_part, "time": best.time_part, "risk": best.risk_part}
    lines.append(f"Biggest advantage: <b>{min(parts, key=parts.get)}</b> (smallest penalty of the three criteria).")
    return lines


# ----------------------------------------------------------------------------
# Bookings (demo shipments) and status
# ----------------------------------------------------------------------------
def make_booking(i, o_name, d_name, pr, cargo, ship_date, rng, best, base_days, gap, o, d):
    late = bool(rng.random() < best.delay_p)
    actual = best.days * rng.normal(1, 0.04) + (rng.gamma(4, best.late_days / 4) if late else 0)
    return {"id": f"SHP{1000 + i}", "origin": o_name, "dest": d_name, "o": o, "d": d, "hub": best.hub,
            "hub_pos": (best.lat, best.lon), "leg_share": float(best.leg_share), "route": best.route, "priority": pr,
            "cargo": int(cargo), "ship_date": ship_date, "planned": float(best.expected_days), "actual": float(max(actual, 3)),
            "late": late, "cost": float(best.cost), "on_time": float(best.on_time), "p_delay": float(best.delay_p),
            "gap": float(gap), "deadline": float(base_days * DEADLINE_MULT[pr]), "month": ship_date.month}


def seed_bookings(n=22, seed=5):
    rng, names, out = np.random.default_rng(seed), list(PORTS), []
    i = 0
    while len(out) < n:
        a, b = rng.choice(len(names), 2, replace=False)
        pr = str(rng.choice(list(WEIGHTS), p=[.25, .5, .25]))
        sd = date.today() - timedelta(days=int(rng.integers(0, 75)))
        g, base = build_options(names[a], PORTS[names[a]], names[b], PORTS[names[b]], sd.month)
        if g is None:
            continue
        r = simulate(score(g, weights_for(pr)), base * DEADLINE_MULT[pr], n=800)
        out.append(make_booking(i, names[a], names[b], pr, rng.integers(50, 900) * 1000, sd, rng, r.iloc[0], base,
                                r.score.iloc[1] - r.score.iloc[0], PORTS[names[a]], PORTS[names[b]]))
        i += 1
    return sorted(out, key=lambda x: x["ship_date"])


def add_booking(r, base_days, o_name, o, d_name, d, pr, cargo):
    bk = st.session_state["bookings"]
    rng = np.random.default_rng(len(bk) + 99)
    b = make_booking(len(bk), o_name, d_name, pr, cargo, date.today(), rng, r.iloc[0], base_days,
                     r.score.iloc[1] - r.score.iloc[0], o, d)
    bk.append(b)
    return b


def progress(b, t):
    return float(np.clip((t - b["ship_date"]).days / b["actual"], 0, 1))


def status_of(b, t):
    el, pg = (t - b["ship_date"]).days, progress(b, t)
    if el < 0:
        return "Scheduled"
    if pg >= 1:
        return "Delivered"
    if b["late"] and el > b["planned"]:
        return "Delayed"
    if pg < 0.06:
        return "Packed"
    return "At hub" if abs(pg - b["leg_share"]) < 0.05 else "In transit"


def position(b, t):
    pg, s = progress(b, t), b["leg_share"]
    return gc_point(b["o"], b["hub_pos"], pg / s) if pg <= s else gc_point(b["hub_pos"], b["d"], (pg - s) / (1 - s))


def eta(b):
    return b["ship_date"] + timedelta(days=int(np.ceil(b["actual"])))


def daily_series(bks, t, days=45):
    """Real counts from the demo bookings, per day, for the KPI sparklines."""
    tot, act, dlv, rev = [], [], [], []
    for k in range(days, -1, -1):
        d = t - timedelta(days=k)
        started = [b for b in bks if b["ship_date"] <= d]
        done = [b for b in started if (d - b["ship_date"]).days >= b["actual"]]
        tot.append(len(started)); dlv.append(len(done)); act.append(len(started) - len(done))
        rev.append(sum(1 for b in started if b["gap"] < review_gap()))
    return tot, act, dlv, rev


# ----------------------------------------------------------------------------
# Cached portfolio evaluation (60 synthetic shipments)
# ----------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def portfolio_eval(wk, gap, n=60, seed=42):
    W = {p: dict(zip(CRIT, v)) for p, v in wk}
    rng, names = np.random.default_rng(seed), list(PORTS)
    ships, strat = [], []
    for i in range(n):
        a, b = rng.choice(len(names), 2, replace=False)
        pr, mo = str(rng.choice(list(WEIGHTS), p=[.25, .5, .25])), int(rng.integers(1, 13))
        g, base = build_options(names[a], PORTS[names[a]], names[b], PORTS[names[b]], mo)
        if g is None:
            continue
        r = simulate(score(g, W[pr]), base * DEADLINE_MULT[pr], n=1500)
        tp = topsis(r, W[pr])
        t_row = r.iloc[int(np.argmax(tp))]
        c, t_, k = norm_parts(g)
        w0 = np.array([W[pr][x] for x in CRIT], float)
        draws = w0 * rng.uniform(0.8, 1.2, (200, 3))
        draws /= draws.sum(1, keepdims=True)
        base_win = int(np.argmin((w0 / w0.sum()) @ np.vstack([c, t_, k])))
        stab = float((np.argmin(draws @ np.vstack([c, t_, k]), axis=1) == base_win).mean())
        gp = r.score.iloc[1] - r.score.iloc[0]
        ships.append({"lane": f"{names[a].split(',')[0]} → {names[b].split(',')[0]}", "priority": pr, "month": MONTHS[mo - 1],
                      "weighted": r.iloc[0].hub, "topsis": t_row.hub, "agree": r.iloc[0].hub == t_row.hub,
                      "gap": gp, "flagged": gp < gap, "stability": stab, "top_p": r.iloc[0].delay_p})
        for s, row in (("Always cheapest", r.loc[r.cost.idxmin()]), ("Always fastest", r.loc[r.expected_days.idxmin()]),
                       ("Weighted score", r.iloc[0]), ("TOPSIS", t_row)):
            strat.append({"strategy": s, "priority": pr, "hub": row.hub, "cost": row.cost,
                          "expected_days": row.expected_days, "on_time": row.on_time * 100})
    return pd.DataFrame(ships), pd.DataFrame(strat)


# ----------------------------------------------------------------------------
# Theme (dark teal + optional ship photo background)
# ----------------------------------------------------------------------------
def _bg_css():
    for name in ("ship_bg.jpg", "ship_bg.jpeg", "ship_bg.png"):
        p = Path(__file__).parent / "assets" / name
        if p.exists():
            mime = "image/png" if name.endswith("png") else "image/jpeg"
            b64 = base64.b64encode(p.read_bytes()).decode()
            return (f"linear-gradient(180deg,rgba(3,16,21,.62) 0%,rgba(3,16,21,.86) 55%,rgba(3,16,21,.94) 100%),"
                    f"url(data:{mime};base64,{b64}) center top/cover fixed no-repeat,#04161B")
    return "radial-gradient(ellipse at 20% 0%,#0B3A44 0%,#06222B 45%,#03121A 100%) fixed"


CSS = """
<style>
:root{--ink:#E6F4F1;--muted:#8FB3B0;--line:rgba(94,234,212,.16);--card:rgba(8,34,41,.80);--acc:#2DD4BF;--amb:#F5B942;--red:#F87171;--blue:#38BDF8;--field:#0B2B33;}
html{font-size:14px;}
.stApp,[data-testid="stAppViewContainer"]{background:__BG__!important;}
[data-testid="stMain"],[data-testid="stMainBlockContainer"]{background:transparent!important;}
header[data-testid="stHeader"]{background:rgba(4,22,28,.78)!important;backdrop-filter:blur(10px);border-bottom:1px solid var(--line);}
header[data-testid="stHeader"] *{color:var(--ink)!important;}
header[data-testid="stHeader"] a[aria-current="page"]{background:rgba(45,212,191,.22)!important;border:1px solid rgba(45,212,191,.55);}
header[data-testid="stHeader"] a[aria-current="page"] *{color:#fff!important;font-weight:700;}
.block-container{padding-top:4.2rem;max-width:1280px;}
:where(.stApp p,.stApp label,.stApp span,.stApp li,.stApp h1,.stApp h2,.stApp h3,.stApp h4,.stApp small,.stApp summary,.stApp div){color:var(--ink);}
[data-testid="stWidgetLabel"] p,[data-testid="stWidgetLabel"] label{color:var(--muted)!important;font-size:.78rem!important;font-weight:600!important;}
[data-testid="stCaptionContainer"] p{color:var(--muted)!important;font-size:.74rem!important;}
div[data-baseweb="select"]>div,div[data-baseweb="input"],div[data-baseweb="base-input"],input,textarea{background:var(--field)!important;color:var(--ink)!important;border-color:var(--line)!important;}
div[data-baseweb="select"] *{color:var(--ink)!important;}
div[data-baseweb="select"]>div *{background-color:transparent!important;}
[data-testid="stSlider"] [role="slider"]{background:var(--acc)!important;box-shadow:none!important;}
div[data-baseweb="select"] svg,div[data-baseweb="input"] svg{fill:var(--ink)!important;}
[data-testid="stNumberInput"] button{background:#10363F!important;color:var(--ink)!important;border-color:var(--line)!important;}
[data-testid="stNumberInput"] button svg{fill:var(--ink)!important;}
div[data-baseweb="popover"],div[data-baseweb="popover"] ul,div[data-baseweb="menu"]{background:#0B2B33!important;}
div[data-baseweb="popover"] li,div[data-baseweb="popover"] li *{background:#0B2B33!important;color:var(--ink)!important;}
div[data-baseweb="popover"] li:hover,div[data-baseweb="popover"] li[aria-selected="true"]{background:#14434D!important;}
[data-baseweb="radio"]>div:first-child{background:var(--field)!important;border:2px solid #4F8F8C!important;}
[data-baseweb="radio"]>div:first-child:has(+input:checked){border-color:var(--acc)!important;background:var(--acc)!important;}
[data-baseweb="checkbox"]>span:first-child{background:var(--field)!important;border:2px solid #4F8F8C!important;}
[data-baseweb="checkbox"] input:checked+span{background:var(--acc)!important;border-color:var(--acc)!important;}
[data-testid="stExpander"]{background:var(--card)!important;border:1px solid var(--line)!important;border-radius:12px!important;}
[data-testid="stExpander"] details,[data-testid="stExpander"] summary{background:transparent!important;color:var(--ink)!important;}
[data-testid="stSliderThumbValue"],[data-testid="stSlider"] [data-testid="stTickBarMin"],[data-testid="stSlider"] [data-testid="stTickBarMax"]{color:var(--ink)!important;}
[data-baseweb="tag"]{background:rgba(45,212,191,.22)!important;border:1px solid rgba(45,212,191,.5);}
[data-baseweb="tag"] *{color:#E6F4F1!important;}
.stTabs [data-baseweb="tab"]{font-weight:600;font-size:.88rem;color:var(--muted)!important;}
.stTabs [aria-selected="true"]{color:var(--acc)!important;}
.stTabs [data-baseweb="tab-highlight"]{background:var(--acc)!important;}
.stTabs [data-baseweb="tab-border"]{background:var(--line)!important;}
[data-testid="stAlert"]{background:rgba(245,185,66,.12)!important;border:1px solid rgba(245,185,66,.35)!important;} [data-testid="stAlert"] *{color:#FBD38D!important;}
.stButton>button,.stDownloadButton>button,[data-testid="stPageLink-NavLink"]{background:linear-gradient(135deg,#2DD4BF,#14B8A6)!important;border:0!important;border-radius:10px!important;box-shadow:0 4px 14px rgba(45,212,191,.25);}
.stButton>button *,.stDownloadButton>button *,[data-testid="stPageLink-NavLink"] *{color:#032A2C!important;font-weight:700!important;}
div[data-testid="stVerticalBlockBorderWrapper"]{background:var(--card)!important;border-radius:16px;border:1px solid var(--line)!important;box-shadow:0 8px 30px rgba(0,0,0,.28);backdrop-filter:blur(6px);}
.head{display:flex;justify-content:space-between;align-items:center;margin:.2rem 0 .9rem;gap:1rem;}
.stApp .head h1{font-size:1.7rem;font-weight:700;margin:0;padding:0;color:#fff!important;}
.stApp .head p{margin:.15rem 0 0;color:var(--muted)!important;font-size:.86rem;}
.chip{display:flex;align-items:center;gap:10px;background:rgba(8,34,41,.85);border:1px solid var(--line);border-radius:999px;padding:5px 14px 5px 6px;}
.chip .av{width:30px;height:30px;border-radius:50%;background:linear-gradient(135deg,#2DD4BF,#38BDF8);color:#032A2C!important;font-weight:800;display:flex;align-items:center;justify-content:center;}
.chip b{display:block;font-size:.82rem;line-height:1.1;} .chip small{color:var(--muted)!important;font-size:.7rem;}
.card-t{font-weight:700;font-size:.95rem;margin-bottom:.15rem;color:#fff;}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:12px 15px;box-shadow:0 8px 24px rgba(0,0,0,.25);backdrop-filter:blur(6px);}
.kpi .row{display:flex;justify-content:space-between;align-items:flex-end;gap:8px;}
.kpi .l{color:var(--muted);font-size:.76rem;display:flex;align-items:center;gap:7px;}
.kpi .ic{background:rgba(45,212,191,.16);border-radius:7px;padding:2px 6px;font-size:.8rem;}
.kpi .v{font-size:1.55rem;font-weight:700;margin-top:4px;line-height:1.15;color:#fff;}
.stApp .kpi .d,.stApp .badge{display:inline-block;border-radius:6px;padding:1px 8px;font-size:.7rem;font-weight:700;margin-top:5px;}
.stApp .ok{background:rgba(74,222,128,.16);color:#86EFAC!important;} .stApp .bad{background:rgba(248,113,113,.18);color:#FCA5A5!important;}
.stApp .info{background:rgba(56,189,248,.16);color:#7DD3FC!important;} .stApp .warn{background:rgba(245,185,66,.18);color:#FCD34D!important;}
.stApp .mute{background:rgba(143,179,176,.16);color:#B7D3D0!important;}
.stApp .badge{border-radius:999px;padding:2px 10px;margin-top:0;}
.leg{display:flex;align-items:center;gap:9px;margin:6px 0;font-size:.82rem;}
.leg .dot{width:10px;height:10px;border-radius:50%;flex:none;} .leg b{margin-left:auto;font-size:.9rem;}
.rt{width:100%;border-collapse:collapse;font-size:.8rem;}
.stApp .rt th{color:var(--muted)!important;text-align:left;font-weight:600;padding:6px 8px;border-bottom:1px solid var(--line);white-space:nowrap;}
.stApp .rt td{padding:7px 8px;border-bottom:1px solid rgba(94,234,212,.08);}
.rt tr.best td{background:rgba(45,212,191,.12);font-weight:600;}
.bar{display:inline-block;width:70px;height:7px;background:rgba(255,255,255,.12);border-radius:4px;vertical-align:middle;margin-right:6px;overflow:hidden;}
.bar div{height:100%;background:linear-gradient(90deg,#14B8A6,#2DD4BF);}
.steps{display:flex;flex-direction:column;gap:0;margin-top:.4rem;}
.step{display:flex;gap:11px;align-items:flex-start;position:relative;padding-bottom:14px;}
.step:not(:last-child):before{content:"";position:absolute;left:8px;top:18px;bottom:0;width:2px;background:rgba(255,255,255,.14);}
.step.done:not(:last-child):before{background:var(--acc);}
.step .pt{width:18px;height:18px;border-radius:50%;border:2px solid #4F8F8C;flex:none;background:var(--field);}
.step.done .pt{background:var(--acc);border-color:var(--acc);} .step.now .pt{background:var(--amb);border-color:var(--amb);box-shadow:0 0 0 4px rgba(245,185,66,.25);}
.step b{display:block;font-size:.84rem;} .step small{color:var(--muted)!important;}
.inv{background:rgba(255,255,255,.04);border:1px dashed rgba(94,234,212,.35);border-radius:14px;padding:18px 22px;}
.inv .tot td{font-weight:800;font-size:1rem;border-top:2px solid var(--acc);}
.stamp{display:inline-block;border:2px solid var(--amb);color:var(--amb)!important;border-radius:6px;padding:1px 10px;font-weight:800;font-size:.72rem;transform:rotate(-3deg);}
</style>
"""


def inject_css():
    st.markdown(CSS.replace("__BG__", _bg_css()), unsafe_allow_html=True)


# ----------------------------------------------------------------------------
# HTML helpers
# ----------------------------------------------------------------------------
def page_head(title, sub=""):
    nm = st.session_state["cfg_name"]
    st.markdown(f'<div class="head"><div><h1>{title}</h1><p>{sub}</p></div><div class="chip">'
                f'<span class="av">{nm[:1].upper()}</span><div><b>{nm}</b><small>{st.session_state["cfg_role"]}</small></div></div></div>',
                unsafe_allow_html=True)


def spark(vals, color=ACC, w=96, h=34):
    v = np.asarray(vals, float)
    if len(v) < 2 or v.max() == v.min():
        v = np.append(v, v[-1] + 1e-6) if len(v) < 2 else v + np.linspace(0, 1e-6, len(v))
    x = np.linspace(2, w - 2, len(v))
    y = h - 3 - (v - v.min()) / (v.max() - v.min() + 1e-9) * (h - 8)
    pts = " ".join(f"{a:.1f},{b:.1f}" for a, b in zip(x, y))
    return (f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}"><polygon points="{pts} {w - 2},{h} 2,{h}" fill="{color}" opacity=".16"/>'
            f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>'
            f'<circle cx="{x[-1]:.1f}" cy="{y[-1]:.1f}" r="3" fill="{color}"/></svg>')


def kpi(icon, label, value, delta="", kind="info", series=None, color=ACC):
    sp = spark(series, color) if series is not None else ""
    d = f'<span class="d {kind}">{delta}</span>' if delta else ""
    st.markdown(f'<div class="kpi"><div class="l"><span class="ic">{icon}</span>{label}</div>'
                f'<div class="row"><div><div class="v">{value}</div>{d}</div>{sp}</div></div>', unsafe_allow_html=True)


def badge(text, kind="info"):
    return f'<span class="badge {kind}">{text}</span>'


def bar(pct, color=None):
    c = f' style="background:{color}"' if color else ""
    return f'<span class="bar"><div style="width:{max(0, min(100, pct)):.0f}%"{c}></div></span>'


def table(headers, rows, hl=None):
    th = "".join(f"<th>{h}</th>" for h in headers)
    body = "".join(f'<tr class="{"best" if i == hl else ""}">' + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for i, r in enumerate(rows))
    st.markdown(f'<table class="rt"><tr>{th}</tr>{body}</table>', unsafe_allow_html=True)


# ----------------------------------------------------------------------------
# Plotly (dark)
# ----------------------------------------------------------------------------
FONT = dict(family="Inter, Segoe UI, Arial", size=12, color=INK)
GRID = "rgba(255,255,255,.08)"


def dark(fig, h=300, **kw):
    margin = kw.pop("margin", dict(l=10, r=10, t=10, b=10))
    fig.update_layout(height=h, margin=margin, font=FONT, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", **kw)
    fig.update_xaxes(gridcolor=GRID, zerolinecolor=GRID, linecolor=GRID, automargin=True, tickfont=dict(color=INK))
    fig.update_yaxes(gridcolor=GRID, zerolinecolor=GRID, linecolor=GRID, automargin=True, tickfont=dict(color=INK))
    return fig


def show(fig):
    cfg = {"displayModeBar": False}
    try:
        st.plotly_chart(fig, width="stretch", theme=None, config=cfg)
    except TypeError:                      # older Streamlit versions
        st.plotly_chart(fig, use_container_width=True, theme=None, config=cfg)


def _geo(fig, h, fit=True):
    fig.update_geos(projection_type="natural earth", showland=True, landcolor="#123943", showocean=True, oceancolor="#061C23",
                    showcountries=True, countrycolor="#1F5560", coastlinecolor="#2E7480", showframe=False,
                    lakecolor="#061C23", bgcolor="rgba(0,0,0,0)", **({"fitbounds": "locations"} if fit else {}))
    fig.update_layout(height=h, margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor="rgba(0,0,0,0)", font=FONT,
                      legend=dict(orientation="h", y=0.02, x=0.01, bgcolor="rgba(4,22,28,.8)", font=dict(size=11, color=INK)))
    return fig


def route_map(r, o_name, o, d_name, d, h=420):
    best_hub = r.iloc[0].hub
    fig = go.Figure()
    for row in r.iloc[::-1].itertuples():
        best = row.hub == best_hub
        fig.add_trace(go.Scattergeo(lon=[o[1], row.lon, d[1]], lat=[o[0], row.lat, d[0]], mode="lines",
                                    line=dict(width=4 if best else 1.4, color=ACC if best else "rgba(143,179,176,.55)",
                                              dash="solid" if best else "dot"),
                                    name=f"{'★ ' if best else ''}{row.hub}", hoverinfo="text",
                                    text=f"{row.route}<br>${row.cost:,.0f} · {row.expected_days:.1f} d · {row.on_time * 100:.0f}% on time"))
    pts = [(o_name, o, GREEN, 13, "Origin"), (d_name, d, RED, 13, "Destination")]
    for row in r.itertuples():
        pts.append((row.hub + (" ★" if row.hub == best_hub else ""), (row.lat, row.lon), AMB if row.hub == best_hub else "#8FB3B0",
                    11 if row.hub == best_hub else 8, "Hub"))
    fig.add_trace(go.Scattergeo(lon=[p[1][1] for p in pts], lat=[p[1][0] for p in pts], mode="markers+text",
                                text=[p[0].split(",")[0] for p in pts], textposition="top center", textfont=dict(size=11, color=INK),
                                marker=dict(size=[p[3] for p in pts], color=[p[2] for p in pts], line=dict(width=2, color="#04161B")),
                                hovertext=[f"{p[4]}: {p[0]}" for p in pts], hoverinfo="text", showlegend=False))
    show(_geo(fig, h))


def fleet_map(items, h=360):
    """items: list of (booking, status, (lat, lon))."""
    fig = go.Figure()
    for b, s, _ in items:
        fig.add_trace(go.Scattergeo(lon=[b["o"][1], b["hub_pos"][1], b["d"][1]], lat=[b["o"][0], b["hub_pos"][0], b["d"][0]],
                                    mode="lines", line=dict(width=1, color="rgba(94,234,212,.22)"), hoverinfo="skip", showlegend=False))
    col = {"Delivered": GREEN, "In transit": BLUE, "At hub": ACC, "Packed": "#8FB3B0", "Delayed": RED, "Scheduled": "#8FB3B0"}
    for s in ["In transit", "At hub", "Delayed", "Packed", "Delivered"]:
        sel = [(b, p) for b, st_, p in items if st_ == s]
        if sel:
            fig.add_trace(go.Scattergeo(lon=[p[1] for _, p in sel], lat=[p[0] for _, p in sel], mode="markers", name=s,
                                        marker=dict(size=9, color=col[s], line=dict(width=1.5, color="#04161B")), hoverinfo="text",
                                        text=[f"{b['id']} · {b['route']}<br>{s}" for b, _ in sel]))
    show(_geo(fig, h, fit=False))


def track_map(b, pos, h=380):
    fig = go.Figure()
    fig.add_trace(go.Scattergeo(lon=[b["o"][1], b["hub_pos"][1], b["d"][1]], lat=[b["o"][0], b["hub_pos"][0], b["d"][0]],
                                mode="lines", line=dict(width=3, color=ACC), hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Scattergeo(lon=[b["o"][1], b["hub_pos"][1], b["d"][1]], lat=[b["o"][0], b["hub_pos"][0], b["d"][0]],
                                mode="markers+text", text=[b["origin"].split(",")[0], b["hub"], b["dest"].split(",")[0]],
                                textposition="top center", textfont=dict(size=11, color=INK), showlegend=False, hoverinfo="skip",
                                marker=dict(size=[11, 9, 11], color=[GREEN, AMB, RED], line=dict(width=2, color="#04161B"))))
    fig.add_trace(go.Scattergeo(lon=[pos[1]], lat=[pos[0]], mode="markers", name="Ship now",
                                marker=dict(size=16, color="#fff", symbol="diamond", line=dict(width=3, color=ACC)),
                                hoverinfo="text", text=f"{b['id']} is here"))
    show(_geo(fig, h))


def donut(labels, values, colors, title, sub, h=240):
    fig = go.Figure(go.Pie(labels=labels, values=values, hole=0.66, sort=False, rotation=25,
                           pull=[0.05 if v == max(values) else 0 for v in values],
                           marker=dict(colors=colors, line=dict(color="#06222B", width=4)),
                           textinfo="label+percent", textposition="outside", textfont=dict(size=11, color=INK),
                           hovertemplate="%{label}: %{value}<extra></extra>"))
    fig.add_annotation(text=f"<b style='font-size:22px'>{title}</b><br><span style='color:#8FB3B0;font-size:11px'>{sub}</span>",
                       x=0.5, y=0.5, showarrow=False, font=FONT)
    fig.update_layout(height=h, margin=dict(l=55, r=55, t=14, b=14), showlegend=False, paper_bgcolor="rgba(0,0,0,0)", font=FONT)
    show(fig)


def gauge(p, deadline, h=170):
    color = GREEN if p >= 90 else AMB if p >= 70 else RED
    fig = go.Figure(go.Indicator(mode="gauge+number", value=p, number=dict(suffix="%", font=dict(size=26, color="#fff")),
                                 title=dict(text=f"Chance to arrive within {deadline:.0f} days", font=dict(size=12, color=MUTED)),
                                 gauge=dict(axis=dict(range=[0, 100], tickcolor="#4F8F8C", tickfont=dict(size=10, color=INK)),
                                            bar=dict(color=color, thickness=0.28), bgcolor="rgba(255,255,255,.06)", borderwidth=0,
                                            steps=[dict(range=[0, 70], color="rgba(248,113,113,.18)"),
                                                   dict(range=[70, 90], color="rgba(245,185,66,.18)"),
                                                   dict(range=[90, 100], color="rgba(74,222,128,.18)")])))
    fig.update_layout(height=h, margin=dict(l=25, r=25, t=38, b=5), paper_bgcolor="rgba(0,0,0,0)", font=FONT)
    show(fig)


# ----------------------------------------------------------------------------
# 3D ship (three.js, loaded from cdnjs; needs internet)
# ----------------------------------------------------------------------------
SHIP_JS = r"""
function rnd(s){ return function(){ s=(s*16807)%2147483647; return (s-1)/2147483646; }; }
function buildShip(seed, stacks){
  const R=rnd(seed||7), g=new THREE.Group();
  const M=(c,r,m)=>new THREE.MeshStandardMaterial({color:c,roughness:r===undefined?.6:r,metalness:m===undefined?.25:m,flatShading:true});
  const hull=new THREE.Mesh(new THREE.BoxGeometry(13,1.3,2.8),M(0x16282e)); hull.position.y=0.2; g.add(hull);
  const stripe=new THREE.Mesh(new THREE.BoxGeometry(13.02,.36,2.82),M(0x8a2b2b,.7,.1)); stripe.position.y=-.27; g.add(stripe);
  const bg=new THREE.BoxGeometry(3,1.3,2.8,4,1,4), pa=bg.attributes.position;
  for(let i=0;i<pa.count;i++){ const x=pa.getX(i); if(x>0){ pa.setZ(i,pa.getZ(i)*(1-x/1.5*.92)); } }
  bg.computeVertexNormals();
  const bow=new THREE.Mesh(bg,M(0x16282e)); bow.position.set(8,.2,0); g.add(bow);
  const sup=new THREE.Mesh(new THREE.BoxGeometry(1.9,2.6,2.5),M(0xe8eef0,.7,.1)); sup.position.set(-5,2.15,0); g.add(sup);
  const win=new THREE.Mesh(new THREE.BoxGeometry(.06,.34,2.3),new THREE.MeshStandardMaterial({color:0xffd27a,emissive:0xffb84d,emissiveIntensity:1.2}));
  win.position.set(-4.03,2.95,0); g.add(win);
  const fun=new THREE.Mesh(new THREE.CylinderGeometry(.36,.42,1.2,8),M(0xc0392b)); fun.position.set(-5.4,4.1,0); g.add(fun);
  const pal=[0x14b8a6,0xf59e0b,0xef4444,0x38bdf8,0x94a3b8,0x2dd4bf,0xea580c,0x1d4ed8,0xe2e8f0];
  const cg=new THREE.BoxGeometry(.94,.5,.8); let glow=null;
  for(let bay=0;bay<(stacks||10);bay++){ for(let col=-1;col<=1;col++){
    const h=2+Math.floor(R()*3);
    for(let k=0;k<h;k++){
      const c=pal[Math.floor(R()*pal.length)];
      const m=new THREE.Mesh(cg,M(c,.55,.2)); m.position.set(-3.3+bay*1.0,.85+.26+k*.52,col*.9); g.add(m);
      if(!glow && bay===5 && col===0 && k===h-1){ m.material=new THREE.MeshStandardMaterial({color:0xffe08a,emissive:0xf5b942,emissiveIntensity:1.4}); glow=m; }
    } } }
  g.userData.glow=glow; return g;
}
function makeWater(w,seg){
  const geo=new THREE.PlaneGeometry(w,w,seg,seg); geo.rotateX(-Math.PI/2);
  const m=new THREE.Mesh(geo,new THREE.MeshStandardMaterial({color:0x0b4452,roughness:.75,metalness:.15,flatShading:true,transparent:true,opacity:.96}));
  m.userData.base=Float32Array.from(geo.attributes.position.array); return m;
}
function waves(m,t){
  const p=m.geometry.attributes.position, b=m.userData.base;
  for(let i=0;i<p.count;i++){ const x=b[i*3],z=b[i*3+2]; p.setY(i,Math.sin(x*.45+t)*.16+Math.cos(z*.35+t*1.2)*.13); }
  p.needsUpdate=true; m.geometry.computeVertexNormals();
}
"""

SHIP_HTML = """
<div id="w" style="position:relative;width:100%;height:__H__px;border-radius:14px;overflow:hidden;background:radial-gradient(ellipse at 50% 100%,#0d4650 0%,#062029 55%,#03131a 100%)">
<canvas id="c" style="width:100%;height:100%;display:block;cursor:grab"></canvas>
<div style="position:absolute;left:14px;top:12px;font:600 13px 'Segoe UI',Arial;color:#E6F4F1">__TITLE__<div style="font-weight:400;font-size:11px;color:#8FB3B0;margin-top:2px">__SUB__</div></div>
<div style="position:absolute;right:12px;bottom:9px;font:11px Arial;color:#6f9794">Drag to rotate</div>
<div id="err" style="position:absolute;left:14px;bottom:10px;font:11px Arial;color:#F5B942"></div></div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
<script>
(function(){
  if(typeof THREE==='undefined'){ document.getElementById('err').textContent='3D needs an internet connection (three.js could not load).'; return; }
  __SHIPJS__
  const w=document.getElementById('w'), cv=document.getElementById('c');
  const renderer=new THREE.WebGLRenderer({canvas:cv,antialias:true,alpha:true});
  renderer.setPixelRatio(Math.min(window.devicePixelRatio||1,2));
  const scene=new THREE.Scene(); scene.fog=new THREE.Fog(0x06202a,16,38);
  const cam=new THREE.PerspectiveCamera(42,1,.1,100);
  scene.add(new THREE.AmbientLight(0x6fa5a5,.55));
  const sun=new THREE.DirectionalLight(0xd5f5ef,.8); sun.position.set(6,11,6); scene.add(sun);
  const p1=new THREE.PointLight(0x2dd4bf,.55,26); p1.position.set(-7,6,5); scene.add(p1);
  const p2=new THREE.PointLight(0xf5b942,.4,20); p2.position.set(5,5,-4); scene.add(p2);
  const ship=buildShip(__SEED__,__STACKS__); scene.add(ship);
  const water=makeWater(44,56); water.position.y=-.55; scene.add(water);
  let th=0.9, ph=1.12, rad=17, drag=false, lx=0, ly=0, auto=true;
  cv.addEventListener('pointerdown',e=>{drag=true;auto=false;lx=e.clientX;ly=e.clientY;cv.style.cursor='grabbing';});
  window.addEventListener('pointerup',()=>{drag=false;auto=true;cv.style.cursor='grab';});
  window.addEventListener('pointermove',e=>{ if(!drag) return; th-= (e.clientX-lx)*.008; ph=Math.min(1.45,Math.max(.55,ph-(e.clientY-ly)*.006)); lx=e.clientX; ly=e.clientY; });
  function size(){ const W=w.clientWidth,H=w.clientHeight; renderer.setSize(W,H,false); cam.aspect=W/H; cam.updateProjectionMatrix(); }
  new ResizeObserver(size).observe(w); size();
  const clock=new THREE.Clock();
  (function loop(){ requestAnimationFrame(loop); const t=clock.getElapsedTime();
    if(auto) th+=.0035; waves(water,t);
    ship.position.y=Math.sin(t*1.1)*.12; ship.rotation.z=Math.sin(t*.9)*.012;
    if(ship.userData.glow) ship.userData.glow.material.emissiveIntensity=1.0+.6*Math.sin(t*3);
    cam.position.set(Math.cos(th)*Math.sin(ph)*rad, Math.cos(ph)*rad, Math.sin(th)*Math.sin(ph)*rad); cam.lookAt(0,1.2,0);
    renderer.render(scene,cam); })();
})();
</script>
"""


def ship3d(title, sub="", height=300, seed=7, stacks=10):
    """Render the animated 3D container ship (needs internet for three.js)."""
    html = (SHIP_HTML.replace("__H__", str(height)).replace("__TITLE__", title).replace("__SUB__", sub)
            .replace("__SHIPJS__", SHIP_JS).replace("__SEED__", str(seed)).replace("__STACKS__", str(stacks)))
    components.html(html, height=height + 4)
