CREATE VIEW vw_product_profitability AS
SELECT 
    p.product_id,
    o.order_date,
    SUM(li.quantity) AS quantity,
    SUM(li.quantity * li.price) AS revenue,
    SUM(li.quantity * p.price) AS cost,
    SUM(li.quantity * li.price) - (SUM(li.quantity) * p.price) AS profit
FROM product p
JOIN line_items li ON p.product_id = li.product_id
JOIN orders o ON li.order_id = o.order_id
GROUP BY p.product_id, o.order_date;