from pathlib import Path
from typing import Protocol


class ObjectStore(Protocol):
    durable: bool
    def put(self, key: str, source: Path): ...
    def download(self, key: str, destination: Path, max_bytes: int): ...
    def verify(self, key: str, digest: str, size: int): ...


class Extractor(Protocol):
    def extract(self, source: Path, media_type: str) -> dict: ...


class Analyst(Protocol):
    def analyze(self, workspace: Path, request: dict, checkpoint) -> dict: ...


class Scanner(Protocol):
    def run(self, state: Path, rules, session: str, mode: str, research: bool): ...
