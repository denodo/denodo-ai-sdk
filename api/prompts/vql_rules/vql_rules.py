VQL_RULES = """
1. Table names must use the format "<database_name>"."<table_name>". In the schema, they appear this way. For instance,
if the database is 'organization' and the table is 'employees', reference it as: "organization"."employees".
Column names must also be wrapped in double quotes. Generating SELECT * FROM employees will fail.
Generating SELECT "CustomerID" FROM "お客様"."Clients", will.

In the case of a JOIN operation, you must also include the table alias (if it exists) wrapped in quotes, like so:

<vql>
    SELECT
        "c"."CustomerID",
        "o"."OrderID",
    FROM
        "お客様"."Clients" c
    JOIN
        "お客様"."Orders" o
    ON
        "c"."CustomerID" = "o"."CustomerID";
</vql>

2. CAST is supported in VQL with these types:

BOOL, CHAR, DECIMAL, FLOAT, FLOAT4, FLOAT8, INT2, INT4, INT8, INTEGER, REAL, TEXT, and VARCHAR.

Valid example using INT2:

SELECT CAST("quantity" AS INT2) FROM "organization"."hardware_bv"

Only use CAST if necessary, as columns typically have the desired data type.

3. In VQL, use double quotes, not single quotes, for column aliases. For example:

    SELECT SUM(revenue) AS "Total Revenue"
    FROM "organization"."products"

Additionally, VQL protected words cannot be used as aliases.
The protected words in VQL are BASE, DF, NOS, OBL, and WS. Using one will cause an error, e.g., SELECT * FROM "example_db"."example_table" AS WS.

4. VQL String Literals and Functions.

- Use single quotes: WHERE name = 'Joseph'
- Escape single quotes by doubling them: 'D''angelo' matches "D'angelo"

- SUBSTR(string, start index, length?). Index starts at 1. The length sets the number of characters to return and includes the index character. If length is omitted, the substring returns everything until the end of the string.
   Example: SUBSTR('Artificial', 2, 5) → 'rtifi'
   Example: SUBSTR('Artificial', 2) → 'rtificial'

- CONCAT(str1, str2, ..., strN). Joins strings together. Requires 2+ parameters.
    Example: CONCAT(GETYEAR(date), '-', GETMONTH(date), '-', GETDAY(date))

- LEN(string). Returns string length

- POSITION(needle IN haystack). Finds starting position of a substring.
    Example: POSITION('no' IN 'Denodo') returns 3

5. In VQL, LIMIT and FETCH can only be used in the main query and not in subqueries. CTE is also considered a subquery.

Example of valid LIMIT in main query:

    SELECT *
    FROM "bank"."customers"
    LIMIT 3;

Example of invalid LIMIT in subquery:

    WHERE "c"."customer_id" = (
        SELECT "customer_id"
        FROM "bank"."loans"
        GROUP BY "customer_id"
        ORDER BY SUM(loan_amount) DESC
        LIMIT 1
    );

Example of invalid LIMIT in CTE:

    WITH "TotalEQ" AS (
        SELECT "customer_id"
        FROM "bank"."loans"
        GROUP BY "customer_id"
        ORDER BY SUM(loan_amount) DESC
        LIMIT 1
    );

6. HAVING clauses are valid in VQL, but subqueries are not allowed in a HAVING clause. A CTE is also considered a subquery.

Valid example of a HAVING clause in VQL:

    SELECT "department", AVG(salary) AS "avg_salary"
    FROM "organization"."employees"
    GROUP BY "department"
    HAVING AVG(salary) > 30000;

Example of invalid HAVING clause (uses subquery SELECT department...):

    SELECT "department", AVG(salary) AS "avg_salary"
    FROM "organization"."employees"
    GROUP BY "department"
    HAVING "department" IN (SELECT "department" FROM "organization"."managers" WHERE "status" = 'senior');

Example of invalid HAVING clause (uses a CTE):

    WITH salary_threshold AS (
        SELECT 30000 AS threshold
    )
    SELECT "department", AVG(salary) AS "avg_salary"
    FROM "organization"."employees", salary_threshold
    GROUP BY "department"
    HAVING AVG(salary) > threshold;

7. In VQL, NULLS LAST is invalid in ORDER BY.

8. In VQL, you cannot use aggregate functions directly in the ORDER BY clause if they are not projected in the SELECT list or projected but inside another function. To avoid this:

- Create the alias name for the projected field
- Use alias name in the ORDER BY clause.

Valid example of using an aggregate function in an ORDER BY clause:

    SELECT "user", ROUND(SUM("amount") / 100000000, 2) AS "total_amount"
    FROM "bank"."customer"
    GROUP BY "user"
    ORDER BY "total_amount"

Invalid example of using an aggregate function in an ORDER BY clause:

    SELECT "user", ROUND(SUM("amount") / 100000000, 2) AS "total_amount"
    FROM "bank"."customer"
    GROUP BY "user"
    ORDER BY SUM("amount")

{EXTRA_RESTRICTIONS}
"""
