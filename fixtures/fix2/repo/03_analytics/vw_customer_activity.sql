CREATE OR REPLACE VIEW analytics.vw_customer_activity AS
WITH event_counts AS (
    SELECT
        customer_id,
        COUNT(*) AS event_count,
        COUNT(DISTINCT session_id) AS session_count,
        MAX(event_time) AS last_seen_at
    FROM staging.web_events
    WHERE customer_id IS NOT NULL
    GROUP BY customer_id
)
SELECT
    lifetime.customer_id,
    lifetime.first_order_date,
    lifetime.last_order_date,
    lifetime.order_count,
    lifetime.lifetime_value,
    COALESCE(events.event_count, 0) AS event_count,
    COALESCE(events.session_count, 0) AS session_count,
    events.last_seen_at
FROM analytics.customer_lifetime AS lifetime
LEFT JOIN event_counts AS events
    ON lifetime.customer_id = events.customer_id;
