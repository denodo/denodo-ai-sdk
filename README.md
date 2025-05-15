![Denodo Logo](api/static/denodo-logo.png)

# Denodo AI SDK

The complete user manual for the Denodo AI SDK is available [in the Denodo Connects documentation section](https://community.denodo.com/docs/html/browse/9.0/en/denodoconnects/index).

The Denodo AI SDK includes all the necessary components required to deploy a query RAG AI agent.

## AI SDK Benchmarks

We test our query-to-SQL pipeline on our propietary benchmark across the whole range of LLMs that we support.
The benchmark dataset consists of 20+ questions in the finance sector.
You may use this benchmark as reference to choose an LLM model.

<em>Latest update: 05/31/2025 on AI SDK version 0.7</em>

| LLM Provider| Model                     | 🎯 Accuracy             | 🕒 LLM execution time (s) | 🔢 Input Tokens   | 🔡 Output Tokens | 💰 Cost per Query |
|-------------|---------------------------|-------------------------|---------------------------|------------------|------------------|-------------------|
| OpenAI      | GPT-4o                    | 🟢                      | 3.20                      | 4,230            | 398              | $0.015            |
| OpenAI      | GPT-4o Mini               | 🟡                      | 4.30                      | 4,607            | 445              | $0.001            |
| OpenAI      | o1                        | 🟢                      | 18.60                     | 5,110            | 5,438            | $0.403            |
| OpenAI      | o1-high                   | 🟢                      | 28.21                     | 3,755            | 6,220            | $0.429            |
| OpenAI      | o1-low                    | 🟢                      | 15.75                     | 3,746            | 2,512            | $0.207            |
| OpenAI      | o3-mini                   | 🟢                      | 16.61                     | 3,756            | 2,750            | $0.016            |
| OpenAI      | o3-mini-high              | 🟢                      | 28.68                     | 3,764            | 8,237            | $0.040            |
| OpenAI      | o3-mini-low               | 🟢                      | 8.66                      | 3,811            | 1,080            | $0.009            |
| OpenRouter  | Amazon Nova Lite          | 🟡                      | 1.34                      | 4,572            | 431              | <$0.001           |
| OpenRouter  | Amazon Nova Micro         | 🔴                      | 1.29                      | 5,788            | 668              | <$0.001           |
| OpenRouter  | Amazon Nova Pro           | 🟢                      | 2.53                      | 4,522            | 424              | $0.005            |
| OpenRouter  | Claude 3.5 Haiku          | 🟢                      | 4.38                      | 4,946            | 495              | $0.006            |
| OpenRouter  | Claude 3.5 Sonnet         | 🟢                      | 5.02                      | 4,569            | 435              | $0.020            |
| OpenRouter  | Claude 3.7 Sonnet         | 🟢                      | 5.46                      | 4,695            | 465              | $0.021            |
| OpenRouter  | Deepseek R1 671b          | 🟢                      | 40.28                     | 4,138            | 3,041            | $0.011            |
| OpenRouter  | Deepseek v3 671b          | 🟢                      | 13.50                     | 4,042            | 424              | $0.005            |
| OpenRouter  | Deepseek v3.1 671b        | 🟡                      | 12.46                     | 4,910            | 435              | $0.006            |
| OpenRouter  | Llama 3.1 8b              | 🔴                      | 2.98                      | 6,024            | 752              | <$0.001           |
| OpenRouter  | Llama 3.1 Nemotron 70b    | 🟡                      | 9.76                      | 5,110            | 892              | $0.001            |
| OpenRouter  | Llama 3.3 70b             | 🟡                      | 10.46                     | 4,681            | 402              | $0.001            |
| OpenRouter  | Microsoft Phi-4 14b       | 🟢                      | 6.75                      | 4,348            | 728              | <$0.001           |
| OpenRouter  | Mistral Small 24b         | 🟢                      | 5.52                      | 5,537            | 563              | <$0.001           |
| OpenRouter  | Qwen 2.5 72b              | 🟢                      | 6.30                      | 4,874            | 463              | $0.004            |
| Google      | Gemini 1.5 Flash          | 🟡                      | 2.18                      | 4,230            | 398              | <$0.001           |
| Google      | Gemini 1.5 Pro            | 🟢                      | 5.44                      | 4,230            | 398              | $0.007            |
| Google      | Gemini 2.0 Flash          | 🟢                      | 2.42                      | 4,230            | 398              | $0.001            |

Please note that "Input Tokens" and "Output Tokens" is the average input/output tokens per query.
Also, each color corresponds to the following range in terms of accuracy:
- 🟢 = 90%+
- 🟡 = 80–90%
- 🔴 = <80%

Finally, any model with its size in the name, i.e.: Llama 3.1 **8b**, represents an **open-source model**.

## List of supported LLM providers

The Denodo AI SDK supports the following LLM providers:

* OpenAI
* AzureOpenAI
* Bedrock
* Google
* GoogleAIStudio
* Anthropic
* NVIDIA
* Groq
* Ollama
* Mistral
* SambaNova
* OpenRouter

Where Bedrock refers to AWS Bedrock, NVIDIA refers to NVIDIA NIM and Google refers to Google Vertex AI.

## List of supported embedding providers + recommended

* OpenAI (text-embedding-3-large)
* AzureOpenAI (text-embedding-3-large)
* Bedrock (amazon.titan-embed-text-v2:0)
* Google (text-multilingual-embedding-002)
* Ollama (bge-m3)
* Mistral (mistral-embed)
* NVIDIA (baai/bge-m3)
* GoogleAIStudio (gemini-embedding-exp-03-07)

Where Bedrock refers to AWS Bedrock, NVIDIA refers to NVIDIA NIM and Google refers to Google Vertex AI.

# Licensing
Please see the file called LICENSE.