"""Adaptadores em memória: testes e execução local sem nenhum serviço externo."""
from __future__ import annotations

import copy
import threading

from ..ports import ModelUnavailable


class MemoryEventStore:
    def __init__(self):
        self._streams: dict[str, list[dict]] = {}
        self._index: dict[str, dict] = {}
        self._lock = threading.Lock()

    def append(self, stream: str, event: dict) -> dict:
        with self._lock:
            evs = self._streams.setdefault(stream, [])
            ev = {**copy.deepcopy(event), "seq": len(evs) + 1}
            evs.append(ev)
            return copy.deepcopy(ev)

    def list(self, stream: str) -> list[dict]:
        return copy.deepcopy(self._streams.get(stream, []))

    def index(self, stream: str, summary: dict) -> None:
        self._index[stream] = copy.deepcopy(summary)

    def streams(self) -> list[dict]:
        return copy.deepcopy(list(self._index.values()))


class MemoryKV:
    def __init__(self):
        self._d: dict[str, dict] = {}
        self._lock = threading.Lock()

    def get(self, key):
        return copy.deepcopy(self._d.get(key))

    def put(self, key, value):
        self._d[key] = copy.deepcopy(value)

    def put_if_absent(self, key, value) -> bool:
        with self._lock:
            if key in self._d:
                return False
            self._d[key] = copy.deepcopy(value)
            return True


class MemoryAudit:
    def __init__(self):
        self.events: list[dict] = []

    def write(self, event):
        self.events.append(copy.deepcopy(event))


class NoModel:
    """Modo 'modelo indisponível' (NFR Reliability 2): só os geradores determinísticos rodam."""
    name = "none"

    def suggest(self, context, cap):
        raise ModelUnavailable("Nenhum modelo configurado neste ambiente")


class FakeModel:
    """Modelo de teste: devolve sugestões fixas e permite testar o filtro de números."""
    name = "fake"

    def __init__(self, suggestions=None, tokens=42):
        self.suggestions = suggestions or [{"title": "Rever R006 junto com R005",
                                            "text": "Investigar se o comprometimento (R006) compensa a renda mais alta exigida em R005.",
                                            "ruleRefs": ["R005", "R006"]}]
        self.tokens = tokens

    def suggest(self, context, cap):
        return copy.deepcopy(self.suggestions[:cap]), self.tokens


class ThreadDispatcher:
    """Executa o job fora da requisição (equivalente local do self-invoke assíncrono da Lambda)."""

    def __init__(self, handler=None, synchronous=False):
        self.handler = handler
        self.synchronous = synchronous

    def dispatch(self, job):
        if self.synchronous:
            self.handler(job)
        else:
            threading.Thread(target=self.handler, args=(job,), daemon=True).start()
