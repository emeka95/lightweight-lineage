CREATE TABLE ingest.order_items (
    order_id BIGINT NOT NULL,
    line_number SMALLINT NOT NULL,
    product_id BIGINT,
    quantity INTEGER,
    unit_price DECIMAL(12, 2),
    discount_amount DECIMAL(12, 2),
    ingested_at TIMESTAMP DEFAULT GETDATE()
)
DISTSTYLE KEY
DISTKEY (order_id)
SORTKEY (order_id, line_number);
