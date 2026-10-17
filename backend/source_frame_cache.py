"""Run-local reuse of exact decoded source pixels, never identity or decisions."""
from collections import OrderedDict
from contextvars import ContextVar
from pathlib import Path
import math
import threading

CURRENT = ContextVar("source_frame_cache", default=None)


class SourceFrameCache:
    def __init__(self, max_bytes=192 * 1024 * 1024, max_entries=96):
        self.max_bytes = max(0, int(max_bytes))
        self.max_entries = max(0, int(max_entries))
        self._frames = OrderedDict()
        self._aliases = {}
        self._bytes = 0
        self._lock = threading.RLock()
        self.hits = self.misses = self.evictions = self.read_batches = 0

    def read(self, video_path, requested, loader):
        wanted = sorted({max(0, int(round(ms))) for ms in requested
                         if isinstance(ms, (int, float)) and not isinstance(ms, bool)
                         and math.isfinite(ms)})
        if not wanted:
            return {}
        try:
            path = Path(video_path)
            st = path.stat()
            source = (str(path.resolve()), st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns)
        except OSError:
            return loader(video_path, wanted)
        # Serialize misses only within this analysis; other reports own their
        # own cache. Return copies so legacy image consumers remain isolated.
        with self._lock:
            result, missing = {}, []
            for ms in wanted:
                key = self._aliases.get((source, ms))
                if key in self._frames:
                    actual, pixels = self._frames[key]
                    self._frames.move_to_end(key)
                    result[ms] = (actual, pixels.copy())
                    self.hits += 1
                else:
                    missing.append(ms)
                    self.misses += 1
            if not missing:
                return result
            self.read_batches += 1
            decoded = loader(video_path, missing)
            for ms, value in decoded.items():
                actual, pixels = value
                result[ms] = value
                if not self.max_entries or pixels.nbytes > self.max_bytes:
                    continue
                key = (source, actual)
                if key not in self._frames:
                    while self._frames and (len(self._frames) >= self.max_entries
                                           or self._bytes + pixels.nbytes > self.max_bytes):
                        old, (_pts, image) = self._frames.popitem(last=False)
                        self._bytes -= image.nbytes
                        self._aliases = {alias: target for alias, target in self._aliases.items() if target != old}
                        self.evictions += 1
                    saved = pixels.copy()
                    saved.flags.writeable = False
                    self._frames[key] = (actual, saved)
                    self._bytes += saved.nbytes
                # Bound aliases too, including many requests for one frame.
                if len(self._aliases) >= self.max_entries * 4:
                    self._aliases.pop(next(iter(self._aliases)))
                self._aliases[(source, ms)] = key
            return {ms: result[ms] for ms in wanted if ms in result}

    def metrics(self):
        with self._lock:
            return {"hits": self.hits, "misses": self.misses, "read_batches": self.read_batches,
                    "evictions": self.evictions, "entries": len(self._frames),
                    "pixel_bytes": self._bytes, "max_pixel_bytes": self.max_bytes,
                    "scope": "RUN_LOCAL_EXACT_SOURCE_PIXELS"}
