"""Papéis e identidade (R15.6). Módulo próprio para o agente usar sem import circular."""
from __future__ import annotations

from dataclasses import dataclass

ROLES_WRITE = {"Policy Specialist"}
ROLES_DECIDE = {"Policy Specialist", "Risk Approver"}
ROLES_READ = {"Policy Specialist", "Risk Approver", "Data Analyst", "Viewer"}


class Forbidden(Exception):
    pass


@dataclass
class Actor:
    id: str
    roles: set

    def require(self, allowed: set, action: str):
        if not (self.roles & allowed):
            raise Forbidden(f"Seu perfil ({', '.join(sorted(self.roles)) or 'nenhum'}) não pode {action}")
