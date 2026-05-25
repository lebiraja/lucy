"""Sandboxed Python code interpreter using subprocess with timeout."""

from __future__ import annotations
import asyncio
import os
import uuid
import base64
from pathlib import Path
from app.config import get_settings


async def run_code(args: dict, workspace_dir: str) -> dict:
    """Execute Python code in a subprocess sandbox.

    Available: pandas, numpy, matplotlib, seaborn, openpyxl
    Files written to workspace_dir are accessible via read_file/generate_chart tools.
    """
    code = args.get("code", "")
    if not code:
        return {"error": "code is required"}

    settings = get_settings()
    workspace = Path(workspace_dir)
    workspace.mkdir(parents=True, exist_ok=True)

    script_name = f"exec_{uuid.uuid4().hex[:8]}.py"
    script_path = workspace / script_name

    # Inject workspace dir so code can save files there
    preamble = f"""
import os, sys
os.chdir({repr(str(workspace))})
sys.path.insert(0, {repr(str(workspace))})
import warnings
warnings.filterwarnings('ignore')
# Make matplotlib non-interactive
import matplotlib
matplotlib.use('Agg')
"""
    full_code = preamble + "\n" + code
    script_path.write_text(full_code, encoding="utf-8")

    before_files = set(workspace.iterdir())

    try:
        proc = await asyncio.create_subprocess_exec(
            "python", str(script_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(workspace),
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=settings.code_execution_timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            return {"error": f"Code execution timed out after {settings.code_execution_timeout}s"}

        stdout_text = stdout.decode("utf-8", errors="replace")[:32768]
        stderr_text = stderr.decode("utf-8", errors="replace")[:8192]

        # Detect new files written
        after_files = set(workspace.iterdir())
        new_files = [f.name for f in (after_files - before_files) if f.name != script_name]

        # Encode any new PNG charts as base64
        charts = []
        for fname in new_files:
            fpath = workspace / fname
            if fname.lower().endswith(".png"):
                charts.append({
                    "filename": fname,
                    "base64": base64.b64encode(fpath.read_bytes()).decode(),
                })

        result = {
            "stdout": stdout_text,
            "stderr": stderr_text if stderr_text else None,
            "exit_code": proc.returncode,
            "files_created": new_files,
            "charts": charts,
        }
        if proc.returncode != 0 and not stdout_text:
            result["error"] = stderr_text or f"Process exited with code {proc.returncode}"

        return result

    finally:
        script_path.unlink(missing_ok=True)
