CREATE EXTERNAL SCHEMA spectrum
FROM DATA CATALOG
DATABASE 'commerce_lake'
IAM_ROLE default
REGION 'us-east-1'
CREATE EXTERNAL DATABASE IF NOT EXISTS;

CREATE EXTERNAL TABLE spectrum.web_events (
    event_id VARCHAR(64),
    session_id VARCHAR(64),
    customer_id BIGINT,
    event_type VARCHAR(40),
    event_time TIMESTAMP,
    properties VARCHAR(65535)
)
PARTITIONED BY (event_date DATE)
STORED AS PARQUET
LOCATION 's3://example-lineage-fixture/commerce/events/';
