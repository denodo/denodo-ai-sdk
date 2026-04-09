![Denodo Logo](api/static/denodo_logo.png)

# Denodo AI SDK

The Denodo AI SDK is an open-source component designed to streamline the integration of the Denodo Platform with Large Language Models (LLMs). It provides developers with the essential tools to build high-performance AI agents that can interact natively with enterprise data through a governed data virtualization layer.

By automating the complexities of Retrieval-Augmented Generation (RAG) and VQL query generation, the SDK ensures AI responses are grounded in real-time, factual enterprise context.

## Key features

- **Text-to-VQL**: Automatically translates natural language questions into Denodo Virtual Query Language (VQL), allowing AI agents to query the Denodo Platform directly without manual SQL/VQL coding.
- **Metadata Search (RAG)**: Uses vectorization to index and search through your technical and business metadata. This enables agents to find the right data assets instantly using semantic search.
- **DeepQuery Agent**: A sophisticated research agent that orchestrates complex tasks. It crafts a multi-step execution plan and carries it out by combining metadata discovery with live VQL data extraction.
- **Model & Vector Store Agnostic**: Provides a flexible architecture to configure and switch between various LLMs and Vector Databases depending on your performance and privacy requirements.

To showcase the AI SDK’s capabilities, a sample chatbot application is included.

The complete user manual for the Denodo AI SDK is available [here](https://community.denodo.com/docs/html/document/denodoconnects/latest/en/Denodo%20AI%20SDK%20-%20User%20Manual).

### Installation

To get started with the AI SDK:

1. Clone this repository and `cd` into it
2. Create a new virtual environment (`python -m venv venv`) in the root of the AI SDK's path
3. Activate the virtual environment (`source venv/bin/activate` for Linux/MacOS or `.\venv\Scripts\activate` for Windows)
4. Install the requirements.txt (`python -m pip install -r requirements.txt`)
5. Rename the configuration templates for both AI SDK (`api/utils/sdk_config.env.example` => `api/utils/sdk_config.env`) and the sample chatbot (`sample_chatbot/chatbot_config.env.example` => `sample_chatbot/chatbot_config.env`)
5. Review the configuration files for both the AI SDK and the sample chatbot and configure your own LLM/embeddings providers

### Specialized chatbots

The sample chatbot includes a sidebar for specialized chatbots. These chatbots behave like custom agents focused on a specific use case, with their own databases, tags, LLM settings, feature flags, and behavioral constraints.

Specialized chatbots are detected automatically from YAML files placed in `api/agents/custom`. Each chatbot can also define its own icon by adding an image file to `api/agents/custom/icons`.

To create a specialized chatbot:

1. Create a new YAML file in `api/agents/custom`.
2. Add the chatbot icon file to `api/agents/custom/icons`.
3. Start or restart the sample chatbot application.

The sample chatbot will discover the new configuration and add the chatbot to the sidebar automatically.

For example, you can create `api/agents/custom/samples_bank.yaml` with:

```yaml
name: "Banking agent"
id: "banking-agent"
description: "Retail banking analytics assistant."
icon_file_name: "bank_agent.png"

settings:
  databases:
    - "samples_bank"

  llm_provider: "OpenAI"
  llm_model: "gpt-4.1-mini"
  unstructured_mode: false
  feedback_enabled: false
  reporting_enabled: false
  deepquery_enabled: false
  user_edit_llm: false
```

And place the corresponding icon at `api/agents/custom/icons/bank_agent.png`.

This example creates a specialized chatbot with:

- Access limited to the `samples_bank` database
- LLM model fixed to `gpt-4.1-mini`
- Unstructured CSV mode disabled
- Feedback disabled
- Reporting disabled
- DeepQuery disabled
- End users unable to edit the selected LLM

This makes it easy to create focused chatbot experiences for specific teams or workflows while keeping the general chatbot available in parallel.

## DeepQuery

### Requirements to use Denodo DeepQuery

- A thinking model from either OpenAI/AWS Bedrock/Google Vertex (Not Ollama).
- An minimum allowance of minimum 50RPM OpenAI/AWS Bedrock/Google Vertex.
- Powerful thinking model with over 128k context length.

### Configuration

Depending on your LLM provider, here's a guide on how to configure Denodo DeepQuery:

#### OpenAI (recommended model: gpt-5.2-high)
```
THINKING_PROVIDER=openai
THINKING_MODEL=gpt-5.2-high
```

#### AWS Bedrock (recommended model: claude-4-sonnet)
```
THINKING_PROVIDER = bedrock
THINKING_MODEL = us.anthropic.claude-sonnet-4-20250514-v1:0

AWS_CLAUDE_THINKING = 1
AWS_CLAUDE_THINKING_TOKENS = 2048
```
Please note that AWS Bedrock requires the previously mentioned extra env variables in sdk_config.env to activate thinking.

#### Google Vertex (recommended model: gemini-3-pro)
```
THINKING_PROVIDER = google
THINKING_MODEL = gemini-3-pro

GOOGLE_THINKING = 1
GOOGLE_THINKING_TOKENS = 2048
```
Please note that Google requires the previously mentioned extra env variables in sdk_config.env to activate thinking.

## AI SDK Benchmarks

We test our query-to-SQL pipeline on our propietary benchmark across the whole range of LLMs that we support.
The benchmark dataset consists of 20+ questions in the finance sector.
You may use this benchmark as reference to choose an LLM model.

<em>Latest update: 03/31/2025 on AI SDK version 0.7</em>

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