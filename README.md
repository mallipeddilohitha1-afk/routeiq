# 🚢 RouteIQ: Shipment Route Recommender

**Live app:** https://routeiq-route-optimizer.streamlit.app/

RouteIQ is a decision-support system that recommends the most suitable shipment route by balancing **cost, transit time and risk** under uncertainty, and explains each recommendation in plain language. It was built for the Aiqon AI Internship take-home assignment, *Optimizing Shipment Routes Under Cost, Time, and Risk Constraints*.

> All data is synthetic. Hub profiles, formulas and rates are stated assumptions, not real market data.

---

## 1. Problem

Choosing a shipment route is not simply choosing the shortest or cheapest path. Every route involves trade-offs:

- a cheaper hub may be slower or more delay-prone,
- a faster hub may cost more,
- a route may pass through congested or geopolitically risky regions.

These objectives conflict, and delay and risk are uncertain. A useful system must therefore (1) evaluate several route options, (2) recommend one based on explicit criteria, and (3) explain why it is preferred over the alternatives.

## 2. Defining "optimal"

There is no single optimal route. What is best depends on the shipment's **priority**, so "optimal" is defined as the route with the best weighted balance of three criteria:

| Priority | Cost weight | Time weight | Risk weight | Rationale |
|----------|:-----------:|:-----------:|:-----------:|-----------|
| Urgent   | 0.15 | 0.50 | 0.35 | Pay more to arrive fast and reliably |
| Standard | 0.40 | 0.30 | 0.30 | Balanced trade-off |
| Economy  | 0.65 | 0.10 | 0.25 | Minimise spend, accept slower transit |

The weights are judgement calls that encode business priorities. Because they are subjective, the system tests how sensitive its decisions are to them (see section 6).

## 3. Synthetic dataset

No public dataset captures hub-level cost, delay and risk together, so a synthetic dataset was constructed (30 shipments, 112 route options, fixed random seed).

**Construction**

- Five trade lanes (India→USA, China→Germany, Japan→UK, Singapore→Canada, India→Australia), each with a base cost and base transit time.
- Four transshipment hubs, each with a "personality". A hub is excluded if it is the shipment's origin or destination.
- Each route's values are the lane base multiplied by the hub factor and a small random noise term.

**Hub personalities (assumptions)**

| Hub | Cost factor | Time factor | Delay prob. | Congestion | Geopolitical | Days if late |
|-----|:----:|:----:|:----:|:----:|:----:|:----:|
| Singapore  | 1.20 | 0.80 | 8%  | 25 | 15 | 2 |
| Dubai      | 1.00 | 0.90 | 16% | 60 | 45 | 3 |
| Colombo    | 0.85 | 1.25 | 25% | 55 | 35 | 5 |
| Port Klang | 1.05 | 1.10 | 10% | 20 | 5  | 2 |

**Intent.** Cheap hubs (Colombo) are slow and delay-prone. Fast hubs (Singapore) are expensive but reliable. Dubai carries the highest geopolitical risk. No hub dominates on every criterion, so every decision is a genuine trade-off.

**Fields per route:** origin, destination, intermediate hub, priority, cargo value, shipping cost, estimated transit days, delay probability, delay days if late, congestion risk (0–100), geopolitical risk (0–100).

## 4. Scoring framework

### 4.1 Expected delivery time

Delay is uncertain, so transit time is adjusted by its expected delay:

```
expected_days = transit_days + delay_probability × delay_days_if_late
```

### 4.2 Normalisation

Cost, expected days and each risk indicator are **min-max normalised within a shipment**:

```
norm(x) = (x − min) / (max − min)
```

This maps the best option to 0 and the worst to 1, so criteria measured in dollars, days and percentages become comparable. Normalising within a shipment compares options only against that shipment's own alternatives.

### 4.3 Composite risk

```
risk = ( norm(delay_probability) + norm(congestion) + norm(geopolitical) ) / 3
```

### 4.4 Weighted score

```
score = w_cost × norm(cost) + w_time × norm(expected_days) + w_risk × risk
```

The route with the **lowest score** is recommended. Weighted scoring was chosen because it is transparent, easy to explain to a logistics operator, and lets priority change the outcome directly.

### 4.5 Confidence check

The gap between the best and second-best score measures how clear the decision is:

```
gap = score(2nd best) − score(best)
```

If the gap is below a review threshold (0.05), the system flags the recommendation as **low confidence** for manual review rather than presenting a false-certain answer.

## 5. Handling conflicting objectives and uncertainty

### 5.1 TOPSIS cross-check

A second, independent method guards against the choice of scoring formula. TOPSIS ranks each route by its relative closeness to an ideal solution (best on every criterion) and distance from an anti-ideal solution (worst on every criterion). It uses five criteria: cost, expected days, delay probability, congestion and geopolitical risk, with the risk weight split equally across the three risk indicators. When weighted scoring and TOPSIS select the same hub, confidence in the decision rises. Disagreement signals a close trade-off.

### 5.2 Monte Carlo on-time probability

Point estimates hide uncertainty, so each route is simulated thousands of times. In each simulated journey:

- the delay probability is drawn from a **Beta** distribution centred on the estimate,
- base transit time is drawn from a **Normal** distribution (±4%),
- if a delay occurs, its length is drawn from a **Gamma** distribution.

From these samples the system reports the **on-time probability** against a deadline and the **P90 transit time** (the duration that 90% of journeys beat). Deadlines scale with priority: base days × 1.0 for Urgent, × 1.25 for Standard, × 1.5 for Economy.

## 6. Explainability

Every recommendation is compared with three reference routes: the cheapest, the fastest and the lowest-risk. The explanation states the difference in cost, arrival time and delay probability. For example:

> *Versus the cheapest option (Colombo): +$310, arrives 6.2 days sooner, −17.0 points delay chance.*

It also identifies which criterion contributed the smallest penalty to the winning route, so an operator can see why a slightly more expensive route can win through much lower delay risk.

## 7. Evaluation

Since this is a decision problem with no ground-truth "correct" route, evaluation compares RouteIQ against simple rules and tests its robustness.

### 7.1 Baseline comparison

Four strategies are compared on average cost, expected days, delay probability and risk, overall and by priority:

- always cheapest,
- always fastest,
- lowest risk,
- RouteIQ (weighted score).

The share of shipments where RouteIQ picks the same hub as each simple rule shows whether it makes real trade-offs. A low overlap means it is not simply copying one rule. Results by priority should show the weighting at work: Urgent shipments favour speed, Economy shipments favour cost.

### 7.2 Sensitivity and decision stability

For each shipment, 200 simulations re-run the decision with perturbed inputs:

- **Weight sensitivity:** each weight randomly varied by ±20%, then renormalised.
- **Estimate uncertainty:** delay probabilities varied by ±30%.

**Decision stability** is the share of simulations in which the recommendation stays the same (1.0 = never changes). Shipments with low stability are **fragile decisions**, listed for human review. This directly addresses the assignment's challenges of parameter sensitivity and uncertain delay estimates.

## 8. Extensions in the application

Beyond the 30-shipment dataset, the app generalises the same logic to any pair of 24 world ports:

- **Distance and detour:** great-circle (haversine) distances. Routing through a hub adds a detour ratio that raises cost and time.
- **Weight-based pricing:** freight cost scales with distance and parcel weight, with bulk discounts for heavy loads and a premium for light parcels, plus a documentation fee and minimum charge.
- **Seasonality:** some hubs have month-dependent delay uplifts (for example monsoon months at Colombo).
- **Business costs:** hub handling fees, cargo insurance, and an inventory holding cost for capital tied up in transit.

## 9. Assumptions and limitations

- **Synthetic data:** hub profiles, noise levels and lanes are invented. Conclusions about specific hubs are illustrative, not factual.
- **Simplified routes:** each option is one origin → hub → destination path, with no vessel schedules, chokepoints or live data.
- **Assumed economics:** freight rates, fees, insurance and exchange rates are demo values.
- **Relative scores:** min-max normalisation ranks options within a shipment, so scores are not comparable across shipments. It is also sensitive to outliers when there are few options.
- **Subjective weights:** the priority weights reflect judgement, not learned preferences.
- **Independent risk indicators:** delay, congestion and geopolitical risk are averaged equally and treated as independent, though in reality they correlate.
- **Small samples:** the evaluation demonstrates behaviour but does not prove statistical performance.

## 10. Future work

- Replace synthetic profiles with real port performance and freight-rate data.
- Support true multi-leg routes and Pareto-front multi-objective optimisation.
- Learn delay probabilities and priority weights from historical shipment outcomes.
- Add cargo-specific constraints such as perishables, customs clearance and carrier capacity.
