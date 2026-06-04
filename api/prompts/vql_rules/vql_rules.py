VQL_RULES = """
1. View names must use the format "<database_name>"."<view_name>". For instance,
if the database is 'organization' and the view is 'employees', reference it as: "organization"."employees".

2. Column names and column aliases must be wrapped in double quotes.

Wrong (unquoted view name without database):

<vql>
SELECT * FROM employees;
</vql>

Correct (quoted database and view, quoted columns and aliases):

<vql>
SELECT
    "c"."CustomerID" AS "Customer",
    "o"."OrderID"
FROM
    "お客様"."Clients" "c"
JOIN
    "お客様"."Orders" "o"
ON
    "c"."CustomerID" = "o"."CustomerID";
</vql>

In the schema, views may appear under this quoting style. Generating SELECT * FROM employees without quotes will fail.

3. VQL supports the following simple data types:

- blob
- boolean
- date
- decimal
- double
- float
- int
- intervaldaysecond
- intervalyearmonth
- localdate
- long
- text
- time
- timestamp
- timestamptz
- vector<double, <integer> >.  A sequence of double numbers with a specified integer length.
- vector<float, <integer> >
- vector<int, <integer> >
- vector<long, <integer> >
- xml

And the following compound data types:

- register. A register of simple data types.
- array. An array-type element must be viewed as a subview. An array will always have a register type associated.
Each subelement contained in the array will belong to this register data type.

Compound data types can be defined with an alias in the schema, in which case [STRUCT] (register) or [ARRAY] (array) will be used as the data type.

For example, a view with the following schema:

# Table: "organization"."projects"
## Columns:
- project_id (int)
- project_name (text)
- project_workers ([STRUCT] project_workers_register)
- project_related_projects ([ARRAY] project_related_projects_array)

Where project_workers_register is a register with the following fields:
- worker_id (int)
- worker_full_name (text)

And project_related_projects_array is an array associated with the project_related_ids register with the following fields:
- project_id_value (int)

Example of accessing register values to retrieve the project ID, the worker ID and the worker full name:

<vql>
SELECT
    "project_id",
    "project_workers"."worker_id",
    "project_workers"."worker_full_name"
FROM "organization"."projects"
</vql>

Example of accessing array values to retrieve the first related project ID of a project:

<vql>
SELECT
    "project_id",
    "project_related_projects"[0]."project_id_value" AS "first_related_project_id"
FROM "organization"."projects"
</vql>

You can use CAST with the supported VQL data types.Example of casting a text column to a decimal so it can be compared against an number:

<vql>
SELECT "product_id", "price"
FROM "store"."products"
WHERE CAST('decimal', "price") > 100;
</vql>

Only use CAST if necessary, as columns typically have the desired data type.

4. VQL strings use single quotes: WHERE name = 'Joseph'. Single quotes can be escaped in VQL strings by doubling them: 'D''angelo' matches D'angelo.

5. VQL string functions:

- SUBSTR(text, start index, length?). Index starts at 1. The length sets the number of characters to return and includes the index character. If length is omitted, the substring returns everything until the end of the string.
  Example: SUBSTR('Artificial', 2, 5) → 'rtifi'
  Example: SUBSTR('Artificial', 2) → 'rtificial'

- CONCAT(str1, str2, ..., strN). Joins strings together. Requires 2+ parameters.
  Example: CONCAT(GETYEAR(date), '-', GETMONTH(date), '-', GETDAY(date))

- LEN(text). Returns string length.

- POSITION(needle IN haystack). Finds starting position of a substring.
  Example: POSITION('no' IN 'Denodo') returns 3

6. Subqueries (a CTE is also considered a subquery) are not allowed in HAVING clauses in VQL. Only simple conditions or aggregate functions comparing results to static values or other aggregates are permitted.

Valid example of a HAVING clause in VQL:

<vql>
SELECT "department", AVG("salary") AS "avg_salary"
FROM "organization"."employees"
GROUP BY "department"
HAVING AVG("salary") > 30000;
</vql>

Example of invalid HAVING clause (uses subquery SELECT department...):

<vql>
SELECT "department", AVG(salary) AS "avg_salary"
FROM "organization"."employees"
GROUP BY "department"
HAVING "department" IN (SELECT "department" FROM "organization"."managers" WHERE "status" = 'senior');
</vql>

Example of invalid HAVING clause because it uses a CTE:

<vql>
WITH salary_threshold AS (
    SELECT 30000 AS threshold
)
SELECT "department", AVG(salary) AS "avg_salary"
FROM "organization"."employees", salary_threshold
GROUP BY "department"
HAVING AVG(salary) > threshold;
</vql>

7. The OFFSET, FETCH and LIMIT clauses limit the number of rows obtained when executing a query.

Use OFFSET <number> ROWS to skip the first n rows of the result set.

Use LIMIT [ <count> ] or FETCH FIRST [ <count> ] ROWS ONLY to obtain only <count> rows of the result set.

However, LIMIT and FETCH can only be used in the outer query and inside a subquery that appears in a CTE body, FROM clause, or WHERE clause. LIMIT and FETCH cannot be used inside a SELECT clause subquery (for example a scalar subquery in the select list).

This query works, because LIMIT is in the outer query:

<vql>
SELECT *
FROM "bank"."customers"
LIMIT 3;
</vql>

This also works, because FETCH is in the outer query:

<vql>
SELECT *
FROM "bank"."customers"
OFFSET 10 ROWS
FETCH NEXT 10 ROWS ONLY;
</vql>

This query fails, because it uses LIMIT in a SELECT subquery:

<vql>
SELECT
    "c"."customer_id",
    (
        SELECT "customer_id"
        FROM "bank"."loans"
        GROUP BY "customer_id"
        ORDER BY SUM("loan_amount") DESC
        LIMIT 1
    ) AS "top_loan_customer"
FROM "bank"."customers" c;
</vql>

Some versions of Denodo do not accept LIMIT or FETCH in any subquery. If your VQL fails for that reason, rewrite to an equivalent query without LIMIT or FETCH in any subquery by using ROW_NUMBER() and filtering on the row number in an outer query.

8. In VQL, NULLS LAST is invalid in ORDER BY.

9. In VQL, you cannot use aggregate functions directly in the ORDER BY clause if they are not projected in the SELECT list or projected but inside another function. To avoid this:

- Create the alias name for the projected field
- Use alias name in the ORDER BY clause.

Valid example of using an aggregate function in an ORDER BY clause:

<vql>
SELECT "user", ROUND(SUM("amount") / 100000000, 2) AS "total_amount"
FROM "bank"."customer"
GROUP BY "user"
ORDER BY "total_amount";
</vql>

Invalid example of using an aggregate function in an ORDER BY clause:

<vql>
SELECT "user", ROUND(SUM("amount") / 100000000, 2) AS "total_amount"
FROM "bank"."customer"
GROUP BY "user"
ORDER BY SUM("amount");
</vql>

11. Views with obligatory columns (marked with [OBLIGATORY] in the schema) are views that can only be queried by providing concrete values for those obligatory columns using the WHERE clause with either the '=' operator (for a single value) or the 'IN' operator (for multiple values). This restriction applies even when targeting other columns.

IMPORTANT: Using generic conditions like 'IS NOT NULL', value ranges like 'BETWEEN', '>', '<', or omitting the field entirely is strictly invalid. This applies even when working with different columns. This restriction cannot be bypassed.

For instance, assuming the view "organization"."employees" has an obligatory field named "department":

Valid example of filtering by the obligatory field with a single concrete value:

<vql>
SELECT "employee_id", "first_name", "last_name"
FROM "organization"."employees"
WHERE "department" = 'Engineering';
</vql>

Valid example of filtering by the obligatory field with multiple concrete values using IN:

<vql>
SELECT "employee_id", "first_name", "last_name"
FROM "organization"."employees"
WHERE "department" IN ('Engineering', 'Sales', 'HR');
</vql>

Example of invalid query because it omits the obligatory field from the WHERE clause:

<vql>
SELECT "employee_id", "first_name", "last_name"
FROM "organization"."employees";
</vql>

Example of invalid query because it uses IS NOT NULL instead of concrete values for the obligatory field:

<vql>
SELECT "employee_id", "first_name", "last_name"
FROM "organization"."employees"
WHERE "department" IS NOT NULL;
</vql>

Example of invalid query because it uses a range (BETWEEN) instead of discrete concrete values:

<vql>
SELECT "employee_id", "first_name", "last_name"
FROM "organization"."employees"
WHERE "department" BETWEEN 'Engineering' AND 'Sales';
</vql>

{EXTRA_RESTRICTIONS}
"""
