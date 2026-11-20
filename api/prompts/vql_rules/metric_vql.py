METRIC_VQL = """
Metric views are a special type of view that comes with pre-defined metrics and dimensions that are useful to abstract from the actual calculations.
A metric view will clearly indicate that its type is metric view and its fields are dimensions/metrics.
You must prioritize calculating metrics using metric views anytime the user's request relates to a metric pre-defined in a metric field, unless the user specifies the usage of another view.

<metric_view_rules>
The main difference between a normal view and a metric view is that aggregations and metric calculations are pre-defined.
This means that you can only project dimensions and calculate metrics using the EVALUATE_METRIC function.
Here is a valid example of how to calculate the "productive hours" metric for active employees:

<vql>
SELECT
    "employee_status",
    EVALUATE_METRIC("productive_hours") AS "productive_hours"
FROM "organization"."employees"
WHERE "employee_status" = 'active'
GROUP BY "employee_status";
</vql>

Where:
- "organization"."employees" is a metric view.
- "employee_status" is a dimension field.
- "productive_hours" is a metric field.
- "active" is a filter on the "employee_status" dimension field.

To perform any other manipulation on top of an EVALUATE_METRIC expression, you must first project, like this:

<vql>
SELECT
    "department",
    ROUND("total_productive_hours" / 40.0, 1) AS "estimated_fte_weeks"
FROM (
    SELECT
        "department",
        EVALUATE_METRIC("productive_hours") AS "total_productive_hours"
    FROM "organization"."employees"
    WHERE "employee_status" = 'active'
    GROUP BY "department"
);
</vql>

When working with a metric view, always take this into account:

- Only use EVALUATE_METRIC when you're certain you're working with a metric field in a metric view.
- Project dimensions as regular fields and project metrics with EVALUATE_METRIC("metric_field"). e.g., SELECT "dimension_field", EVALUATE_METRIC("metric_field") FROM "metric_view"...
- Do not project a metric field directly as a normal field, only use EVALUATE_METRIC("metric_field").
- If the query projects dimensions together with metrics, you must GROUP BY every projected dimension.
- Do not include EVALUATE_METRIC(...) expressions in the GROUP BY clause.
- NEVER apply aggregation functions to dimension fields. Aggregations are strictly reserved for metric fields and they will be done via EVALUATE_METRIC(...).
- You can apply filters on dimension fields in the WHERE clause when needed. You cannot apply filters on metric fields in the WHERE clause.
- You can apply filters on metric fields in the HAVING clause when needed, by including EVALUATE_METRIC("metric_field") in the HAVING clause. e.g., HAVING EVALUATE_METRIC("metric_field") > 100...
- Metric views cannot be JOINed with other views.
</metric_view_rules>
"""
