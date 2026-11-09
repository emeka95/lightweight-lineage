UNLOAD ('
    SELECT
        sales_month,
        category_name,
        order_count,
        item_quantity,
        gross_sales,
        net_sales
    FROM analytics.mv_monthly_sales
')
TO 's3://example-lineage-fixture/exports/monthly_sales/'
IAM_ROLE default
FORMAT AS PARQUET
PARTITION BY (sales_month)
ALLOWOVERWRITE
PARALLEL OFF;
