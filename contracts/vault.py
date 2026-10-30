"""Vault calls: core <-> vault."""
from datetime import datetime
from typing import Protocol

from pydantic import BaseModel


class Receipt(BaseModel):
    portal_id: str
    scheme_id: str | None = None
    receipt_number: str
    submitted_at: datetime


class VaultCalls(Protocol):
    def put_portal_id(self, owner: str, portal_id: str, value: str) -> None: ...

    def get_portal_id(self, owner: str, portal_id: str) -> str | None: ...

    def put_receipt(self, owner: str, receipt: Receipt) -> None: ...

    def list_receipts(self, owner: str) -> list[Receipt]: ...
