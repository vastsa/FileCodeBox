"""过期清理任务游标分批行为。

验证超过单批上限的记录仍能在同一轮里全部处理，且单条删除失败不会让
循环在同一批上反复重试（游标必须前进）。
"""
import datetime
from unittest.mock import patch

import pytest

from apps.base.models import FileCodes, PresignUploadSession
from apps.base.tasks import clean_expired_presign_sessions, delete_expire_files
from core.utils import get_now


class _SleepSentinel(Exception):
    pass


async def _run_round(tmp_path):
    def _sleep(_seconds):
        raise _SleepSentinel

    with patch("apps.base.tasks.data_root", tmp_path), patch(
        "core.storage.local.data_root", tmp_path
    ), patch("apps.base.tasks.asyncio.sleep", side_effect=_sleep):
        with pytest.raises(_SleepSentinel):
            await delete_expire_files()


async def _make_expired(code: str, tmp_path, now):
    file_path = "share/data/2026/01/01"
    path = tmp_path / file_path / f"uuid-{code}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"payload")
    return await FileCodes.create(
        code=code,
        file_path=file_path,
        uuid_file_name=f"uuid-{code}",
        size=1,
        expired_at=now - datetime.timedelta(days=1),
    )


@pytest.mark.asyncio
async def test_more_than_one_batch_all_cleaned(db, tmp_path, monkeypatch):
    monkeypatch.setattr("apps.base.tasks.CLEANUP_BATCH_SIZE", 2)
    now = await get_now()
    codes = [f"batch{i}" for i in range(5)]
    for code in codes:
        await _make_expired(code, tmp_path, now)
    await FileCodes.create(
        code="alive",
        file_path="share/data/2026/01/01",
        uuid_file_name="uuid-alive",
        expired_at=now + datetime.timedelta(days=30),
    )

    await _run_round(tmp_path)

    assert await FileCodes.all().count() == 1
    assert (await FileCodes.all().first()).code == "alive"


@pytest.mark.asyncio
async def test_failed_row_does_not_block_progress(db, tmp_path, monkeypatch):
    monkeypatch.setattr("apps.base.tasks.CLEANUP_BATCH_SIZE", 1)
    now = await get_now()
    for code in ["bad", "good1", "good2"]:
        await _make_expired(code, tmp_path, now)

    real_delete = FileCodes.delete

    async def flaky_delete(self, using_db=None):
        if self.code == "bad":
            raise RuntimeError("delete boom")
        return await real_delete(self, using_db=using_db)

    monkeypatch.setattr(FileCodes, "delete", flaky_delete)

    await _run_round(tmp_path)

    assert await FileCodes.filter(code="bad").exists()
    assert not await FileCodes.filter(code="good1").exists()
    assert not await FileCodes.filter(code="good2").exists()


@pytest.mark.asyncio
async def test_failed_presign_delete_does_not_block_progress(db, tmp_path, monkeypatch):
    monkeypatch.setattr("apps.base.tasks.CLEANUP_BATCH_SIZE", 1)
    now = await get_now()
    for uid in ["bad-p", "good-p1", "good-p2"]:
        await PresignUploadSession.create(
            upload_id=uid,
            file_name="f.bin",
            file_size=1,
            save_path="share/data/2026/01/01/f.bin",
            mode="proxy",
            expires_at=now - datetime.timedelta(minutes=5),
        )

    real_delete = PresignUploadSession.delete

    async def flaky_delete(self, using_db=None):
        if self.upload_id == "bad-p":
            raise RuntimeError("presign delete boom")
        return await real_delete(self, using_db=using_db)

    monkeypatch.setattr(PresignUploadSession, "delete", flaky_delete)

    def _sleep(_seconds):
        raise _SleepSentinel

    with patch("apps.base.tasks.data_root", tmp_path), patch(
        "core.storage.local.data_root", tmp_path
    ), patch("apps.base.tasks.asyncio.sleep", side_effect=_sleep):
        with pytest.raises(_SleepSentinel):
            await clean_expired_presign_sessions()

    assert await PresignUploadSession.filter(upload_id="bad-p").exists()
    assert not await PresignUploadSession.filter(upload_id="good-p1").exists()
    assert not await PresignUploadSession.filter(upload_id="good-p2").exists()
