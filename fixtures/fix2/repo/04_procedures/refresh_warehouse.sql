CREATE OR REPLACE PROCEDURE ops.refresh_warehouse()
LANGUAGE plpgsql
AS $$
BEGIN
    CALL ops.refresh_daily_sales();
    CALL ops.refresh_customer_lifetime();
    REFRESH MATERIALIZED VIEW analytics.mv_monthly_sales;
END;
$$;
