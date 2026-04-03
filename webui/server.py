"""
LangExtract WebUI - Claude Code-style workspace interface.
Connects to local LLMs running on Spark devices via OpenAI-compatible APIs.
"""

import asyncio
import json
import os
import subprocess
import time
import uuid
from pathlib import Path
from typing import Optional

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

load_dotenv()

app = FastAPI(title="LangExtract WebUI")
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")

# ── Config ───────────────────────────────────────────────────────────────────

PROJECTS_ROOT = Path(os.getenv("PROJECTS_ROOT", "./projects")).resolve()
PROJECTS_ROOT.mkdir(parents=True, exist_ok=True)

def parse_endpoints() -> dict[str, str]:
    """Parse LLM_ENDPOINTS env var into {name: url} dict."""
    raw = os.getenv("LLM_ENDPOINTS", "local=http://localhost:11434")
    endpoints = {}
    for entry in raw.split(","):
        entry = entry.strip()
        if "=" in entry:
            name, url = entry.split("=", 1)
            endpoints[name.strip()] = url.strip()
        else:
            endpoints[entry] = entry
    return endpoints

LLM_ENDPOINTS = parse_endpoints()

# ── In-memory state ──────────────────────────────────────────────────────────

conversations: dict[str, dict] = {}  # id -> {messages, project, model, endpoint, title}


# ── LLM proxy ────────────────────────────────────────────────────────────────

async def list_models(endpoint_url: str) -> list[dict]:
    """Fetch available models from an OpenAI-compatible endpoint."""
    # Try Ollama /api/tags first, then OpenAI /v1/models
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            r = await client.get(f"{endpoint_url}/api/tags")
            if r.status_code == 200:
                data = r.json()
                return [{"id": m["name"], "name": m["name"]} for m in data.get("models", [])]
        except Exception:
            pass
        try:
            r = await client.get(f"{endpoint_url}/v1/models")
            if r.status_code == 200:
                data = r.json()
                return [{"id": m["id"], "name": m.get("id", "")} for m in data.get("data", [])]
        except Exception:
            pass
    return []


async def stream_chat(endpoint_url: str, model: str, messages: list[dict], system: str = ""):
    """Stream chat completions from an OpenAI-compatible endpoint."""
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
    }
    if system:
        payload["messages"] = [{"role": "system", "content": system}] + payload["messages"]

    # Try Ollama native API first, then OpenAI-compatible
    urls_to_try = [
        f"{endpoint_url}/api/chat",
        f"{endpoint_url}/v1/chat/completions",
    ]

    async with httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=10.0)) as client:
        for url in urls_to_try:
            try:
                async with client.stream("POST", url, json=payload) as response:
                    if response.status_code != 200:
                        continue
                    is_ollama = "/api/chat" in url
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        if is_ollama:
                            try:
                                data = json.loads(line)
                                content = data.get("message", {}).get("content", "")
                                if content:
                                    yield content
                                if data.get("done"):
                                    return
                            except json.JSONDecodeError:
                                continue
                        else:
                            if line.startswith("data: "):
                                line = line[6:]
                            if line == "[DONE]":
                                return
                            try:
                                data = json.loads(line)
                                delta = data["choices"][0].get("delta", {})
                                content = delta.get("content", "")
                                if content:
                                    yield content
                            except (json.JSONDecodeError, KeyError, IndexError):
                                continue
                    return
            except Exception:
                continue
        yield "[Error: Could not connect to LLM endpoint]"


# ── Skills engine ─────────────────────────────────────────────────────────────

SKILLS = {
    "file_read": {
        "name": "Read File",
        "icon": "file-text",
        "description": "Read contents of a file in the project",
    },
    "file_write": {
        "name": "Write File",
        "icon": "edit",
        "description": "Create or overwrite a file",
    },
    "file_list": {
        "name": "List Files",
        "icon": "folder",
        "description": "List directory contents",
    },
    "shell": {
        "name": "Shell",
        "icon": "terminal",
        "description": "Execute a shell command in the project directory",
    },
    "search": {
        "name": "Search",
        "icon": "search",
        "description": "Search for text in project files",
    },
}


def resolve_project_path(project: str, rel_path: str = ".") -> Path:
    """Safely resolve a path within a project directory."""
    project_dir = (PROJECTS_ROOT / project).resolve()
    target = (project_dir / rel_path).resolve()
    if not str(target).startswith(str(project_dir)):
        raise ValueError("Path traversal detected")
    return target


async def execute_skill(skill_id: str, params: dict, project: str) -> dict:
    """Execute a skill and return the result."""
    project_dir = resolve_project_path(project)
    project_dir.mkdir(parents=True, exist_ok=True)

    if skill_id == "file_read":
        path = resolve_project_path(project, params.get("path", ""))
        if not path.is_file():
            return {"error": f"File not found: {params.get('path')}"}
        content = path.read_text(errors="replace")
        # Truncate large files
        if len(content) > 50000:
            content = content[:50000] + "\n\n... [truncated]"
        return {"content": content, "path": str(path.relative_to(project_dir))}

    elif skill_id == "file_write":
        path = resolve_project_path(project, params.get("path", ""))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(params.get("content", ""))
        return {"ok": True, "path": str(path.relative_to(project_dir))}

    elif skill_id == "file_list":
        path = resolve_project_path(project, params.get("path", "."))
        if not path.is_dir():
            return {"error": f"Not a directory: {params.get('path')}"}
        entries = []
        for item in sorted(path.iterdir()):
            rel = str(item.relative_to(project_dir))
            entries.append({
                "name": item.name,
                "path": rel,
                "type": "dir" if item.is_dir() else "file",
                "size": item.stat().st_size if item.is_file() else None,
            })
        return {"entries": entries}

    elif skill_id == "shell":
        cmd = params.get("command", "")
        if not cmd:
            return {"error": "No command provided"}
        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True,
                timeout=30, cwd=str(project_dir),
            )
            return {
                "stdout": result.stdout[-10000:] if result.stdout else "",
                "stderr": result.stderr[-5000:] if result.stderr else "",
                "returncode": result.returncode,
            }
        except subprocess.TimeoutExpired:
            return {"error": "Command timed out (30s)"}

    elif skill_id == "search":
        pattern = params.get("pattern", "")
        path = resolve_project_path(project, params.get("path", "."))
        results = []
        try:
            r = subprocess.run(
                ["grep", "-rn", "--include=*", "-l", pattern, str(path)],
                capture_output=True, text=True, timeout=15,
            )
            for line in r.stdout.strip().split("\n")[:50]:
                if line:
                    results.append(str(Path(line).relative_to(project_dir)))
        except Exception:
            pass
        return {"matches": results, "pattern": pattern}

    return {"error": f"Unknown skill: {skill_id}"}


# ── API routes ────────────────────────────────────────────────────────────────

@app.get("/")
async def index():
    return HTMLResponse((Path(__file__).parent / "static" / "index.html").read_text())


@app.get("/api/endpoints")
async def get_endpoints():
    """List configured LLM endpoints and their models."""
    result = {}
    for name, url in LLM_ENDPOINTS.items():
        models = await list_models(url)
        result[name] = {"url": url, "models": models, "online": len(models) > 0}
    return result


@app.get("/api/models/{endpoint_name}")
async def get_models(endpoint_name: str):
    url = LLM_ENDPOINTS.get(endpoint_name)
    if not url:
        raise HTTPException(404, "Endpoint not found")
    return await list_models(url)


@app.get("/api/projects")
async def list_projects():
    projects = []
    for d in sorted(PROJECTS_ROOT.iterdir()):
        if d.is_dir() and not d.name.startswith("."):
            file_count = sum(1 for _ in d.rglob("*") if _.is_file())
            projects.append({"name": d.name, "files": file_count})
    return projects


@app.post("/api/projects")
async def create_project(data: dict):
    name = data.get("name", "").strip()
    if not name or "/" in name or "\\" in name:
        raise HTTPException(400, "Invalid project name")
    path = PROJECTS_ROOT / name
    path.mkdir(parents=True, exist_ok=True)
    return {"name": name}


@app.get("/api/projects/{project}/tree")
async def project_tree(project: str, path: str = "."):
    result = await execute_skill("file_list", {"path": path}, project)
    return result


@app.get("/api/projects/{project}/file")
async def read_file(project: str, path: str):
    result = await execute_skill("file_read", {"path": path}, project)
    return result


@app.get("/api/conversations")
async def list_conversations():
    return [
        {"id": cid, "title": c.get("title", "New chat"), "project": c.get("project"),
         "model": c.get("model"), "updated": c.get("updated")}
        for cid, c in sorted(conversations.items(), key=lambda x: x[1].get("updated", 0), reverse=True)
    ]


@app.post("/api/conversations")
async def create_conversation(data: dict):
    cid = str(uuid.uuid4())[:8]
    conversations[cid] = {
        "messages": [],
        "project": data.get("project"),
        "model": data.get("model", ""),
        "endpoint": data.get("endpoint", ""),
        "title": data.get("title", "New chat"),
        "updated": time.time(),
    }
    return {"id": cid}


@app.delete("/api/conversations/{cid}")
async def delete_conversation(cid: str):
    conversations.pop(cid, None)
    return {"ok": True}


@app.get("/api/skills")
async def get_skills():
    return SKILLS


# ── WebSocket for streaming chat ──────────────────────────────────────────────

SYSTEM_PROMPT_TEMPLATE = """You are a helpful coding assistant working in a project workspace.
You have access to skills/tools to interact with the project filesystem.

When you need to use a skill, output a JSON block like this:
```tool
{{"skill": "skill_id", "params": {{"key": "value"}}}}
```

Available skills:
- file_read: Read a file. Params: {{"path": "relative/path"}}
- file_write: Write a file. Params: {{"path": "relative/path", "content": "file content"}}
- file_list: List directory. Params: {{"path": "."}}
- shell: Run shell command. Params: {{"command": "ls -la"}}
- search: Search in files. Params: {{"pattern": "search term", "path": "."}}

Current project: {project}
Project path: {project_path}

Be concise. Use markdown. When writing code, use fenced code blocks with language tags.
When you use a tool, explain briefly what you're doing and why."""


@app.websocket("/ws/chat/{cid}")
async def ws_chat(ws: WebSocket, cid: str):
    await ws.accept()

    if cid not in conversations:
        await ws.send_json({"type": "error", "content": "Conversation not found"})
        await ws.close()
        return

    conv = conversations[cid]

    try:
        while True:
            data = await ws.receive_json()

            if data.get("type") == "message":
                user_msg = data["content"]
                conv["messages"].append({"role": "user", "content": user_msg})
                conv["updated"] = time.time()

                # Auto-title from first message
                if conv["title"] == "New chat" and len(conv["messages"]) == 1:
                    conv["title"] = user_msg[:60] + ("..." if len(user_msg) > 60 else "")

                endpoint_url = LLM_ENDPOINTS.get(conv["endpoint"], "")
                if not endpoint_url:
                    endpoint_url = next(iter(LLM_ENDPOINTS.values()), "http://localhost:11434")

                project = conv.get("project", "default")
                system = SYSTEM_PROMPT_TEMPLATE.format(
                    project=project,
                    project_path=str(resolve_project_path(project)),
                )

                # Stream response
                full_response = ""
                await ws.send_json({"type": "stream_start"})

                async for chunk in stream_chat(endpoint_url, conv["model"], conv["messages"], system):
                    full_response += chunk
                    await ws.send_json({"type": "stream", "content": chunk})

                await ws.send_json({"type": "stream_end"})

                conv["messages"].append({"role": "assistant", "content": full_response})

                # Check for tool calls in response
                await process_tool_calls(ws, full_response, project, conv)

            elif data.get("type") == "skill":
                # Direct skill execution from UI
                result = await execute_skill(data["skill"], data.get("params", {}), conv.get("project", "default"))
                await ws.send_json({"type": "skill_result", "skill": data["skill"], "result": result})

    except WebSocketDisconnect:
        pass


async def process_tool_calls(ws: WebSocket, response: str, project: str, conv: dict):
    """Extract and execute tool calls from assistant response."""
    import re
    pattern = r"```tool\s*\n({.*?})\s*\n```"
    matches = re.findall(pattern, response, re.DOTALL)

    for match in matches:
        try:
            call = json.loads(match)
            skill_id = call.get("skill", "")
            params = call.get("params", {})

            await ws.send_json({"type": "skill_exec", "skill": skill_id, "params": params})
            result = await execute_skill(skill_id, params, project)
            await ws.send_json({"type": "skill_result", "skill": skill_id, "result": result})

            # Feed result back to LLM
            conv["messages"].append({
                "role": "user",
                "content": f"[Tool result for {skill_id}]:\n```json\n{json.dumps(result, indent=2, default=str)}\n```"
            })

        except (json.JSONDecodeError, KeyError):
            continue


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8080"))
    print(f"\n  ⬡ LangExtract WebUI")
    print(f"  → http://{host}:{port}")
    print(f"  → Endpoints: {', '.join(f'{k} ({v})' for k, v in LLM_ENDPOINTS.items())}")
    print(f"  → Projects: {PROJECTS_ROOT}\n")
    uvicorn.run(app, host=host, port=port)
