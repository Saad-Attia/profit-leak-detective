# Findings: Harbor & Field Distribution (simulated data), 2023-2025

> All numbers come from the simulated dataset in this repository and are produced by `03_analysis.py`.

## Q1. Are we more profitable, or just selling more?

- Net revenue grew from $14.87M (2023) to $19.50M (2025), +31.1% over two years.
- Gross profit peaked in 2024 at $3.36M and fell to $2.74M in 2025 (-18.4%). Gross margin went from 18.7% to 14.1%.
- Pocket profit (after rebates and freight) fell -28.3% in 2025 to $1.83M; pocket margin is 9.4%.
- In 2025, 11.0% of list-price sales went out as invoice discounts, 2.7% as rebates and 1.4% as freight.
- Supplier costs rose faster than prices in 2025. Worst category: Beverages, cost per case +8.5% vs net price -5.4%, gross margin -12.6 pts.

## Q2. Which products and customers make or destroy profit?

- 69 of 393 active customers lost money in 2025 at pocket level, holding 2.0% of net revenue and losing $20K in total.
- Loss-making customers by segment: Convenience Store 69.
- The top 20% of customers earn 77% of total pocket profit.
- 69 of 130 Convenience Store customers are loss-making.
- The biggest customer, FreshCart Group, brings $2.26M (12% of revenue) but only $24K of pocket profit: a 1.1% pocket margin after a 16.4% average discount and $159K of rebates.
- Convenience Store: pocket margin -0.4%, freight 10.2% of revenue, returns 3.6%, average order $290.
- National Chain: pocket margin 6.0%, freight 0.7% of revenue, returns 0.8%, average order $24K.
- HoReCa: pocket margin 11.1%, freight 3.4% of revenue, returns 2.0%, average order $935.
- Independent Grocery: pocket margin 16.0%, freight 3.0% of revenue, returns 1.1%, average order $1K.
- Regional Supermarket: pocket margin 16.2%, freight 1.2% of revenue, returns 0.9%, average order $5K.
- National chains: $11.04M of revenue (57%) but only $661K of pocket profit; 0 of 8 chains are loss-making after rebates.
- Returns cost $153K of profit in 2025; the single biggest source is Personal Care sold to National Chain (return rate 0.9%, impact -$15K).

## Q3. Are reps giving away margin?

- Rana Ezzat (R12, West): +4.7 pts above peers selling to the same segments, = $41K of extra discount in 2025.
- Omar Rashed (R05, North): +4.2 pts above peers selling to the same segments, = $17K of extra discount in 2025.
- Tarek Hassan (R09, South): +1.2 pts above peers selling to the same segments, = $7K of extra discount in 2025.
- Correlation between a customer's discount rate and its sales, within each segment: Convenience Store -0.28, HoReCa -0.19, Independent Grocery -0.07, Regional Supermarket -0.10. Bigger discounts are not buying bigger customers.

## Q4. What is sold below its minimum profitable price?

- 4,923 order lines across 77 SKUs were invoiced below unit cost in 2025: $2.82M of sales, $194K of gross loss.
- By segment: National Chain -$175K, Convenience Store -$8K, Regional Supermarket -$6K, Independent Grocery -$3K, HoReCa -$3K.
- By category: Beverages -$125K, Dairy -$65K, Snacks -$2K, Canned Goods -$1K, Frozen -$2.
- 27.5% of 2025 sales were priced below the floor of cost + 8% gross margin.

## Q5. What-if scenarios (2025 base, annual pocket profit)

Assumptions: elasticity 1.0 (each 1% price rise loses 1% volume on the affected lines); 10% of small orders lost after the fee. Base pocket profit: $1.83M.

| Scenario | Change in pocket profit |
|---|---|
| Price floor (min 8% gross margin on every line) | +$525K |
| Cap invoice discounts at 10% | +$448K |
| $25 delivery fee on orders under $400 | +$56K |
| Halve expired Bakery/Dairy returns from convenience stores | +$8K |
| All four together | +$777K |

There were 2,506 orders under $400 in 2025, with a combined pocket profit of $4K.
