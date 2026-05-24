# Core Module

[English](#) | [Español](README.es.md)

The `core` module manages all communications with local artificial intelligence and memory services. It contains the core clients for interacting with Ollama and Engram.

## File Breakdown

### brain.py

This file is the interface for **Ollama**. It communicates with the local Ollama instance on port 11434.

- **chat(model, messages, format, tools)**: Sends the conversation history, system prompt, and dynamic tools list to Ollama's chat API. Stream is set to `False` to handle tool execution sequentially.
- **embed(model, text)**: Generates a vector representation of a given string using the configured embedding model (`nomic-embed-text` by default).

### memory.py

This file connects to **Engram**, the long-term memory vector database, running on port 7437.

- **save(title, content, mem_type, topic_key)**: Persists an observation, preference, or setup detail in the vector database.
- **search(query, limit)**: Queries Engram for the most semantically relevant saved memories.
- **search_expanded(query, limit)**: Improves standard semantic search by performing fallback queries with individual words (excluding Spanish connectors and stopwords). It returns a deduplicated collection of relevant memory elements.

## Execution Flow

1. The user inputs a query in `main.py`.
2. The system queries `memory.py` using `search_expanded`.
3. The retrieved observations are injected into the system prompt context as a "Long-Term Memory" block.
4. The system prompt, context, conversation history, and available system tools are sent to `brain.py`.
5. Ollama processes the prompt and decides whether to respond directly or output a JSON tool call request.
