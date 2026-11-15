# RouteIQ: Shipment Route Optimization under Cost, Time and Risk

Aiqon AI Internship take-home assignment: recommend the most suitable shipping route for a shipment by balancing **cost, transit time and risk**, and explain why.

- **Live app:** <(https://routeiq-route-optimizer.streamlit.app/)>
- **Notebook:** `Aiqon_Shipment_Route_Optimization.ipynb`

---

## 1. What this project does

For each shipment there are several route options through different transshipment hubs (Singapore, Dubai, Colombo, Port Klang). The system:

1. **Evaluates** every route option on cost, expected transit time and risk.
2. **Recommends** one route using a priority-based weighted score.
3. **Explains** the choice in plain language, for example: *"+$120 vs the cheapest option, arrives 3.1 days sooner, 8.0 points lower delay chance."*
4. **Flags** close decisions for human review and tests how stable each recommendation is.

## 2. Defining "optimal"

"Optimal" depends on the shipment's priority, so each priority has its own weights:

| Priority | Cost | Time | Risk |
|---|---|---|---|
| Urgent | 0.15 | 0.50 | 0.35 |
| Standard | 0.40 | 0.30 | 0.30 |
| Economy | 0.65 | 0.10 | 0.25 |

Urgent cargo pays for speed, Economy cargo pays for savings.

## 3. Method

- **Expected days** = estimated transit days + delay probability × delay days if late.
- **Risk** = average of three min-max normalised indicators: delay probability, congestion risk and geopolitical risk.
- **Score** (lower is better) = cost weight × normalised cost + time weight × normalised expected days + risk weight × normalised risk. Normalisation (min-max) is done **within each shipment**.
- **Confidence flag:** if the score gap between the best and second-best route is below 0.05, the decision is marked "low confidence, review manually".

## 4. Synthetic dataset

No public dataset was used. The data is synthetic and reproducible (`numpy` seed 42).

- **30 shipments**, each with **3 to 4 route options** (a hub equal to the origin or destination is skipped), 106 or so route records in `shipments.csv`.
- **Lanes** (origin, destination, base cost USD, base days): India→USA (2000, 30), China→Germany (2500, 35), Japan→UK (2300, 32), Singapore→Canada (2200, 34), India→Australia (1500, 20).
- **Hub profiles** (assumptions):

| Hub | Cost factor | Time factor | Delay prob. | Congestion | Geopolitical | Days if late |
|---|---|---|---|---|---|---|
| Singapore | 1.20 | 0.80 | 0.08 | 25 | 15 | 2 |
| Dubai | 1.00 | 0.90 | 0.16 | 60 | 45 | 3 |
| Colombo | 0.85 | 1.25 | 0.25 | 55 | 35 | 5 |
| Port Klang | 1.05 | 1.10 | 0.10 | 20 | 5 | 2 |

- Each shipment's cost, time, delay probability and risk values are the hub profile plus random noise, clipped to valid ranges.
- Priority mix: Urgent 25%, Standard 50%, Economy 25%.

## 5. Evaluation

The recommendation system is compared with three simple rules on all 30 shipments:

- **Always cheapest**, **Always fastest**, **Lowest risk**, and **RouteIQ (weighted score)**.
- Metrics: average cost, expected days, delay chance and risk score, overall and by priority.
- **Sensitivity analysis** (200 simulations per shipment): how often the same route is recommended when the priority weights change by ±20%, and when the delay estimates change by ±30%.
- Shipments whose recommendation changes often are listed as **fragile decisions** for human review.

Results are in the notebook outputs and in the dashboard's **Evaluation** and **Sensitivity** tabs.

## 6. Project structure

```
├── Aiqon_Shipment_Route_Optimization.ipynb   # main solution: data, scoring, evaluation, sensitivity
├── shipments.csv                             # synthetic dataset produced by the notebook
├── app.py                                    # Streamlit entry point (page navigation)
├── views.py                                  # app pages; the Dashboard follows the notebook logic
├── core.py                                   # shared theme, charts and the extended demo model
├── requirements.txt
└── README.md
```

## 7. How to run

**Notebook:** open it in Google Colab and choose *Runtime → Run all*. To run locally:

```bash
pip install pandas numpy matplotlib seaborn ipywidgets jupyter
jupyter notebook Aiqon_Shipment_Route_Optimization.ipynb
```

**Dashboard app (Python 3.11):**

```bash
pip install -r requirements.txt
streamlit run app.py
```

## 8. App pages

- **Dashboard** (from the notebook): dataset overview, hub scorecard, risk comparison, trade-off map, route recommendation with explanation, evaluation against baselines, sensitivity analysis, assumptions and data-quality report.
- **Shipping, Tracking, Invoice, Compare, Reports, Settings** (extended demo): these pages extend the same idea to any origin and destination using a distance and parcel-weight cost model, a Monte Carlo on-time probability, a TOPSIS cross-check, a simulated tracking view and origin and destination currencies. They use a different cost model from the notebook and are not part of the notebook's results.

## 9. Assumptions

- All data is synthetic. Hub profiles, weights, base costs, fees and the demo exchange rates (for example USD to INR 88) are assumptions, not real tariffs or live rates.
- Priority weights were chosen by judgement, not learned from data.
- Delay is modelled as a single probability and a fixed number of delay days per hub.
- The extended app pages use assumed freight rates per kg per 1,000 km, with bulk discounts by weight.

## 10. Limitations

- **Min-max normalisation** within each shipment makes the best option on a criterion score 0 and the worst score 1, even when the real difference is small. This can exaggerate small gaps. The score-gap flag and the stability tests reduce, but do not remove, this effect.
- Synthetic data cannot capture real port disruptions, seasonality or carrier pricing.
- With only 3 to 4 options per shipment, a single noisy value can change the winner.
- Weights are fixed per priority level, so the system does not learn from past decisions.

## 11. Future work

- Calibrate hub profiles with real carrier and port-performance data.
- Learn or elicit weights from planners instead of fixing them.
- Normalise against absolute reference ranges instead of within each shipment.
- Add live congestion and geopolitical risk feeds.
