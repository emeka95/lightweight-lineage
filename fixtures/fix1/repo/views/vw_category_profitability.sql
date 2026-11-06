CREATE VIEW vw_category_profitability AS
SELECT 
    c.category_id,
    o.order_date,
    SUM(li.quantity) AS quantity,
    SUM(li.quantity * li.price) AS revenue,
    SUM(li.quantity * p.price) AS cost,
    SUM(li.quantity * li.price) - (SUM(li.quantity) * p.price) AS profit
FROM category c
JOIN product p ON c.category_id = p.category_id
JOIN line_items li ON p.product_id = li.product_id
JOIN orders o ON li.order_id = o.order_id
GROUP BY c.category_id, o.order_date;