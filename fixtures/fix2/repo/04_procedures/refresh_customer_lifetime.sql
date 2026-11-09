CREATE OR REPLACE PROCEDURE ops.refresh_customer_lifetime()
LANGUAGE plpgsql
AS $$
BEGIN
    MERGE INTO analytics.customer_lifetime
    USING (
        SELECT
            customer_id,
            MIN(order_date) AS first_order_date,
            MAX(order_date) AS last_order_date,
            COUNT(DISTINCT order_id) AS order_count,
            SUM(net_sales) AS lifetime_value,
            GETDATE() AS last_refreshed_at
        FROM analytics.vw_order_detail
        GROUP BY customer_id
    ) AS current_sales
    ON analytics.customer_lifetime.customer_id = current_sales.customer_id
    WHEN MATCHED THEN UPDATE SET
        first_order_date = current_sales.first_order_date,
        last_order_date = current_sales.last_order_date,
        order_count = current_sales.order_count,
        lifetime_value = current_sales.lifetime_value,
        last_refreshed_at = current_sales.last_refreshed_at
    WHEN NOT MATCHED THEN INSERT (
        customer_id,
        first_order_date,
        last_order_date,
        order_count,
        lifetime_value,
        last_refreshed_at
    ) VALUES (
        current_sales.customer_id,
        current_sales.first_order_date,
        current_sales.last_order_date,
        current_sales.order_count,
        current_sales.lifetime_value,
        current_sales.last_refreshed_at
    );
END;
$$;
