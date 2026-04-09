"""NotebookEditTool — edit Jupyter notebook cells. Mirrors src/tools/NotebookEditTool/NotebookEditTool.ts"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from optimus.tool import Tool, ToolUseContext, ValidationResult

NOTEBOOK_EDIT_TOOL_NAME = "NotebookEdit"

INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "notebook_path": {"type": "string", "description": "Absolute path to the Jupyter notebook (.ipynb)."},
        "cell_id": {"type": "string", "description": "ID or index of the cell to edit."},
        "new_source": {"type": "string", "description": "New source content for the cell."},
        "cell_type": {
            "type": "string",
            "enum": ["code", "markdown"],
            "description": "Cell type when inserting a new cell.",
        },
        "edit_mode": {
            "type": "string",
            "enum": ["replace", "insert_above", "insert_below", "delete"],
            "description": "How to apply the edit.",
        },
    },
    "required": ["notebook_path", "cell_id", "new_source"],
}

DESCRIPTION = """\
Edit a Jupyter notebook (.ipynb) by modifying, inserting, or deleting cells.
The notebook_path must be an absolute path to an existing .ipynb file.
Use cell_id to reference a specific cell by its id or index.
"""


class NotebookEditTool(Tool):
    name: str = NOTEBOOK_EDIT_TOOL_NAME
    description: str = DESCRIPTION
    input_schema: dict[str, Any] = INPUT_SCHEMA

    async def check_permissions(self, input_data: dict[str, Any], ctx: ToolUseContext) -> ValidationResult:
        return ValidationResult(allowed=True)

    async def call(self, input_data: dict[str, Any], ctx: ToolUseContext) -> list[dict[str, Any]]:
        from optimus.utils.path import expand_path
        from optimus.utils.cwd import get_cwd

        nb_path = expand_path(input_data["notebook_path"], get_cwd())
        cell_id: str = input_data["cell_id"]
        new_source: str = input_data["new_source"]
        edit_mode: str = input_data.get("edit_mode", "replace")
        cell_type: str = input_data.get("cell_type", "code")

        try:
            nb = json.loads(Path(nb_path).read_text(encoding="utf-8"))
        except FileNotFoundError:
            return [{"type": "text", "text": f"Notebook not found: {nb_path}"}]
        except json.JSONDecodeError as exc:
            return [{"type": "text", "text": f"Invalid notebook JSON: {exc}"}]

        cells: list[dict] = nb.get("cells", [])

        # Resolve cell index
        idx: int | None = None
        try:
            idx = int(cell_id)
            if idx < 0 or idx >= len(cells):
                return [{"type": "text", "text": f"Cell index out of range: {idx}"}]
        except ValueError:
            for i, c in enumerate(cells):
                if c.get("id") == cell_id:
                    idx = i
                    break
            if idx is None:
                return [{"type": "text", "text": f"Cell not found: {cell_id}"}]

        source_lines = new_source.splitlines(keepends=True)

        if edit_mode == "replace":
            cells[idx]["source"] = source_lines
        elif edit_mode == "delete":
            cells.pop(idx)
        elif edit_mode in ("insert_above", "insert_below"):
            insert_idx = idx if edit_mode == "insert_above" else idx + 1
            new_cell: dict[str, Any] = {
                "cell_type": cell_type,
                "source": source_lines,
                "metadata": {},
                "outputs": [] if cell_type == "code" else [],
                "execution_count": None,
            }
            cells.insert(insert_idx, new_cell)

        nb["cells"] = cells
        Path(nb_path).write_text(json.dumps(nb, indent=1), encoding="utf-8")
        return [{"type": "text", "text": f"Notebook {nb_path} updated (cell {cell_id}, mode={edit_mode})."}]


notebook_edit_tool = NotebookEditTool()
