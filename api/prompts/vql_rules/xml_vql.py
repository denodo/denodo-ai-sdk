XML_VQL = """
XML functions:

    - XMLQUERY(<XQuery expression:text> [, <is XQuery file:boolean>] [, <xml value:text>] [, <is XML file:boolean>]):xml. Extracts information from an XML document using the XQuery language.
    - XPATH(<xml value:xml>, <XPath expression:text> [, <xml header:boolean> ]):xml. Selects nodes from an XML document based on an XPath expression.
    - XSLT( <XML value:{xml|text}>, <xslValue:{xml|text}>, [, <is path to XML:boolean> ] [, <is path to XSLT:boolean> ]:xml. Returns the result of applying an XSL transformation to an XML."""
