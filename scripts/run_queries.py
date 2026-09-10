"""Ejecuta en SQLite las cinco consultas analíticas y muestra resultados reales."""

import json
import sqlite3
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config.json"
SQL_FILE = ROOT / "sql" / "consultas.sql"


def main():
    with CONFIG.open(encoding="utf-8") as file:
        config = json.load(file)

    statements = [statement.strip() for statement in SQL_FILE.read_text(encoding="utf-8").split(";") if statement.strip()]
    if len(statements) != 5:
        raise ValueError(f"Se esperaban 5 consultas y se encontraron {len(statements)}")

    database = ROOT / config["paths"]["database"]
    with sqlite3.connect(database) as connection:
        for number, statement in enumerate(statements, start=1):
            result = pd.read_sql_query(statement, connection)
            print(f"\nCONSULTA {number} — {len(result)} filas")
            print(result.to_string(index=False))


if __name__ == "__main__":
    main()
