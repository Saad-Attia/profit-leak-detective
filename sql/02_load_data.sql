-- =============================================================================
-- 02_load_data.sql  (run in psql from the project root folder)
-- \copy reads the files from your computer, so no server file access is needed.
-- =============================================================================

\copy dim_date         FROM 'data/clean/dim_date.csv'         WITH (FORMAT csv, HEADER true)
\copy dim_rep          FROM 'data/clean/dim_rep.csv'          WITH (FORMAT csv, HEADER true)
\copy dim_product      FROM 'data/clean/dim_product.csv'      WITH (FORMAT csv, HEADER true)
\copy dim_customer     FROM 'data/clean/dim_customer.csv'     WITH (FORMAT csv, HEADER true)
\copy dim_product_cost (sku, effective_from, unit_cost, effective_to) FROM 'data/clean/dim_product_cost.csv' WITH (FORMAT csv, HEADER true)
\copy dim_price_list   FROM 'data/clean/dim_price_list.csv'   WITH (FORMAT csv, HEADER true)
\copy fact_sales       FROM 'data/clean/fact_sales.csv'       WITH (FORMAT csv, HEADER true)
\copy fact_returns     FROM 'data/clean/fact_returns.csv'     WITH (FORMAT csv, HEADER true)
\copy fact_orders      FROM 'data/clean/fact_orders.csv'      WITH (FORMAT csv, HEADER true)

-- quick row-count check
SELECT 'fact_sales' AS table_name, COUNT(*) FROM fact_sales
UNION ALL SELECT 'fact_returns', COUNT(*) FROM fact_returns
UNION ALL SELECT 'fact_orders',  COUNT(*) FROM fact_orders
UNION ALL SELECT 'dim_customer', COUNT(*) FROM dim_customer
UNION ALL SELECT 'dim_product',  COUNT(*) FROM dim_product;
