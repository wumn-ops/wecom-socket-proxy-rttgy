"""WebSocket 长连接运行时状态（供 /health 与主动推送使用）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class ConnectionState:
    connected: bool = False
    authenticated: bool = False
    reconnect_attempt: int = 0
    last_error: str = ""
    last_chat_id: str = ""
    last_userid: str = ""
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc)

    def snapshot(self) -> dict[str, object]:
        return {
            "connected": self.connected,
            "authenticated": self.authenticated,
            "reconnect_attempt": self.reconnect_attempt,
            "last_error": self.last_error or None,
            "last_chat_id": self.last_chat_id or None,
            "last_userid": self.last_userid or None,
            "updated_at": self.updated_at.isoformat(),
        }


state = ConnectionState()
