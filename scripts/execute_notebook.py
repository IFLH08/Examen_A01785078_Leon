"""Ordena y ejecuta el notebook de exploración con el entorno del proyecto."""

import asyncio
import os
import sys
import warnings
from pathlib import Path

import nbformat
from nbclient import NotebookClient


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "notebooks" / "01_exploracion.ipynb"


def order_join_question(notebook):
    """Coloca la pregunta del JOIN después del análisis de nulos (pregunta 2)."""
    ids = [cell.get("id") for cell in notebook.cells]
    join_ids = ["join-ingenuo", "join-interpretacion"]
    if not all(cell_id in ids for cell_id in join_ids):
        return

    join_cells = []
    for cell_id in join_ids:
        index = next(i for i, cell in enumerate(notebook.cells) if cell.get("id") == cell_id)
        join_cells.append(notebook.cells.pop(index))

    target = next(
        i for i, cell in enumerate(notebook.cells)
        if cell.get("id") == "368c3f32"
    ) + 1
    notebook.cells[target:target] = join_cells


def main():
    if sys.platform == "win32":
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    os.environ.setdefault("IPYTHONDIR", str(ROOT / "data" / ".ipython"))

    with NOTEBOOK.open(encoding="utf-8") as file:
        notebook = nbformat.read(file, as_version=4)

    order_join_question(notebook)
    client = NotebookClient(
        notebook,
        timeout=300,
        kernel_name="python3",
        resources={"metadata": {"path": str(ROOT)}},
    )
    client.execute()

    with NOTEBOOK.open("w", encoding="utf-8", newline="\n") as file:
        nbformat.write(notebook, file)

    print(f"Notebook ejecutado: {NOTEBOOK.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
