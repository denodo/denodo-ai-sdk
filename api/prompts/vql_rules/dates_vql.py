DATES_VQL = """
VQL Date Functions

Convert Text to Date
- Function: TO_TIMESTAMPTZ(pattern, text). The pattern follows date and time Java patterns.
- Purpose: Convert TEXT to DATE for date comparisons in VQL.
- WARNING: TO_DATE is deprecated, use TO_TIMESTAMPTZ instead.

Date Filtering Examples

1. Date Column (TYPE: DATE)
   SELECT COUNT("p"."payment_id") AS "count_payments"
   FROM "bank"."payments" AS p
   WHERE "p"."payment_date" BETWEEN
         TO_TIMESTAMPTZ('yyyy-MM-dd', '2023-01-01') AND
         TO_TIMESTAMPTZ('yyyy-MM-dd', '2023-12-31');

2. Text Column (TYPE: TEXT)
   SELECT COUNT("p"."payment_id") AS "count_payments"
   FROM "bank"."payments" AS p
   WHERE TO_TIMESTAMPTZ('yyyy-MM-dd', "p"."payment_date") BETWEEN
         TO_TIMESTAMPTZ('yyyy-MM-dd', '2023-01-01') AND
         TO_TIMESTAMPTZ('yyyy-MM-dd', '2023-12-31');

3. Filter from Now to 3 Months Ago (TYPE: DATE)
   SELECT COUNT("p"."payment_id") AS "count_payments"
   FROM "bank"."payments" AS p
   WHERE "p"."payment_date" BETWEEN ADDMONTH(NOW(), -3) AND NOW();

Date Modification Functions
- Add/Subtract:
  - ADDDAY(date, days)
  - ADDHOUR(date, hours)
  - ADDMINUTE(date, minutes)
  - ADDSECOND(date, seconds)
  - ADDWEEK(date, weeks)
  - ADDYEAR(date, years)
  - ADDMONTH(date, months)

Extract Information from Timestamp
- Functions:
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
   SELECT GETMONTH(date) AS "month", SUM(revenue)
   FROM "organization"."sales_bv"
   GROUP BY "month";

2. Calculate Age in Years
   SELECT "student_id", "student_name",
          (GETYEAR(NOW()) - GETYEAR("student_birthday")) AS "age"
   FROM "school"."students";

Additional Notes
- Use NOW() to get the current timestamp.
"""
