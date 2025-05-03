# json_store.py
import json, threading
from pathlib import Path
from typing import Any, Dict, Optional

class JSONStore(dict):
    """
    A dict that transparently persists itself to a JSON file.
    Flushes on every mutating op; thread‑safe enough for a toy server.
    """
    _lock = threading.Lock()

    def __init__(self, file_path: str, initial: Optional[Dict[str, Any]] = None):
        self._path = Path(file_path)
        if self._path.exists():
            data = json.loads(self._path.read_text() or "{}")
        else:
            data = initial or {}
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps(data, indent=2))
        super().__init__(data)

    # ---------- internal ----------
    def _flush(self) -> None:
        with self._lock:
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self, indent=2))
            tmp.replace(self._path)

    # ---------- mutating methods ----------
    def __setitem__(self, k, v):  super().__setitem__(k, v); self._flush()
    def __delitem__(self, k):     super().__delitem__(k);   self._flush()
    def clear(self):              super().clear();          self._flush()
    def pop(self, k, d=None):
        result = super().pop(k, d); self._flush(); return result
    def popitem(self):
        result = super().popitem(); self._flush(); return result
    def update(self, *a, **kw):   super().update(*a, **kw); self._flush()
    def setdefault(self, k, d=None):
        if k not in self: super().setdefault(k, d); self._flush()
        return self[k]
