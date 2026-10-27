"""OpenDAL 合并/上传的流式化契约（不依赖 opendal SDK）。

`core.storage.opendal` 只在构造函数里 import SDK，因此可以用 fake operator
钉住：优先走 open("wb") 流式写入；版本过旧时才回退整文件写入。
"""
import hashlib
import io
from types import SimpleNamespace

import pytest

from core.storage import OpenDALFileStorage


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class FakeWriter:
    def __init__(self, path, store, events):
        self.path = path
        self.store = store
        self.events = events

    async def write(self, data):
        self.events.append(("write", len(data)))
        self.store[self.path] = self.store.get(self.path, b"") + data
        return len(data)

    async def close(self):
        self.events.append(("close",))


class FakeOperator:
    def __init__(self, files=None, support_open=True):
        self.store = dict(files or {})
        self.support_open = support_open
        self.events = []

    async def open(self, path, mode):
        if not self.support_open:
            raise AttributeError("open")
        assert mode == "wb"
        return FakeWriter(path, self.store, self.events)

    async def read(self, path):
        try:
            return self.store[path]
        except KeyError as exc:
            raise FileNotFoundError(path) from exc

    async def write(self, path, data):
        self.events.append(("fallback_write", len(data)))
        self.store[path] = data

    async def delete(self, path):
        self.events.append(("delete", path))
        self.store.pop(path, None)


def _storage(operator) -> OpenDALFileStorage:
    storage = OpenDALFileStorage.__new__(OpenDALFileStorage)
    storage.operator = operator
    return storage


def _chunk_files(chunks):
    base = "share/data/2026/01/01/uuid/chunks/upload-1"
    return {f"{base}/{index}.part": data for index, data in chunks.items()}


def _records(chunks):
    return {
        index: SimpleNamespace(chunk_hash=_sha(data))
        for index, data in chunks.items()
    }


async def test_merge_uses_streaming_writer():
    chunks = {0: b"aaaa", 1: b"bbbbbb"}
    operator = FakeOperator(_chunk_files(chunks))
    storage = _storage(operator)

    save_path = "share/data/2026/01/01/uuid/merged.bin"
    out, digest = await storage.merge_chunks(
        "upload-1", 2, 4, save_path, _records(chunks)
    )

    merged = b"aaaa" + b"bbbbbb"
    assert out == save_path
    assert digest == _sha(merged)
    assert operator.store[save_path] == merged
    assert ("fallback_write", len(merged)) not in operator.events
    assert [event for event in operator.events if event[0] == "write"] == [
        ("write", 4),
        ("write", 6),
    ]
    assert ("close",) in operator.events


async def test_merge_hash_mismatch_removes_partial_object():
    chunks = {0: b"aaaa"}
    operator = FakeOperator(_chunk_files(chunks))
    storage = _storage(operator)
    records = {0: SimpleNamespace(chunk_hash=_sha(b"wrong"))}

    save_path = "share/data/2026/01/01/uuid/merged.bin"
    with pytest.raises(ValueError, match="哈希不匹配"):
        await storage.merge_chunks("upload-1", 1, 4, save_path, records)

    assert save_path not in operator.store
    assert ("delete", save_path) in operator.events


async def test_merge_falls_back_when_open_unsupported():
    chunks = {0: b"aaaa", 1: b"bbbb"}
    operator = FakeOperator(_chunk_files(chunks), support_open=False)
    storage = _storage(operator)

    save_path = "share/data/2026/01/01/uuid/merged.bin"
    _, digest = await storage.merge_chunks(
        "upload-1", 2, 4, save_path, _records(chunks)
    )

    merged = b"aaaabbbb"
    assert digest == _sha(merged)
    assert operator.store[save_path] == merged
    assert ("fallback_write", len(merged)) in operator.events


async def test_save_file_streams_in_bounded_blocks():
    payload = b"x" * (600 * 1024)
    operator = FakeOperator()
    storage = _storage(operator)

    await storage.save_file(io.BytesIO(payload), "share/data/big.bin")

    assert operator.store["share/data/big.bin"] == payload
    writes = [event[1] for event in operator.events if event[0] == "write"]
    assert len(writes) >= 2
    assert all(size <= 256 * 1024 for size in writes)


async def test_save_file_falls_back_when_open_unsupported():
    payload = b"y" * 1024
    operator = FakeOperator(support_open=False)
    storage = _storage(operator)

    await storage.save_file(io.BytesIO(payload), "share/data/fallback.bin")

    assert operator.store["share/data/fallback.bin"] == payload
    assert ("fallback_write", len(payload)) in operator.events
