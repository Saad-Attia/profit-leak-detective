"""
03_analysis.py
--------------
Answers the five management questions and runs the pricing simulator.

Q1. Are we becoming more profitable, or just selling more?
Q2. Which products and customers make or destroy profit?
Q3. Are sales reps giving away margin through discounts?
Q4. Which products are sold below their minimum profitable price?
Q5. What happens to profit if we change prices, discounts or delivery terms?

Run:  python 03_analysis.py
Input:  ../data/clean/*.csv
Output: ../outputs/tables/*.csv, ../outputs/charts/*.png, ../outputs/findings.md
"""
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick

ROOT = Path(__file__).resolve().parents[1]
CLEAN = ROOT / "data" / "clean"
TAB, CH = ROOT / "outputs" / "tables", ROOT / "outputs" / "charts"
TAB.mkdir(parents=True, exist_ok=True)
CH.mkdir(parents=True, exist_ok=True)

# ---- assumptions used by the simulator (shown in the dashboard as what-if parameters)
MIN_GM = 0.08            # price floor: net price must keep at least 8% gross margin over unit cost
DISC_CAP = 0.10          # maximum invoice discount
SMALL_ORDER = 400        # orders below this value pay a delivery fee
DELIVERY_FEE = 25        # fee charged on small orders
ELASTICITY = 1.0         # % volume lost for each 1% net price increase (deliberately cautious)
SMALL_ORDER_LOSS = 0.10  # share of small orders assumed lost after the fee is introduced

# ---- load
s = pd.read_csv(CLEAN / "fact_sales.csv", parse_dates=["order_date"])
r = pd.read_csv(CLEAN / "fact_returns.csv", parse_dates=["return_date"])
o = pd.read_csv(CLEAN / "fact_orders.csv", parse_dates=["delivery_date"])
cust = pd.read_csv(CLEAN / "dim_customer.csv")
prod = pd.read_csv(CLEAN / "dim_product.csv")
reps = pd.read_csv(CLEAN / "dim_rep.csv")

s = s.merge(prod[["sku", "product_name", "category"]], on="sku").merge(
    cust[["customer_id", "customer_name", "segment", "region", "cohort_year"]], on="customer_id")
s["year"] = s.order_date.dt.year
r = r.merge(s[["line_id", "year", "category", "segment", "region", "customer_name", "product_name"]],
            on="line_id", how="left")
o = o.merge(cust[["customer_id", "segment"]], on="customer_id")
o["year"] = o.delivery_date.dt.year

F = {}  # findings used in findings.md


def money(x):
    sign = "-" if x < 0 else ""
    x = abs(x)
    if x >= 1e6:
        return f"{sign}${x/1e6:,.2f}M"
    if x >= 1e3:
        return f"{sign}${x/1e3:,.0f}K"
    return f"{sign}${x:,.0f}"


# ===========================================================================
# Q1. More profitable, or just selling more?
# ===========================================================================
y = s.groupby("year").agg(gross_sales=("gross_sales", "sum"), discounts=("discount_amount", "sum"),
                          net_sales=("net_sales", "sum"), cogs=("cogs", "sum"), rebates=("rebate_amount", "sum"),
                          freight=("freight_cost", "sum"), cases=("quantity", "sum"))
ry = r.groupby("year").agg(return_credit=("credit_amount", "sum"), cost_recovered=("cost_recovered", "sum"),
                           write_off=("write_off_cost", "sum"))
y = y.join(ry)
y["net_revenue"] = y.net_sales - y.return_credit
y["gross_profit"] = y.net_revenue - (y.cogs - y.cost_recovered)
y["gross_margin"] = y.gross_profit / y.net_revenue
y["pocket_profit"] = y.gross_profit - y.rebates - y.freight
y["pocket_margin"] = y.pocket_profit / y.net_revenue
y["revenue_growth"] = y.net_revenue.pct_change()
y["gp_growth"] = y.gross_profit.pct_change()
y["pocket_growth"] = y.pocket_profit.pct_change()
y.round(4).to_csv(TAB / "q1_yearly_kpis.csv")
F["y"] = y

# monthly trend for the line chart
s["month"] = s.order_date.dt.to_period("M").dt.to_timestamp()
r["month"] = r.return_date.dt.to_period("M").dt.to_timestamp()
m = s.groupby("month").agg(net_sales=("net_sales", "sum"), cogs=("cogs", "sum"))
m = m.join(r.groupby("month").agg(cr=("credit_amount", "sum"), rec=("cost_recovered", "sum"))).fillna(0)
m["net_revenue"] = m.net_sales - m.cr
m["gross_profit"] = m.net_revenue - (m.cogs - m.rec)
m["gross_margin"] = m.gross_profit / m.net_revenue
m.to_csv(TAB / "q1_monthly_trend.csv")

# 2025 price waterfall (per $ of gross sales)
w25 = y.loc[2025]
waterfall = pd.DataFrame({
    "step": ["Gross sales (list price)", "Invoice discounts", "Returns credited", "Net revenue", "Cost of goods",
             "Gross profit", "Volume rebates", "Freight to customers", "Pocket profit"],
    "amount": [w25.gross_sales, -w25.discounts, -w25.return_credit, w25.net_revenue,
               -(w25.cogs - w25.cost_recovered), w25.gross_profit, -w25.rebates, -w25.freight, w25.pocket_profit]})
waterfall["pct_of_gross"] = waterfall.amount / w25.gross_sales
waterfall.to_csv(TAB / "q1_price_waterfall_2025.csv", index=False)

# cost increases vs price increases by category (2024 -> 2025, per case)
cat_y = s[s.year.isin([2024, 2025])].groupby(["category", "year"]).agg(
    net=("net_sales", "sum"), cogs=("cogs", "sum"), q=("quantity", "sum"))
cat_y["net_per_case"] = cat_y.net / cat_y.q
cat_y["cost_per_case"] = cat_y.cogs / cat_y.q
cat_y["gm"] = 1 - cat_y.cogs / cat_y.net
pt = cat_y.unstack("year")
pass_through = pd.DataFrame({
    "cost_change": pt.cost_per_case[2025] / pt.cost_per_case[2024] - 1,
    "net_price_change": pt.net_per_case[2025] / pt.net_per_case[2024] - 1,
    "gm_2024": pt.gm[2024], "gm_2025": pt.gm[2025]})
pass_through["gm_change_pts"] = (pass_through.gm_2025 - pass_through.gm_2024) * 100
pass_through = pass_through.sort_values("gm_change_pts")
pass_through.round(4).to_csv(TAB / "q1_cost_pass_through.csv")
F["pt"] = pass_through

# ===========================================================================
# Q2. Products and customers
# ===========================================================================
s25, r25 = s[s.year == 2025], r[r.year == 2025]


def profit_table(keys):
    a = s25.groupby(keys).agg(net_sales=("net_sales", "sum"), cogs=("cogs", "sum"), rebates=("rebate_amount", "sum"),
                              freight=("freight_cost", "sum"), cases=("quantity", "sum"),
                              orders=("order_id", "nunique"), avg_discount=("discount_pct", "mean"))
    b = r25.groupby(keys).agg(return_credit=("credit_amount", "sum"), cost_recovered=("cost_recovered", "sum"))
    a = a.join(b).fillna({"return_credit": 0, "cost_recovered": 0})
    a["net_revenue"] = a.net_sales - a.return_credit
    a["gross_profit"] = a.net_revenue - (a.cogs - a.cost_recovered)
    a["pocket_profit"] = a.gross_profit - a.rebates - a.freight
    a["gross_margin"] = a.gross_profit / a.net_revenue
    a["pocket_margin"] = a.pocket_profit / a.net_revenue
    return a


seg = profit_table("segment").sort_values("pocket_margin")
seg["freight_pct"] = seg.freight / seg.net_revenue
seg["return_pct"] = seg.return_credit / seg.net_sales
seg["avg_order_value"] = seg.net_sales / seg.orders
seg.round(4).to_csv(TAB / "q2_segment_profitability_2025.csv")
F["seg"] = seg

custp = profit_table(["customer_id", "customer_name", "segment"]).reset_index().sort_values("pocket_profit")
custp.round(4).to_csv(TAB / "q2_customer_profitability_2025.csv", index=False)
loss_c = custp[custp.pocket_profit < 0]
F["cust_total"], F["cust_loss"] = len(custp), len(loss_c)
F["cust_loss_rev_share"] = loss_c.net_revenue.sum() / custp.net_revenue.sum()
F["cust_loss_amount"] = loss_c.pocket_profit.sum()
F["cust_loss_by_seg"] = loss_c.groupby("segment").size().sort_values(ascending=False)
# whale curve: cumulative pocket profit, best customers first
whale = custp.sort_values("pocket_profit", ascending=False).reset_index(drop=True)
whale["cum_profit_pct"] = whale.pocket_profit.cumsum() / whale.pocket_profit.sum()
whale["cum_customer_pct"] = (whale.index + 1) / len(whale)
F["top20_share"] = whale.loc[whale.cum_customer_pct <= 0.2, "pocket_profit"].sum() / whale.pocket_profit.sum()
whale.round(4).to_csv(TAB / "q2_whale_curve_2025.csv", index=False)
chains = custp[custp.segment == "National Chain"].sort_values("net_revenue", ascending=False)
F["chains"] = chains

prodp = profit_table(["sku", "product_name", "category"]).reset_index().sort_values("pocket_profit")
prodp.round(4).to_csv(TAB / "q2_product_profitability_2025.csv", index=False)
F["prod_loss"] = prodp[prodp.pocket_profit < 0]
F["cat"] = profit_table("category").sort_values("pocket_margin")
F["cat"].round(4).to_csv(TAB / "q2_category_profitability_2025.csv")

# returns: where they come from
rx = r25.groupby(["segment", "category"]).agg(credit=("credit_amount", "sum"), write_off=("write_off_cost", "sum"),
                                              impact=("profit_impact", "sum")).reset_index()
sold = s25.groupby(["segment", "category"]).net_sales.sum().rename("net_sales").reset_index()
rx = rx.merge(sold, on=["segment", "category"])
rx["return_rate"] = rx.credit / rx.net_sales
rx.sort_values("impact").round(4).to_csv(TAB / "q2_returns_by_segment_category_2025.csv", index=False)
F["ret"] = rx
F["ret_reason"] = r25.groupby("reason").profit_impact.sum().sort_values()

# ===========================================================================
# Q3. Rep discounting
# ===========================================================================
field = s25[s25.rep_id != "R14"]  # key accounts negotiate chain contracts centrally
rep = field.groupby("rep_id").agg(gross_sales=("gross_sales", "sum"), discount_amount=("discount_amount", "sum"),
                                  net_sales=("net_sales", "sum"), cogs=("cogs", "sum"),
                                  customers=("customer_id", "nunique"))
rep["avg_discount"] = rep.discount_amount / rep.gross_sales
rep["gross_margin"] = 1 - rep.cogs / rep.net_sales
rep["sales_per_customer"] = rep.net_sales / rep.customers
rep = rep.join(reps.set_index("rep_id")[["rep_name", "region"]])
# discount compared with the other reps selling to the same segments (mix-adjusted)
seg_disc = field.groupby("segment").apply(lambda d: d.discount_amount.sum() / d.gross_sales.sum())
field = field.assign(expected_disc=field.segment.map(seg_disc) * field.gross_sales)
exp = field.groupby("rep_id").expected_disc.sum()
rep["excess_discount"] = rep.discount_amount - exp
rep["excess_discount_pts"] = rep.excess_discount / rep.gross_sales * 100
rep = rep.sort_values("excess_discount", ascending=False)
rep.round(4).to_csv(TAB / "q3_rep_discounting_2025.csv")
F["rep"] = rep
# do generous reps sell more per customer? (same segment comparison)
cs = field.groupby(["rep_id", "customer_id", "segment"]).agg(
    net=("net_sales", "sum"), gross=("gross_sales", "sum"), disc=("discount_amount", "sum")).reset_index()
cs["disc_rate"] = cs.disc / cs.gross
F["disc_vol_corr"] = cs.groupby("segment").apply(lambda d: d.disc_rate.corr(d.net)).round(2)

# ===========================================================================
# Q4. Below minimum profitable price
# ===========================================================================
s25 = s25.assign(net_price=s25.net_sales / s25.quantity,
                 floor_price=s25.unit_cost / (1 - MIN_GM))
below_cost = s25[s25.net_price < s25.unit_cost]
below_floor = s25[s25.net_price < s25.floor_price]
F["below_cost_lines"], F["below_cost_sales"] = len(below_cost), below_cost.net_sales.sum()
F["below_cost_loss"] = (below_cost.net_sales - below_cost.cogs).sum()
F["below_cost_skus"] = below_cost.sku.nunique()
F["below_floor_sales_share"] = below_floor.net_sales.sum() / s25.net_sales.sum()
bc = below_cost.groupby(["category", "segment"]).agg(lines=("line_id", "size"), net_sales=("net_sales", "sum"),
                                                     loss=("gross_profit", "sum")).reset_index().sort_values("loss")
bc.round(2).to_csv(TAB / "q4_below_cost_by_category_segment_2025.csv", index=False)
F["below_cost_by_seg"] = below_cost.groupby("segment").gross_profit.sum().sort_values()
F["below_cost_by_cat"] = below_cost.groupby("category").gross_profit.sum().sort_values()
skus_bc = below_cost.groupby(["sku", "product_name", "category"]).agg(
    lines=("line_id", "size"), net_sales=("net_sales", "sum"), loss=("gross_profit", "sum"),
    avg_net_price=("net_price", "mean"), unit_cost=("unit_cost", "mean")).reset_index().sort_values("loss")
skus_bc["min_price_8pct"] = skus_bc.unit_cost / (1 - MIN_GM)
skus_bc.round(2).to_csv(TAB / "q4_skus_sold_below_cost_2025.csv", index=False)

# ===========================================================================
# Q5. Simulator (2025 base year, annual effect on pocket profit)
# ===========================================================================
base_pocket = y.loc[2025, "pocket_profit"]
base_lines = s25.copy()


def apply_price_levers(d, cap=None, floor=None):
    """Return line-level pocket profit after capping discounts and/or enforcing a price floor.
    Volume on each changed line falls by ELASTICITY x the % price increase."""
    price = d.net_price.to_numpy().copy()
    if cap is not None:
        price = np.maximum(price, d.list_price.to_numpy() * (1 - cap))
    if floor is not None:
        price = np.maximum(price, d.unit_cost.to_numpy() / (1 - floor))
    up = price / d.net_price.to_numpy() - 1
    keep = np.clip(1 - ELASTICITY * up, 0, 1)
    qty = d.quantity.to_numpy() * keep
    new_net = price * qty
    new_cogs = d.unit_cost.to_numpy() * qty
    new_reb = new_net * d.rebate_pct_line.to_numpy()
    new_frt = d.freight_cost.to_numpy() * keep
    return new_net - new_cogs - new_reb - new_frt


def lever_effect(d, **kw):
    return apply_price_levers(d, **kw).sum() - d.pocket_profit.sum()


def scen_fee(d):
    """Charge a delivery fee on small orders; assume a share of them is lost."""
    ordp = d.groupby("order_id").agg(net=("net_sales", "sum"), pocket=("pocket_profit", "sum"))
    small = ordp[ordp.net < SMALL_ORDER]
    fee_income = len(small) * (1 - SMALL_ORDER_LOSS) * DELIVERY_FEE
    lost_profit = small.pocket.sum() * SMALL_ORDER_LOSS  # negative pocket -> losing them helps
    return fee_income - lost_profit, len(small), small.pocket.sum()


def scen_returns(d_ret):
    """Halve expired returns of short-life goods to convenience stores (smaller, more frequent drops)."""
    x = d_ret[(d_ret.reason == "Expired") & d_ret.category.isin(["Bakery", "Dairy"]) &
              (d_ret.segment == "Convenience Store")]
    return -x.profit_impact.sum() * 0.5


base_lines = base_lines.assign(rebate_pct_line=base_lines.rebate_amount / base_lines.net_sales)

sc = []
sc.append((f"Price floor (min {MIN_GM:.0%} gross margin on every line)", lever_effect(base_lines, floor=MIN_GM)))
sc.append((f"Cap invoice discounts at {DISC_CAP:.0%}", lever_effect(base_lines, cap=DISC_CAP)))
fee, n_small, small_pocket = scen_fee(base_lines)
sc.append((f"${DELIVERY_FEE} delivery fee on orders under ${SMALL_ORDER}", fee))
sc.append(("Halve expired Bakery/Dairy returns from convenience stores", scen_returns(r25)))
both = lever_effect(base_lines, cap=DISC_CAP, floor=MIN_GM)  # applied together, so no double count
sc.append(("All four together", both + fee + sc[3][1]))
scen = pd.DataFrame(sc, columns=["scenario", "pocket_profit_change"])
scen["new_pocket_profit"] = base_pocket + scen.pocket_profit_change
scen.round(0).to_csv(TAB / "q5_simulator_scenarios_2025.csv", index=False)
F["scen"], F["n_small"], F["small_pocket"] = scen, n_small, small_pocket

# ===========================================================================
# Charts (dark theme, same palette as the dashboard)
# ===========================================================================
BG, PANEL, TXT, MUTED = "#0F172A", "#111C33", "#E2E8F0", "#94A3B8"
BLUE, GREEN, RED, AMBER = "#3B82F6", "#22C55E", "#EF4444", "#F59E0B"
plt.rcParams.update({"figure.facecolor": BG, "axes.facecolor": PANEL, "axes.edgecolor": "#334155",
                     "axes.labelcolor": TXT, "xtick.color": MUTED, "ytick.color": MUTED, "text.color": TXT,
                     "font.size": 10, "axes.titleweight": "bold", "axes.titlesize": 12})


def save(fig, name):
    fig.tight_layout()
    fig.savefig(CH / name, dpi=150)
    plt.close(fig)


fig, ax = plt.subplots(figsize=(10, 4.2))
ax.plot(m.index, m.net_revenue / 1e6, color=BLUE, lw=2, label="Net revenue")
ax2 = ax.twinx()
ax2.plot(m.index, m.gross_margin, color=GREEN, lw=2, label="Gross margin %")
ax2.yaxis.set_major_formatter(mtick.PercentFormatter(1, 0))
ax2.tick_params(colors=MUTED)
ax.set_ylabel("Net revenue ($M)")
ax.set_title("Revenue keeps growing while gross margin falls")
ax.legend(loc="upper left", frameon=False)
ax2.legend(loc="upper right", frameon=False)
save(fig, "01_revenue_vs_margin_trend.png")

fig, ax = plt.subplots(figsize=(10, 4.2))
steps = waterfall.step.tolist()
vals = waterfall.amount.to_numpy() / 1e6
bottoms, running = [], 0
colors = []
for st, v in zip(steps, vals):
    if st in ("Gross sales (list price)", "Net revenue", "Gross profit", "Pocket profit"):
        bottoms.append(0); running = v; colors.append(BLUE if st != "Pocket profit" else GREEN)
    else:
        running += v; bottoms.append(running); colors.append(RED)
heights = [v if b == 0 else -v for v, b in zip(vals, bottoms)]
ax.bar(range(len(steps)), heights, bottom=bottoms, color=colors)
for i, (v, b) in enumerate(zip(vals, bottoms)):
    ax.text(i, (b if b else 0) + abs(heights[i]) + 0.3, f"{v:,.1f}", ha="center", color=TXT, fontsize=9)
ax.set_xticks(range(len(steps)), [x.replace(" (list price)", "") for x in steps], rotation=25, ha="right")
ax.set_ylabel("$M")
ax.set_title("2025 price waterfall: from list price to pocket profit")
save(fig, "02_price_waterfall_2025.png")

fig, ax = plt.subplots(figsize=(7, 4.2))
ax.plot(whale.cum_customer_pct, whale.cum_profit_pct, color=BLUE, lw=2)
ax.axhline(1, color=MUTED, ls="--", lw=1)
ax.xaxis.set_major_formatter(mtick.PercentFormatter(1, 0))
ax.yaxis.set_major_formatter(mtick.PercentFormatter(1, 0))
ax.set_xlabel("Customers, most profitable first")
ax.set_ylabel("Cumulative pocket profit")
ax.set_title("Customer whale curve, 2025")
save(fig, "03_customer_whale_curve.png")

fig, ax = plt.subplots(figsize=(8, 4.2))
segc = {"National Chain": BLUE, "Regional Supermarket": "#A78BFA", "Independent Grocery": GREEN,
        "Convenience Store": RED, "HoReCa": AMBER}
for sg, d in custp.groupby("segment"):
    ax.scatter(d.net_revenue / 1e3, d.pocket_margin, s=12 + d.orders / 2, alpha=0.7, color=segc[sg], label=sg)
ax.axhline(0, color=MUTED, lw=1)
ax.set_xscale("log")
ax.yaxis.set_major_formatter(mtick.PercentFormatter(1, 0))
ax.set_xlabel("Net revenue 2025 ($K, log scale)")
ax.set_ylabel("Pocket margin")
ax.set_title("Customers: revenue vs pocket margin (bubble = orders)")
ax.legend(frameon=False, fontsize=8, loc="lower right")
save(fig, "04_customer_scatter.png")

fig, ax = plt.subplots(figsize=(8, 4.2))
rr = rep.sort_values("excess_discount_pts")
ax.barh(rr.rep_name, rr.excess_discount_pts, color=[RED if v > 1 else BLUE for v in rr.excess_discount_pts])
ax.axvline(0, color=MUTED, lw=1)
ax.set_xlabel("Discount vs same-segment average (percentage points)")
ax.set_title("Field reps: discount above or below their peers, 2025")
save(fig, "05_rep_excess_discount.png")

fig, ax = plt.subplots(figsize=(9, 4.2))
sc_plot = scen.iloc[:-1]
ax.barh(sc_plot.scenario.str.replace("$", r"\$", regex=False), sc_plot.pocket_profit_change / 1e3, color=GREEN)
for i, v in enumerate(sc_plot.pocket_profit_change / 1e3):
    ax.text(v + 5, i, f"+\\${v:,.0f}K", va="center", fontsize=9)
ax.set_xlabel("Change in 2025 pocket profit ($K)")
ax.set_title("Simulator: profit impact of each lever")
save(fig, "06_simulator_scenarios.png")

# ===========================================================================
# findings.md
# ===========================================================================
y23, y24, y25 = y.loc[2023], y.loc[2024], y.loc[2025]
seg_ = F["seg"]
rep_top = rep.head(3)
worst_cat = pass_through.index[0]
chains_ = F["chains"]
lines = []
A = lines.append
A("# Findings: Harbor & Field Distribution (simulated data), 2023-2025\n")
A("> All numbers come from the simulated dataset in this repository and are produced by `03_analysis.py`.\n")
A("## Q1. Are we more profitable, or just selling more?\n")
A(f"- Net revenue grew from {money(y23.net_revenue)} (2023) to {money(y25.net_revenue)} (2025), "
  f"+{y25.net_revenue / y23.net_revenue - 1:.1%} over two years.")
A(f"- Gross profit peaked in 2024 at {money(y24.gross_profit)} and fell to {money(y25.gross_profit)} in 2025 "
  f"({y25.gp_growth:+.1%}). Gross margin went from {y23.gross_margin:.1%} to {y25.gross_margin:.1%}.")
A(f"- Pocket profit (after rebates and freight) fell {y25.pocket_growth:+.1%} in 2025 to {money(y25.pocket_profit)}; "
  f"pocket margin is {y25.pocket_margin:.1%}.")
A(f"- In 2025, {abs(waterfall.loc[1, 'pct_of_gross']):.1%} of list-price sales went out as invoice discounts, "
  f"{abs(waterfall.loc[6, 'pct_of_gross']):.1%} as rebates and {abs(waterfall.loc[7, 'pct_of_gross']):.1%} as freight.")
A(f"- Supplier costs rose faster than prices in 2025. Worst category: {worst_cat}, cost per case "
  f"{pass_through.loc[worst_cat, 'cost_change']:+.1%} vs net price {pass_through.loc[worst_cat, 'net_price_change']:+.1%}, "
  f"gross margin {pass_through.loc[worst_cat, 'gm_change_pts']:+.1f} pts.\n")
A("## Q2. Which products and customers make or destroy profit?\n")
A(f"- {F['cust_loss']} of {F['cust_total']} active customers lost money in 2025 at pocket level, "
  f"holding {F['cust_loss_rev_share']:.1%} of net revenue and losing {money(abs(F['cust_loss_amount']))} in total.")
A("- Loss-making customers by segment: " + ", ".join(f"{k} {v}" for k, v in F["cust_loss_by_seg"].items()) + ".")
A(f"- The top 20% of customers earn {F['top20_share']:.0%} of total pocket profit.")
seg_counts = custp.segment.value_counts()
for sg, n_loss in F["cust_loss_by_seg"].items():
    A(f"- {n_loss} of {seg_counts[sg]} {sg} customers are loss-making.")
big = custp.sort_values("net_revenue").iloc[-1]
A(f"- The biggest customer, {big.customer_name}, brings {money(big.net_revenue)} ({big.net_revenue / custp.net_revenue.sum():.0%} of revenue) "
  f"but only {money(big.pocket_profit)} of pocket profit: a {big.pocket_margin:.1%} pocket margin after a "
  f"{big.avg_discount:.1%} average discount and {money(big.rebates)} of rebates.")
for sg in seg_.index:
    A(f"- {sg}: pocket margin {seg_.loc[sg, 'pocket_margin']:.1%}, freight {seg_.loc[sg, 'freight_pct']:.1%} of revenue, "
      f"returns {seg_.loc[sg, 'return_pct']:.1%}, average order {money(seg_.loc[sg, 'avg_order_value'])}.")
A(f"- National chains: {money(chains_.net_revenue.sum())} of revenue ({chains_.net_revenue.sum() / custp.net_revenue.sum():.0%}) "
  f"but only {money(chains_.pocket_profit.sum())} of pocket profit; "
  f"{(chains_.pocket_profit < 0).sum()} of {len(chains_)} chains are loss-making after rebates.")
top_ret = F["ret"].sort_values("impact").iloc[0]
A(f"- Returns cost {money(abs(F['ret_reason'].sum()))} of profit in 2025; the single biggest source is "
  f"{top_ret.category} sold to {top_ret.segment} (return rate {top_ret.return_rate:.1%}, impact {money(top_ret.impact)}).\n")
A("## Q3. Are reps giving away margin?\n")
for rid, rw in rep_top.iterrows():
    A(f"- {rw.rep_name} ({rid}, {rw.region}): {rw.excess_discount_pts:+.1f} pts above peers selling to the same segments, "
      f"= {money(rw.excess_discount)} of extra discount in 2025.")
A("- Correlation between a customer's discount rate and its sales, within each segment: "
  + ", ".join(f"{k} {v:+.2f}" for k, v in F["disc_vol_corr"].items())
  + ". Bigger discounts are not buying bigger customers.\n")
A("## Q4. What is sold below its minimum profitable price?\n")
A(f"- {F['below_cost_lines']:,} order lines across {F['below_cost_skus']} SKUs were invoiced below unit cost in 2025: "
  f"{money(F['below_cost_sales'])} of sales, {money(abs(F['below_cost_loss']))} of gross loss.")
A("- By segment: " + ", ".join(f"{k} {money(v)}" for k, v in F["below_cost_by_seg"].items()) + ".")
A("- By category: " + ", ".join(f"{k} {money(v)}" for k, v in F["below_cost_by_cat"].items()) + ".")
A(f"- {F['below_floor_sales_share']:.1%} of 2025 sales were priced below the floor of cost + {MIN_GM:.0%} gross margin.\n")
A("## Q5. What-if scenarios (2025 base, annual pocket profit)\n")
A(f"Assumptions: elasticity {ELASTICITY:.1f} (each 1% price rise loses 1% volume on the affected lines); "
  f"{SMALL_ORDER_LOSS:.0%} of small orders lost after the fee. Base pocket profit: {money(base_pocket)}.\n")
A("| Scenario | Change in pocket profit |\n|---|---|")
for _, rw in scen.iterrows():
    A(f"| {rw.scenario} | {'+' if rw.pocket_profit_change >= 0 else ''}{money(rw.pocket_profit_change)} |")
A(f"\nThere were {F['n_small']:,} orders under ${SMALL_ORDER} in 2025, with a combined pocket profit of {money(F['small_pocket'])}.")
(ROOT / "outputs" / "findings.md").write_text("\n".join(lines) + "\n")
print("\n".join(lines))
