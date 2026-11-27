"""
05_render_mockups.py
--------------------
Renders the four dashboard pages as black-theme mockups (1280 x 720) using the
real 2025 numbers, so the Power BI build has an exact visual target.
Positions match docs/POWER_BI_BUILD_GUIDE_BLACK.md.

Run:  python 05_render_mockups.py      (needs playwright with chromium)
Output: ../docs/mockups/page*.png
"""
from pathlib import Path
import numpy as np
import pandas as pd
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
CLEAN = ROOT / "data" / "clean"
OUT = ROOT / "docs" / "mockups"
OUT.mkdir(parents=True, exist_ok=True)

# ---- design tokens (same as powerbi/control_tower_black_theme.json)
BG, CARD, BORDER, TXT, MUTED, DIM, TRACK = "#000000", "#0A0A0A", "#262626", "#FAFAFA", "#A3A3A3", "#737373", "#262626"
BLUE, GREEN, RED, ORANGE = "#3B82F6", "#22C55E", "#EF4444", "#F97316"
MIN_GM, CAP, ELAST, THR, FEE, LOST = 0.08, 0.10, 1.0, 400, 25, 0.10

# ---------------------------------------------------------------- data
s = pd.read_csv(CLEAN / "fact_sales.csv", parse_dates=["order_date"])
r = pd.read_csv(CLEAN / "fact_returns.csv", parse_dates=["sale_date"])
cust = pd.read_csv(CLEAN / "dim_customer.csv")
prod = pd.read_csv(CLEAN / "dim_product.csv")
reps = pd.read_csv(CLEAN / "dim_rep.csv")
s = s.merge(cust[["customer_id", "customer_name", "segment"]], on="customer_id").merge(prod[["sku", "product_name", "category"]], on="sku")
r = r.merge(cust[["customer_id", "customer_name", "segment"]], on="customer_id").merge(prod[["sku", "category"]], on="sku")
s["year"], r["year"] = s.order_date.dt.year, r.sale_date.dt.year
s["month"] = s.order_date.dt.month
r["month"] = r.sale_date.dt.month


def pnl(sd, rd):
    net = sd.net_sales.sum() - rd.credit_amount.sum()
    gp = net - (sd.cogs.sum() - rd.cost_recovered.sum())
    pocket = gp - sd.rebate_amount.sum() - sd.freight_cost.sum()
    return dict(net=net, gp=gp, gm=gp / net if net else 0, pocket=pocket, pm=pocket / net if net else 0)


s25, r25, s24, r24 = s[s.year == 2025], r[r.year == 2025], s[s.year == 2024], r[r.year == 2024]
k25, k24 = pnl(s25, r25), pnl(s24, r24)
below_cost = s25[s25.net_sales < s25.unit_cost * s25.quantity]
bc_loss = (below_cost.net_sales - below_cost.unit_cost * below_cost.quantity).sum()
below_floor_pct = s25[s25.net_sales < s25.unit_cost * s25.quantity / (1 - MIN_GM)].net_sales.sum() / s25.net_sales.sum()
ret_impact = r25.profit_impact.sum()

# rep excess discount (mix-adjusted, field reps)
field = s25[s25.rep_id != "R14"]
seg_rate = field.groupby("segment").apply(lambda d: d.discount_amount.sum() / d.gross_sales.sum())
field = field.assign(exp=field.gross_sales * field.segment.map(seg_rate))
rp = field.groupby("rep_id").agg(g=("gross_sales", "sum"), d=("discount_amount", "sum"), e=("exp", "sum"))
rp["pts"] = (rp.d - rp.e) / rp.g * 100
rp["usd"] = rp.d - rp.e
rp = rp.join(reps.set_index("rep_id")[["rep_name", "region"]]).sort_values("pts", ascending=False)
excess = rp.usd.clip(lower=0).sum()
leak_total = abs(bc_loss) + excess + abs(ret_impact)


def group_pnl(key):
    out = {}
    for k, sd in s25.groupby(key):
        out[k] = pnl(sd, r25[r25[key] == k]) | dict(orders=sd.order_id.nunique(), disc=sd.discount_amount.sum() / sd.gross_sales.sum(),
                                                  freight=sd.freight_cost.sum(), rebates=sd.rebate_amount.sum())
    return pd.DataFrame(out).T


cat = group_pnl("category").sort_values("pm", ascending=False)
seg = group_pnl("segment").sort_values("pm", ascending=False)
cp = group_pnl("customer_name")
cp["segment"] = cp.index.map(cust.set_index("customer_name").segment)
active = len(cp)
loss_c = cp[cp.pocket < 0]
top20 = cp.sort_values("pocket", ascending=False).head(int(active * 0.2)).pocket.sum() / cp.pocket.sum()
biggest = cp.sort_values("net", ascending=False).iloc[0]

mon = pd.DataFrame({m: pnl(s25[s25.month == m], r25[r25.month == m]) for m in range(1, 13)}).T

# cost vs price per case
def per_case(d):
    g = d.groupby("category").agg(n=("net_sales", "sum"), c=("cogs", "sum"), q=("quantity", "sum"))
    return g.n / g.q, g.c / g.q
p25, c25 = per_case(s25)
p24, c24 = per_case(s24)
pt = pd.DataFrame({"cost": c25 / c24 - 1, "price": p25 / p24 - 1}).sort_values("cost", ascending=False)

skus = below_cost.assign(loss=below_cost.net_sales - below_cost.unit_cost * below_cost.quantity).groupby(
    ["sku", "product_name", "category"]).agg(lines=("line_id", "size"), sales=("net_sales", "sum"), loss=("loss", "sum"),
                                              price=("net_sales", "sum"), q=("quantity", "sum"), cost=("unit_cost", "mean")).reset_index()
skus["avg_price"] = skus.price / skus.q
skus["min_price"] = skus.cost / (1 - MIN_GM)
skus = skus.sort_values("loss").head(6)
ret_cat = r25.groupby("category").profit_impact.sum().sort_values()

# simulator (2025, line level)
def sim(d, cap=True, floor=True):
    npz = d.net_sales / d.quantity
    p = npz.copy()
    if cap:
        p = np.maximum(p, d.list_price * (1 - CAP))
    if floor:
        p = np.maximum(p, d.unit_cost / (1 - MIN_GM))
    keep = np.clip(1 - ELAST * (p / npz - 1), 0, 1)
    q = d.quantity * keep
    newnet = p * q
    pocket = (newnet * (1 - d.rebate_amount / d.net_sales) - d.unit_cost * q - d.freight_cost * keep).sum()
    return pocket - d.pocket_profit.sum(), newnet.sum() / d.net_sales.sum() - 1, q.sum() / d.quantity.sum() - 1


def fee(d):
    o = d.groupby("order_id").agg(n=("net_sales", "sum"), p=("pocket_profit", "sum"))
    sm = o[o.n < THR]
    return len(sm) * (1 - LOST) * FEE - sm.p.sum() * LOST


u_cap, _, _ = sim(s25, True, False)
u_floor, _, _ = sim(s25, False, True)
u_price, rev_chg, vol_chg = sim(s25)
u_fee = fee(s25)
uplift = u_price + u_fee
seg_sim = {k: (seg.loc[k, "pocket"], seg.loc[k, "pocket"] + sim(d)[0] + fee(d)) for k, d in s25.groupby("segment")}
cat_sim = {k: (cat.loc[k, "pocket"], sim(d)[0], sim(d)[1], sim(d)[2]) for k, d in s25.groupby("category")}

# waterfall
wf = [("Gross sales", s25.gross_sales.sum()), ("Discounts", -s25.discount_amount.sum()), ("Returns", -r25.credit_amount.sum()),
      ("COGS", -(s25.cogs.sum() - r25.cost_recovered.sum())), ("Rebates", -s25.rebate_amount.sum()),
      ("Freight", -s25.freight_cost.sum())]


# ---------------------------------------------------------------- helpers
def M(x, d=2):
    sign = "-" if x < 0 else ""
    x = abs(x)
    return f"{sign}${x/1e6:,.{d}f}M" if x >= 1e6 else (f"{sign}${x/1e3:,.0f}K" if x >= 1e3 else f"{sign}${x:,.0f}")


def P(x, d=1, sign=False):
    return f"{x*100:+.{d}f}%" if sign else f"{x*100:.{d}f}%"


def col(v, good=0):
    return GREEN if v >= good else RED


CSS = f"""
*{{box-sizing:border-box;margin:0;padding:0}}
body{{width:1280px;height:720px;background:{BG};font-family:Inter,'Segoe UI',sans-serif;color:{TXT};position:relative;overflow:hidden}}
.box{{position:absolute;background:{CARD};border:1px solid {BORDER};border-radius:12px;padding:14px 16px}}
.title{{font-size:13px;font-weight:600;color:{TXT};margin-bottom:10px;letter-spacing:.1px}}
.sub{{font-size:11px;color:{MUTED}}}
.pill{{display:inline-block;padding:3px 10px;border-radius:999px;font-size:10.5px;font-weight:600;border:1px solid}}
.crit{{color:#F87171;background:#2A0E0E;border-color:#5B1C1C}} .rev{{color:#FB923C;background:#2A1608;border-color:#5A2E10}}
.ok{{color:#4ADE80;background:#06210F;border-color:#14532D}}
.nav{{position:absolute;right:16px;top:16px;display:flex;gap:6px}}
.nav span{{font-size:11px;padding:5px 11px;border-radius:999px;background:#171717;color:{MUTED};border:1px solid {BORDER}}}
.nav span.on{{background:{TXT};color:#000;font-weight:600;border-color:{TXT}}}
.flt{{position:absolute;left:16px;top:78px;display:flex;gap:8px;align-items:center}}
.flt span{{font-size:11px;padding:6px 12px;border-radius:8px;background:{CARD};border:1px solid {BORDER};color:{TXT}}}
.flt span b{{color:{MUTED};font-weight:400}}
.kpis{{display:flex;height:100%;align-items:center}}
.kpi{{flex:1;padding:0 18px;border-left:1px solid {BORDER}}} .kpi:first-child{{border-left:none;padding-left:4px}}
.kl{{font-size:11px;color:{MUTED};margin-bottom:6px}} .kv{{font-size:26px;font-weight:600;letter-spacing:-.5px}}
.kr{{font-size:10.5px;margin-top:4px;color:{DIM}}}
.row{{display:flex;justify-content:space-between;align-items:center;font-size:11.5px;padding:7px 0;border-bottom:1px solid #171717}}
.row:last-child{{border-bottom:none}}
.bar{{margin:0 0 9px;display:inline-block;width:100%}} .bl{{display:flex;justify-content:space-between;font-size:11.5px;margin-bottom:5px}}
.track{{height:7px;background:{TRACK};border-radius:4px;overflow:hidden}} .fill{{height:100%;border-radius:4px}}
table{{width:100%;border-collapse:collapse;font-size:11px}} th{{text-align:left;color:{DIM};font-weight:500;padding:4px 6px;border-bottom:1px solid {BORDER}}}
td{{padding:4px 6px;border-bottom:1px solid #171717}} td.n,th.n{{text-align:right}}
.foot{{position:absolute;left:16px;bottom:6px;font-size:9.5px;color:{DIM}}}
"""

TABS = ["Overview", "Customers", "Products & Reps", "Simulator"]


def page(active, body, filters=True):
    nav = "".join(f'<span class="{"on" if t == active else ""}">{t}</span>' for t in TABS)
    flt = ('<div class="flt"><span><b>Year</b>&nbsp; 2025 ▾</span><span><b>Region</b>&nbsp; All ▾</span>'
           '<span><b>Segment</b>&nbsp; All ▾</span><span style="border:none;background:none;color:#737373">'
           'Reporting period · Year · Region · Customer segment</span></div>') if filters else ""
    return f"""<html><head><style>{CSS}</style></head><body>
<div class="box" style="left:16px;top:12px;width:1248px;height:56px;padding:9px 16px">
 <div style="font-size:15px;font-weight:700;letter-spacing:.3px">DISTRIBUTION <span style="color:{DIM}">|</span> PROFITABILITY CONTROL TOWER</div>
 <div class="sub" style="margin-top:3px">Harbor &amp; Field Distribution · simulated data · FY 2025</div>
 <div class="nav">{nav}</div></div>{flt}{body}
<div class="foot">Simulated dataset. All figures are produced by the project's Python/SQL and reconcile to the Power BI measures.</div>
</body></html>"""


def box(x, y, w, h, inner, title=None, pad=None):
    t = f'<div class="title">{title}</div>' if title else ""
    p = f"padding:{pad};" if pad else ""
    return f'<div class="box" style="left:{x}px;top:{y}px;width:{w}px;height:{h}px;{p}">{t}{inner}</div>'


def kpis(items):
    html = ""
    for label, val, color, ref, refcol in items:
        html += (f'<div class="kpi"><div class="kl">{label}</div><div class="kv" style="color:{color}">{val}</div>'
                 f'<div class="kr" style="color:{refcol}">{ref}</div></div>')
    return f'<div class="kpis">{html}</div>'


def bars(rows, scale, fmt=P, colfn=None, w=None):
    out = ""
    for label, v in rows:
        c = colfn(v) if colfn else (RED if v < 0 else (BLUE if v < 0.10 else GREEN))
        pct = min(abs(v) / scale, 1) * 100
        out += (f'<div class="bar"><div class="bl"><span>{label}</span><span style="color:{c};font-weight:600">{fmt(v)}</span></div>'
                f'<div class="track"><div class="fill" style="width:{pct:.1f}%;background:{c}"></div></div></div>')
    return out


def pill(s):
    cls = {"Critical": "crit", "Review": "rev", "Loss": "crit", "Thin": "rev"}.get(s, "ok")
    return f'<span class="pill {cls}">{s}</span>'


def line_svg(w, h, series, labels):
    """Two lines, each scaled to its own range (secondary axis)."""
    pad_l, pad_r, pad_t, pad_b = 8, 8, 10, 22
    W, H = w - pad_l - pad_r, h - pad_t - pad_b
    svg = f'<svg width="{w}" height="{h}">'
    for i in range(4):
        yy = pad_t + H * i / 3
        svg += f'<line x1="{pad_l}" x2="{w-pad_r}" y1="{yy}" y2="{yy}" stroke="#1C1C1C"/>'
    for vals, c in series:
        lo, hi = min(vals), max(vals)
        rng = hi - lo or 1
        lo -= rng * 0.35
        hi += rng * 0.15
        pts = [(pad_l + W * i / (len(vals) - 1), pad_t + H * (1 - (v - lo) / (hi - lo))) for i, v in enumerate(vals)]
        d = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        svg += f'<polyline points="{d}" fill="none" stroke="{c}" stroke-width="3" stroke-linejoin="round" stroke-linecap="round"/>'
    for i, lab in enumerate(labels):
        if lab:
            x = pad_l + W * i / (len(labels) - 1)
            svg += f'<text x="{x}" y="{h-5}" font-size="10.5" fill="{MUTED}" text-anchor="{"start" if i == 0 else ("end" if i == len(labels)-1 else "middle")}">{lab}</text>'
    return svg + "</svg>"


def legend(items):
    return '<div style="display:flex;gap:16px;font-size:10.5px;margin-top:4px">' + "".join(
        f'<span style="color:{c}">● {t}</span>' for t, c in items) + "</div>"


# ================================================================ PAGE 1
months = ["Jan", "", "", "", "", "Jun", "", "", "", "", "", "Dec"]
p1 = box(16, 120, 1248, 96, kpis([
    ("Net Revenue", M(k25["net"]), TXT, f'{P(k25["net"]/k24["net"]-1, sign=True)} vs 2024', GREEN),
    ("Gross Profit", M(k25["gp"]), GREEN, f'{P(k25["gp"]/k24["gp"]-1, sign=True)} vs 2024', RED),
    ("Gross Margin", P(k25["gm"]), TXT, f'{(k25["gm"]-k24["gm"])*100:+.1f} pts vs 2024', RED),
    ("Pocket Profit", M(k25["pocket"]), TXT, f'{P(k25["pocket"]/k24["pocket"]-1, sign=True)} vs 2024', RED),
    ("Sales Below Price Floor", P(below_floor_pct), RED, "priced under cost + 8% margin", DIM),
]), pad="10px 16px")
p1 += box(16, 228, 820, 262, line_svg(788, 186, [(mon.net.tolist(), BLUE), (mon.gp.tolist(), GREEN)], months)
          + legend([("Net revenue", BLUE), ("Gross profit (right axis)", GREEN)]), "Revenue vs Gross Profit Trend")
leak_rows = "".join(f'<div class="row"><span>{a}</span><span style="color:{RED};font-weight:600">{b}</span></div>' for a, b in [
    ("Below-cost sales", M(bc_loss)), ("Excess rep discounts", M(-excess)), ("Returns write-offs", M(ret_impact))])
p1 += box(848, 228, 416, 262, f'<div style="font-size:38px;font-weight:700;color:{RED};letter-spacing:-1px">{M(leak_total)}</div>'
          f'<div class="sub" style="margin:2px 0 14px">profit lost to three leaks in 2025</div>'
          f'<div style="border-top:1px solid {BORDER};padding-top:6px">{leak_rows}</div>'
          f'<div class="sub" style="margin-top:12px">= {P(leak_total/k25["pocket"],0)} of 2025 pocket profit</div>', "Profit Leakage")
p1 += box(16, 502, 616, 198, f'<div style="columns:2;column-gap:28px">{bars([(k, v.pm) for k, v in cat.iterrows()], 0.25)}</div>',
          "Pocket Margin by Category")
crit = 0.10 * k25["pocket"]
att = [("Products sold below cost", M(bc_loss), "Critical" if abs(bc_loss) >= crit else "Review"),
       ("Gross margin vs last year", f'{(k25["gm"]-k24["gm"])*100:+.1f} pts', "Critical"),
       ("Returns write-offs", M(ret_impact), "Critical" if abs(ret_impact) >= crit else "Review"),
       ("Loss-making customers", f"{len(loss_c)} of {active}", "Critical" if len(loss_c) >= 0.25 * active else "Review"),
       ("Excess rep discounts", M(-excess), "Critical" if excess >= crit else "Review")]
p1 += box(644, 502, 620, 198, "".join(f'<div class="row" style="padding:4px 0"><span>{a}</span><span style="display:flex;gap:14px;align-items:center">'
                                      f'<span style="color:{MUTED}">{b}</span>{pill(c)}</span></div>' for a, b, c in att),
          "Management Attention")

# ================================================================ PAGE 2
def scatter_svg(w, h):
    colors = {"National Chain": BLUE, "Regional Supermarket": "#A78BFA", "Independent Grocery": GREEN,
              "Convenience Store": RED, "HoReCa": ORANGE}
    pl, pr, pt_, pb = 34, 8, 6, 20
    W, H = w - pl - pr, h - pt_ - pb
    xlo, xhi, ylo, yhi = np.log10(500), np.log10(3e6), -0.25, 0.25
    svg = f'<svg width="{w}" height="{h}">'
    for v in [-0.2, -0.1, 0, 0.1, 0.2]:
        yy = pt_ + H * (1 - (v - ylo) / (yhi - ylo))
        svg += (f'<line x1="{pl}" x2="{w-pr}" y1="{yy}" y2="{yy}" stroke="{"#525252" if v == 0 else "#1C1C1C"}"/>'
                f'<text x="{pl-6}" y="{yy+3}" font-size="9.5" fill="{DIM}" text-anchor="end">{v*100:.0f}%</text>')
    for v, lab in [(1e3, "$1K"), (1e4, "$10K"), (1e5, "$100K"), (1e6, "$1M")]:
        xx = pl + W * (np.log10(v) - xlo) / (xhi - xlo)
        svg += f'<text x="{xx}" y="{h-5}" font-size="9.5" fill="{DIM}" text-anchor="middle">{lab}</text>'
    for _, rw in cp.iterrows():
        if rw.net <= 0:
            continue
        xx = pl + W * (np.log10(max(rw.net, 500)) - xlo) / (xhi - xlo)
        yy = pt_ + H * (1 - (np.clip(rw.pm, ylo, yhi) - ylo) / (yhi - ylo))
        rr = 2.5 + np.sqrt(rw.orders) / 2.2
        svg += f'<circle cx="{xx:.1f}" cy="{yy:.1f}" r="{rr:.1f}" fill="{colors[rw.segment]}" fill-opacity="0.65"/>'
    return svg + "</svg>" + legend([(k, v) for k, v in colors.items()])


p2 = box(16, 120, 1248, 96, kpis([
    ("Active Customers", f"{active}", TXT, "bought in 2025", DIM),
    ("Loss-Making Customers", f"{len(loss_c)}", RED, f"all {loss_c.segment.value_counts().index[0].lower()}s", RED),
    ("Revenue in Loss-Makers", P(loss_c.net.sum() / cp.net.sum()), TXT, "small accounts, big cost to serve", DIM),
    ("Top 20% Customers' Profit", P(top20, 0), TXT, "share of pocket profit", DIM),
    ("Biggest Customer Margin", P(biggest.pm), ORANGE, f"{biggest.name} · {P(biggest.net/cp.net.sum(),0)} of revenue", DIM),
]), pad="10px 16px")
p2 += box(16, 228, 620, 270, scatter_svg(588, 200), "Customers: Revenue vs Pocket Margin")
p2 += box(648, 228, 616, 270, bars([(k, v.pm) for k, v in seg.iterrows()], 0.20)
          + f'<div class="sub" style="margin-top:6px">Freight eats {P(seg.loc["Convenience Store","freight"]/seg.loc["Convenience Store","net"])} '
            f'of convenience-store revenue vs {P(seg.loc["National Chain","freight"]/seg.loc["National Chain","net"])} for chains.</div>',
          "Pocket Margin by Segment")
worst = cp.sort_values("pocket").head(4)
rows = "".join(f'<tr><td>{n}</td><td>{rw.segment}</td><td class="n">{M(rw.net)}</td><td class="n">{P(rw.disc)}</td>'
               f'<td class="n" style="color:{RED}">{M(rw.pocket)}</td><td class="n" style="color:{RED}">{P(rw.pm)}</td>'
               f'<td class="n">{pill("Loss")}</td></tr>' for n, rw in worst.iterrows())
p2 += box(16, 510, 820, 190, f'<table><tr><th>Customer</th><th>Segment</th><th class="n">Net revenue</th><th class="n">Discount</th>'
          f'<th class="n">Pocket profit</th><th class="n">Margin</th><th class="n">Status</th></tr>{rows}</table>',
          "Customers Losing the Most")


def waterfall_svg(w, h):
    pl, pb = 6, 30
    W, H = w - 2 * pl, h - pb - 14
    top = wf[0][1]
    n = len(wf) + 1
    bw = W / n * 0.62
    svg, run = f'<svg width="{w}" height="{h}">', 0
    items = wf + [("Pocket", sum(v for _, v in wf))]
    for i, (lab, v) in enumerate(items):
        x = pl + W * i / n + (W / n - bw) / 2
        if i == 0 or lab == "Pocket":
            y0, y1, c = 0, v, (BLUE if i == 0 else GREEN)
        else:
            y0, y1, c = run + v, run, RED
        if i == 0:
            run = v
        elif lab != "Pocket":
            run += v
        ya, yb = 14 + H * (1 - max(y0, y1) / top), 14 + H * (1 - min(y0, y1) / top)
        svg += f'<rect x="{x:.1f}" y="{ya:.1f}" width="{bw:.1f}" height="{max(yb-ya,1.5):.1f}" rx="3" fill="{c}"/>'
        svg += f'<text x="{x+bw/2:.1f}" y="{ya-3:.1f}" font-size="9" fill="{MUTED}" text-anchor="middle">{M(v,1)}</text>'
        svg += f'<text x="{x+bw/2:.1f}" y="{h-12}" font-size="9" fill="{DIM}" text-anchor="middle">{lab}</text>'
    return svg + "</svg>"


p2 += box(848, 510, 416, 190, waterfall_svg(384, 140), "Where Each Dollar of List Price Goes")

# ================================================================ PAGE 3
p3 = box(16, 120, 1248, 96, kpis([
    ("SKUs Sold Below Cost", f"{below_cost.sku.nunique()}", TXT, f"{len(below_cost):,} order lines", DIM),
    ("Below-Cost Sales", M(below_cost.net_sales.sum()), TXT, f"{P(below_cost.net_sales.sum()/s25.net_sales.sum())} of net sales", DIM),
    ("Below-Cost Gross Loss", M(bc_loss, 0) if abs(bc_loss) >= 1e6 else M(bc_loss), RED, "90% with national chains", RED),
    ("Excess Rep Discount", M(excess), RED, "3 reps above their peers", RED),
    ("Returns Profit Impact", M(ret_impact), RED, "write-offs + credits", DIM),
]), pad="10px 16px")


def pt_rows():
    out = ""
    for k, v in pt.iterrows():
        out += (f'<div style="display:grid;grid-template-columns:120px 1fr 52px;align-items:center;gap:8px;font-size:11px;margin-bottom:7px">'
                f'<span>{k}</span><div><div class="track" style="height:5px;margin-bottom:3px"><div class="fill" style="width:{min(abs(v.cost)/0.16,1)*100:.0f}%;background:{RED}"></div></div>'
                f'<div class="track" style="height:5px"><div class="fill" style="width:{min(abs(v.price)/0.16,1)*100:.0f}%;background:{BLUE if v.price>=0 else ORANGE}"></div></div></div>'
                f'<span style="text-align:right;color:{RED if v.price < v.cost else GREEN};font-weight:600">{(v.price-v.cost)*100:+.1f}</span></div>')
    return out + legend([("Cost per case change", RED), ("Net price change", BLUE), ("Price cut", ORANGE)]) + \
        '<div class="sub" style="margin-top:3px">Right column: price change minus cost change (pts)</div>'


p3 += box(16, 228, 616, 270, pt_rows(), "Did Prices Keep Up With Supplier Costs? (2025 vs 2024)")


def rep_rows():
    out = ""
    for rid, v in rp.iterrows():
        w = min(abs(v.pts) / 5, 1) * 50
        bar = (f'<div style="position:relative;height:7px;background:{TRACK};border-radius:4px">'
               f'<div style="position:absolute;left:50%;top:-2px;width:1px;height:11px;background:#525252"></div>'
               f'<div style="position:absolute;top:0;height:7px;border-radius:4px;background:{RED if v.pts>1 else "#525252"};'
               f'{"left:50%" if v.pts>=0 else f"right:50%"};width:{w:.1f}%"></div></div>')
        tag = '<span class="pill rev" style="padding:0 7px;font-size:9px;line-height:14px">Review</span>' if v.pts > 1 else ""
        out += (f'<div style="display:grid;grid-template-columns:110px 1fr 54px 64px;gap:10px;align-items:center;font-size:10.5px;height:17px">'
                f'<span>{v.rep_name}</span>{bar}<span style="text-align:right;color:{RED if v.pts>1 else MUTED}">{v.pts:+.1f} pts</span>'
                f'<span style="text-align:right">{tag}</span></div>')
    return out


p3 += box(644, 228, 620, 270, rep_rows(), "Discount vs Peers Selling to the Same Segments")
rows = "".join(f'<tr><td>{rw.sku}</td><td>{rw.product_name}</td><td>{rw.category}</td><td class="n">{rw.lines}</td>'
               f'<td class="n">{M(rw.sales)}</td><td class="n" style="color:{RED}">{M(rw.loss)}</td>'
               f'<td class="n">${rw.avg_price:,.2f}</td><td class="n" style="color:{GREEN}">${rw.min_price:,.2f}</td></tr>'
               for _, rw in skus.head(5).iterrows())
p3 += box(16, 510, 820, 190, f'<table><tr><th>SKU</th><th>Product</th><th>Category</th><th class="n">Lines</th><th class="n">Sales</th>'
          f'<th class="n">Gross loss</th><th class="n">Avg price</th><th class="n">Min price (8% GM)</th></tr>{rows}</table>',
          "SKUs Sold Below Cost")
p3 += box(848, 510, 416, 190, f'<div style="columns:2;column-gap:22px">' +
          bars([(k, v) for k, v in ret_cat.items()], abs(ret_cat.min()), fmt=lambda v: M(v), colfn=lambda v: RED) + "</div>",
          "Returns Profit Impact by Category")

# ================================================================ PAGE 4
def slider(label, val, pos):
    return (f'<div style="margin-bottom:16px"><div class="bl"><span style="color:{MUTED}">{label}</span><span style="font-weight:600">{val}</span></div>'
            f'<div style="position:relative;height:5px;background:{TRACK};border-radius:3px"><div style="width:{pos}%;height:5px;background:{TXT};border-radius:3px"></div>'
            f'<div style="position:absolute;left:calc({pos}% - 7px);top:-5px;width:14px;height:14px;border-radius:50%;background:{TXT}"></div></div></div>')


lever_pills = "".join(f'<span class="pill" style="color:#000;background:{TXT};border-color:{TXT};margin:0 6px 6px 0">✓ {t}</span>'
                      for t in ["Discount cap", "Price floor", "Small-order fee"])
panel = (f'<div style="margin-bottom:18px">{lever_pills}</div>' + slider("Discount cap", "10%", 20) + slider("Minimum gross margin", "8%", 40)
         + slider("Volume lost per 1% price rise", "1.0", 50) + slider("Small-order threshold", "$400", 33)
         + slider("Delivery fee", "$25", 42) + slider("Small orders lost", "10%", 20)
         + f'<div class="sub" style="font-size:10px;line-height:1.45;margin-top:4px">Prices change line by line; volume falls by the elasticity on lines whose price rises. Returns unchanged.</div>')
p4 = box(16, 76, 300, 624, panel, "Levers")
p4 += box(328, 76, 936, 96, kpis([
    ("Current Pocket Profit", M(k25["pocket"]), TXT, "FY 2025", DIM),
    ("Simulated Pocket Profit", M(k25["pocket"] + uplift), GREEN, "all levers on", DIM),
    ("Uplift", "+" + M(uplift), GREEN, f'{P(uplift/k25["pocket"], 0, sign=True)} pocket profit', GREEN),
    ("Revenue / Volume", f'{P(rev_chg, sign=True)}', ORANGE, f'{P(vol_chg, sign=True)} cases', ORANGE),
]), pad="10px 16px")
p4 += box(328, 184, 460, 300, bars([("Price floor (8% minimum margin)", u_floor), ("Discount cap at 10%", u_cap),
                                    ("$25 fee on orders under $400", u_fee)], max(u_floor, u_cap), fmt=lambda v: "+" + M(v),
                                   colfn=lambda v: GREEN)
          + f'<div class="sub" style="margin-top:10px">Each lever calculated on its own. Together they add {M(uplift)} '
            f'(less than the sum, because the floor and the cap overlap on the same lines).</div>', "Uplift From Each Lever")


def seg_bars():
    mx = max(max(a, b) for a, b in seg_sim.values())
    out = ""
    for k in seg.index:
        a, b = seg_sim[k]
        out += (f'<div style="margin-bottom:9px"><div class="bl"><span>{k}</span><span style="color:{GREEN};font-weight:600">'
                f'{M(a)} → {M(b)}</span></div>'
                f'<div class="track" style="height:5px;margin-bottom:3px"><div class="fill" style="width:{max(a,0)/mx*100:.1f}%;background:#737373"></div></div>'
                f'<div class="track" style="height:5px"><div class="fill" style="width:{max(b,0)/mx*100:.1f}%;background:{GREEN}"></div></div></div>')
    return out + legend([("Current", "#737373"), ("Simulated", GREEN)])


p4 += box(800, 184, 464, 300, seg_bars(), "Current vs Simulated Pocket Profit by Segment")
rows = "".join(f'<tr><td>{k}</td><td class="n">{M(a)}</td><td class="n" style="color:{GREEN}">{M(a+u)}</td>'
               f'<td class="n" style="color:{GREEN}">+{M(u)}</td><td class="n">{P(rv, sign=True)}</td><td class="n">{P(vl, sign=True)}</td></tr>'
               for k, (a, u, rv, vl) in sorted(cat_sim.items(), key=lambda kv: -kv[1][1])[:5])
p4 += box(328, 496, 936, 204, f'<table><tr><th>Category</th><th class="n">Current pocket</th><th class="n">Simulated (price levers)</th>'
          f'<th class="n">Uplift</th><th class="n">Revenue change</th><th class="n">Volume change</th></tr>{rows}</table>',
          "Impact by Category (price levers)")

pages = {"page1_overview": page("Overview", p1), "page2_customers": page("Customers", p2),
         "page3_products_reps": page("Products & Reps", p3), "page4_simulator": page("Simulator", p4, filters=False)}
with sync_playwright() as pw:
    br = pw.chromium.launch()
    pg = br.new_page(viewport={"width": 1280, "height": 720}, device_scale_factor=2)
    for name, html in pages.items():
        (OUT / f"{name}.html").write_text(html)
        pg.set_content(html)
        pg.wait_for_timeout(200)
        pg.screenshot(path=str(OUT / f"{name}.png"))
    br.close()
print("KPIs:", {k: round(v, 4) for k, v in k25.items()}, "leak", round(leak_total), "uplift", round(uplift),
      "below floor", round(below_floor_pct, 4), "loss customers", len(loss_c), "top20", round(top20, 3))
print("saved to", OUT)
