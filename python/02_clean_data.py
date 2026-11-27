"""
02_clean_data.py
----------------
Cleans the raw ERP exports and builds a star schema for Power BI and SQL.

Every cleaning decision is written to data/clean/data_quality_log.csv with the
number of rows it affected, so the numbers in the dashboard can be traced back.

Run:  python 02_clean_data.py
Input:  ../data/raw/*.csv
Output: ../data/clean/*.csv
"""
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW, CLEAN = ROOT / "data" / "raw", ROOT / "data" / "clean"
CLEAN.mkdir(parents=True, exist_ok=True)

LOG = []


def log(table, issue, rows, action):
    """Record one data-quality decision."""
    LOG.append(dict(step=len(LOG) + 1, table=table, issue=issue, rows_affected=int(rows), action=action))
    print(f"[{table}] {issue}: {rows:,} -> {action}")


# --------------------------------------------------------------------------
# Products
# --------------------------------------------------------------------------
prod = pd.read_csv(RAW / "products_raw.csv")
bad_cat = (prod.category != prod.category.str.strip().str.title().str.replace("Horeca", "HoReCa")).sum()
prod["category"] = prod.category.str.strip().str.title()
log("products", "Category text with wrong case or trailing spaces", bad_cat, "Trimmed and title-cased")
dup = prod.duplicated("sku").sum()
prod = prod.drop_duplicates("sku")
log("products", "Duplicate SKU rows in product master", dup, "Kept first occurrence")

# --------------------------------------------------------------------------
# Customers
# --------------------------------------------------------------------------
cust = pd.read_csv(RAW / "customers_raw.csv")
test_ids = cust.loc[cust.customer_name.str.contains("TEST", case=False), "customer_id"].tolist()
cust = cust[~cust.customer_id.isin(test_ids)]
log("customers", "Internal test account", len(test_ids), "Removed (and its sales lines)")

messy = (cust.customer_name != cust.customer_name.str.strip()).sum() + cust.customer_name.str.isupper().sum()
cust["customer_name"] = cust.customer_name.str.strip()
cust["customer_name"] = np.where(cust.customer_name.str.isupper() | cust.customer_name.str.islower(),
                                 cust.customer_name.str.title(), cust.customer_name)
log("customers", "Names in all caps, lowercase or with leading spaces", messy, "Trimmed and title-cased")

REGION_MAP = {"nrth": "North", "north": "North", "central": "Central", "west": "West",
              "south": "South", "east": "East"}
bad_reg = (~cust.region.isin(["North", "South", "East", "West", "Central"])).sum()
cust["region"] = cust.region.str.strip().str.lower().map(REGION_MAP).fillna(cust.region)
log("customers", "Region typos (e.g. 'Nrth', 'WEST', 'central ')", bad_reg, "Mapped to 5 standard regions")

# duplicate customer records: same name (case-insensitive) and city, different ID
cust["_key"] = cust.customer_name.str.lower() + "|" + cust.city.str.lower()
cust = cust.sort_values("customer_id")
master = cust.groupby("_key").customer_id.transform("first")
CUST_ID_MAP = dict(zip(cust.customer_id, master))
n_dup_cust = (cust.customer_id != master).sum()
cust = cust[cust.customer_id == master].drop(columns="_key")
log("customers", "Duplicate customer records (same name and city, different ID)", n_dup_cust,
    "Merged into the original customer ID")

cust["account_open_date"] = pd.to_datetime(cust.account_open_date)
cust["cohort_year"] = np.where(cust.account_open_date.dt.year < 2023, "Before 2023",
                               cust.account_open_date.dt.year.astype(str))

# --------------------------------------------------------------------------
# Sales lines
# --------------------------------------------------------------------------
s = pd.read_csv(RAW / "sales_lines_raw.csv")
n0 = len(s)

n_test = s.customer_id.isin(test_ids).sum()
s = s[~s.customer_id.isin(test_ids)]
log("sales_lines", "Lines booked to the test account", n_test, "Removed")

n_map = s.customer_id.map(lambda x: CUST_ID_MAP.get(x, x) != x).sum()
s["customer_id"] = s.customer_id.map(lambda x: CUST_ID_MAP.get(x, x))
log("sales_lines", "Lines booked to a duplicate customer ID", n_map, "Re-pointed to the master customer ID")

n_dup = s.duplicated().sum()
s = s.drop_duplicates()
log("sales_lines", "Exact duplicate lines (double export)", n_dup, "Removed")

n_neg = (s.quantity <= 0).sum()
s = s[s.quantity > 0]
log("sales_lines", "Negative-quantity lines (returns keyed in the sales system)", n_neg,
    "Removed: returns_raw.csv is the single source for returns, so keeping them would double count")

# dates arrive in two formats
iso = s.order_date.str.match(r"^\d{4}-\d{2}-\d{2}$")
log("sales_lines", "Order dates in DD/MM/YYYY instead of YYYY-MM-DD", (~iso).sum(), "Parsed with the correct format")
s["order_date"] = pd.to_datetime(s.order_date.where(iso), format="%Y-%m-%d").fillna(
    pd.to_datetime(s.order_date.where(~iso), format="%d/%m/%Y"))

bad_sku = (s.sku != s.sku.str.strip().str.upper()).sum()
s["sku"] = s.sku.str.strip().str.upper()
log("sales_lines", "SKU codes in lowercase or with trailing spaces", bad_sku, "Trimmed and upper-cased")
unknown = (~s.sku.isin(prod.sku)).sum()
log("sales_lines", "SKUs not found in product master", unknown, "Checked: none" if unknown == 0 else "Flagged")

pct = s.discount > 1
log("sales_lines", "Discount typed as a whole number (8 instead of 0.08)", pct.sum(), "Divided by 100")
s.loc[pct, "discount"] = s.loc[pct, "discount"] / 100

miss_rep = s.rep_id.isna().sum()
s["rep_id"] = s.rep_id.fillna(s.customer_id.map(cust.set_index("customer_id").rep_id))
log("sales_lines", "Missing rep_id", miss_rep, "Filled with the customer's assigned rep")

# recompute amounts from price, quantity and discount and check them against the export
s["gross_sales"] = (s.list_price * s.quantity).round(2)
s["discount_amount"] = (s.gross_sales * s.discount).round(2)
s["net_sales"] = (s.gross_sales - s.discount_amount).round(2)
mismatch = (abs(s.net_sales - s.net_amount) > 0.05).sum()
log("sales_lines", "Exported net_amount differs from price x qty x (1 - discount) by more than $0.05",
    mismatch, "Checked: none" if mismatch == 0 else "Used the recomputed net_sales")

# --------------------------------------------------------------------------
# Supplier costs: cost valid on the order date
# --------------------------------------------------------------------------
costs = pd.read_csv(RAW / "supplier_costs_raw.csv", parse_dates=["effective_from"]).sort_values("effective_from")
first_cost = costs.groupby("sku").effective_from.min()
late = first_cost[first_cost > "2023-01-01"]
log("supplier_costs", "SKUs whose first cost record starts after Jan 2023", len(late),
    f"Earliest known cost used for earlier dates ({', '.join(late.index)})")
s = s.sort_values("order_date")
s = pd.merge_asof(s, costs, left_on="order_date", right_on="effective_from", by="sku", direction="backward")
missing = s.unit_cost.isna()
if missing.any():
    back = pd.merge_asof(s.loc[missing, ["order_date", "sku"]].reset_index(), costs, left_on="order_date",
                         right_on="effective_from", by="sku", direction="forward").set_index("index")
    s.loc[missing, "unit_cost"] = back.unit_cost
log("sales_lines", "Lines with no cost on the order date", missing.sum(), "Back-filled from the earliest cost")
s["cogs"] = (s.unit_cost * s.quantity).round(2)

# --------------------------------------------------------------------------
# Rebates and freight
# --------------------------------------------------------------------------
s = s.merge(cust[["customer_id", "segment", "region", "rebate_pct"]], on="customer_id", how="left")
s["rebate_amount"] = (s.net_sales * s.rebate_pct).round(2)

dl = pd.read_csv(RAW / "deliveries_raw.csv", parse_dates=["delivery_date"])
dl = dl[~dl.order_id.str.startswith("SOTEST")]
dl["customer_id"] = dl.customer_id.map(lambda x: CUST_ID_MAP.get(x, x))
order_val = s.groupby("order_id").net_sales.sum()
dl["order_value"] = dl.order_id.map(order_val)
dl = dl.merge(cust[["customer_id", "region"]], on="customer_id", how="left")
dl["size_band"] = pd.cut(dl.order_value, [0, 500, 2000, 10000, np.inf], labels=["<500", "500-2k", "2k-10k", "10k+"])
miss_f = dl.freight_cost.isna().sum()
med = dl.groupby(["region", "size_band"], observed=True).freight_cost.transform("median")
dl["freight_cost"] = dl.freight_cost.fillna(med.round(2))
log("deliveries", "Missing freight cost", miss_f, "Imputed with the median for the same region and order-size band")

# allocate each order's freight to its lines by share of net sales
s = s.merge(dl[["order_id", "freight_cost"]], on="order_id", how="left")
s["freight_cost"] = (s.freight_cost * s.net_sales / s.order_id.map(order_val)).round(2)

s["gross_profit"] = (s.net_sales - s.cogs).round(2)
s["pocket_profit"] = (s.gross_profit - s.rebate_amount - s.freight_cost).round(2)

# --------------------------------------------------------------------------
# Returns
# --------------------------------------------------------------------------
r = pd.read_csv(RAW / "returns_raw.csv", parse_dates=["return_date"])
REASON = {"expired": "Expired", "expiry": "Expired", "damaged": "Damaged", "dmg": "Damaged",
          "wrong item": "Wrong Item", "customer refused": "Customer Refused", "refused": "Customer Refused"}
bad_reason = (~r.reason.isin(["Expired", "Damaged", "Wrong Item", "Customer Refused"])).sum()
r["reason"] = r.reason.str.strip().str.lower().map(REASON)
log("returns", "Inconsistent return reasons (EXPIRED, expiry, DMG, Refused ...)", bad_reason,
    "Mapped to 4 standard reasons")
r["customer_id"] = r.customer_id.map(lambda x: CUST_ID_MAP.get(x, x))
r = r.merge(s[["order_id", "sku", "line_id", "order_date", "rep_id", "quantity", "net_sales", "unit_cost"]],
            on=["order_id", "sku"], how="left")
unmatched = r.line_id.isna().sum()
log("returns", "Returns that do not match a sales line", unmatched, "Checked: none" if unmatched == 0 else "Removed")
r = r.dropna(subset=["line_id"])
over = (r.return_qty > r.quantity).sum()
r["return_qty"] = np.minimum(r.return_qty, r.quantity)
log("returns", "Returned quantity above quantity sold", over, "Capped at quantity sold" if over else "Checked: none")
r["credit_amount"] = (r.net_sales / r.quantity * r.return_qty).round(2)
r["cost_amount"] = (r.unit_cost * r.return_qty).round(2)
r["is_write_off"] = r.reason.isin(["Expired", "Damaged"])
r["cost_recovered"] = np.where(r.is_write_off, 0, r.cost_amount)
r["write_off_cost"] = np.where(r.is_write_off, r.cost_amount, 0)
# effect on profit: lose the credited revenue, get the stock back only if it can be resold
r["profit_impact"] = (-r.credit_amount + r.cost_recovered).round(2)

# --------------------------------------------------------------------------
# Dimensions and save
# --------------------------------------------------------------------------
dates = pd.DataFrame({"date": pd.date_range("2023-01-01", "2025-12-31")})
dates["year"] = dates.date.dt.year
dates["quarter"] = "Q" + dates.date.dt.quarter.astype(str)
dates["month_no"] = dates.date.dt.month
dates["month_name"] = dates.date.dt.strftime("%b")
dates["year_month"] = dates.date.dt.strftime("%Y-%m")
dates["month_start"] = dates.date.dt.to_period("M").dt.to_timestamp()

reps = pd.read_csv(RAW / "sales_reps_raw.csv")
price_list = pd.read_csv(RAW / "price_list_raw.csv", parse_dates=["effective_from"])
dim_cost = costs.sort_values(["sku", "effective_from"]).copy()
dim_cost["effective_to"] = dim_cost.groupby("sku").effective_from.shift(-1) - pd.Timedelta(days=1)
dim_cost["effective_to"] = dim_cost.effective_to.fillna(pd.Timestamp("2099-12-31"))

fact_sales = s[["line_id", "order_id", "order_date", "customer_id", "rep_id", "sku", "quantity", "list_price",
                "discount", "gross_sales", "discount_amount", "net_sales", "unit_cost", "cogs",
                "rebate_amount", "freight_cost", "gross_profit", "pocket_profit"]].rename(
    columns={"discount": "discount_pct"}).sort_values("line_id")
fact_sales["line_id"] = fact_sales.line_id.astype(int)
r = r.rename(columns={"order_date": "sale_date"})  # returns are reported in the year of the original sale
fact_returns = r[["return_id", "line_id", "order_id", "sku", "customer_id", "rep_id", "sale_date", "return_date", "reason",
                  "return_qty", "credit_amount", "cost_amount", "cost_recovered", "write_off_cost",
                  "profit_impact"]].copy()
fact_returns["line_id"] = fact_returns.line_id.astype(int)
fact_orders = dl[["order_id", "customer_id", "delivery_date", "order_value", "size_band", "freight_cost"]]

prod[["sku", "product_name", "category", "supplier", "pack"]].to_csv(CLEAN / "dim_product.csv", index=False)
cust[["customer_id", "customer_name", "segment", "region", "city", "rep_id", "account_open_date",
      "cohort_year", "rebate_pct", "payment_terms_days"]].to_csv(CLEAN / "dim_customer.csv", index=False)
reps.to_csv(CLEAN / "dim_rep.csv", index=False)
dates.to_csv(CLEAN / "dim_date.csv", index=False)
dim_cost.to_csv(CLEAN / "dim_product_cost.csv", index=False)
price_list.to_csv(CLEAN / "dim_price_list.csv", index=False)
fact_sales.to_csv(CLEAN / "fact_sales.csv", index=False)
fact_returns.to_csv(CLEAN / "fact_returns.csv", index=False)
fact_orders.to_csv(CLEAN / "fact_orders.csv", index=False)
pd.DataFrame(LOG).to_csv(CLEAN / "data_quality_log.csv", index=False)

# reconciliation: every clean line traces back to a raw line
print(f"\nRaw sales lines: {n0:,}  ->  clean lines: {len(fact_sales):,}")
print(f"Net sales: ${fact_sales.net_sales.sum():,.0f} | returns: {len(fact_returns):,} | orders: {len(fact_orders):,}")
assert fact_sales.line_id.is_unique, "line_id must be unique"
assert fact_sales.unit_cost.notna().all(), "every line needs a cost"
assert fact_orders.freight_cost.notna().all(), "every order needs freight"
assert abs(fact_sales.freight_cost.sum() - fact_orders.freight_cost.sum()) < 50, "freight allocation must reconcile"
print("All checks passed.")
