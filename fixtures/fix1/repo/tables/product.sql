CREATE TABLE product (
    product_id INT PRIMARY KEY,
    category_id INT,
    FOREIGN KEY (category_id) REFERENCES category(category_id),
    name VARCHAR(100),
    description TEXT,
    price DECIMAL(10, 2),
    created_at DATETIME2 DEFAULT CURRENT_TIMESTAMP
    
);