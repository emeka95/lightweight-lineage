CREATE TABLE staging.orders
DISTSTYLE KEY
DISTKEY (customer_id)
COMPOUND SORTKEY (order_date, order_id)
AS
SELECT
    order_id,
    customer_id,
    order_status,
    CAST(ordered_at AS DATE) AS order_date,
    ordered_at
FROM ingest.orders
WHERE order_id IS NOT NULL
  AND order_status <> 'TEST'
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY order_id
    ORDER BY source_updated_at DESC, ingested_at DESC
) = 1;
