CREATE TABLE staging.customers
DISTSTYLE ALL
SORTKEY (customer_id)
AS
WITH ranked_customers AS (
    SELECT
        customer_id,
        LOWER(TRIM(email)) AS email,
        INITCAP(TRIM(first_name)) AS first_name,
        INITCAP(TRIM(last_name)) AS last_name,
        created_at,
        updated_at,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY updated_at DESC, ingested_at DESC
        ) AS row_num
    FROM ingest.customers
    WHERE customer_id IS NOT NULL
)
SELECT
    customer_id,
    email,
    first_name,
    last_name,
    created_at,
    updated_at
FROM ranked_customers
WHERE row_num = 1;
