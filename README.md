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

### Requirements

The AI SDK requires:

- Python 3.11/3.12/3.13
- A Denodo 9.0.5 or higher (either Express or Enterprise Plus license is required) instance, with cache enabled.
- An LLM provider
- An embeddings model provider

### Installation

To get started with the AI SDK:

1. Clone this repository and `cd` into it
2. Create a new virtual environment (`python -m venv venv`) in the root of the AI SDK's path
3. Activate the virtual environment (`source venv/bin/activate` for Linux/MacOS or `.\venv\Scripts\activate` for Windows)
4. Install the requirements.txt (`python -m pip install -r requirements.txt`)
5. Rename the configuration templates for both AI SDK (`api/utils/sdk_config.env.example` => `api/utils/sdk_config.env`) and the sample chatbot (`sample_chatbot/utils/chatbot_config.env.example` => `sample_chatbot/utils/chatbot_config.env`)
6. Review the configuration files for both the AI SDK and the sample chatbot and configure your own LLM/embeddings providers

## Metadata column selection

`GET /getMetadata` accepts optional `use_columns` and `ignore_columns` query
parameters. Each is a JSON string containing rules with a `columns` list and an
optional unquoted `database.view` name:

```json
[{"columns": ["id", "name"]}, {"view": "hr.employees", "columns": ["department_id"]}]
```

Use `use_columns` to keep only matching columns and `ignore_columns` to exclude
columns. Global and matching view rules are combined; exclusions take precedence.
Column names match case-insensitively and literally, without wildcards. View names
match exactly. Views without a matching inclusion rule remain unrestricted.
Omitting either parameter, or passing an empty string or `[]`, adds no rules.
Invalid rules return HTTP 422 before synchronization begins.

The SDK filters returned metadata and sample values before normalization and
vectorization. Associations that reference removed columns are omitted. If a
composite primary key loses a member, its remaining columns are no longer marked
as a primary key. These options do not change Denodo permissions or prevent Data
Marketplace from retrieving the original samples.

After changing rules, run a full synchronization (`incremental=false`) for all
affected databases/tags so previously indexed columns and samples are replaced.
Use the same rules for overlapping synchronization sources. Returned views with no
remaining sample rows have their old indexed samples removed. When column rules
are supplied, sample cleanup also runs with `examples_per_table=0`.

## Benchmarks

We test our text-to-VQL pipeline on our propietary benchmark across the whole range of LLMs that we support.
The benchmark dataset consists of 50+ questions in the finance sector.
You may use this benchmark as reference to choose an LLM model.

<em>Latest update: 05/18/2026 on AI SDK version 1.2</em>

| LLM Provider | Model | 🎯 Accuracy | 🔢 Input Tokens | 🔡 Output Tokens | 📊 Total Tokens | 💰 Cost per Query |
|--------------|-------|-------------|----------------|-----------------|-----------------|-------------------|
| OpenAI       | gpt-5.5                       | 🟢           |          7,092 |             396 |           7,488 |            $0.047 |
| OpenAI       | gpt-5.5-pro                   | 🟢           |          4,335 |           2,330 |           6,665 |            $0.549 |
| OpenAI       | gpt-5.4                       | 🟢           |          7,825 |             433 |           8,258 |            $0.026 |
| OpenAI       | gpt-5.4-pro                   | 🟢           |          3,967 |           1,643 |           5,610 |            $0.415 |
| OpenAI       | gpt-5.4-nano                  | 🟡           |          8,632 |             509 |           9,141 |            $0.002 |
| OpenAI       | gpt-5.4-mini                  | 🟢           |          6,942 |             394 |           7,336 |            $0.007 |
| OpenAI       | gpt-oss-120b                  | 🟡           |          6,636 |             947 |           7,583 |            $0.001 |
| OpenAI       | gpt-oss-20b                   | 🟢           |          7,098 |           2,172 |           9,270 |            $0.001 |
| OpenAI       | gpt-5.3-codex                 | 🟡           |          7,601 |             446 |           8,047 |            $0.020 |
| Google       | gemini-3.1-pro-preview        | 🟢           |          7,825 |           3,726 |          11,551 |            $0.060 |
| Google       | gemini-3-flash-preview        | 🟢           |          9,397 |             456 |           9,853 |            $0.006 |
| Google       | gemini-3.1-flash-lite-preview | 🟢           |          8,430 |             442 |           8,872 |            $0.003 |
| Google       | gemma-4-31b-it                | 🟢           |          8,527 |             442 |           8,969 |            $0.001 |
| Google       | gemma-4-26b-a4b-it            | 🟡           |          9,103 |             423 |           9,526 |            $0.001 |
| Anthropic    | claude-opus-4.7               | 🟢           |         12,994 |             501 |          13,495 |            $0.077 |
| Anthropic    | claude-sonnet-4.6             | 🟢           |          8,770 |             424 |           9,194 |            $0.033 |
| Anthropic    | claude-haiku-4.5              | 🟢           |          8,856 |             469 |           9,325 |            $0.011 |
| DeepSeek     | deepseek-v4-pro               | 🟡           |          8,856 |             481 |           9,337 |            $0.004 |
| DeepSeek     | deepseek-v4-flash             | 🟡           |          8,492 |             402 |           8,894 |            $0.001 |
| MoonshotAI   | kimi-k2.6                     | 🟡           |          8,068 |             691 |           8,759 |            $0.008 |
| Qwen         | qwen3.6-plus                  | 🟡           |          7,795 |             406 |           8,201 |            $0.003 |
| Qwen         | qwen3.6-27b                   | 🟡           |          8,215 |             587 |           8,802 |            $0.005 |
| Qwen         | qwen3.6-35b-a3b               | 🟢           |          8,356 |             763 |           9,119 |            $0.002 |
| Qwen         | qwen3.6-max-preview           | 🟡           |          8,247 |             476 |           8,723 |            $0.012 |
| Qwen         | qwen3.6-flash                 | 🟡           |          8,238 |             774 |           9,012 |            $0.002 |
| xAI          | grok-4.3                      | 🔴           |          8,358 |             345 |           8,703 |            $0.011 |
| MiniMax      | minimax-m2.7                  | 🟡           |          6,915 |           3,080 |           9,995 |            $0.006 |
| MistralAI    | mistral-small-2603            | 🟡           |          8,637 |             457 |           9,094 |            $0.002 |
| MistralAI    | ministral-14b-2512            | 🟡           |          9,251 |             677 |           9,928 |            $0.002 |
| MistralAI    | mistral-medium-3-5            | 🟡           |          8,889 |             427 |           9,316 |            $0.017 |
| MistralAI    | devstral-2512                 | 🟡           |          8,992 |             424 |           9,416 |            $0.004 |
| Meta         | llama-4-maverick              | 🟡           |          7,620 |             489 |           8,109 |            $0.001 |
| Meta         | llama-4-scout                 | 🟡           |          9,469 |             718 |          10,187 |            $0.001 |
| Z-AI         | glm-5.1                       | 🟡           |          8,724 |             442 |           9,166 |            $0.001 |
| Z-AI         | glm-5-turbo                   | 🟡           |          8,063 |             360 |           8,423 |            $0.011 |

Important things to note:

- "Input Tokens", "Output Tokens", and "Total Tokens" are the average per query.
- Any model with its size in the name, i.e.: gpt-oss-**20b**, represents an **open-source model**.
- Each color corresponds to the following range in terms of accuracy:
  - 🟢 = 90%+
  - 🟡 = 80%–89%
  - 🔴 = <80%

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
* Ollama (qwen3-embedding:8b)
* Mistral (mistral-embed)
* NVIDIA (baai/bge-m3)
* GoogleAIStudio (gemini-embedding-exp-03-07)

Where Bedrock refers to AWS Bedrock, NVIDIA refers to NVIDIA NIM and Google refers to Google Vertex AI.

## Running as a Windows Service

The Denodo AI SDK provides built-in support to run as a native Windows Service. This allows the API and sample chatbot to run continuously in the background, start automatically on system boot, and operate unattended without requiring an active user desktop session.

All service-related files and scripts are located in the `bin/windows/` folder.

### Prerequisites

Ensure you have completed all steps in the [Installation](#installation) section beforehand.

### Configuration (`service.env`)

You can customize how the service behaves by creating a configuration file in `bin/windows/`:

1. Copy or rename `bin/windows/service.env.example` to `bin/windows/service.env`.
2. Adjust the settings as needed:

| Setting | Default | Description |
|---|---|---|
| `DENODO_AI_SDK_SERVICE_STARTUP` | `manual` | Windows startup type: `auto` (starts on boot), `delayed` (delayed auto start), `manual`, or `disabled`. |
| `DENODO_AI_SDK_SERVICE_MODE` | `both` | Components to run: `both` (FastAPI + Chatbot), `api`, or `sample_chatbot`. |
| `DENODO_AI_SDK_SERVICE_VENV_DIR` | *(auto-detect)* | Virtual environment folder name or path (optional). If empty or not defined, it auto-detects `venv` and `.venv` in the project root. |
| `DENODO_AI_SDK_SERVICE_MCP` | `0` | Set to `1` to enable remote MCP endpoint support. |
| `DENODO_AI_SDK_SERVICE_LOG_LEVEL` | `INFO` | Output log level (`DEBUG`, `INFO`). |
| `DENODO_AI_SDK_SERVICE_TIMEOUT` | *(SDK default)* | Seconds to wait for the API and chatbot to answer /health at startup. |
| `DENODO_AI_SDK_SERVICE_MAX_LOG_SIZE` | `1` | Maximum file size in MB before rotating logs. |
| `DENODO_AI_SDK_SERVICE_MAX_LOG_FILES` | `5` | Maximum number of log session files to retain in `<AI_SDK_DATA_DIR>/windows_service/logs/`. |
| `DENODO_AI_SDK_SERVICE_PAUSE_ON_ERROR` | `0` | Console behavior on failure: `0` (disabled / exits immediately for unattended CI/CD pipelines), `1` (pauses console window on error for manual debugging). |
| `AI_SDK_DATA_DIR` | `data/` | Data directory for logs, cache, vector stores, and other generated files. Relative (to project root) or absolute path. Shared with `sdk_config.env` and `chatbot_config.env`. |

> **Note on Environment Variables:** Settings can be defined in `service.env` or passed as Windows system environment variables. If a setting is defined in both places, the value in `service.env` takes precedence.

### How to Run

Administrative Batch scripts are provided inside `bin/windows/` to manage the service lifecycle without manual command-line configuration (they will automatically request elevation via UAC if needed):

1. **Install and start the service:** Run `install_service.bat`. This registers `DenodoAISDK` in the Windows Service Control Manager and launches the configured components.
2. **Stop the service:** Run `stop_service.bat` to shut down the background processes and free network ports.
3. **Start the service:** Run `start_service.bat` to launch it again after being stopped.
4. **Remove the service:** Run `uninstall_service.bat` to unregister and completely remove the service from Windows.

### Logs and Troubleshooting

* **Log Files:** Output from the running application is captured under `<AI_SDK_DATA_DIR>/windows_service/logs/service_YYYYMMDD_HHMMSS.log` with automatic size rotation and cleanup based on your configuration.
* **Windows Event Viewer:** Service lifecycle events (starts, stops, or unexpected termination) are recorded under `Windows Logs > Application` (Source: `DenodoAISDK`).
* **Interactive Debugging:** To diagnose startup or dependency issues directly in your console, open an elevated prompt, navigate to `bin/windows/`, and run:
  ```cmd
  python service.py debug
  ```

# Licensing
Please see the file called LICENSE.
