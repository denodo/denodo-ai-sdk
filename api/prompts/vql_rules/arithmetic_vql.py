ARITHMETIC_VQL = """
Arithmetic in VQL:

- Use MULT(x, y) for multiplication.
- Use DIV(dividend, divisor) for division.
- Use STDEV() to calculate the standard deviation over a set.

Types matter in VQL. Operations between INTEGERs yield INTEGER results, losing decimals. CAST to FLOAT to preserve decimals, especially for percentages.

Example:

<vql>
SELECT DIV(4, 100)
</vql>

returns 0.

Use:

<vql>
SELECT DIV(CAST(4 AS FLOAT), CAST(100 AS FLOAT))
</vql>

to get 0.04.

In VQL, you must avoid division by zero by adding explicit conditions to check for values different from 0.

Invalid examples of dividing by zero:

Example 1: Simple division

<vql>
SELECT "sales"."revenue" / "sales"."units_sold" AS "price_per_unit"
FROM "company"."sales"
</vql>

Example 2: Percentage calculation

<vql>
SELECT "students"."passed_exams" / "students"."total_exams" * 100 AS "pass_rate"
FROM "school"."students"
</vql>

Example 3: Using CASE but missing zero check

CASE
WHEN "orders"."total_items" IS NOT NULL THEN "orders"."total_cost" / "orders"."total_items"
ELSE NULL
END

All above examples will throw an error if the divisor (units_sold, total_exams, total_items) is zero.

Valid examples with proper zero checks:

Example 1: Simple division with zero check

<vql>
SELECT
    CASE
    WHEN "sales"."units_sold" != 0 THEN "sales"."revenue" / "sales"."units_sold"
    ELSE NULL
    END AS "price_per_unit"
FROM "company"."sales"
</vql>

Example 2: Percentage calculation with zero check

<vql>
SELECT
    CASE
    WHEN "students"."total_exams" != 0 THEN "students"."passed_exams" / "students"."total_exams" * 100
    ELSE NULL
    END AS "pass_rate"
FROM "school"."students"
</vql>

Example 3: Complete CASE with both NULL and zero checks

CASE
WHEN "orders"."total_items" IS NOT NULL AND "orders"."total_items" != 0 THEN "orders"."total_cost" / "orders"."total_items"
ELSE NULL
END
"""
