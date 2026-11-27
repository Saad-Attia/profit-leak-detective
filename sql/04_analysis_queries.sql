-- =============================================================================
-- 04_analysis_queries.sql
-- One query per management question. Each one can be run on its own.
-- =============================================================================


-- -----------------------------------------------------------------------------
-- Q1a. Are we more profitable, or just selling more?  (year-on-year growth)
-- -----------------------------------------------------------------------------
SELECT year,
       ROUND(net_revenue, 0)                                              AS net_revenue,
       ROUND(gross_profit, 0)                                             AS gross_profit,
       ROUND(100 * gross_margin, 1)                                       AS gross_margin_pct,
       ROUND(pocket_profit, 0)                                            AS pocket_profit,
       ROUND(100 * (net_revenue  / LAG(net_revenue)  OVER (ORDER BY year) - 1), 1) AS revenue_growth_pct,
       ROUND(100 * (gross_profit / LAG(gross_profit) OVER (ORDER BY year) - 1), 1) AS gp_growth_pct,
       ROUND(100 * (pocket_profit / LAG(pocket_profit) OVER (ORDER BY year) - 1), 1) AS pocket_growth_pct
FROM vw_yearly_kpis
ORDER BY year;


-- -----------------------------------------------------------------------------
-- Q1b. Did prices keep up with supplier costs?  (per case, 2024 vs 2025)
-- -----------------------------------------------------------------------------
WITH cat_year AS (
    SELECT category, year,
           SUM(net_sales) / SUM(quantity)                 AS net_per_case,
           SUM(quantity * unit_cost) / SUM(quantity)      AS cost_per_case,
           1 - SUM(quantity * unit_cost) / SUM(net_sales) AS gross_margin
    FROM vw_line_profit
    WHERE year IN (2024, 2025)
    GROUP BY category, year
)
SELECT cur.category,
       ROUND(100 * (cur.cost_per_case / prv.cost_per_case - 1), 1) AS cost_change_pct,
       ROUND(100 * (cur.net_per_case  / prv.net_per_case  - 1), 1) AS net_price_change_pct,
       ROUND(100 * (cur.gross_margin - prv.gross_margin), 1)       AS gm_change_pts
FROM cat_year cur
JOIN cat_year prv ON prv.category = cur.category AND prv.year = 2024
WHERE cur.year = 2025
ORDER BY gm_change_pts;


-- -----------------------------------------------------------------------------
-- Q2a. Segment profitability 2025: where does profit leak after the invoice?
-- -----------------------------------------------------------------------------
WITH seg AS (
    SELECT segment,
           SUM(net_revenue)   AS net_revenue,
           SUM(gross_profit)  AS gross_profit,
           SUM(rebate_amount) AS rebates,
           SUM(freight_cost)  AS freight,
           SUM(pocket_profit) AS pocket_profit,
           COUNT(DISTINCT order_id) AS orders
    FROM vw_line_profit
    WHERE year = 2025
    GROUP BY segment
)
SELECT segment,
       ROUND(net_revenue, 0)                          AS net_revenue,
       ROUND(100 * gross_profit / net_revenue, 1)     AS gross_margin_pct,
       ROUND(100 * freight / net_revenue, 1)          AS freight_pct,
       ROUND(100 * pocket_profit / net_revenue, 1)    AS pocket_margin_pct,
       ROUND(net_revenue / orders, 0)                 AS avg_order_value
FROM seg
ORDER BY pocket_margin_pct;


-- -----------------------------------------------------------------------------
-- Q2b. Customer profitability ranking and whale curve, 2025
-- -----------------------------------------------------------------------------
WITH cust AS (
    SELECT customer_id, customer_name, segment,
           SUM(net_revenue)   AS net_revenue,
           SUM(pocket_profit) AS pocket_profit
    FROM vw_line_profit
    WHERE year = 2025
    GROUP BY customer_id, customer_name, segment
),
ranked AS (
    SELECT *,
           RANK() OVER (ORDER BY pocket_profit DESC)                         AS profit_rank,
           SUM(pocket_profit) OVER (ORDER BY pocket_profit DESC
                                    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
             / SUM(pocket_profit) OVER ()                                    AS cum_profit_share,
           COUNT(*) OVER ()                                                  AS n_customers
    FROM cust
)
SELECT profit_rank, customer_name, segment,
       ROUND(net_revenue, 0)                       AS net_revenue,
       ROUND(pocket_profit, 0)                     AS pocket_profit,
       ROUND(100 * pocket_profit / net_revenue, 1) AS pocket_margin_pct,
       ROUND(100 * cum_profit_share, 1)            AS cum_profit_share_pct,
       ROUND(100.0 * profit_rank / n_customers, 1) AS cum_customer_pct
FROM ranked
ORDER BY profit_rank;


-- -----------------------------------------------------------------------------
-- Q2c. How many customers lose money, and how much revenue do they hold?
-- -----------------------------------------------------------------------------
WITH cust AS (
    SELECT customer_id, segment,
           SUM(net_revenue) AS net_revenue, SUM(pocket_profit) AS pocket_profit
    FROM vw_line_profit
    WHERE year = 2025
    GROUP BY customer_id, segment
)
SELECT segment,
       COUNT(*)                                                     AS customers,
       COUNT(*) FILTER (WHERE pocket_profit < 0)                    AS loss_making,
       ROUND(SUM(pocket_profit) FILTER (WHERE pocket_profit < 0), 0) AS loss_amount
FROM cust
GROUP BY ROLLUP (segment)
ORDER BY loss_making DESC;


-- -----------------------------------------------------------------------------
-- Q2d. Returns: which segment x category combinations cost the most?
-- -----------------------------------------------------------------------------
SELECT c.segment, p.category,
       COUNT(*)                         AS returns,
       ROUND(SUM(r.credit_amount), 0)   AS credit,
       ROUND(SUM(r.write_off_cost), 0)  AS write_off,
       ROUND(SUM(r.profit_impact), 0)   AS profit_impact
FROM fact_returns r
JOIN fact_sales   s ON s.line_id = r.line_id
JOIN dim_customer c ON c.customer_id = r.customer_id
JOIN dim_product  p ON p.sku = r.sku
WHERE EXTRACT(YEAR FROM s.order_date) = 2025
GROUP BY c.segment, p.category
ORDER BY profit_impact
LIMIT 10;


-- -----------------------------------------------------------------------------
-- Q3. Are reps giving away margin?  Mix-adjusted: compare each field rep with
--     the average discount of the segments they sell to.
-- -----------------------------------------------------------------------------
WITH field AS (
    SELECT * FROM vw_line_profit
    WHERE year = 2025 AND rep_id <> 'R14'          -- R14 = key accounts, contract pricing
),
seg_rate AS (
    SELECT segment, SUM(discount_amount) / SUM(gross_sales) AS seg_disc_rate
    FROM field
    GROUP BY segment
),
rep_agg AS (
    SELECT f.rep_id,
           SUM(f.gross_sales)                   AS gross_sales,
           SUM(f.discount_amount)               AS discount_amount,
           SUM(f.gross_sales * sr.seg_disc_rate) AS expected_discount,
           COUNT(DISTINCT f.customer_id)        AS customers,
           SUM(f.net_sales)                     AS net_sales
    FROM field f
    JOIN seg_rate sr ON sr.segment = f.segment
    GROUP BY f.rep_id
)
SELECT r.rep_id, d.rep_name, d.region,
       ROUND(100 * discount_amount / gross_sales, 1)                         AS avg_discount_pct,
       ROUND(100 * (discount_amount - expected_discount) / gross_sales, 1)   AS excess_discount_pts,
       ROUND(discount_amount - expected_discount, 0)                         AS excess_discount_usd,
       ROUND(net_sales / customers, 0)                                       AS sales_per_customer
FROM rep_agg r
JOIN dim_rep d ON d.rep_id = r.rep_id
ORDER BY excess_discount_usd DESC;


-- -----------------------------------------------------------------------------
-- Q4. Lines invoiced below unit cost in 2025, by SKU, with the minimum price
--     that keeps an 8% gross margin.
-- -----------------------------------------------------------------------------
SELECT sku, product_name, category,
       COUNT(*)                                      AS lines,
       ROUND(SUM(net_sales), 0)                      AS net_sales,
       ROUND(SUM(net_sales - quantity * unit_cost), 0) AS gross_loss,
       ROUND(AVG(net_price), 2)                      AS avg_net_price,
       ROUND(AVG(unit_cost), 2)                      AS avg_unit_cost,
       ROUND(AVG(unit_cost) / (1 - 0.08), 2)         AS min_price_8pct_gm
FROM vw_line_profit
WHERE year = 2025
  AND net_price < unit_cost
GROUP BY sku, product_name, category
ORDER BY gross_loss
LIMIT 20;


-- -----------------------------------------------------------------------------
-- Q4b. Summary: below-cost sales by segment and category
-- -----------------------------------------------------------------------------
SELECT segment, category,
       COUNT(*)                                        AS lines,
       ROUND(SUM(net_sales), 0)                        AS net_sales,
       ROUND(SUM(net_sales - quantity * unit_cost), 0) AS gross_loss
FROM vw_line_profit
WHERE year = 2025 AND net_price < unit_cost
GROUP BY segment, category
ORDER BY gross_loss;


-- -----------------------------------------------------------------------------
-- Q5. Simulator check: price floor at 8% gross margin, elasticity 1.0
--     (the full what-if version lives in Power BI and 03_analysis.py)
-- -----------------------------------------------------------------------------
WITH lines AS (
    SELECT l.*,
           GREATEST(net_price, unit_cost / (1 - 0.08))                     AS new_price,
           rebate_amount / NULLIF(net_sales, 0)                            AS rebate_rate
    FROM vw_line_profit l
    WHERE year = 2025
),
sim AS (
    SELECT *,
           GREATEST(0, 1 - 1.0 * (new_price / net_price - 1)) AS keep_share
    FROM lines
)
SELECT ROUND(SUM(net_sales - quantity * unit_cost - rebate_amount - freight_cost), 0) AS base_pocket_before_returns,
       ROUND(SUM(new_price * quantity * keep_share * (1 - rebate_rate)
                 - unit_cost * quantity * keep_share
                 - freight_cost * keep_share), 0)                               AS simulated_pocket_before_returns,
       ROUND(SUM(new_price * quantity * keep_share * (1 - rebate_rate)
                 - unit_cost * quantity * keep_share
                 - freight_cost * keep_share)
             - SUM(net_sales - quantity * unit_cost - rebate_amount - freight_cost), 0) AS uplift
FROM sim;
