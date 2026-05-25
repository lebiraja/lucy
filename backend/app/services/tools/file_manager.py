"""File read/write tools sandboxed to session workspace directory."""

from __future__ import annotations
from pathlib import Path


def _safe_path(workspace_dir: str, rel_path: str) -> Path:
    """Resolve path and ensure it stays within workspace_dir."""
    workspace = Path(workspace_dir).resolve()
    target = (workspace / rel_path).resolve()
    if not str(target).startswith(str(workspace)):
        raise PermissionError(f"Path traversal attempt blocked: {rel_path}")
    return target


async def read_file(args: dict, workspace_dir: str) -> dict:
    """Read a file from the session workspace (max 1MB)."""
    path = args.get("path", "")
    if not path:
        return {"error": "path is required"}

    try:
        target = _safe_path(workspace_dir, path)
        if not target.exists():
            return {"error": f"File not found: {path}"}
        if target.stat().st_size > 1_048_576:
            return {"error": f"File too large (max 1MB): {path}"}
        content = target.read_text(encoding="utf-8", errors="replace")
        return {"path": path, "content": content, "size_bytes": target.stat().st_size}
    except PermissionError as e:
        return {"error": str(e)}


async def write_file(args: dict, workspace_dir: str) -> dict:
    """Write a file to the session workspace."""
    path = args.get("path", "")
    content = args.get("content", "")
    if not path:
        return {"error": "path is required"}

    try:
        target = _safe_path(workspace_dir, path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return {"path": path, "size_bytes": len(content.encode()), "success": True}
    except PermissionError as e:
        return {"error": str(e)}
