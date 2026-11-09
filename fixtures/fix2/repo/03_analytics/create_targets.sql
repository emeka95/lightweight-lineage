CREATE TABLE analytics.daily_sales (
    order_date DATE,
    category_name VARCHAR(128),
    order_count BIGINT,
    item_quantity BIGINT,
    gross_sales DECIMAL(18, 2),
    net_sales DECIMAL(18, 2),
    refreshed_at TIMESTAMP DEFAULT GETDATE()
)
DISTSTYLE KEY
DISTKEY (order_date)
SORTKEY (order_date, category_name);

CREATE TABLE analytics.customer_lifetime (
    customer_id BIGINT,
    first_order_date DATE,
    last_order_date DATE,
    order_count BIGINT,
    lifetime_value DECIMAL(18, 2),
    last_refreshed_at TIMESTAMP
)
DISTSTYLE KEY
DISTKEY (customer_id)
SORTKEY (customer_id);
