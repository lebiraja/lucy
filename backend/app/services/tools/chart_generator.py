"""Chart generation tool using matplotlib."""

from __future__ import annotations
import asyncio
import base64
import uuid
from pathlib import Path


async def generate_chart(args: dict, workspace_dir: str) -> dict:
    """Generate a chart and save as PNG. Returns base64-encoded image."""
    chart_type = args.get("chart_type", "bar")
    data = args.get("data", {})
    title = args.get("title", "Chart")

    if not data:
        return {"error": "data is required"}

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _render_chart, chart_type, data, title, workspace_dir)


def _render_chart(chart_type: str, data: dict, title: str, workspace_dir: str) -> dict:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import seaborn as sns

        sns.set_theme(style="darkgrid")
        fig, ax = plt.subplots(figsize=(10, 6))

        labels = data.get("labels", [])
        values = data.get("values", [])
        x_label = data.get("x_label", "")
        y_label = data.get("y_label", "")

        if chart_type == "bar":
            ax.bar(labels, values, color=sns.color_palette("husl", len(labels)))
        elif chart_type == "line":
            ax.plot(labels, values, marker="o", linewidth=2)
            ax.fill_between(range(len(labels)), values, alpha=0.1)
        elif chart_type == "pie":
            ax.pie(values, labels=labels, autopct="%1.1f%%", startangle=90)
        elif chart_type == "scatter":
            x = data.get("x", values)
            y = data.get("y", labels)
            ax.scatter(x, y, alpha=0.7, s=60)
        else:
            ax.bar(labels, values)

        ax.set_title(title, fontsize=14, fontweight="bold")
        if x_label:
            ax.set_xlabel(x_label)
        if y_label:
            ax.set_ylabel(y_label)
        plt.tight_layout()

        workspace = Path(workspace_dir)
        workspace.mkdir(parents=True, exist_ok=True)
        fname = f"chart_{uuid.uuid4().hex[:8]}.png"
        fpath = workspace / fname
        fig.savefig(str(fpath), dpi=150, bbox_inches="tight")
        plt.close(fig)

        b64 = base64.b64encode(fpath.read_bytes()).decode()
        return {"filename": fname, "path": str(fpath), "base64": b64, "chart_type": chart_type}

    except Exception as e:
        return {"error": f"Chart generation failed: {str(e)}"}
