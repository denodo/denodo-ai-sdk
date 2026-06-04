JSON_VQL = """
JSON functions:

- AVRO_TO_JSON(<AVRO document:blob>, <JSON schema:text>):text. Returns a JSON document from an AVRO document and a JSON schema.
- JSON_TO_AVRO(<JSON document:text>, <JSON schema:text>):blob. Returns an AVRO document from a JSON document and a schema.
- COMPLEX_TYPE_TO_JSON(<array value:array>, <JSON document:text>):text. Converts a register or an array to a text value with a JSON document.
- JSON_TO_COMPLEX_TYPE(<JSON document:text>, <JSON schema:text>):text. Converts a JSON expression to a register complex type.
- JSONPATH(<JSON document:text>, <JSONPath expression:text> [, jsonOutput:boolean]):text. Returns the nodes from a JSON document selected by a JSONPath expression.
"""
