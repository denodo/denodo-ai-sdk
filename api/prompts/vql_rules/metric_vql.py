METRIC_VQL = """
Metric views are special views that come with pre-defined metrics and dimensions that are useful to abstract from the actual calculations.
A metric view will clearly indicate that its type is metric view and its fields are dimensions/metrics.
You must prioritize calculating metrics using metric views anytime the user's request relates to a metric pre-defined in a metric field, unless otherwise specified by the user.

<metric_view_rules>
The main difference between a normal view and a metric view is that you can calculate a metric by using the EVALUATE_METRIC function.
Here is a valid example of how to calculate the "productive hours" metric for active employees:

<vql>
SELECT
    "employee_status",
    evaluate_metric("productive_hours") AS "productive_hours"
FROM "organization"."employees"
WHERE "employee_status" = 'active'
GROUP BY "employee_status";
</vql>

When working with a metric view, take this into account:

- Only use EVALUATE_METRIC when you're certain you're working with a metric view.
- Project dimensions as regular fields and project metrics with EVALUATE_METRIC("metric_field"). e.g., SELECT "dimension_field", EVALUATE_METRIC("metric_field") FROM "metric_view"...
- Do not project a metric directly as a normal field.
- If the query projects dimensions together with metrics, you must GROUP BY every projected dimension.
- Do not include EVALUATE_METRIC(...) expressions in the GROUP BY clause.
- NEVER apply aggregation functions to dimension fields. Aggregations are strictly reserved for metric fields.
- You can apply filters on dimension fields in the WHERE clause when needed. You cannot apply filters on metric fields in the WHERE clause.
- You can apply filters on metric fields in the HAVING clause when needed, by including EVALUATE_METRIC("metric_field") in the HAVING clause. e.g., HAVING EVALUATE_METRIC("metric_field") > 100...
- Metric views cannot be JOINed with other views.
</metric_view_rules>
"""
