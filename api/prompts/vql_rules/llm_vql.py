LLM_VQL = """
VQL supports the following LLM-powered functions.
LLM-powered functions can be useful for summarization, translation and general prompting.

- SENTIMENT_AI(<value:text> [, <sentiment scale:array> ]):text. LLM-powered. Analyzes the sentiment of the provided text input by querying the AI to check if the sentiment is negative, neutral, mixed or positive.
You can also supply a custom sentiments scale by passing a custom array of sentiments to the function. Example:

<vql>
SELECT
    "review",
    SENTIMENT_AI(
        "review",
        {
            row('very negative'),
            row('negative'),
            row('neutral'),
            row('positive'),
            row('very positive')
        }
    ) AS "sentiment"
FROM "organization"."customer";
</vql>

- CLASSIFY_AI(<value:text>, <classification scale:array>):text. LLM-powered. Takes a given text and a classification scale as input, and returns an accurate classification based on the content of the text. Example:

<vql>
SELECT
    "address",
        CLASSIFY_AI(
            "address",
            {
                row('Number of street between 1-500'),
                row('Number of street between 501-999'),
                row('Number of street over 999')
            }
        ) AS "classification"
FROM "organization"."customer";
</vql>

Both scale arrays in SENTIMENT_AI and CLASSIFY_AI also accept description and example values for each row. Example for SENTIMENT_AI:

<vql>
SELECT
    "review",
    SENTIMENT_AI(
        "review",
        {
            row('1', 'The customer used very negative words to describe the product', 'Example: "This product is TERRIBLE"'),
            row('2', 'The customer used negative words to describe the product', 'Example: "This product is not good"'),
            row('3', 'The customer used neutral words to describe the product', 'Example: "This product is okay"'),
            row('4', 'The customer used positive words to describe the product', 'Example: "This product is good"'),
            row('5', 'The customer used very positive words to describe the product', 'Example: "This product is GREAT"')
        }
    ) AS "sentiment"
FROM "organization"."customer";
</vql>

In this example, SENTIMENT_AI will return, for each "review" value, one of the following values: 1, 2, 3, 4 or 5 based on the given description and examples.

- ENRICH_AI(<prompt:text>):text. LLM-powered. Queries the LLM with the provided prompt. For example, you can use this to extract information from a column, like this:

<vql>
SELECT
    "address",
    ENRICH_AI(
        CONCAT(
            'I need you to extract only the street name from this address: "',
            "address",
            '"\nLimit your response to just the street name and nothing else, like "Philips St".'
        )
    ) AS "street"
FROM "organization"."customer";
</vql>

- ENRICH_AI_BINARY(<text prompt>, <binary blob>, <content type text>):text. LLM-powered. Queries the LLM with the provided prompt and an image or a PDF document.
- EXTRACT_AI(<value:text>, <entityArray:array>):register. LLM-powered. Identifies and extracts the most relevant occurrence of specified entities from a given text. Given the input text and specified entities, the function uses AI to determine and return the most accurate and contextually appropriate matches.
- SUMMARIZE_AI(<value:text> [, <word length:int>]):text. LLM-powered. Generates summaries with LLM.
- TRANSLATE_AI(<value:text>, <target language:text> [, <origin language:text>]):text. LLM-powered. Performs language translation with an LLM.
"""
