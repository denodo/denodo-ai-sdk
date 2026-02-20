WINDOW_VQL = """
Apart from the ones from the SQL standard, VQL supports these window functions:

    - LISTAGG (<measure expression>, <delimiter expression:text>) WITHIN GROUP (<window order by clause>) OVER ([<window partition clause> ]):text. Orders data within each group specified in the clause ORDER BY and then, concatenates the values of the measure column. It separates each value with the "delimiter expression".
    - STDEV(<expression>) OVER ([<window partition clause>] [<window order by clause>]):number. Computes the statistical sample standard deviation of the current row with respect to the group within a window."""
