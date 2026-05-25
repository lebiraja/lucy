"""CSV/Excel parsing tool using pandas."""

from __future__ import annotations
import asyncio
from pathlib import Path


async def parse_csv(args: dict, workspace_dir: str) -> dict:
    """Parse a CSV or Excel file. Operations: describe, head, query."""
    path = args.get("path", "")
    operation = args.get("operation", "head")
    query = args.get("query", "")

    if not path:
        return {"error": "path is required"}

    workspace = Path(workspace_dir)
    target = (workspace / path).resolve()
    if not str(target).startswith(str(workspace.resolve())):
        return {"error": "Path traversal blocked"}
    if not target.exists():
        return {"error": f"File not found: {path}"}

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _parse, str(target), operation, query)


def _parse(filepath: str, operation: str, query: str) -> dict:
    try:
        import pandas as pd

        if filepath.endswith((".xlsx", ".xls")):
            df = pd.read_excel(filepath)
        else:
            df = pd.read_csv(filepath)

        if operation == "describe":
            desc = df.describe(include="all").fillna("").to_dict()
            return {
                "shape": list(df.shape),
                "columns": list(df.columns),
                "dtypes": {c: str(t) for c, t in df.dtypes.items()},
                "describe": desc,
            }
        elif operation == "head":
            n = 20
            rows = df.head(n).fillna("").to_dict(orient="records")
            return {"shape": list(df.shape), "columns": list(df.columns), "rows": rows}
        elif operation == "query" and query:
            result = df.query(query).head(50).fillna("").to_dict(orient="records")
            return {"query": query, "row_count": len(result), "rows": result}
        else:
            return {"error": f"Unknown operation '{operation}'. Use: describe, head, query"}

    except Exception as e:
        return {"error": f"CSV parsing failed: {str(e)}"}
