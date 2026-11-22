"""多线程下载、断点续传、SHA256 校验。

线程只往 queue 塞事件，Tk 主线程负责读 queue 刷新 UI。
"""
from __future__ import annotations

import hashlib
import json
import os
import queue
import re
import shutil
import threading
import time
import urllib.error
import urllib.request

USER_AGENT = "SpellCardHomework/1.0"


class DownloadJob:
    def __init__(self, url: str, dest: str, expected_sha256: str = "",
                 max_threads: int = 8, timeout: float = 20.0):
        self.url = str(url or "")
        self.dest = os.path.abspath(dest)
        self.expected_sha256 = (expected_sha256 or "").strip().lower()
        self.max_threads = max(1, min(32, int(max_threads or 8)))
        self.timeout = max(5.0, float(timeout or 20))
        self.events: "queue.Queue[dict]" = queue.Queue()

        self.part = self.dest + ".part"
        self.manifest_path = self.part + ".json"
        self._lock = threading.RLock()
        self._pause = threading.Event()
        self._cancel = threading.Event()
        self._running = False
        self._thread: threading.Thread | None = None
        self._error = ""
        self._prepared = False
        self._total = 0
        self._etag = ""
        self._url = self.url
        self._ranges = False
        self._threads = 1
        self._segments: list[dict] = []
        self._downloaded = 0
        self._last_emit = 0.0
        self._done = False

    # ------------------------------------------------------------ 对外控制
    def start(self) -> None:
        if self._running or self._done:
            return
        self._cancel.clear()
        self._error = ""
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def pause(self) -> None:
        self._pause.set()

    def resume(self) -> None:
        if self._done or self._cancel.is_set():
            return
        self._pause.clear()
        self.start()

    def cancel(self) -> None:
        self._cancel.set()
        self._pause.clear()
        if not self._running:
            self._cleanup()

    @property
    def threads(self) -> int:
        return self._threads

    @property
    def total(self) -> int:
        return self._total

    @property
    def downloaded(self) -> int:
        return self._downloaded

    @property
    def segments(self) -> list[dict]:
        with self._lock:
            return [dict(s) for s in self._segments]

    # ------------------------------------------------------------ 事件
    def _emit(self, kind: str, **data) -> None:
        data["type"] = kind
        self.events.put(data)

    def _emit_progress(self, force: bool = False) -> None:
        now = time.time()
        if not force and now - self._last_emit < 0.15:
            return
        self._last_emit = now
        with self._lock:
            segs = [dict(s) for s in self._segments]
            done = sum(int(s.get("done") or 0) for s in segs)
            self._downloaded = done
        self._emit("progress", done=done, total=self._total,
                   threads=self._threads, segments=segs)

    # ------------------------------------------------------------ 主流程
    def _run(self) -> None:
        try:
            if not self._prepared:
                self._prepare()
            if self._cancel.is_set():
                self._cleanup()
                self._emit("canceled")
                return
            if self._pause.is_set():
                self._save_manifest()
                self._emit("paused")
                return
            if self._error:
                self._emit("error", code=self._error)
                return

            self._prepare_segments()
            self._spawn_workers()
            self._join_workers()
            if self._cancel.is_set():
                self._cleanup()
                self._emit("canceled")
                return
            if self._pause.is_set():
                self._save_manifest()
                self._emit("paused")
                return
            if self._error:
                self._emit("error", code=self._error)
                return
            if any(int(s.get("done") or 0) < int(s["end"]) - int(s["start"]) + 1
                   for s in self._segments):
                self._emit("error", code="incomplete")
                return
            self._finish()
        except Exception as e:
            self._error = f"exception:{e}"
            self._emit("error", code=self._error)
        finally:
            self._running = False

    def _prepare(self) -> None:
        self._emit("status", text="正在向人间之里打听号外大小…")
        headers = {"User-Agent": USER_AGENT}
        total = 0
        try:
            req = urllib.request.Request(self.url, headers=headers, method="HEAD")
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                self._url = r.geturl() or self.url
                total = int(r.headers.get("Content-Length") or 0)
                self._etag = str(r.headers.get("ETag") or
                                 r.headers.get("Last-Modified") or "")
                self._ranges = "bytes" in str(
                    r.headers.get("Accept-Ranges") or "").lower()
        except Exception:
            # 少数 CDN 拒绝 HEAD，用 Range: 0-0 探一次
            req = urllib.request.Request(
                self.url, headers={**headers, "Range": "bytes=0-0"})
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                self._url = r.geturl() or self.url
                cr = str(r.headers.get("Content-Range") or "")
                m = re.search(r"/(\d+)$", cr)
                total = int(m.group(1)) if m else int(
                    r.headers.get("Content-Length") or 0)
                self._etag = str(r.headers.get("ETag") or
                                 r.headers.get("Last-Modified") or "")
                self._ranges = True
        if total <= 0:
            raise RuntimeError("无法读取安装包大小")

        self._total = total
        try:
            free = shutil.disk_usage(os.path.dirname(self.dest) or ".").free
            if free < total + 5 * 1024 * 1024:
                raise RuntimeError("disk")
        except OSError:
            pass
        if total < 4 * 1024 * 1024 or not self._ranges:
            self._threads = 1
        else:
            chunks = max(1, total // (1024 * 1024))
            self._threads = min(self.max_threads, chunks, 32)
        self._downloaded = 0

        # 载入可用的断点
        data = None
        try:
            with open(self.manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = None
        try:
            part_ok = (os.path.exists(self.part) and
                       os.path.getsize(self.part) == total)
        except Exception:
            part_ok = False
        ok = (
            part_ok
            and isinstance(data, dict)
            and int(data.get("total") or 0) == total
            and str(data.get("etag") or "") == self._etag
            and str(data.get("url") or "") == self._url
            and isinstance(data.get("segments"), list)
            and len(data.get("segments") or []) > 0
        )
        if ok:
            self._segments = data["segments"]
            self._threads = max(1, min(int(data.get("threads") or self._threads), 32))
            self._downloaded = sum(int(s.get("done") or 0) for s in self._segments)
        else:
            try:
                if os.path.exists(self.part):
                    os.remove(self.part)
            except Exception:
                pass
            self._segments = self._make_segments(self._threads)
            self._downloaded = 0
        os.makedirs(os.path.dirname(self.dest), exist_ok=True)
        # 预分配
        if not os.path.exists(self.part) or os.path.getsize(self.part) != total:
            with open(self.part, "wb") as f:
                f.truncate(total)
        self._save_manifest()
        self._prepared = True
        self._emit("meta", total=total, threads=self._threads,
                   segments=[dict(s) for s in self._segments],
                   etag=self._etag)
        self._emit_progress(force=True)

    def _make_segments(self, n: int) -> list[dict]:
        n = max(1, min(n, 32))
        size = self._total
        base = size // n
        out = []
        start = 0
        for i in range(n):
            end = size - 1 if i == n - 1 else start + base - 1
            if end >= start:
                out.append({"start": start, "end": end, "done": 0})
            start = end + 1
        return out

    def _prepare_segments(self) -> None:
        if self._segments:
            return
        self._segments = self._make_segments(self._threads)

    def _spawn_workers(self) -> None:
        self._workers = []
        for i in range(len(self._segments)):
            t = threading.Thread(target=self._worker, args=(i,), daemon=True)
            self._workers.append(t)
            t.start()

    def _join_workers(self) -> None:
        for t in getattr(self, "_workers", []):
            t.join()
        self._workers = []

    # ------------------------------------------------------------ 分片下载
    def _worker(self, idx: int) -> None:
        seg = self._segments[idx]
        attempt = 0
        while not self._cancel.is_set() and not self._pause.is_set():
            start = int(seg["start"]) + int(seg["done"])
            end = int(seg["end"])
            if start > end:
                return
            try:
                self._download_part(idx, start, end)
                return
            except Exception as e:
                if self._cancel.is_set() or self._pause.is_set():
                    return
                attempt += 1
                if attempt >= 3:
                    with self._lock:
                        self._error = f"segment:{idx}:{e}"
                    return
                time.sleep((1, 3, 7)[min(attempt - 1, 2)])

    def _download_part(self, idx: int, start: int, end: int) -> None:
        seg = self._segments[idx]
        headers = {"User-Agent": USER_AGENT, "Range": f"bytes={start}-{end}"}
        req = urllib.request.Request(self._url, headers=headers)
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            code = int(getattr(r, "status", 200) or 200)
            if code != 206 and (start > 0 or end < self._total - 1):
                raise RuntimeError("服务器不支持断点续传")
            with open(self.part, "r+b") as f:
                f.seek(start)
                left = end - start + 1
                while left > 0:
                    if self._cancel.is_set() or self._pause.is_set():
                        return
                    chunk = r.read(min(64 * 1024, left))
                    if not chunk:
                        break
                    f.write(chunk)
                    seg["done"] = int(seg["done"]) + len(chunk)
                    left -= len(chunk)
                    self._emit_progress()
                if left > 0 and not (self._cancel.is_set() or self._pause.is_set()):
                    raise RuntimeError("分片未下载完整")

    # ------------------------------------------------------------ 完成/校验
    def _finish(self) -> None:
        self._emit("status", text="号外到手，正在验明正身…")
        sha = self._sha256(self.part)
        if self.expected_sha256:
            if sha.lower() != self.expected_sha256:
                self._cleanup()
                self._emit("error", code="sha256")
                return
        os.replace(self.part, self.dest)
        try:
            os.remove(self.manifest_path)
        except Exception:
            pass
        self._done = True
        self._emit("done", path=self.dest, sha256=sha,
                   verified=bool(self.expected_sha256), total=self._total)

    @staticmethod
    def _sha256(path: str) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            while True:
                b = f.read(1024 * 1024)
                if not b:
                    break
                h.update(b)
        return h.hexdigest()

    # ------------------------------------------------------------ 辅助
    def _save_manifest(self) -> None:
        try:
            with self._lock:
                data = {
                    "url": self._url,
                    "total": self._total,
                    "etag": self._etag,
                    "threads": self._threads,
                    "segments": [dict(s) for s in self._segments],
                }
            os.makedirs(os.path.dirname(self.manifest_path), exist_ok=True)
            with open(self.manifest_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _cleanup(self) -> None:
        self._prepared = False
        with self._lock:
            self._segments = []
        for p in (self.part, self.manifest_path):
            try:
                if os.path.exists(p):
                    os.remove(p)
            except Exception:
                pass
