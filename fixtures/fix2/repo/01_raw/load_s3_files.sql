COPY ingest.customers
FROM 's3://example-lineage-fixture/commerce/customers/'
IAM_ROLE default
FORMAT AS PARQUET;

COPY ingest.orders
FROM 's3://example-lineage-fixture/commerce/orders/'
IAM_ROLE default
FORMAT AS PARQUET;

COPY ingest.order_items
FROM 's3://example-lineage-fixture/commerce/order_items/'
IAM_ROLE default
FORMAT AS PARQUET;

COPY ingest.products
FROM 's3://example-lineage-fixture/commerce/products/'
IAM_ROLE default
FORMAT AS PARQUET;
