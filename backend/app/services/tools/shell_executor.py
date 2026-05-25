"""Shell executor with allowlist-only commands, sandboxed to workspace dir."""

from __future__ import annotations
import asyncio
import shlex
from pathlib import Path
from app.config import get_settings

ALLOWED_COMMANDS = {"ls", "cat", "head", "tail", "wc", "grep", "find", "echo", "pwd", "du", "sort", "uniq", "cut", "awk", "sed"}


async def run_shell(args: dict, workspace_dir: str) -> dict:
    """Run a safe shell command inside the session workspace directory."""
    command = args.get("command", "")
    if not command:
        return {"error": "command is required"}

    try:
        parts = shlex.split(command)
    except ValueError as e:
        return {"error": f"Invalid command: {e}"}

    if not parts:
        return {"error": "Empty command"}

    base_cmd = parts[0].lstrip("./")
    if base_cmd not in ALLOWED_COMMANDS:
        return {"error": f"Command '{base_cmd}' is not allowed. Allowed: {', '.join(sorted(ALLOWED_COMMANDS))}"}

    workspace = Path(workspace_dir)
    workspace.mkdir(parents=True, exist_ok=True)

    settings = get_settings()

    try:
        proc = await asyncio.create_subprocess_exec(
            *parts,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(workspace),
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=settings.shell_execution_timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            return {"error": f"Command timed out after {settings.shell_execution_timeout}s"}

        return {
            "stdout": stdout.decode("utf-8", errors="replace")[:65536],
            "stderr": stderr.decode("utf-8", errors="replace")[:4096] or None,
            "exit_code": proc.returncode,
        }

    except FileNotFoundError:
        return {"error": f"Command not found: {parts[0]}"}
