from __future__ import annotations

from typing import Protocol


class ObjectStore(Protocol):
    def put_csv(self, content: str) -> str:
        """Guarda el CSV y devuelve su URI."""


class PipelineRunner(Protocol):
    def start(self, input_path: str, load_date: str) -> str:
        """Arranca la orquestación y devuelve el identificador de la ejecución."""
