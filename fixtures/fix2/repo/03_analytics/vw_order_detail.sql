CREATE OR REPLACE VIEW analytics.vw_order_detail AS
WITH line_totals AS (
    SELECT
        order_id,
        SUM(quantity) AS item_quantity,
        SUM(net_amount) AS net_sales
    FROM staging.order_items
    GROUP BY order_id
)
SELECT
    orders.order_id,
    orders.customer_id,
    customers.email,
    orders.order_date,
    orders.order_status,
    totals.item_quantity,
    totals.net_sales
FROM staging.orders AS orders
JOIN staging.customers AS customers
    ON orders.customer_id = customers.customer_id
JOIN line_totals AS totals
    ON orders.order_id = totals.order_id;
