DATES_VQL = """
Convert Text to Date

- Function: TO_TIMESTAMPTZ(pattern, text). The pattern follows date and time Java patterns.
- Purpose: Convert TEXT to DATE for date comparisons in VQL.
- WARNING: TO_DATE is deprecated, use TO_TIMESTAMPTZ instead.

For an entire calendar day, month, or year, use an inclusive lower bound and an exclusive upper bound: field >= start AND field < start_of_next_period.

Date Filtering Examples

1. Date Column (TYPE: DATE)

<vql>
SELECT COUNT("p"."payment_id") AS "count_payments"
FROM "bank"."payments" AS "p"
WHERE "p"."payment_date" >=
      TO_TIMESTAMPTZ('yyyy-MM-dd', '2023-01-01')
  AND "p"."payment_date" <
      TO_TIMESTAMPTZ('yyyy-MM-dd', '2024-01-01');
</vql>

2. Text Column (TYPE: TEXT)

<vql>
SELECT COUNT("p"."payment_id") AS "count_payments"
FROM "bank"."payments" AS "p"
WHERE TO_TIMESTAMPTZ('yyyy-MM-dd', "p"."payment_date") >=
      TO_TIMESTAMPTZ('yyyy-MM-dd', '2023-01-01')
  AND TO_TIMESTAMPTZ('yyyy-MM-dd', "p"."payment_date") <
      TO_TIMESTAMPTZ('yyyy-MM-dd', '2024-01-01');
</vql>

3. Filter from Now to 3 Months Ago (TYPE: DATE)

<vql>
SELECT COUNT("p"."payment_id") AS "count_payments"
FROM "bank"."payments" AS "p"
WHERE "p"."payment_date" BETWEEN ADDMONTH(NOW(), -3) AND NOW();
</vql>

Date Modification Functions

Add/Subtract:

- ADDDAY(date, days)
- ADDHOUR(date, hours)
- ADDMINUTE(date, minutes)
- ADDSECOND(date, seconds)
- ADDWEEK(date, weeks)
- ADDMONTH(date, months)
- ADDYEAR(date, years)

Extract Information from Timestamp

Functions:

- GETDAY(date)
- GETDAYOFWEEK(date)
- GETDAYOFYEAR(date)
- GETDAYSBETWEEN(date1, date2)
- GETHOUR(date)
- GETMILLISECOND(date)
- GETMINUTE(date)
- GETMONTH(date)
- GETMONTHSBETWEEN(date1, date2)
- GETQUARTER(date)
- GETSECOND(date)
- GETWEEK(date)
- GETYEAR(date)

Examples of Extracting Information

1. Get Month and Sum Revenue

<vql>
SELECT GETMONTH("date") AS "month", SUM("revenue") AS "total_revenue"
FROM "organization"."sales_bv"
GROUP BY "month";
</vql>

2. Calculate Age in Years

Calculate completed years of age. For February 29 birthdays, use February 28 in non-leap years.

<vql>
SELECT "student_id", "student_name",
       (GETYEAR(NOW()) - GETYEAR("student_birthday"))
       - CASE
           WHEN GETMONTH("student_birthday") = 2
                AND GETDAY("student_birthday") = 29
                AND GETMONTH(NOW()) = 2
                AND GETDAY(NOW()) = 28
                AND GETMONTH(ADDDAY(NOW(), 1)) = 3
           THEN 0
           WHEN GETMONTH(NOW()) * 100 + GETDAY(NOW())
                < GETMONTH("student_birthday") * 100 + GETDAY("student_birthday")
           THEN 1
           ELSE 0
         END AS "age"
FROM "school"."students";
</vql>

Additional Notes

- Use NOW() to get the current timestamp.
"""
