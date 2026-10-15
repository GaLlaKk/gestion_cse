import json
from pathlib import Path

def check_jsonl(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue  # Skip empty lines
            try:
                json.loads(line)
            except json.JSONDecodeError as e:
                print(f"Error on line {i}: {e}")

check_jsonl(Path(__file__).resolve().parent / "donnees" / "services_origin.jsonl")
