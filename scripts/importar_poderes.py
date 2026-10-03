"""Converte arquivos de texto em registros de poderes usando Groq."""

import json
import shutil
import time
from pathlib import Path
from typing import Any

from ollama import chat
from unidecode import unidecode

from mm_ia.config import DATA_DIR, OLLAMA_MODEL
from mm_ia.prompts.prompt_poderes_feitos import PROMPT

INPUT_DIR = DATA_DIR / "poderes_txt"
PROCESSED_DIR = DATA_DIR / "processados"
ERROR_DIR = DATA_DIR / "erro"
OUTPUT_FILE = DATA_DIR / "poderes_prontos.json"
MAX_ATTEMPTS = 5
RETRY_DELAY_SECONDS = 8


def _load_records() -> dict[str, Any]:
    if not OUTPUT_FILE.exists():
        return {}
    with OUTPUT_FILE.open(encoding="utf-8") as source:
        return json.load(source)


def _save_records(records: dict[str, Any]) -> None:
    with OUTPUT_FILE.open("w", encoding="utf-8") as destination:
        json.dump(records, destination, ensure_ascii=False, indent=2)


def _record_key(name: str) -> str:
    return unidecode(name).lower().strip().replace(" ", "_")


def _structure(name: str, text: str) -> dict[str, Any]:
    response = chat(
        model=OLLAMA_MODEL,
        messages=[
            {"role": "system", "content": PROMPT},
            {"role": "user", "content": f"Poder: {name}\n\nTexto:\n{text}"},
        ],
        options={"temperature": 0},
        format="json",
        think=False,
    )
    content = response.message.content
    if not content:
        raise ValueError("A API retornou uma resposta vazia.")
    return json.loads(content)


def import_texts() -> None:
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    ERROR_DIR.mkdir(parents=True, exist_ok=True)

    records = _load_records()
    files = sorted(INPUT_DIR.glob("*.txt"))
    print(f"{len(files)} arquivos encontrados.")

    for file_path in files:
        key = _record_key(file_path.stem)
        if key in records:
            print(f"[PULADO] {file_path.stem} já existe.")
            shutil.move(str(file_path), str(PROCESSED_DIR / file_path.name))
            continue

        succeeded = False
        text = file_path.read_text(encoding="utf-8")
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                records[key] = _structure(file_path.stem, text)
                _save_records(records)
                shutil.move(str(file_path), str(PROCESSED_DIR / file_path.name))
                print(f"[OK] {file_path.stem}")
                succeeded = True
                break
            except Exception as error:
                print(f"[ERRO] {file_path.stem}: {error}")
                if attempt < MAX_ATTEMPTS:
                    time.sleep(RETRY_DELAY_SECONDS)

        if not succeeded:
            shutil.move(str(file_path), str(ERROR_DIR / file_path.name))


if __name__ == "__main__":
    import_texts()
