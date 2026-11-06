CREATE TABLE category (
    category_id INT PRIMARY KEY,
    name VARCHAR(100),
    description TEXT,
    created_at DATETIME2 DEFAULT CURRENT_TIMESTAMP
);