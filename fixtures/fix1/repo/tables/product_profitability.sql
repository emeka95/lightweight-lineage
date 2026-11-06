CREATE TABLE product_profitability (
    product_id INT PRIMARY KEY,
    order_date DATE,
    quantity INT,
    revenue DECIMAL(10, 2),
    cost DECIMAL(10, 2),
    profit DECIMAL(10, 2),
    created_at DATETIME2 DEFAULT CURRENT_TIMESTAMP
);