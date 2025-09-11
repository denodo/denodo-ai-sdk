ANALYSIS_TRACE_TEMPLATE = """
This was the original analysis plan:

<analysis_plan>
{plan}
</analysis_plan>

{cohorts}

These were the tools called, in the order they were called:
<tool_calls>
{tool_calls}
</tool_calls>

This was the final conclusion of the analysis:
<conclusion>
{answer}
</conclusion>
"""