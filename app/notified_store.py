"""已发送上线测试提醒的记录 ID 持久化（每条仅提醒一次）。"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from threading import Lock

logger = logging.getLogger(__name__)


class NotifiedRecordStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = Lock()
        self._record_ids: set[str] = set()
        self._load()

    def contains(self, record_id: str) -> bool:
        with self._lock:
            return record_id in self._record_ids

    def add(self, record_id: str) -> None:
        with self._lock:
            if record_id in self._record_ids:
                return
            self._record_ids.add(record_id)
            self._save()

    def count(self) -> int:
        with self._lock:
            return len(self._record_ids)

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            logger.warning("读取通知状态文件失败 path=%s err=%s", self._path, exc)
            return
        ids = data.get("record_ids") or []
        if isinstance(ids, list):
            self._record_ids = {str(item) for item in ids if item}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"record_ids": sorted(self._record_ids)}
        self._path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
