CREATE TABLE staging.order_items
DISTSTYLE KEY
DISTKEY (order_id)
SORTKEY (order_id, product_id)
AS
SELECT
    item.order_id,
    item.line_number,
    item.product_id,
    product.category_name,
    item.quantity,
    item.unit_price,
    item.discount_amount,
    item.quantity * item.unit_price - COALESCE(item.discount_amount, 0) AS net_amount,
    product.list_price AS current_list_price
FROM ingest.order_items AS item
LEFT JOIN ingest.products AS product
    ON item.product_id = product.product_id
WHERE item.quantity > 0;
