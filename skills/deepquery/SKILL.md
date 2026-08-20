---
name: deepquery
description: How and when to use the deep_query tool for complex, multi-step analytical reports. Read this before proposing or running any DeepQuery analysis.
---

# DeepQuery

The DeepQuery agent is designed for complex analytical questions that require multi-step reasoning and data analysis. You can only execute the DeepQuery agent via the deep_query tool if explicitly requested by the user.
If the user does not mention DeepQuery in his request, you must proceed with other tools.

The agent does not have access to your conversation with the user, so you must pay attention to the feedback given by the user and include it in the analysis request. For example, if the user mentions 'use this view in your analysis' or 'be careful with metric/calculation', you must pass it along in the analysis request.

## Example analysis requests

- Identify the top-performing product in terms of both revenue and customer satisfaction. Consider total revenue, total quantity sold, and average customer rating over the past 12 months. Break down the product's monthly performance to detect any seasonality or sales spikes. Also analyze what types of customers are purchasing it most often (e.g., age, region). Compare its performance with other products in the same category. Summarize key themes from customer reviews to explain why this product might be performing well.

- Analyze the best-performing course on the platform in the last 6 months. Use metrics: number of enrollments, average completion rate, student ratings, and re-enrollment rates (students who took multiple courses from the same instructor). Identify monthly trends in engagement and completion. Break down performance by course category and difficulty level, and show which student segments (e.g., age groups, countries) are most engaged with this course. Compare it to other top-3 courses in the same category and suggest factors driving its success based on reviews and completion behavior.

## The 3-step process

Coming up with a detailed analysis request must always follow the following 3-step process:

1. The first time the user requests a DeepQuery report, you must first call metadata_search as many times as needed to understand the schema you're working with.
2. Then, you must come up with a suggested 3-5 line advanced analysis plan based on the output of metadata_search and ask the user for modification/confirmation before calling the deep_query tool.
3. Once a 3-5 line final advanced analysis request is confirmed, you will go ahead and pass it to the deep_query tool.

NOTE: Calling metadata_search to understand the user's data is COMPULSORY before proposing an analysis request to the user.
NOTE: Receiving explicit confirmation from the user regarding the final analysis request that will be sent is COMPULSORY.
NOTE: DeepQuery is able to perform deep, thorough analysis. Analysis requests must aim to maximize this capability.
