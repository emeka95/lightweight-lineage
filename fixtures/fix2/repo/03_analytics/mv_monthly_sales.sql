CREATE MATERIALIZED VIEW analytics.mv_monthly_sales
AUTO REFRESH YES
AS
SELECT
    DATE_TRUNC('month', order_date)::DATE AS sales_month,
    category_name,
    SUM(order_count) AS order_count,
    SUM(item_quantity) AS item_quantity,
    SUM(gross_sales) AS gross_sales,
    SUM(net_sales) AS net_sales
FROM analytics.daily_sales
GROUP BY DATE_TRUNC('month', order_date)::DATE, category_name;
