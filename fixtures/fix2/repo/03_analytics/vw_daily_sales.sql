CREATE OR REPLACE VIEW analytics.vw_daily_sales AS
SELECT
    orders.order_date,
    items.category_name,
    COUNT(DISTINCT orders.order_id) AS order_count,
    SUM(items.quantity) AS item_quantity,
    SUM(items.quantity * items.unit_price) AS gross_sales,
    SUM(items.net_amount) AS net_sales
FROM staging.orders AS orders
JOIN staging.order_items AS items
    ON orders.order_id = items.order_id
GROUP BY orders.order_date, items.category_name;
