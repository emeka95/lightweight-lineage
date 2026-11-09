CREATE TABLE staging.web_events
DISTSTYLE KEY
DISTKEY (customer_id)
SORTKEY (event_date, customer_id)
AS
SELECT
    event_id,
    session_id,
    customer_id,
    event_type,
    event_time,
    event_date,
    JSON_EXTRACT_PATH_TEXT(properties, 'page', 'path', TRUE) AS page_path,
    JSON_EXTRACT_PATH_TEXT(properties, 'device', 'type', TRUE) AS device_type
FROM spectrum.web_events
WHERE event_date >= DATEADD(day, -90, CURRENT_DATE);
