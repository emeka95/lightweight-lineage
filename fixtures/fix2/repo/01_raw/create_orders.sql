CREATE TABLE ingest.orders (
    order_id BIGINT NOT NULL,
    customer_id BIGINT,
    order_status VARCHAR(24),
    ordered_at TIMESTAMP,
    source_updated_at TIMESTAMP,
    ingested_at TIMESTAMP DEFAULT GETDATE()
)
DISTSTYLE KEY
DISTKEY (customer_id)
COMPOUND SORTKEY (ordered_at, order_id);
