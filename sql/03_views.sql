-- =============================================================================
-- 03_views.sql
-- Reusable views. Returns are attributed to the year of the ORIGINAL sale, so a
-- December sale returned in January still belongs to the year it was sold.
-- =============================================================================

-- One row per sales line with its returns already netted off.
CREATE OR REPLACE VIEW vw_line_profit AS
WITH ret AS (
    SELECT line_id,
           SUM(credit_amount)  AS return_credit,
           SUM(cost_recovered) AS cost_recovered,
           SUM(write_off_cost) AS write_off_cost
    FROM fact_returns
    GROUP BY line_id
)
SELECT s.line_id,
       s.order_id,
       s.order_date,
       EXTRACT(YEAR FROM s.order_date)::INT                     AS year,
       s.customer_id, c.customer_name, c.segment, c.region, c.cohort_year,
       s.rep_id, s.sku, p.product_name, p.category,
       s.quantity, s.list_price, s.discount_pct, s.unit_cost,
       s.net_sales / s.quantity                                 AS net_price,
       s.gross_sales, s.discount_amount, s.net_sales,
       COALESCE(r.return_credit, 0)                             AS return_credit,
       s.net_sales - COALESCE(r.return_credit, 0)               AS net_revenue,
       s.cogs - COALESCE(r.cost_recovered, 0)                   AS cogs_after_returns,
       s.rebate_amount,
       s.freight_cost,
       -- gross profit: revenue kept minus cost of goods not recovered
       (s.net_sales - COALESCE(r.return_credit, 0))
         - (s.cogs - COALESCE(r.cost_recovered, 0))             AS gross_profit,
       (s.net_sales - COALESCE(r.return_credit, 0))
         - (s.cogs - COALESCE(r.cost_recovered, 0))
         - s.rebate_amount - s.freight_cost                     AS pocket_profit
FROM fact_sales s
JOIN dim_customer c ON c.customer_id = s.customer_id
JOIN dim_product  p ON p.sku = s.sku
LEFT JOIN ret     r ON r.line_id = s.line_id;


-- Yearly KPI view used by Q1 and as a reconciliation check against Power BI.
CREATE OR REPLACE VIEW vw_yearly_kpis AS
SELECT year,
       SUM(gross_sales)                                   AS gross_sales,
       SUM(discount_amount)                               AS discounts,
       SUM(net_revenue)                                   AS net_revenue,
       SUM(gross_profit)                                  AS gross_profit,
       SUM(gross_profit) / NULLIF(SUM(net_revenue), 0)    AS gross_margin,
       SUM(rebate_amount)                                 AS rebates,
       SUM(freight_cost)                                  AS freight,
       SUM(pocket_profit)                                 AS pocket_profit,
       SUM(pocket_profit) / NULLIF(SUM(net_revenue), 0)   AS pocket_margin
FROM vw_line_profit
GROUP BY year;
