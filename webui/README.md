# LangExtract WebUI

A Claude Code-style workspace interface for interacting with local LLMs running on your devices (e.g., Spark boards with Ollama).

## Features

- **Claude Code aesthetic** — dark terminal-style UI with monospace fonts, accent glows, and clean layout
- **Multi-endpoint support** — connect to multiple LLM servers (Spark 1, Spark 2, etc.)
- **Project workspace** — organize work in projects with file browsing and editing
- **Skills/Tools** — file read/write, shell execution, search, directory listing
- **Streaming chat** — real-time token streaming via WebSocket
- **Tool use** — the LLM can autonomously use skills (read files, run commands, etc.)
- **Conversation management** — multiple conversations with history

## Quick Start

```bash
cd webui

# Install dependencies
pip install -r requirements.txt

# Configure your endpoints
cp .env.example .env
# Edit .env with your Spark IPs

# Run
python server.py
```

Then open http://localhost:8080

## Configuration

Edit `.env`:

```ini
# Your Spark devices running Ollama (or any OpenAI-compatible server)
LLM_ENDPOINTS=spark1=http://192.168.1.10:11434,spark2=http://192.168.1.11:11434

# Where project files are stored
PROJECTS_ROOT=./projects

# Server binding
HOST=0.0.0.0
PORT=8080
```

## Supported LLM Backends

Any server exposing an OpenAI-compatible or Ollama API:
- **Ollama** (`/api/chat`, `/api/tags`)
- **llama.cpp server** (`/v1/chat/completions`)
- **vLLM** (`/v1/chat/completions`)
- **LocalAI** (`/v1/chat/completions`)
- **LM Studio** (`/v1/chat/completions`)

## Architecture

```
webui/
├── server.py          # FastAPI backend (LLM proxy, skills, projects, WS)
├── static/
│   ├── index.html     # Single-page app
│   ├── style.css      # Claude Code-inspired theme
│   └── app.js         # Frontend logic
├── projects/          # Project workspaces (auto-created)
├── requirements.txt
└── .env.example
```
