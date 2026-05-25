# Viernes Pilot

[English](#) | [Español](README.es.md)

Viernes Pilot is a local, privacy-first developer assistant and workspace orchestrator. It integrates WSL with the Windows host to automate development environments, fuzzy-launch desktop applications, and orchestrate interactive terminal tabs.

## Prerequisites

- **Python**: Version 3.12 or higher.
- **Ollama**: Running locally with a model that supports native Tool Calling (e.g., `qwen3.5:9b` which was used during development) and the `nomic-embed-text` embedding model.
- **Engram**: Active on port 7437 (local vector database for memory).

## Installation

Do not install packages directly into your system Python. A virtual environment must be used.

1. Clone the repository:
   ```bash
   git clone https://github.com/ifmlinares/viernes-pilot.git
   cd viernes-pilot
   ```

2. Create a Python virtual environment:
   ```bash
   python3 -m venv .venv
   ```

3. Activate the virtual environment:
   - **Linux / macOS / WSL**:
     ```bash
     source .venv/bin/activate
     ```
   - **Windows (Command Prompt)**:
     ```cmd
     .venv\Scripts\activate.bat
     ```
   - **Windows (PowerShell)**:
     ```powershell
     .venv\Scripts\Activate.ps1
     ```

4. Install the dependencies inside the activated environment:
   ```bash
   pip install -r requirements.txt
   ```

5. Configure environment variables:
   Copy the template file `.env.example` to `.env` and customize your settings (e.g., model name, Ollama or Engram host addresses):
   ```bash
   cp .env.example .env
   ```

## Execution

Ensure your virtual environment is active before running the application:

```bash
python3 main.py
```

## Modular Documentation

For detailed information about each component of the system, refer to the respective module documentation:

- **Core Module**: Details about Ollama client and Engram memory integration.
  - [English](core/README.md) | [Español](core/README.es.md)
- **Tools Module**: Details about the fuzzy launcher and terminal integration.
  - [English](tools/README.md) | [Español](tools/README.es.md)
- **Tests Module**: Instructions for running unit and connectivity tests.
  - [English](tests/README.md) | [Español](tests/README.es.md)

## Project Standards

For guidelines regarding documentation layout and code standards in this repository, see the [Documentation Standard](skills/documentacion.md).

## License

Distributed under the MIT License. See the LICENSE file for details.
