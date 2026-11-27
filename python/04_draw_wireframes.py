"""
04_draw_wireframes.py
---------------------
Draws the dashboard wireframes (1280 x 720 canvas) used in docs/POWER_BI_BUILD_GUIDE.md.
Positions are in Power BI pixels: set them in Format > General > Properties > Size and position.

Run:  python 04_draw_wireframes.py
Output: ../docs/wireframes/page*.png
"""
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

OUT = Path(__file__).resolve().parents[1] / "docs" / "wireframes"
OUT.mkdir(parents=True, exist_ok=True)

BG, PANEL, EDGE, TXT, MUTED = "#0F172A", "#111C33", "#334155", "#E2E8F0", "#94A3B8"
KIND_COL = {"kpi": "#1D4ED8", "chart": "#111C33", "slicer": "#0B3B2E", "table": "#2A1F45", "text": "#0F172A"}

SLICERS = [("slicer", "Year", 800, 14, 150, 42), ("slicer", "Region", 962, 14, 150, 42),
           ("slicer", "Segment", 1114, 14, 150, 42)]

PAGES = {
    "page1_executive": ("1. Executive Profitability", SLICERS + [
        ("kpi", "Net Revenue\nvs PY %", 16, 68, 240, 96),
        ("kpi", "Gross Profit\nvs PY %", 268, 68, 240, 96),
        ("kpi", "Gross Margin %\nvs PY pts", 520, 68, 240, 96),
        ("kpi", "Pocket Profit\nvs PY %", 772, 68, 240, 96),
        ("kpi", "Profit Leakage $\n(below-cost + excess disc. + returns)", 1024, 68, 240, 96),
        ("chart", "Line & clustered column:\nmonthly Net Revenue (columns) + Gross Margin % (line)", 16, 176, 760, 260),
        ("chart", "Waterfall: Gross sales -> discounts -> returns\n-> COGS -> rebates -> freight -> Pocket profit", 788, 176, 476, 260),
        ("chart", "Bar: Gross margin change (pts)\nby category, CY vs PY", 16, 448, 500, 256),
        ("chart", "Bar: Pocket margin %\nby segment", 528, 448, 360, 256),
        ("table", "Table: Management attention\n(issue | $ impact | status icon)", 900, 448, 364, 256),
    ]),
    "page2_customers": ("2. Customer & Segment Profitability", SLICERS + [
        ("kpi", "Active Customers", 16, 68, 303, 96),
        ("kpi", "Loss-Making Customers", 331, 68, 303, 96),
        ("kpi", "Revenue in Loss-Making\nCustomers %", 646, 68, 303, 96),
        ("kpi", "Top 20% Customers'\nShare of Pocket Profit", 961, 68, 303, 96),
        ("chart", "Scatter: Net Revenue (x, log) vs Pocket Margin % (y)\nsize = Orders, legend = Segment", 16, 176, 760, 300),
        ("chart", "Line: Customer whale curve\n(cumulative pocket profit)", 788, 176, 476, 300),
        ("chart", "Stacked bar: per segment\nGross profit -> rebates -> freight -> pocket", 16, 488, 620, 216),
        ("table", "Table: customers ranked by pocket profit\n(bottom 15 by default)", 648, 488, 616, 216),
    ]),
    "page3_products_reps": ("3. Products, Pricing & Sales Reps", SLICERS + [
        ("kpi", "SKUs Sold\nBelow Cost", 16, 68, 240, 96),
        ("kpi", "Below-Cost\nSales $", 268, 68, 240, 96),
        ("kpi", "Below-Cost\nGross Loss $", 520, 68, 240, 96),
        ("kpi", "Excess Rep\nDiscount $", 772, 68, 240, 96),
        ("kpi", "Returns Profit\nImpact $", 1024, 68, 240, 96),
        ("chart", "Clustered bar: Cost change % vs\nNet price change % by category", 16, 176, 500, 260),
        ("table", "Table: SKUs sold below cost\n(lines | sales | loss | avg price | cost | min price)", 528, 176, 736, 260),
        ("chart", "Bar: Excess discount pts by rep\n(mix-adjusted, field reps)", 16, 448, 500, 256),
        ("table", "Matrix heatmap: Returns profit impact\nSegment (rows) x Category (columns)", 528, 448, 736, 256),
    ]),
    "page4_simulator": ("4. Pricing & Profit Simulator", [
        ("slicer", "Levers ON/OFF\n(Discount cap | Price floor | Small-order fee)", 16, 68, 300, 120),
        ("slicer", "Discount cap %", 16, 196, 300, 70),
        ("slicer", "Minimum gross margin %", 16, 274, 300, 70),
        ("slicer", "Price elasticity", 16, 352, 300, 70),
        ("slicer", "Small-order threshold $", 16, 430, 300, 70),
        ("slicer", "Delivery fee $", 16, 508, 300, 70),
        ("slicer", "Small orders lost %", 16, 586, 300, 70),
        ("text", "Assumptions note", 16, 664, 300, 40),
        ("kpi", "Current Pocket\nProfit", 328, 68, 225, 96),
        ("kpi", "Simulated Pocket\nProfit", 565, 68, 225, 96),
        ("kpi", "Uplift $", 802, 68, 225, 96),
        ("kpi", "Revenue Change %", 1039, 68, 225, 96),
        ("chart", "Bar: Uplift by lever", 328, 176, 460, 260),
        ("chart", "Clustered bar: Current vs Simulated\npocket profit by segment", 800, 176, 464, 260),
        ("table", "Table by category: current pocket | simulated | uplift\n| revenue change % | volume change %", 328, 448, 936, 256),
    ]),
}


for key, (title, boxes) in PAGES.items():
    fig = plt.figure(figsize=(12.8, 7.2), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 1280)
    ax.set_ylim(720, 0)
    ax.axis("off")
    fig.patch.set_facecolor(BG)
    ax.text(16, 30, "PROFIT CONTROL TOWER", color=TXT, fontsize=14, fontweight="bold", va="center")
    ax.text(16, 50, title + "   |   Harbor & Field Distribution (simulated data)", color=MUTED, fontsize=9, va="center")
    for kind, label, x, y, w, h in boxes:
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=8",
                                    fc=KIND_COL[kind], ec=EDGE, lw=1))
        ax.text(x + w / 2, y + h / 2, label, color=TXT, fontsize=8.5, ha="center", va="center", wrap=True)
        ax.text(x + 6, y + h - 6, f"x{x} y{y} w{w} h{h}", color=MUTED, fontsize=6.5, ha="left", va="bottom")
    fig.savefig(OUT / f"{key}.png", facecolor=BG)
    plt.close(fig)
print("wireframes saved to", OUT)
