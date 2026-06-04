METRIC_VQL = """
Metric views are special views that come with pre-defined metrics and dimensions that are useful to abstract from the actual calculations.
A metric view will clearly indicate its type is metric and its fields are dimensions/metrics.
Only use EVALUATE_METRIC when you're certain you're working with a metric view.

You must prioritize calculating metrics using metric views anytime the user request relates to a metric pre-defined in a metric field, unless otherwise specified by the user.

- Project dimensions as regular columns.
- Project metrics with EVALUATE_METRIC("metric_field"). Do not reference a metric directly as a normal column in the SELECT list.
- You must always use GROUP BY with at least one dimension. NEVER generate a query against a metric view without it.
- If the query projects dimensions together with metrics, GROUP BY every projected dimension.
- Do not include EVALUATE_METRIC(...) expressions in the GROUP BY clause.
- NEVER apply aggregation functions to dimension fields; aggregations are strictly reserved for metric fields.
- Apply filters on dimensions in the WHERE clause when needed.
- Apply filters on metrics in the HAVING clause when needed by including EVALUATE_METRIC("metric_field") in the HAVING clause.

Valid example to calculate the "productive hours" metric for active employees:

<vql>
SELECT
    "employee_status",
    evaluate_metric("productive_hours") AS "productive_hours"
FROM "organization"."employees"
WHERE "employee_status" = 'active'
GROUP BY "employee_status";
</vql>
"""
