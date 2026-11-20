TEXT_VQL = """
The VQL text functions are:

- ASCII( <value:text> ):int. Returns the Unicode code point of the first character of the input value.
- BASE64_TO_BASE10( <value:text> ):text. Converts a string from base64 to base10.
- BASE64_TO_HEX( <value:text> ):text. Converts a string from base64 to hexadecimal (hex) or base16.
- CHAR( <code:int> ):text. Returns the character associated with a Unicode code point. When the code point is higher than 255 and the function is pushed down to Impala or Hive, it returns NULL.
- CONCAT( <value_1:text>, <value_2:text> [, <value_N:text> ]* ):text. Concatenates two or more text values.
- CONCATLIST( [ <separator:text> ,] <value:array> ):text. Returns one value with all the values of an array. Each value is separated by a character. If not present, the separator is a space character.
- DELETESPACES( <value:text> ):text. Removes all the spaces from a string.
- ENDWITH( <value:text>, <suffix:text> ):boolean. Returns true if the second string is a suffix of the first. The comparison is case-sensitive.
- HEX_TO_BASE64( <value:text> ):text. Converts a string from hexadecimal (hex) or base16 to base64.
- INITCAP( <str:text> ):text. Capitalizes the first letter of each word and converts all other letters to lowercase. Words are separated by spaces or punctuation. Returns NULL if str is NULL.
- INSTR( <str1:text>, <str2:text> ):int. Returns the index of the first occurrence of str2 within str1. The index of the first character is 0. Returns -1 if str2 is not present. Returns NULL if str1 is NULL. Case-sensitive when executed by Virtual DataPort. Pushdown to a database may be case-insensitive.
- LEFT( <value:text>, <count:int> ):text. Extracts a specified number of characters from the left-hand side of a text string. The number of characters must be positive. Spaces count as characters.
- LEFTPAD( <source_string:text>, <length:int> [, <pad_string:text>] ):text. Returns a copy of a string left-padded to length. If pad_string is not present, the pad is a blank space. If source_string is longer than length, it trims the string. Alias: LPAD.
- LEN( <value:text> ):int. Returns the number of characters in a text string. Spaces count as characters.
- LOWER( <value:text> ):text. Converts text to lowercase.
- LTRIM( <value:text> ):text. Returns the input value without its leading whitespace and carriage returns.
- MAX( <value_1:text>, <value_2:text> [, <value_N:text> ]* ):text. Returns the lexicographically greatest argument. The comparison is case sensitive.
- MIN( <value_1:text>, <value_2:text> [, <value_N:text> ]* ):text. Returns the lexicographically lowest argument. The comparison is case sensitive.
- POSITION( <value_1:text> IN <value_2:text> ):int. Returns the first position at which value_1 occurs within value_2. Returns NULL if either value is NULL. Returns 1 if value_1 is empty. Returns 0 if value_1 does not occur in value_2.
- PRINTF( [ <locale:text>, ] <value_2:text>, <value_3:double> ):text. Formats a double with a Java format expression. locale is optional and selects locale-specific number formatting.
- PROPERCASE( <value:text> ):text. Returns the first letter capitalized and the rest in lowercase.
- REGEXP( <original_text:text>, <regex:text>, <replacement:text> ):text. Replaces each substring that matches regex with replacement. regex and replacement are regular expressions. Returns NULL if any parameter is NULL.
- REGEXP_COUNT( <original_text:text>, <regex:text> ):int. Returns the number of times a regular expression occurs in a string. Matching is case-sensitive by default. Returns NULL if any parameter is NULL.
- REGEXP_SUBSTR extracts a substring from a source string using a regular expression. position is 1-based and defaults to 1. occurrence defaults to 1. parameter flags are i (case-insensitive), c (case-sensitive, the default), m (multi-line), s (dot matches newlines), and e (extract a capturing group). group_num 0 returns the whole match. The e flag with no group_num returns group 1. A group_num greater than 0 extracts that group even without e. Returns NULL if source or pattern is NULL, pattern is empty, position or occurrence is zero or negative, the occurrence is not found, or group_num is invalid. Syntax:
    1. REGEXP_SUBSTR( <source:text>, <pattern:text> ):text
    2. REGEXP_SUBSTR( <source:text>, <pattern:text>, <position:int> ):text
    3. REGEXP_SUBSTR( <source:text>, <pattern:text>, <position:int>, <occurrence:int> ):text
    4. REGEXP_SUBSTR( <source:text>, <pattern:text>, <position:int>, <occurrence:int>, <parameters:text> ):text
    5. REGEXP_SUBSTR( <source:text>, <pattern:text>, <position:int>, <occurrence:int>, <parameters:text>, <group_num:int> ):text
- RIGHT( <value:text>, <count:int> ):text. Extracts a specified number of characters from the right-hand side of a text string. The number of characters must be positive. Spaces count as characters.
- REMOVEACCENTS( <value:text> ):text. Replaces accented characters with the same characters without an accent.
- REPEAT( <value:text>, <count:int> ):text. Repeats text count times. If count is 0 or less, it returns an empty string.
- REPLACE( <value:text>, <from:text>, <to:text> ):text. Replaces all occurrences of from with to. Returns NULL if value is NULL or from is an empty string. If from or to is NULL, it returns value.
- REPLACEMAP replaces each key in a text with its value. Syntax:
    1. REPLACEMAP( <search_text:text>, <map_name:text> ):text. Returns NULL if the map does not exist.
    2. REPLACEMAP( <search_text:text>, <database_name.view_name:text>, <key_field:text>, <value_field:text> ):text. Returns NULL if the view or the fields do not exist.
- RIGHTPAD( <source_string:text>, <length:int> [, <pad_string:text>] ):text. Returns a copy of a string right-padded to length. If pad_string is not present, the pad is a blank space. If source_string is longer than length, it trims the string. Alias: RPAD.
- RTRIM( <value:text> ):text. Returns the input value without its trailing white spaces and carriage returns.
- SIMILARITY( <value_1:text>, <value_2:text> [ , <algorithm:text> ] ):double. Calculates the textual similarity between two strings. If algorithm is not present, it uses JaroWinklerTFIDF. Other algorithms: ScaledLevenshtein, JaroWinkler, Jaro, Level2 Jaro, MongeElkan, Level2MongeElkan, TFIDF, Jaccard, UnsmoothedJS.
- SPLIT( <regexp:text>, <value:text> ):array. Splits value around matches of regexp and returns an array of the substrings. The matches are not included in the result.
- STARTWITH( <value:text>, <prefix:text> ):boolean. Returns true if the second string is a prefix of the first. The comparison is case-sensitive.
- SUBSTRING and SUBSTR return a substring of an input string. Syntax 1 and Syntax 2 are not equivalent. Avoid a negative start_index, because pushdown to some sources wraps around the end of the string. Syntax:
    1. SUBSTRING( <value:text>, <start_index:int> [, <end_index:int> ] ):text. The first character is index 0. If end_index is absent, the result goes from start_index to the end of the input value. If end_index is present, the result extends to end_index - 1. Returns an empty string if the indexes are equal or start_index is past the end. Returns NULL if any parameter is NULL or start_index is greater than end_index.
    2. SUBSTRING( <value:text> FROM <start_index:int> [ FOR <length:int> ] ):text, SUBSTR( <value:text> FROM <start_index:int> [ FOR <length:int> ] ):text, and SUBSTR( <value:text>, <start_index:int> [, <length:int> ] ):text behave the same. The first character is index 1. If length is absent, the substring extends to the end. Returns NULL if any parameter is NULL.
- TEXT_TO_HEX( <value:text> ):text. Converts text to hexadecimal (hex) or base16.
- TRIM returns the input string without its leading and/or trailing pad characters. Syntax:
    1. TRIM( <value:text> ):text. Removes spaces and carriage returns.
    2. TRIM( [ <trim_specification> [ <trim_character:text> ] FROM ] <value:text> ):text. trim_specification is LEADING, TRAILING, or BOTH. Omitting it is equivalent to BOTH. By default this form removes spaces but not carriage returns. If trim_character has more than one character, only the first is used. Returns NULL if value is NULL.
- UPPER( <value:text> ):text. Converts text to uppercase.
"""
