-- =============================================================================
-- Profit Leak Detective | B2B Distribution Profitability Control Tower
-- 01_create_schema.sql  (PostgreSQL)
-- Star schema: 6 dimensions, 3 facts. Load order: dimensions first, then facts.
-- =============================================================================

DROP TABLE IF EXISTS fact_returns, fact_sales, fact_orders,
    dim_product_cost, dim_price_list, dim_customer, dim_product, dim_rep, dim_date CASCADE;

CREATE TABLE dim_date (
    date            DATE PRIMARY KEY,
    year            INT  NOT NULL,
    quarter         VARCHAR(2) NOT NULL,
    month_no        INT  NOT NULL,
    month_name      VARCHAR(3) NOT NULL,
    year_month      VARCHAR(7) NOT NULL,
    month_start     DATE NOT NULL
);

CREATE TABLE dim_rep (
    rep_id          VARCHAR(5) PRIMARY KEY,
    rep_name        VARCHAR(60) NOT NULL,
    region          VARCHAR(20) NOT NULL,
    role            VARCHAR(40) NOT NULL
);

CREATE TABLE dim_product (
    sku             VARCHAR(10) PRIMARY KEY,
    product_name    VARCHAR(80) NOT NULL,
    category        VARCHAR(40) NOT NULL,
    supplier        VARCHAR(60) NOT NULL,
    pack            VARCHAR(20)
);

CREATE TABLE dim_customer (
    customer_id         VARCHAR(6) PRIMARY KEY,
    customer_name       VARCHAR(80) NOT NULL,
    segment             VARCHAR(30) NOT NULL,
    region              VARCHAR(20) NOT NULL,
    city                VARCHAR(30) NOT NULL,
    rep_id              VARCHAR(5) REFERENCES dim_rep (rep_id),
    account_open_date   DATE NOT NULL,
    cohort_year         VARCHAR(12) NOT NULL,
    rebate_pct          NUMERIC(5,3) NOT NULL DEFAULT 0,
    payment_terms_days  INT NOT NULL DEFAULT 0
);

-- supplier cost history (one row per cost change, effective_to = day before next change)
CREATE TABLE dim_product_cost (
    sku             VARCHAR(10) REFERENCES dim_product (sku),
    effective_from  DATE NOT NULL,
    unit_cost       NUMERIC(10,2) NOT NULL,
    effective_to    DATE NOT NULL,
    PRIMARY KEY (sku, effective_from)
);

CREATE TABLE dim_price_list (
    sku             VARCHAR(10) REFERENCES dim_product (sku),
    effective_from  DATE NOT NULL,
    list_price      NUMERIC(10,2) NOT NULL,
    PRIMARY KEY (sku, effective_from)
);

-- one row per order line; cost, rebate and freight already attached in Python
CREATE TABLE fact_sales (
    line_id         INT PRIMARY KEY,
    order_id        VARCHAR(12) NOT NULL,
    order_date      DATE NOT NULL REFERENCES dim_date (date),
    customer_id     VARCHAR(6) NOT NULL REFERENCES dim_customer (customer_id),
    rep_id          VARCHAR(5) NOT NULL REFERENCES dim_rep (rep_id),
    sku             VARCHAR(10) NOT NULL REFERENCES dim_product (sku),
    quantity        INT NOT NULL CHECK (quantity > 0),
    list_price      NUMERIC(10,2) NOT NULL,
    discount_pct    NUMERIC(6,4) NOT NULL CHECK (discount_pct BETWEEN 0 AND 1),
    gross_sales     NUMERIC(12,2) NOT NULL,
    discount_amount NUMERIC(12,2) NOT NULL,
    net_sales       NUMERIC(12,2) NOT NULL,
    unit_cost       NUMERIC(10,2) NOT NULL,
    cogs            NUMERIC(12,2) NOT NULL,
    rebate_amount   NUMERIC(12,2) NOT NULL,
    freight_cost    NUMERIC(12,2) NOT NULL,
    gross_profit    NUMERIC(12,2) NOT NULL,
    pocket_profit   NUMERIC(12,2) NOT NULL
);

CREATE TABLE fact_returns (
    return_id       VARCHAR(10) PRIMARY KEY,
    line_id         INT NOT NULL REFERENCES fact_sales (line_id),
    order_id        VARCHAR(12) NOT NULL,
    sku             VARCHAR(10) NOT NULL REFERENCES dim_product (sku),
    customer_id     VARCHAR(6) NOT NULL REFERENCES dim_customer (customer_id),
    rep_id          VARCHAR(5) NOT NULL REFERENCES dim_rep (rep_id),
    sale_date       DATE NOT NULL REFERENCES dim_date (date),
    return_date     DATE NOT NULL,
    reason          VARCHAR(20) NOT NULL,
    return_qty      INT NOT NULL,
    credit_amount   NUMERIC(12,2) NOT NULL,
    cost_amount     NUMERIC(12,2) NOT NULL,
    cost_recovered  NUMERIC(12,2) NOT NULL,
    write_off_cost  NUMERIC(12,2) NOT NULL,
    profit_impact   NUMERIC(12,2) NOT NULL
);

CREATE TABLE fact_orders (
    order_id        VARCHAR(12) PRIMARY KEY,
    customer_id     VARCHAR(6) NOT NULL REFERENCES dim_customer (customer_id),
    delivery_date   DATE NOT NULL,
    order_value     NUMERIC(12,2) NOT NULL,
    size_band       VARCHAR(10) NOT NULL,
    freight_cost    NUMERIC(10,2) NOT NULL
);

CREATE INDEX ix_sales_date     ON fact_sales (order_date);
CREATE INDEX ix_sales_customer ON fact_sales (customer_id);
CREATE INDEX ix_sales_sku      ON fact_sales (sku);
CREATE INDEX ix_returns_line   ON fact_returns (line_id);
