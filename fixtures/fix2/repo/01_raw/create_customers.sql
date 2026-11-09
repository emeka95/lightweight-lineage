CREATE TABLE ingest.customers (
    customer_id BIGINT NOT NULL,
    email VARCHAR(256),
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    ingested_at TIMESTAMP DEFAULT GETDATE()
)
DISTSTYLE ALL
SORTKEY (customer_id);
