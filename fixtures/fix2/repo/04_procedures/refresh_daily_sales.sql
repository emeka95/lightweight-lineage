CREATE OR REPLACE PROCEDURE ops.refresh_daily_sales()
LANGUAGE plpgsql
AS $$
BEGIN
    DELETE FROM analytics.daily_sales;

    INSERT INTO analytics.daily_sales (
        order_date,
        category_name,
        order_count,
        item_quantity,
        gross_sales,
        net_sales,
        refreshed_at
    )
    SELECT
        order_date,
        category_name,
        order_count,
        item_quantity,
        gross_sales,
        net_sales,
        GETDATE()
    FROM analytics.vw_daily_sales;
END;
$$;
