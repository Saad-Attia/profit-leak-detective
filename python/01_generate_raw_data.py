"""
01_generate_raw_data.py
-----------------------
Creates the SIMULATED raw data for "Harbor & Field Distribution", a fictional
B2B food and household-goods wholesaler (Jan 2023 - Dec 2025).

The data is synthetic. It is designed to behave like a real distributor's ERP
exports: supplier cost increases that are not passed on, rep-level discounting,
volume rebates for chains, freight on small drops, and short-life returns.
It also contains the kind of data-quality problems real exports have, so the
cleaning step (02_clean_data.py) has real work to do.

Run:  python 01_generate_raw_data.py
Output: ../data/raw/*.csv
"""
from pathlib import Path
import numpy as np
import pandas as pd

SEED = 42
rng = np.random.default_rng(SEED)
ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
RAW.mkdir(parents=True, exist_ok=True)

START, END = pd.Timestamp("2023-01-01"), pd.Timestamp("2025-12-31")
MONTHS = pd.date_range(START, END, freq="MS")

# --------------------------------------------------------------------------
# 1. Products, suppliers, list prices and supplier costs
# --------------------------------------------------------------------------
CATS = {
    # category: (n_skus, price_lo, price_hi, target_margin, n_suppliers)
    "Beverages":          (30, 8, 40, 0.22, 3),
    "Snacks":             (28, 10, 35, 0.30, 2),
    "Dairy":              (22, 12, 45, 0.18, 2),
    "Bakery":             (18, 6, 20, 0.28, 2),
    "Canned Goods":       (24, 15, 50, 0.24, 2),
    "Frozen":             (16, 20, 70, 0.26, 2),
    "Household Cleaning": (22, 12, 40, 0.32, 1),
    "Personal Care":      (20, 15, 55, 0.35, 1),
}
NOUNS = {
    "Beverages": ["Orange Juice", "Cola", "Sparkling Water", "Iced Tea", "Energy Drink", "Mango Nectar", "Still Water", "Lemonade", "Apple Juice", "Cold Brew"],
    "Snacks": ["Potato Chips", "Tortilla Chips", "Salted Peanuts", "Choc Wafer", "Granola Bar", "Pretzels", "Popcorn", "Cheese Puffs", "Mixed Nuts", "Rice Crackers"],
    "Dairy": ["Full Cream Milk", "Low-Fat Milk", "Greek Yogurt", "Cheddar Block", "Butter", "Labneh", "Cream Cheese", "Drinking Yogurt", "Feta", "Cooking Cream"],
    "Bakery": ["Sliced Bread", "Croissant", "Burger Buns", "Pita Bread", "Muffins", "Toast Bread", "Brioche", "Rusks", "Bagels", "Tortilla Wraps"],
    "Canned Goods": ["Tuna Chunks", "Chickpeas", "Fava Beans", "Sweet Corn", "Tomato Paste", "Peeled Tomatoes", "Baked Beans", "Sardines", "Mushrooms", "Peaches"],
    "Frozen": ["Frozen Peas", "Chicken Nuggets", "Beef Burgers", "French Fries", "Mixed Veg", "Fish Fillets", "Pizza Base", "Spinach", "Okra", "Ice Cream Tub"],
    "Household Cleaning": ["Dish Soap", "Laundry Powder", "Floor Cleaner", "Bleach", "Glass Cleaner", "Fabric Softener", "Sponges", "Bin Bags", "Kitchen Towels", "Toilet Cleaner"],
    "Personal Care": ["Shampoo", "Body Wash", "Toothpaste", "Hand Soap", "Deodorant", "Conditioner", "Baby Wipes", "Facial Tissue", "Lotion", "Toothbrush Pack"],
}
SUPPLIER_NAMES = ["Atlas Foods", "Blue River Beverages", "Crestline Snacks", "Dalewood Dairy", "Evergreen Bakeries",
                  "Fairport Canning", "Glacier Frozen", "Homestead Brands", "Ironbridge Supply", "Juniper Home Care",
                  "Keystone Personal Care", "Lakeside Drinks", "Meadow Farms", "Northstar Packers", "Oakline Foods"]

products, sup_rows = [], []
sup_iter = iter(SUPPLIER_NAMES)
sku_n = 1
for cat, (n, lo, hi, m, n_sup) in CATS.items():
    sups = [next(sup_iter) for _ in range(n_sup)]
    for i in range(n):
        noun = NOUNS[cat][i % len(NOUNS[cat])]
        size = ["Small", "Medium", "Large", "Family", "Bulk"][(i // len(NOUNS[cat])) % 5]
        price = round(float(rng.uniform(lo, hi)), 2)
        margin = float(np.clip(m + rng.normal(0, 0.04), 0.10, 0.45))
        products.append(dict(
            sku=f"SKU{sku_n:04d}", product_name=f"{noun} {size}", category=cat,
            supplier=sups[i % n_sup], pack=f"Case of {rng.choice([6, 12, 24])}",
            list_price_2023=price, base_margin=margin))
        sku_n += 1
prod = pd.DataFrame(products)

# yearly list prices (price list updated every January)
price_rows = []
for _, p in prod.iterrows():
    for yr, mult in [(2023, 1.0), (2024, 1.04), (2025, 1.04 * 1.03)]:
        price_rows.append(dict(sku=p.sku, effective_from=f"{yr}-01-01",
                               list_price=round(p.list_price_2023 * mult, 2)))
price_list = pd.DataFrame(price_rows)

# supplier cost change points
COST_EVENTS = [  # (date, category or None for all, multiplier)
    ("2024-01-01", None, 1.035),
    ("2025-01-01", None, 1.02),
    ("2025-03-01", "Dairy", 1.14),
    ("2025-04-01", "Canned Goods", 1.11),
    ("2025-06-01", "Beverages", 1.09),
    ("2025-07-01", "Frozen", 1.06),
]
cost_rows = []
for _, p in prod.iterrows():
    cost = p.list_price_2023 * (1 - p.base_margin)
    cost_rows.append(dict(sku=p.sku, effective_from="2023-01-01", unit_cost=round(cost, 2)))
    for d, cat, mult in COST_EVENTS:
        if cat is None or cat == p.category:
            cost *= mult
            cost_rows.append(dict(sku=p.sku, effective_from=d, unit_cost=round(cost, 2)))
costs = pd.DataFrame(cost_rows)

# --------------------------------------------------------------------------
# 2. Sales reps and customers
# --------------------------------------------------------------------------
REGIONS = {
    "Central": (["Riverton", "Kingsford"], 18),
    "North":   (["Northgate", "Pinehill"], 26),
    "South":   (["Southport", "Bayview", "Sandmere"], 30),
    "East":    (["Eastfield", "Millbrook"], 24),
    "West":    (["Westvale", "Redrock", "Highmoor"], 34),
}
FIRST = ["Adam", "Mona", "Karim", "Sara", "Omar", "Laila", "Hany", "Nour", "Tarek", "Dina", "Yousef", "Rana", "Ziad", "Hala"]
LAST = ["Fahmy", "Saleh", "Nabil", "Kamel", "Rashed", "Amin", "Galal", "Mansour", "Hassan", "Fouad", "Selim", "Ezzat", "Barakat", "Sami"]
rep_regions = ["Central"] * 3 + ["North"] * 3 + ["South"] * 3 + ["East"] * 2 + ["West"] * 2
reps = []
for i, reg in enumerate(rep_regions, start=1):
    reps.append(dict(rep_id=f"R{i:02d}", rep_name=f"{FIRST[i-1]} {LAST[i-1]}", region=reg, role="Field Sales Rep"))
reps.append(dict(rep_id="R14", rep_name=f"{FIRST[13]} {LAST[13]}", region="National", role="Key Account Manager"))
reps = pd.DataFrame(reps)
# extra discount habit per rep (percentage points) -> the "generous" reps
REP_EXTRA = {r: 0.0 for r in reps.rep_id}
REP_EXTRA.update({"R05": 0.055, "R12": 0.06, "R09": 0.02})

SEGMENTS = {
    # segment: (count, base_disc_lo, base_disc_hi, rebate_lo, rebate_hi, orders_per_month, lines, qty_mean)
    "National Chain":       (8,   0.08, 0.11, 0.03, 0.06, 4.0, 20, 38),
    "Regional Supermarket": (50,  0.04, 0.07, 0.00, 0.02, 1.5, 10, 14),
    "Independent Grocery":  (150, 0.02, 0.06, 0.00, 0.00, 1.2, 6, 6),
    "Convenience Store":    (130, 0.03, 0.08, 0.00, 0.00, 2.0, 4, 2.6),
    "HoReCa":               (62,  0.03, 0.07, 0.00, 0.00, 2.0, 6, 4.5),
}
SEG_CAT_PREF = {
    "National Chain":       {c: 1.0 for c in CATS},
    "Regional Supermarket": {c: 1.0 for c in CATS},
    "Independent Grocery":  {**{c: 1.0 for c in CATS}, "Frozen": 0.5},
    "Convenience Store":    {"Beverages": 3, "Snacks": 3, "Bakery": 2.5, "Dairy": 2.5, "Canned Goods": 0.5,
                             "Frozen": 0.3, "Household Cleaning": 0.5, "Personal Care": 0.8},
    "HoReCa":               {"Beverages": 2, "Snacks": 0.5, "Bakery": 2.5, "Dairy": 3, "Canned Goods": 1.5,
                             "Frozen": 3, "Household Cleaning": 1, "Personal Care": 0.2},
}
CHAIN_NAMES = ["FreshCart Group", "ValueWay Stores", "DailyBasket", "GreenAisle Markets", "MegaThrift",
               "CityPantry Group", "PrimeShelf", "HomeHarvest Stores"]
NAME_A = ["Al Noor", "Sunrise", "Corner", "Golden", "Family", "Star", "Royal", "Palm", "Blue Door", "Happy",
          "Oasis", "Lotus", "Crescent", "Harbor", "Garden", "Cedar", "Union", "Metro", "Village", "Silver"]
NAME_B = {"Regional Supermarket": ["Supermarket", "Hypermarket", "Market"],
          "Independent Grocery": ["Grocery", "Mini Market", "Foods"],
          "Convenience Store": ["Kiosk", "Express", "Quick Shop", "24/7"],
          "HoReCa": ["Cafe", "Restaurant", "Hotel", "Bistro", "Catering"]}

cust_rows, cid = [], 1
used_names = set()
for seg, (n, dlo, dhi, rlo, rhi, opm, lines, qty) in SEGMENTS.items():
    for k in range(n):
        if seg == "National Chain":
            name, region = CHAIN_NAMES[k], "Central"
            city, rep = "Riverton", "R14"
            start = pd.Timestamp("2021-06-01")
        else:
            region = rng.choice(list(REGIONS), p=[0.28, 0.18, 0.2, 0.17, 0.17])
            city = rng.choice(REGIONS[region][0])
            rep = rng.choice(reps.loc[reps.region == region, "rep_id"].to_numpy())
            while True:
                name = f"{rng.choice(NAME_A)} {rng.choice(NAME_B[seg])} {city}"
                if name not in used_names:
                    break
                name = f"{name} {rng.integers(2, 9)}"
                if name not in used_names:
                    break
            # growth push: many new convenience and HoReCa accounts in 2024-2025
            if seg == "Convenience Store":
                start = pd.Timestamp("2022-03-01") if k < 30 else (
                    pd.Timestamp("2024-01-01") + pd.DateOffset(months=int(rng.integers(0, 12))) if k < 80
                    else pd.Timestamp("2025-01-01") + pd.DateOffset(months=int(rng.integers(0, 9))))
            elif seg == "HoReCa":
                start = pd.Timestamp("2022-01-01") if k < 30 else (
                    pd.Timestamp("2024-01-01") + pd.DateOffset(months=int(rng.integers(0, 12))) if k < 46
                    else pd.Timestamp("2025-01-01") + pd.DateOffset(months=int(rng.integers(0, 9))))
            else:
                start = pd.Timestamp("2020-01-01") + pd.DateOffset(months=int(rng.integers(0, 40)))
        used_names.add(name)
        base_disc = rng.uniform(dlo, dhi)
        rebate = round(rng.uniform(rlo, rhi), 3)
        # the biggest chain negotiated the deepest terms when its contract was renewed
        if name == "FreshCart Group":
            base_disc, rebate = 0.125, 0.07
        # new convenience accounts were signed with an "intro" discount that never expired
        if seg == "Convenience Store" and start >= pd.Timestamp("2024-01-01"):
            base_disc = rng.uniform(0.09, 0.12)
        churn = None
        if seg in ("Independent Grocery", "Regional Supermarket") and rng.random() < 0.06:
            churn = pd.Timestamp("2024-01-01") + pd.DateOffset(months=int(rng.integers(0, 22)))
        cust_rows.append(dict(
            customer_id=f"C{cid:04d}", customer_name=name, segment=seg, region=region, city=city,
            rep_id=rep, account_open_date=start.date(), rebate_pct=rebate,
            payment_terms_days=int(rng.choice([30, 45, 60] if seg == "National Chain" else [0, 15, 30])),
            _base_disc=base_disc, _churn=churn))
        cid += 1
cust = pd.DataFrame(cust_rows)

# --------------------------------------------------------------------------
# 3. Orders and order lines
# --------------------------------------------------------------------------
SEASON = {1: 0.92, 2: 0.9, 3: 0.98, 4: 1.0, 5: 1.03, 6: 1.08, 7: 1.12, 8: 1.1, 9: 1.0, 10: 0.98, 11: 1.02, 12: 1.15}
YEAR_VOL = {2023: 1.0, 2024: 1.04, 2025: 1.07}
PROMO_CATS = {"Snacks", "Beverages"}  # chain promotion Apr-Dec 2025

prod_by_cat = {c: prod.loc[prod.category == c, "sku"].to_numpy() for c in CATS}
price_lookup = price_list.assign(year=lambda d: d.effective_from.str[:4].astype(int)).set_index(["sku", "year"]).list_price
cost_sorted = costs.assign(effective_from=pd.to_datetime(costs.effective_from)).sort_values(["sku", "effective_from"])
cost_dict = {s: g for s, g in cost_sorted.groupby("sku")}
prod_cat = prod.set_index("sku").category.to_dict()

def unit_cost_on(sku, date):
    g = cost_dict[sku]
    return float(g.loc[g.effective_from <= date, "unit_cost"].iloc[-1])

line_rows, order_rows = [], []
oid = 100000
for _, c in cust.iterrows():
    seg = c.segment
    n_cust, dlo, dhi, rlo, rhi, opm, n_lines, qty_mean = SEGMENTS[seg]
    if c.customer_name == "FreshCart Group":
        opm = opm * 1.8
    prefs = SEG_CAT_PREF[seg]
    cats = list(prefs)
    w = np.array([prefs[k] for k in cats], float)
    w /= w.sum()
    open_d = pd.Timestamp(c.account_open_date)
    for m in MONTHS:
        if m < open_d.replace(day=1) or (c._churn is not None and m >= c._churn):
            continue
        n_orders = rng.poisson(opm * SEASON[m.month])
        for _ in range(n_orders):
            oid += 1
            day = int(rng.integers(1, m.days_in_month + 1))
            odate = m.replace(day=day)
            k_lines = max(1, int(rng.poisson(n_lines)))
            chosen_cats = rng.choice(cats, size=k_lines, p=w)
            # dict keeps insertion order, so the run is reproducible (a set would not be)
            skus = list(dict.fromkeys(rng.choice(prod_by_cat[cat]) for cat in chosen_cats))
            order_value = 0.0
            for sku in skus:
                cat = prod_cat[sku]
                promo = (seg == "National Chain" and cat in PROMO_CATS and odate >= pd.Timestamp("2025-04-01"))
                vol = YEAR_VOL[odate.year] * (1.25 if promo else 1.0)
                qty = max(1, int(round(rng.lognormal(np.log(qty_mean * vol), 0.5))))
                lp = float(price_lookup[(sku, odate.year)])
                disc = c._base_disc + REP_EXTRA[c.rep_id] + (0.15 if promo else 0.0) + rng.uniform(0, 0.015)
                disc = round(float(np.clip(disc, 0, 0.35)), 4)
                net = round(lp * qty * (1 - disc), 2)
                order_value += net
                line_rows.append(dict(order_id=f"SO{oid}", order_date=odate, customer_id=c.customer_id,
                                      rep_id=c.rep_id, sku=sku, quantity=qty, list_price=lp,
                                      discount=round(disc, 4), net_amount=net,
                                      _promo=promo, _seg=seg, _cat=cat))
            # freight: a fixed drop cost by region plus a small variable part
            base = REGIONS[c.region][1] if c.region in REGIONS else 18
            freight = base * rng.uniform(0.9, 1.15) + 0.006 * order_value
            order_rows.append(dict(order_id=f"SO{oid}", customer_id=c.customer_id,
                                   delivery_date=(odate + pd.Timedelta(days=int(rng.integers(1, 4)))).date(),
                                   freight_cost=round(freight, 2), _region=c.region))
lines = pd.DataFrame(line_rows)
orders = pd.DataFrame(order_rows)
lines.insert(0, "line_id", np.arange(1, len(lines) + 1))

# --------------------------------------------------------------------------
# 4. Returns (short-life goods to small stores come back expired)
# --------------------------------------------------------------------------
ret_p = np.full(len(lines), 0.012)
short_life = lines._cat.isin(["Bakery", "Dairy"]).to_numpy()
seg_arr = lines._seg.to_numpy()
ret_p[short_life & (seg_arr == "Convenience Store")] = 0.11
ret_p[short_life & (seg_arr == "HoReCa")] = 0.05
ret_p[short_life & np.isin(seg_arr, ["Independent Grocery"])] = 0.03
is_ret = rng.random(len(lines)) < ret_p
r = lines.loc[is_ret].copy()
reasons_short = ["Expired", "Damaged", "Wrong Item", "Customer Refused"]
reasons_other = ["Damaged", "Wrong Item", "Customer Refused", "Expired"]
r["reason"] = [rng.choice(reasons_short, p=[0.65, 0.2, 0.1, 0.05]) if c in ("Bakery", "Dairy")
               else rng.choice(reasons_other, p=[0.5, 0.3, 0.15, 0.05]) for c in r._cat]
r["return_qty"] = np.maximum(1, np.ceil(r.quantity * rng.uniform(0.3, 1.0, len(r)))).astype(int)
r["return_date"] = (r.order_date + pd.to_timedelta(rng.integers(4, 21, len(r)), unit="D")).dt.date
returns = r[["order_id", "sku", "customer_id", "return_date", "return_qty", "reason"]].reset_index(drop=True)
returns.insert(0, "return_id", [f"RT{i:06d}" for i in range(1, len(returns) + 1)])

# --------------------------------------------------------------------------
# 5. Inject realistic data-quality problems
# --------------------------------------------------------------------------
lines_raw = lines.drop(columns=["_promo", "_seg", "_cat"]).copy()
lines_raw["order_date"] = lines_raw.order_date.dt.strftime("%Y-%m-%d")
n = len(lines_raw)
# a) 8% of dates exported as DD/MM/YYYY by a second system
idx = rng.choice(n, int(n * 0.08), replace=False)
lines_raw.loc[idx, "order_date"] = pd.to_datetime(lines_raw.loc[idx, "order_date"]).dt.strftime("%d/%m/%Y")
# b) 3% of SKU codes in lowercase or with trailing spaces
idx = rng.choice(n, int(n * 0.03), replace=False)
lines_raw.loc[idx, "sku"] = [s.lower() if i % 2 else s + "  " for i, s in enumerate(lines_raw.loc[idx, "sku"])]
# c) 2% missing rep_id
idx = rng.choice(n, int(n * 0.02), replace=False)
lines_raw.loc[idx, "rep_id"] = np.nan
# d) 4% of discounts typed as whole percentages (8 instead of 0.08)
idx = rng.choice(n, int(n * 0.04), replace=False)
lines_raw.loc[idx, "discount"] = (lines_raw.loc[idx, "discount"] * 100).round(2)
# e) 0.6% exact duplicate lines (double export)
dups = lines_raw.sample(frac=0.006, random_state=SEED)
lines_raw = pd.concat([lines_raw, dups], ignore_index=True)
# f) returns also keyed as negative sales lines for ~20% of returns (double count risk)
neg = returns.sample(frac=0.2, random_state=SEED).merge(
    lines.drop(columns=["_promo", "_seg", "_cat"]), on=["order_id", "sku", "customer_id"], how="left")
neg_lines = pd.DataFrame(dict(
    line_id=np.arange(9_000_001, 9_000_001 + len(neg)), order_id=neg.order_id,
    order_date=pd.to_datetime(neg.return_date).dt.strftime("%Y-%m-%d"), customer_id=neg.customer_id,
    rep_id=neg.rep_id, sku=neg.sku, quantity=-neg.return_qty, list_price=neg.list_price,
    discount=neg.discount, net_amount=(-neg.return_qty * neg.list_price * (1 - neg.discount)).round(2)))
lines_raw = pd.concat([lines_raw, neg_lines], ignore_index=True)
# g) a test account used by IT
test = lines_raw.sample(60, random_state=7).copy()
test["customer_id"] = "C9999"
test["order_id"] = ["SOTEST" + str(i) for i in range(len(test))]
test["line_id"] = np.arange(9_500_001, 9_500_001 + len(test))
lines_raw = pd.concat([lines_raw, test], ignore_index=True).sample(frac=1, random_state=SEED).reset_index(drop=True)

# customers: messy names, region typos, duplicate records
cust_raw = cust.drop(columns=["_base_disc", "_churn"]).copy()
cust_raw["customer_name"] = [nm if sg == "National Chain" else (nm.upper() if i % 9 == 0 else ("  " + nm if i % 13 == 0 else nm))
                             for i, (nm, sg) in enumerate(zip(cust_raw.customer_name, cust_raw.segment))]
typo = {"North": "Nrth", "Central": "central ", "West": "WEST"}
idx = rng.choice(len(cust_raw), 25, replace=False)
cust_raw.loc[idx, "region"] = cust_raw.loc[idx, "region"].map(lambda x: typo.get(x, x))
dup_src = cust_raw[cust_raw.segment.isin(["Independent Grocery", "Regional Supermarket"])].sample(6, random_state=3)
dup_rows = dup_src.copy()
dup_rows["customer_id"] = [f"C{9000 + i}" for i in range(len(dup_rows))]
dup_rows["customer_name"] = dup_rows.customer_name.str.lower()
cust_raw = pd.concat([cust_raw, dup_rows, pd.DataFrame([dict(
    customer_id="C9999", customer_name="TEST ACCOUNT - DO NOT USE", segment="Internal", region="Central",
    city="Riverton", rep_id="R01", account_open_date="2023-01-01", rebate_pct=0,
    payment_terms_days=0)])], ignore_index=True)
# some lines of the duplicated customers were booked under the duplicate ID
for _, d in dup_rows.iterrows():
    orig = dup_src.loc[dup_src.customer_name.str.lower() == d.customer_name, "customer_id"].iloc[0]
    mask = (lines_raw.customer_id == orig) & (rng.random(len(lines_raw)) < 0.3)
    lines_raw.loc[mask, "customer_id"] = d.customer_id

# products: category casing and duplicated master rows
prod_raw = prod.drop(columns=["base_margin", "list_price_2023"]).copy()
idx = rng.choice(len(prod_raw), 20, replace=False)
prod_raw.loc[idx, "category"] = prod_raw.loc[idx, "category"].map(lambda x: x.lower() if len(x) % 2 else x + " ")
prod_raw = pd.concat([prod_raw, prod_raw.sample(3, random_state=11)], ignore_index=True)

# supplier costs: one SKU missing its first cost record
costs_raw = costs.drop(costs[(costs.sku == "SKU0047") & (costs.effective_from == "2023-01-01")].index)

# deliveries: 1% missing freight
orders_raw = orders.drop(columns=["_region"]).copy()
idx = rng.choice(len(orders_raw), int(len(orders_raw) * 0.01), replace=False)
orders_raw.loc[idx, "freight_cost"] = np.nan

# returns: inconsistent reason text
alias = {"Expired": ["Expired", "EXPIRED", "expiry", "Expired "], "Damaged": ["Damaged", "damaged", "DMG"],
         "Wrong Item": ["Wrong Item", "wrong item"], "Customer Refused": ["Customer Refused", "Refused"]}
returns_raw = returns.copy()
returns_raw["reason"] = [rng.choice(alias[x]) for x in returns_raw.reason]

# --------------------------------------------------------------------------
# 6. Save
# --------------------------------------------------------------------------
lines_raw.to_csv(RAW / "sales_lines_raw.csv", index=False)
cust_raw.to_csv(RAW / "customers_raw.csv", index=False)
prod_raw.to_csv(RAW / "products_raw.csv", index=False)
price_list.to_csv(RAW / "price_list_raw.csv", index=False)
costs_raw.to_csv(RAW / "supplier_costs_raw.csv", index=False)
reps.to_csv(RAW / "sales_reps_raw.csv", index=False)
orders_raw.to_csv(RAW / "deliveries_raw.csv", index=False)
returns_raw.to_csv(RAW / "returns_raw.csv", index=False)

print(f"sales lines: {len(lines_raw):,} | orders: {len(orders_raw):,} | customers: {len(cust_raw):,} "
      f"| products: {len(prod_raw):,} | returns: {len(returns_raw):,}")
