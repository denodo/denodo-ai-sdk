AGGREGATE_VQL = """
VQL supports the standard SQL aggregation functions. It also supports the following ones:

    - FIRST(field). Returns the first value of a field of each group of values.
    - LAST(field). Returns the last value of a field of each group of values.
    - LIST(field). Returns an array with all the values of a specified field.
    - MEDIAN(expression:[timetimestamp | timestamptz | numeric]). Returns the middle number of a field for each group of values.
    - NEST(field1 [, fieldN]) or NEST(*). Returns an array with the values of the selected fields.
    - STDEV(expression). Returns the sample standard deviation.
    - STDEVP(expression) Returns the population standard deviation.
    - VAR(expression) Returns the sample variance.
    - VARP(expression) Returns the population variance.
    - The GROUP_CONCAT function returns, for each group, a string with the concatenation of the values of the specified fields. Syntax:
        1. GROUP_CONCAT ([ DISTINCT | ALL ] <field name:identifier> [, <field name:identifier>]...) :text
        2. GROUP_CONCAT ([ <ignore null:boolean> , ] [ <row separator:text> [, <field separator:text> ]], <field name:identifier> [, <field name:identifier>]...) :text
    - UNNEST is not a valid VQL function. Instead use a statement with the VQL FLATTEN operator which projects the array elements as fields.
    The result of the VQL FLATTEN operator is a view with the elements of the array projected as fields.
    Simple datatypes in the array use the name of the datatype itself like string, date or integer as the projected fieldname.

    Valid VQL FLATTEN operator example: FLATTEN "tablename" as "t" ("t"."arrayfield")
    (Important: The projected field from the array can not have an alias with the AS operator! This results in an invalid VQL statement).

    Valid VQL example where genre_array is an array with data of type string):
    SELECT
        DISTINCT string AS genre
    FROM
        FLATTEN tvshows.iv_tmdb AS t (t.genre_array);

    Invalid VQL FLATTEN:
    SELECT
        DISTINCT genre
    FROM
        FLATTEN tvshows.iv_tmdb AS t (t.genre_array) AS genre;"""
