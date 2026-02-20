CAST_VQL = """
VQL supports the standard SQL CAST function and the following ones:

    - ARRAY_TO_STRING. Converts an array field to a string that contains the elements of the array separated by a character. Signatures:
        1. ARRAY_TO_STRING(<separator:text>, <array value:array>):text.
        2. ARRAY_TO_STRING(<separator:text>, <array begin delimiter:text>, <array end delimiter:text>, <register begin delimiter:text>,<register end delimiter:text>, <array value:array> ):text
    - CREATETYPEFROMXML(<new type name:text>, <xml value:{xml|text}>):text. Creates a register or an array type from XML data. If the type is created correctly, it returns the name of the new type.
        Example: SELECT CREATETYPEFROMXML('title_type',
                '<titles>
                    <title lang="en">XQuery Kick Start</title>
                    <title lang="en">Learning XML</title>
                </titles>') FROM Dual();
    - REGISTER(<field name:any type> [, <field name:any type> ]*):register. Creates a register with the values of the fields of a view.
        Example of a register: Register {1, A, Register {hello , how're you}}."""
