CAST_VQL = """
When working with converting data types, you can use the following VQL functions:
- CAST(<data type>, <value>). Converts a value to a different data type.

Example:

<vql>
SELECT CAST('decimal', "price") AS "price_decimal"
FROM "store"."products"
</vql>

The following table shows the possible type conversions. The column Output Type contains the possible values of the parameter VQL data type.

Type conversions permitted with the CAST function:

| Input Value Type (type of the parameter value) | Output Type (possible value of vdp data type depending on the type of the input value) |
| --- | --- |
| array | array |
| text, blob | blob |
| text, int, long, float, double, boolean | boolean |
| text, date (deprecated), localdate, timestamp, timestamptz, time, long | date (deprecated) |
| text, int, long, float, double | decimal |
| text, int, long, float, double | double |
| text, int, long, float, double | float |
| text, int, long, float, double, boolean | int |
| text, date (deprecated), localdate, timestamp, timestamptz, long | localdate |
| text, int, long, float, double | long |
| xml, register | register |
| array, blob, boolean, decimal, double, float, int, localdate, long, register, text, time, timestamp, timestamptz, xml, date (deprecated) | text |
| text, date (deprecated), timestamp, timestamptz, time, long | time |
| text, date (deprecated), localdate, timestamp, timestamptz, time, long | timestamp |
| text, date (deprecated), localdate, timestamp, timestamptz, time, long | timestamptz |
| text, blob, xml, register, array | xml |

Casting a boolean value to an integer returns 1 for true, 0 for false.

- ARRAY_TO_STRING. Converts an array field to a string that contains the elements of the array separated by a character. Signatures:
    1. ARRAY_TO_STRING(<separator:text>, <array value:array>):text.
    2. ARRAY_TO_STRING(<separator:text>, <array begin delimiter:text>, <array end delimiter:text>, <register begin delimiter:text>,<register end delimiter:text>, <array value:array> ):text
- CREATETYPEFROMXML(<new type name:text>, <xml value:{xml|text}>):text. Creates a register or an array type from XML data. If the type is created correctly, it returns the name of the new type.

Example:

<vql>
SELECT CREATETYPEFROMXML('title_type',
        '<titles>
            <title lang="en">XQuery Kick Start</title>
            <title lang="en">Learning XML</title>
        </titles>') FROM Dual();
</vql>

- REGISTER(<field name:any type> [, <field name:any type> ]*):register. Creates a register with the values of the fields of a view.

Example of a register: Register {1, A, Register {hello , how're you}}

- UNNEST is not a valid VQL function. Instead use FLATTEN.

- FLATTEN <view identifier> AS <alias:identifier> ( <alias> [. <register field> ]* . <array field> ). Projects the array elements as fields.

Example of a valid FLATTEN on a "iv_tmdb" view with a "genre_array" array field associated with the register of field names "genre".

<vql>
SELECT
    DISTINCT "genre"
FROM
    FLATTEN "tvshows"."iv_tmdb" AS "t" ("t"."genre_array");
</vql>

Example of a valid FLATTEN on multiple array fields:

<vql>
SELECT
    "genre",
    "production_company"
FROM
    FLATTEN "tvshows"."iv_tmdb" AS "t"
    ("t"."genre_array")
    ("t"."production_company_array");
</vql>

Important: The FLATTEN operator must be applied on an existing array field.
FLATTEN cannot be applied to an array that is built on the fly within the same query (for example, the result of a function like SPLIT that produces an array).
Instead, when the array does not exist as a field yet, first materialize it in a CTE (WITH clause) so that it becomes an array field in a view, and then apply FLATTEN to that CTE.

Valid VQL example where the array is built with a function and flattened through a CTE:

Suppose the view "sales"."products" has a field "tags" of type string that stores several tags separated by commas (for example 'sale,new,featured').
To get one row per tag, first build an array field from that string inside a CTE, and then FLATTEN that array field:

<vql>
WITH tags_array AS (
    SELECT SPLIT(',', tags) AS tag_list
    FROM "sales"."products"
)
SELECT string AS tag
FROM FLATTEN tags_array AS t (t.tag_list);
</vql>

In this example:
- "sales"."products" is the original view (database "sales", view "products") and "tags" is a string field holding comma-separated values.
- "tags_array" is the CTE, and "tag_list" is the array field created on the fly with SPLIT inside that CTE. The CTE is referenced by its name, without the database qualifier.
- FLATTEN is applied to the array field "tag_list" of the CTE "tags_array".
- "string" is the projected field for the simple array elements. This is the result of SPLIT which creates an array with associated register of field name "string".
"""
