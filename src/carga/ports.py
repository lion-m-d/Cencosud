from __future__ import annotations

from typing import Protocol


class ObjectStore(Protocol):
    def put_csv(self, content: str, file_name: str) -> tuple[str, str]:
        """Guarda el CSV con su nombre y devuelve la URI y el nombre usado."""


class PipelineRunner(Protocol):
    def start(self, input_path: str, load_date: str, file_name: str) -> str:
        """Arranca la orquestación y devuelve el identificador de la ejecución."""
