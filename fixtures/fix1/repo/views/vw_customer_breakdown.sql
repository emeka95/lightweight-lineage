CREATE VIEW vw_customer_breakdown AS
SELECT 
    c.customer_id,
    a.address AS customer_address,
    SUM(li.quantity) AS quantity_ordered,
    SUM(li.quantity * li.price) AS revenue_generated,
    SUM(li.quantity * li.price) - (SUM(li.quantity) * p.price) AS profit
FROM customers c
JOIN orders o ON c.customer_id = o.customer_id
JOIN address a ON c.address_id = a.address_id
JOIN line_items li ON o.order_id = li.order_id
JOIN product p ON li.product_id = p.product_id
GROUP BY c.customer_id, a.address;