CREATE PROCEDURE process_sales
AS
BEGIN
    SET NOCOUNT ON;

    INSERT INTO product_profitability (
        product_id,
        order_date,
        quantity,
        revenue,
        cost
    )
    SELECT
        product_id,
        order_date,
        quantity,
        revenue,
        cost
    FROM vw_product_profitability;

    INSERT INTO category_profitability (
        category_id,
        order_date,
        quantity,
        revenue,
        cost
    )
    SELECT
        category_id,
        order_date,
        quantity,
        revenue,
        cost
    FROM vw_category_profitability;
END;