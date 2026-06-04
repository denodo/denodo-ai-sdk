AGGREGATE_VQL = """
VQL supports the standard SQL aggregation functions. It also supports the following ones:

- FIRST(field). Returns the first value of a field of each group of values.
- LAST(field). Returns the last value of a field of each group of values.
- LIST(field). Returns an array with all the values of a specified field.
- MEDIAN(expression:[timetimestamp | timestamptz | numeric]). Returns the middle number of a field for each group of values.
- NEST(field1 [, fieldN]) or NEST(*). Returns an array with the values of the selected fields.
- STDEV(expression). Returns the sample standard deviation.
- STDEVP(expression). Returns the population standard deviation.
- VAR(expression). Returns the sample variance.
- VARP(expression). Returns the population variance.
- The GROUP_CONCAT function returns, for each group, a string with the concatenation of the values of the specified fields. Syntax:
    1. GROUP_CONCAT ([ DISTINCT | ALL ] <field name:identifier> [, <field name:identifier>]...) :text
    2. GROUP_CONCAT ([ <ignore null:boolean> , ] [ <row separator:text> [, <field separator:text> ]], <field name:identifier> [, <field name:identifier>]...) :text
"""
