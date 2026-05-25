# Lucy — Agent Tool System

Agents can use tools during task execution. Tools are invoked mid-response via a structured `<tool_call>` tag, executed by the backend, and the result is fed back into the conversation context before the agent continues.

---

## How Tool Use Works

The tool system is implemented as an agentic loop inside `run_agent_step()`:

1. The agent's system prompt includes a list of permitted tools and usage instructions
2. The LLM responds with a `<tool_call>{"tool": "tool_name", "args": {...}}</tool_call>` tag
3. The backend parses the tag, executes the tool, and appends the result to the message context
4. The LLM is re-invoked with the tool result and continues reasoning
5. This repeats up to `MAX_TOOL_ITERATIONS` (default: 5) per agent step

**Tool call format (injected into system prompt):**
```
To use a tool, respond with:
<tool_call>{"tool": "web_search", "args": {"query": "..."}}</tool_call>

After receiving tool results, continue your response normally.
```

---

## Tool Registry

All tools live in `backend/app/services/tools/`. Each is an async function:

```python
async def tool_name(args: dict, workspace_dir: str) -> dict
```

---

## Available Tools

### `web_search`
**File:** `tools/web_search.py`  
**API:** SerpAPI (`https://serpapi.com/search`)  
**Key:** `SERPER_API_KEY`

Search Google for current information.

```json
// Input
{ "query": "latest AI research 2026" }

// Output
{
  "query": "latest AI research 2026",
  "answer_box": "Direct answer if available",
  "knowledge_graph": "Entity description if available",
  "results": [
    { "title": "...", "link": "https://...", "snippet": "..." }
  ]
}
```

---

### `news_search`
**File:** `tools/news_search.py`  
**API:** NewsAPI (`https://newsapi.org/v2/everything`)  
**Key:** `NEWS_API_KEY`

Search recent news articles.

```json
// Input
{ "query": "OpenAI GPT-5", "days": 7 }

// Output
{
  "query": "OpenAI GPT-5",
  "total_results": 142,
  "articles": [
    { "title": "...", "description": "...", "url": "...", "published_at": "...", "source": "TechCrunch" }
  ]
}
```

---

### `run_code`
**File:** `tools/code_interpreter.py`  
**Sandbox:** subprocess with 30s timeout (configurable via `CODE_EXECUTION_TIMEOUT`)

Execute Python code. Available libraries: `pandas`, `numpy`, `matplotlib`, `seaborn`, `openpyxl`. Working directory is the session workspace.

```json
// Input
{
  "code": "import pandas as pd\ndf = pd.DataFrame({'x': [1,2,3], 'y': [4,5,6]})\nprint(df.describe())"
}

// Output
{
  "stdout": "         x    y\ncount  3.0  3.0\n...",
  "stderr": null,
  "exit_code": 0,
  "files_created": ["analysis.csv"],
  "charts": [
    { "filename": "chart_abc123.png", "base64": "iVBORw0K..." }
  ]
}
```

Charts saved as `.png` files are automatically base64-encoded and included in the response. They appear inline in the chat UI.

---

### `run_shell`
**File:** `tools/shell_executor.py`  
**Timeout:** 10s (`SHELL_EXECUTION_TIMEOUT`)  
**Allowlist:** `ls`, `cat`, `head`, `tail`, `wc`, `grep`, `find`, `echo`, `pwd`, `du`, `sort`, `uniq`, `cut`, `awk`, `sed`

Run a safe shell command inside the session workspace directory.

```json
// Input
{ "command": "ls -la" }

// Output
{ "stdout": "total 12\n-rw-r--r-- 1 root root 412 ...", "stderr": null, "exit_code": 0 }
```

Commands not in the allowlist are rejected. The working directory is always the session workspace — no path traversal possible.

---

### `read_file`
**File:** `tools/file_manager.py`  
**Max size:** 1MB

Read a file from the session workspace.

```json
// Input
{ "path": "report.txt" }

// Output
{ "path": "report.txt", "content": "...", "size_bytes": 412 }
```

---

### `write_file`
**File:** `tools/file_manager.py`

Write a file to the session workspace.

```json
// Input
{ "path": "summary.md", "content": "# Summary\n..." }

// Output
{ "path": "summary.md", "size_bytes": 128, "success": true }
```

All paths are sandboxed to `/tmp/lucy-workspace/session_{id}/`. Path traversal attempts (`../`) are blocked.

---

### `generate_chart`
**File:** `tools/chart_generator.py`  
**Library:** matplotlib + seaborn

Generate a chart image. Returns base64 PNG that renders inline in the chat UI.

```json
// Input
{
  "chart_type": "bar",
  "data": {
    "labels": ["Q1", "Q2", "Q3", "Q4"],
    "values": [42, 58, 71, 93],
    "x_label": "Quarter",
    "y_label": "Revenue ($M)"
  },
  "title": "Quarterly Revenue 2026"
}

// Output
{ "filename": "chart_abc123.png", "base64": "iVBORw0K...", "chart_type": "bar" }
```

**Supported chart types:** `bar`, `line`, `pie`, `scatter`

For `scatter`, use `data.x` and `data.y` arrays instead of `labels`/`values`.

---

### `parse_csv`
**File:** `tools/parse_csv.py`  
**Library:** pandas  
**Formats:** `.csv`, `.xlsx`, `.xls`

Parse and analyze CSV or Excel files in the session workspace.

```json
// Input — describe
{ "path": "sales_data.csv", "operation": "describe" }

// Output
{
  "shape": [1000, 8],
  "columns": ["date", "product", "revenue", "units"],
  "dtypes": { "date": "object", "revenue": "float64" },
  "describe": { "revenue": { "mean": 4200.5, "std": 812.3 } }
}
```

```json
// Input — head
{ "path": "sales_data.csv", "operation": "head" }

// Output
{ "shape": [1000, 8], "columns": [...], "rows": [{...}, ...] }
```

```json
// Input — query
{ "path": "sales_data.csv", "operation": "query", "query": "revenue > 5000" }

// Output
{ "query": "revenue > 5000", "row_count": 127, "rows": [{...}, ...] }
```

---

## Tool Permissions by Role

| Role | web_search | news_search | run_code | run_shell | read_file | write_file | generate_chart | parse_csv |
|------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| CEO | ✓ | ✓ | | | | | | |
| CTO | ✓ | | ✓ | ✓ | ✓ | ✓ | ✓ | |
| CFO | ✓ | ✓ | | | | | ✓ | ✓ |
| Manager | ✓ | ✓ | | | ✓ | ✓ | | |
| Planner | ✓ | ✓ | | | ✓ | | | |
| Questioner | ✓ | ✓ | | | | | | |
| Developer | ✓ | | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Employee | ✓ | | ✓ | | ✓ | ✓ | ✓ | ✓ |
| Tester | | | ✓ | ✓ | ✓ | ✓ | | |

---

## Adding a New Tool

1. Create `backend/app/services/tools/my_tool.py`:
```python
async def my_tool(args: dict, workspace_dir: str) -> dict:
    query = args.get("query", "")
    # ... do work ...
    return {"result": "..."}
```

2. Register in `backend/app/services/tools/__init__.py`:
```python
from app.services.tools.my_tool import my_tool

TOOL_REGISTRY["my_tool"] = my_tool
TOOL_PERMISSIONS["developer"].append("my_tool")
TOOL_DESCRIPTIONS["my_tool"] = 'my_tool({"query": "..."}) → Description of what it does'
```

That's it. The tool is immediately available to any agent with the right role on next request.

---

## Workspace

Each session gets a sandboxed directory:
```
/tmp/lucy-workspace/session_{id}/
```

Mounted as Docker volume `lucy_workspace` — persists across backend restarts.

Files written during a session are accessible via:
- `GET /api/sessions/{id}/files` — list files
- `GET /api/sessions/{id}/files/{filename}` — download
- `read_file` tool — agents can read each other's output
