CREATE TABLE ingest.products (
    product_id BIGINT NOT NULL,
    product_name VARCHAR(256),
    category_name VARCHAR(128),
    list_price DECIMAL(12, 2),
    is_active BOOLEAN,
    updated_at TIMESTAMP
)
DISTSTYLE ALL
SORTKEY (product_id);
