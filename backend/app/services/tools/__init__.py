"""Tool registry for Lucy agents.

Each tool is an async callable: async (args: dict, workspace_dir: str) -> dict
Tools are permission-gated by agent role.
"""

from __future__ import annotations

from app.services.tools.web_search import web_search
from app.services.tools.news_search import news_search
from app.services.tools.code_interpreter import run_code
from app.services.tools.shell_executor import run_shell
from app.services.tools.file_manager import read_file, write_file
from app.services.tools.chart_generator import generate_chart
from app.services.tools.parse_csv import parse_csv

TOOL_REGISTRY: dict[str, callable] = {
    "web_search": web_search,
    "news_search": news_search,
    "run_code": run_code,
    "run_shell": run_shell,
    "read_file": read_file,
    "write_file": write_file,
    "generate_chart": generate_chart,
    "parse_csv": parse_csv,
}

TOOL_PERMISSIONS: dict[str, list[str]] = {
    "ceo":              ["web_search", "news_search"],
    "cto":              ["web_search", "run_code", "run_shell", "read_file", "write_file", "generate_chart"],
    "cfo":              ["web_search", "news_search", "parse_csv", "generate_chart"],
    "manager":          ["web_search", "news_search", "read_file", "write_file"],
    "hr_manager":       ["web_search", "news_search", "read_file", "write_file"],
    "backend_manager":  ["web_search", "run_code", "read_file", "write_file"],
    "frontend_manager": ["web_search", "run_code", "read_file", "write_file"],
    "qa_manager":       ["web_search", "run_code", "run_shell", "read_file", "write_file"],
    "planner":          ["web_search", "news_search", "read_file"],
    "questioner":       ["web_search", "news_search"],
    "employee":         ["web_search", "run_code", "read_file", "write_file", "generate_chart", "parse_csv"],
    "developer":        ["web_search", "run_code", "run_shell", "read_file", "write_file", "generate_chart", "parse_csv"],
    "tester":           ["run_code", "run_shell", "read_file", "write_file"],
}

TOOL_DESCRIPTIONS: dict[str, str] = {
    "web_search":     'web_search({"query": "search terms"}) → Search Google via SerpAPI for current information, links, and snippets',
    "news_search":    'news_search({"query": "topic", "days": 7}) → Search recent news articles',
    "run_code":       'run_code({"code": "python code here"}) → Execute Python (pandas, numpy, matplotlib available)',
    "run_shell":      'run_shell({"command": "ls -la"}) → Run safe shell command (ls, cat, grep, find, etc.)',
    "read_file":      'read_file({"path": "filename.txt"}) → Read a file from the workspace',
    "write_file":     'write_file({"path": "filename.txt", "content": "..."}) → Write a file to the workspace',
    "generate_chart": 'generate_chart({"chart_type": "bar", "data": {"labels": [...], "values": [...]}, "title": "..."}) → Generate a chart image',
    "parse_csv":      'parse_csv({"path": "data.csv", "operation": "describe"}) → Parse CSV/Excel (operations: describe, head, query)',
}


def get_tool_prompt(role: str) -> str:
    """Build the tool-use instruction block for a given agent role."""
    allowed = TOOL_PERMISSIONS.get(role, [])
    if not allowed:
        return ""

    tool_lines = "\n".join(
        f"  - {TOOL_DESCRIPTIONS[t]}" for t in allowed if t in TOOL_DESCRIPTIONS
    )

    return (
        f"\n\nYou have access to the following tools:\n{tool_lines}\n\n"
        "To use a tool, output a tool call tag like this (on its own line):\n"
        "<tool_call>{\"tool\": \"tool_name\", \"args\": {\"key\": \"value\"}}</tool_call>\n\n"
        "You can use multiple tools in sequence. After receiving tool results, continue your analysis.\n"
        "When you have enough information, provide your final answer normally (no tool_call tag)."
    )


async def execute_tool(tool_name: str, args: dict, workspace_dir: str) -> dict:
    """Execute a named tool and return its result."""
    fn = TOOL_REGISTRY.get(tool_name)
    if not fn:
        return {"error": f"Unknown tool: {tool_name}"}
    try:
        return await fn(args, workspace_dir)
    except Exception as e:
        return {"error": str(e)}
