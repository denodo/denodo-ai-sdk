LLM_VQL = """
VQL supports the following LLM-powered functions.
LLM-powered functions can be useful for summarization, translation and general prompting.

    - CLASSIFY_AI(<value:text>, <classification scale:array>): text. LLM-powered. Takes a given text and a classification scale as input, and returns an accurate classification based on the content of the text. Example:
            SELECT
                    address,
                    CLASSIFY_AI(
                        address,
                        {
                            row('Number of street between 1-500'),
                            row('Number of street between 501-999'),
                            row('Number of street over 999')
                        }
                    ) AS classification
        FROM organization.customer;
    - ENRICH_AI(<prompt:text>): text. LLM-powered. Queries the LLM with the provided prompt. For example,
    you can use this to extract information from a column, like this:

        SELECT
        address,
        ENRICH_AI(
            CONCAT(
                'I need you to extract only the street name from this address: "',
                address,
                '"\nLimit your response to just the street name and nothing else, like "Philips St"'
            )
        ) AS street
        FROM enterprise.customer;
    - ENRICH_AI_BINARY(<text prompt>, <binary blob>, <content type text>):text. LLM-powered. Queries the LLM with the provided prompt and an image or a PDF document.
    - EXTRACT_AI(<value:text>, <entityArray:array>):register. LLM-powered. Identifies and extracts the most relevant occurrence of specified entities from a given text. Given the input text and specified entities, the function uses AI to determine and return the most accurate and contextually appropriate matches.
    - SENTIMENT_AI(<value:text> [, <custom sentiments:array> ]):text. LLM-powered. Analyzes the sentiment of the provided text input by querying the AI to check if the sentiment is negative, neutral, mixed or positive.
    - SUMMARIZE_AI(<value:text> [, <word length:int>]):text. LLM-powered. Generates summaries with LLM.
    - TRANSLATE_AI(<value:text>, <target language:text> [, <origin language:text>]):text. LLM-powered. Performs language translation with an LLM.
    """
