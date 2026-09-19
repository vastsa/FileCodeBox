"""寄件授权回归：游客关闭、身份隔离、并发配额、续期及迁移不公开私有文件。"""

import asyncio
import importlib
import unittest
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from tortoise import connections

from apps.admin.dependencies import create_token, verify_token
from apps.base.models import DeliveryCode, FileCodes, StorageReservation
from apps.base.quota import get_storage_usage, reserve_storage
from apps.base.upload_access import UploadAccess, prepare_upload
from apps.base.upload_sessions import abort_upload, commit_delivery
from apps.base.views import share_api, chunk_api, presign_api, get_code_file_by_code
from apps.delivery.schemas import CreateDeliveryCode, UpdateDeliveryCode, BatchDeliveryCodes
from apps.delivery.services import create_code, verify_code, refresh_session, update_code, list_codes, batch_codes
from apps.delivery.views import admin_api, public_api
from core.settings import settings
from core.utils import get_now
from tests.helpers import init_memory_db, close_db


class DeliveryAuthorizationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.original = dict(settings.user_config)
        settings.open_upload = 0
        settings.jwt_secret = "delivery-regression-test-secret"
        settings.file_storage = "local"
        settings.storage_limit = 100
        settings.upload_size = 1024
        settings.expire_style = ["day", "forever"]
        self.directory = TemporaryDirectory()
        self.storage_patch = patch("core.storage.data_root", Path(self.directory.name))
        self.storage_patch.start()
        await init_memory_db()
        # 限流器是进程级对象，每个用例使用全新访问窗口，避免前一用例消耗本例额度。
        from apps.base.utils import ip_limit
        for limiter in ip_limit.values():
            limiter.ips.clear()
        app = FastAPI()
        for router in (share_api, chunk_api, presign_api, admin_api, public_api):
            app.include_router(router)
        self.client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    async def asyncTearDown(self):
        await self.client.aclose()
        await close_db()
        self.storage_patch.stop()
        self.directory.cleanup()
        settings.user_config = self.original

    async def make_code(self, code="DeliveryTest1", max_uploads=2, **extra):
        result = await create_code(CreateDeliveryCode(
            name="测试收件", code=code, storage_type="local", target_path="inbox",
            expires_at=await get_now() + timedelta(days=1), max_uploads=max_uploads, **extra,
        ))
        session = await verify_code(code)
        return result["item"]["id"], {"Authorization": "Bearer " + session["token"]}

    async def test_guest_closed_delivery_works_and_admin_isolation(self):
        code_id, headers = await self.make_code()
        denied = await self.client.post("/share/text/", data={"text": "hello"})
        self.assertEqual(denied.status_code, 403)
        sent = await self.client.post("/share/text/", data={"text": "hello"}, headers=headers)
        self.assertEqual(sent.status_code, 200, sent.text)
        share = await FileCodes.get(delivery_id=code_id)
        self.assertEqual(sent.json()["detail"]["code"], share.code)
        self.assertEqual(await StorageReservation.all().count(), 0)
        admin = await self.client.get("/admin/delivery/codes", headers=headers)
        self.assertEqual(admin.status_code, 401)

    async def test_final_slot_atomic_and_exhausted_code_keeps_files(self):
        code_id, headers = await self.make_code(max_uploads=1)
        results = await asyncio.gather(*[
            self.client.post("/share/text/", data={"text": "hello"}, headers=headers)
            for _ in range(4)
        ])
        self.assertEqual(sum(r.status_code == 200 for r in results), 1)
        record = await DeliveryCode.get(id=code_id)
        self.assertEqual(record.used_count, 1)
        self.assertEqual(record.reserved_count, 0)
        self.assertFalse(record.enabled)
        self.assertEqual(await FileCodes.filter(delivery_id=code_id).count(), 1)

    async def test_capacity_reservation_is_single_and_cleanup_failure_stays_charged(self):
        code_id, _ = await self.make_code()
        access = UploadAccess(code_id=code_id)
        token, _ = await prepare_upload(access, "sample.txt", 70, "quota-session")
        await reserve_storage("chunk:" + token, 70, 300)
        await reserve_storage("chunk:" + token, 70, 300)
        self.assertEqual((await get_storage_usage())["reserved"], 70)
        self.assertEqual(await StorageReservation.all().count(), 1)
        with self.assertRaises(HTTPException):
            await reserve_storage("other", 31, 300)
        with patch("apps.base.upload_sessions.get_storage", side_effect=RuntimeError("offline")):
            await abort_upload(access.record.id)
        self.assertEqual((await get_storage_usage())["reserved"], 70)
        self.assertEqual((await DeliveryCode.get(id=code_id)).reserved_count, 0)
        await abort_upload(access.record.id)
        self.assertEqual((await get_storage_usage())["reserved"], 0)

    async def test_cross_code_and_guest_cannot_access_chunk_session(self):
        code_id, headers = await self.make_code()
        _, other_headers = await self.make_code("DeliveryTest2")
        init = await self.client.post("/chunk/upload/init/", headers=headers, json={
            "file_name": "sample.txt", "file_size": 5, "chunk_size": 5, "file_hash": "hash",
        })
        self.assertEqual(init.status_code, 200, init.text)
        token = init.json()["detail"]["upload_id"]
        for identity in (other_headers, {}):
            settings.open_upload = 1
            response = await self.client.delete("/chunk/upload/" + token, headers=identity)
            self.assertEqual(response.status_code, 404, response.text)
        self.assertEqual((await DeliveryCode.get(id=code_id)).reserved_count, 1)

    async def test_refresh_preserves_session_and_revocation_invalidates_old_token(self):
        code_id, headers = await self.make_code()
        original_payload = verify_token(headers["Authorization"][7:])
        # 模拟传输经过 14 分钟，验证续期真正延长有效期且原会话不丢失。
        with patch("apps.admin.dependencies.time.time", return_value=original_payload["exp"] - 60):
            refreshed = await refresh_session(headers["Authorization"])
            self.assertGreater(verify_token(refreshed["token"])["exp"], original_payload["exp"])
        self.assertIn("token", refreshed)
        self.assertNotIn("target_path", refreshed)
        await update_code(code_id, UpdateDeliveryCode(code="ChangedCode1"))
        with self.assertRaises(HTTPException) as error:
            await refresh_session(headers["Authorization"])
        self.assertEqual(error.exception.status_code, 401)
        # 已过期令牌不能通过 refresh 接口自行复活。
        expired = create_token({"purpose": "delivery", "delivery_id": code_id}, expires_in=-1)
        response = await self.client.post("/api/delivery/refresh", headers={"Authorization": "Bearer " + expired})
        self.assertEqual(response.status_code, 401)

    async def test_list_sql_pagination_hides_secret_and_filters_tags(self):
        await self.make_code(tags=["客户", "one"])
        await self.make_code("DeliveryTest2", tags=["two"])
        result = await list_codes(page_size=1)
        self.assertEqual(result["total"], 2)
        self.assertEqual(len(result["items"]), 1)
        self.assertNotIn("code", result["items"][0])
        selected = await list_codes(tag="ONE")
        self.assertEqual(selected["total"], 1)
        self.assertEqual((await list_codes(tag="' OR 1=1 --"))["total"], 0)

    async def test_soft_delete_and_batch_update_keep_association(self):
        code_id, headers = await self.make_code()
        sent = await self.client.post("/share/text/", data={"text": "hello"}, headers=headers)
        self.assertEqual(sent.status_code, 200, sent.text)
        await batch_codes(BatchDeliveryCodes(ids=[code_id], action="update", max_uploads=5))
        await batch_codes(BatchDeliveryCodes(ids=[code_id], action="delete"))
        record = await DeliveryCode.get(id=code_id)
        self.assertTrue(record.deleted)
        self.assertEqual(record.max_uploads, 5)
        self.assertEqual(await FileCodes.filter(delivery_id=code_id).count(), 1)

    async def test_changed_code_cannot_commit_old_reservation(self):
        code_id, _ = await self.make_code()
        access = UploadAccess(code_id=code_id)
        await prepare_upload(access, "Text", 5, "old-session")
        await update_code(code_id, UpdateDeliveryCode(code="ChangedCode1"))
        with self.assertRaises(HTTPException):
            await commit_delivery(access.record, {"code": "result", "text": "hello", "size": 5})
        self.assertEqual(await FileCodes.all().count(), 0)
        self.assertEqual((await DeliveryCode.get(id=code_id)).used_count, 0)

    async def test_private_migration_never_creates_public_download(self):
        # 在真实旧迁移表上构造历史数据，迁移后再次执行验证幂等性。
        conn = connections.get("default")
        await conn.execute_query("DROP TABLE deliverycode")
        for number in (8, 9, 10, 12):
            await importlib.import_module(f"apps.base.migrations.migrations_{number:03d}").migrate()
        await conn.execute_query(
            "INSERT INTO deliveryfile (delivery_id, token, filename, stored_name, file_path, storage_type, size, status) "
            "VALUES (77, 'legacy-token', 'private.txt', 'object.txt', 'inbox', 'local', 7, 'stored')"
        )
        migration = importlib.import_module("apps.base.migrations.migrations_013")
        await migration.migrate()
        await migration.migrate()
        file = await FileCodes.get(delivery_id=77)
        self.assertTrue(file.is_private)
        self.assertFalse((await get_code_file_by_code(file.code))[0])
        self.assertFalse(await conn.execute_query_dict("SELECT name FROM sqlite_master WHERE name='deliveryfile'"))
        self.assertEqual((await get_storage_usage())["used"], 7)

    async def test_chunk_delivery_completion_retry_does_not_consume_twice(self):
        code_id, headers = await self.make_code(max_uploads=1)
        result = await self.client.post("/chunk/upload/init/", headers=headers, json={
            "file_name": "sample.txt", "file_size": 5, "chunk_size": 5, "file_hash": "hash",
        })
        token = result.json()["detail"]["upload_id"]
        part = await self.client.post(f"/chunk/upload/chunk/{token}/0", headers=headers,
                                      files={"chunk": ("part", b"hello", "application/octet-stream")})
        self.assertEqual(part.status_code, 200, part.text)
        result = await self.client.post(f"/chunk/upload/complete/{token}", headers=headers,
                                        json={"expire_style": "day", "expire_value": 1})
        self.assertEqual(result.status_code, 200, result.text)
        retry = await self.client.post(f"/chunk/upload/complete/{token}", headers=headers,
                                       json={"expire_style": "day", "expire_value": 1})
        self.assertEqual(retry.json()["detail"]["code"], result.json()["detail"]["code"])
        self.assertEqual((await DeliveryCode.get(id=code_id)).used_count, 1)
        self.assertEqual((await get_storage_usage())["used"], 5)
        download = await self.client.get("/share/select/", params={"code": result.json()["detail"]["code"]})
        self.assertEqual(download.content, b"hello")

    async def test_proxy_delivery_rejects_underreported_size(self):
        _, headers = await self.make_code()
        result = await self.client.post("/presign/upload/init", headers=headers, json={
            "file_name": "sample.txt", "file_size": 5, "expire_style": "day", "expire_value": 1,
        })
        self.assertEqual(result.status_code, 200, result.text)
        token = result.json()["detail"]["upload_id"]
        wrong = await self.client.put(f"/presign/upload/proxy/{token}", headers=headers,
                                     files={"file": ("sample.txt", b"a" * 150, "text/plain")})
        self.assertEqual(wrong.status_code, 400, wrong.text)
        self.assertEqual(await FileCodes.all().count(), 0)
        valid = await self.client.put(f"/presign/upload/proxy/{token}", headers=headers,
                                     files={"file": ("sample.txt", b"hello", "text/plain")})
        self.assertEqual(valid.status_code, 200, valid.text)
        self.assertEqual((await get_storage_usage())["used"], 5)

    async def test_digest_removal_keeps_known_codes_and_disables_unknown_codes(self):
        # 使用旧版表验证迁移行为，缺失原文的授权只能停用，不能伪造恢复口令。
        conn = connections.get("default")
        await conn.execute_query("DROP TABLE deliverycode")
        for number in (8, 9, 10, 12):
            await importlib.import_module(f"apps.base.migrations.migrations_{number:03d}").migrate()
        expiry = await get_now() + timedelta(days=1)
        await conn.execute_query(
            "INSERT INTO deliverycode (id, code_digest, code_value, name, storage_type, target_path, expires_at, max_uploads, auth_version) "
            "VALUES (1, 'old-digest-a', 'KeepExistingCode1', 'known', 'local', 'inbox', ?, 5, 3)", [expiry],
        )
        await conn.execute_query(
            "INSERT INTO deliverycode (id, code_digest, name, storage_type, target_path, expires_at, max_uploads, auth_version) "
            "VALUES (2, 'old-digest-b', 'unknown', 'local', 'inbox', ?, 5, 7)", [expiry],
        )
        await FileCodes.create(code="existing-share", delivery_id=2, text="private relationship", size=20)
        migration = importlib.import_module("apps.base.migrations.migrations_014")
        await migration.migrate()
        await migration.migrate()
        columns = {item["name"] for item in await conn.execute_query_dict("PRAGMA table_info(deliverycode)")}
        self.assertNotIn("code_digest", columns)
        self.assertNotIn("owner_id", columns)
        self.assertTrue((await DeliveryCode.get(id=1)).enabled)
        self.assertIn("token", await verify_code("KeepExistingCode1"))
        unknown = await DeliveryCode.get(id=2)
        self.assertFalse(unknown.enabled)
        self.assertEqual(unknown.auth_version, 8)
        self.assertTrue(await FileCodes.filter(delivery_id=2).exists())
        # 重设口令不会自动扩大权限，管理员还需显式重新启用。
        await update_code(2, UpdateDeliveryCode(code="NewKnownCode2"))
        self.assertFalse((await DeliveryCode.get(id=2)).enabled)

    async def test_missing_original_requires_reset_before_enable(self):
        record = await DeliveryCode.create(
            code_value=None, name="需要重新设码", storage_type="local", target_path="inbox",
            expires_at=await get_now() + timedelta(days=1), max_uploads=2, enabled=False,
        )
        headers = {"Authorization": "Bearer " + create_token({"is_admin": True})}
        response = await self.client.patch(f"/admin/delivery/codes/{record.id}", json={"enabled": True}, headers=headers)
        self.assertEqual(response.status_code, 409)
        with self.assertRaises(HTTPException):
            await batch_codes(BatchDeliveryCodes(ids=[record.id], action="enable"))
        await update_code(record.id, UpdateDeliveryCode(code="ResetAndEnable1"))
        response = await self.client.patch(f"/admin/delivery/codes/{record.id}", json={"enabled": True}, headers=headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("token", await verify_code("ResetAndEnable1"))

    async def test_digest_migration_rejects_duplicate_originals_without_data_loss(self):
        conn = connections.get("default")
        await conn.execute_query("DROP TABLE deliverycode")
        for number in (8, 9, 10, 12):
            await importlib.import_module(f"apps.base.migrations.migrations_{number:03d}").migrate()
        for number in (1, 2):
            await conn.execute_query(
                "INSERT INTO deliverycode (id, code_digest, code_value, name, storage_type, target_path, expires_at, max_uploads) "
                "VALUES (?, ?, 'DuplicatedCode1', 'duplicate', 'local', 'inbox', ?, 2)",
                [number, str(number), await get_now() + timedelta(days=1)],
            )
        with self.assertRaises(RuntimeError) as error:
            await importlib.import_module("apps.base.migrations.migrations_014").migrate()
        self.assertNotIn("DuplicatedCode1", str(error.exception))
        columns = {item["name"] for item in await conn.execute_query_dict("PRAGMA table_info(deliverycode)")}
        self.assertIn("code_digest", columns)
        self.assertEqual(len(await conn.execute_query_dict("SELECT id FROM deliverycode")), 2)

    async def test_normal_upload_keeps_upstream_storage_behavior(self):
        # 普通游客上传不写寄件归属或公共后端快照，也不改变上游的开放游客鉴权规则。
        settings.open_upload = 1
        response = await self.client.post('/share/text/', data={'text': 'ordinary'}, headers={'Authorization': 'Bearer invalid'})
        self.assertEqual(response.status_code, 200, response.text)
        record = await FileCodes.get(code=response.json()['detail']['code'])
        self.assertIsNone(record.delivery_id)
        self.assertIsNone(record.storage_type)
        from apps.base.models import UploadChunk, PresignUploadSession
        self.assertNotIn('storage_type', UploadChunk._meta.fields_map)
        self.assertNotIn('storage_type', PresignUploadSession._meta.fields_map)

    async def test_chunk_size_extension_is_limited_to_delivery(self):
        # 普通分片保留上游按整片容量计算的规则，寄件才按自己的预占容量校验。
        settings.open_upload = 1
        settings.upload_size = 5
        payload = {'file_name': 'partial.txt', 'file_size': 5, 'chunk_size': 4, 'file_hash': 'partial'}
        ordinary = await self.client.post('/chunk/upload/init/', json=payload)
        self.assertEqual(ordinary.status_code, 403)
        _, headers = await self.make_code()
        delivery = await self.client.post('/chunk/upload/init/', json=payload, headers=headers)
        self.assertEqual(delivery.status_code, 200, delivery.text)

    async def test_normal_file_ignores_legacy_snapshot(self):
        # 旧版本曾为普通文件写入的快照不会继续改变上游默认存储选择。
        from apps.base.share_storage import storage_for_share
        marker = object()
        record = await FileCodes.create(code='ordinary-legacy', storage_type='s3')
        with patch.dict('apps.base.share_storage.storages', {'local': lambda: marker}):
            self.assertIs(await storage_for_share(record), marker)

    async def test_delivery_s3_uses_existing_proxy_without_exposing_direct_url(self):
        # 使用会生成直传地址的驱动替身，确认寄件根本不会请求该 URL；普通上传保持直传。
        class DirectStorage:
            calls = 0

            async def generate_presigned_upload_url(self, path, expires):
                self.calls += 1
                return 'https://storage.invalid/presigned-test'

        backend = DirectStorage()
        settings.file_storage = 's3'
        settings.s3_access_key_id = 'test-key'
        settings.s3_secret_access_key = 'test-secret'
        settings.s3_bucket_name = 'test-bucket'
        settings.s3_endpoint_url = 'http://127.0.0.1:9000'
        result = await create_code(CreateDeliveryCode(
            name='S3寄件', code='S3ScopedDelivery1', storage_type='s3', target_path='incoming',
            expires_at=await get_now() + timedelta(days=1), max_uploads=2,
        ))
        session = await verify_code('S3ScopedDelivery1')
        headers = {'Authorization': 'Bearer ' + session['token']}
        payload = {'file_name': 'sample.txt', 'file_size': 5, 'expire_style': 'day'}
        with patch.dict('core.storage.storages', {'s3': lambda: backend}):
            response = await self.client.post('/presign/upload/init', json=payload, headers=headers)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()['detail']['mode'], 'proxy')
            self.assertEqual(backend.calls, 0)
            settings.open_upload = 1
            ordinary = await self.client.post('/presign/upload/init', json=payload)
            self.assertEqual(ordinary.status_code, 200, ordinary.text)
            self.assertEqual(ordinary.json()['detail']['mode'], 'direct')
            self.assertEqual(backend.calls, 1)

    async def test_legacy_delivery_direct_session_cannot_bypass_proxy(self):
        # 即使升级前数据库中留有直传会话，也不能绕开现在的寄件代理校验。
        from apps.base.models import PresignUploadSession
        code_id, headers = await self.make_code(max_uploads=1)
        result = await self.client.post('/presign/upload/init', headers=headers, json={
            'file_name': 'legacy.txt', 'file_size': 5, 'expire_style': 'day',
        })
        token = result.json()['detail']['upload_id']
        await PresignUploadSession.filter(upload_id=token).update(mode='direct')
        response = await self.client.post('/presign/upload/confirm/' + token, headers=headers)
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(await FileCodes.all().count(), 0)
        self.assertEqual((await DeliveryCode.get(id=code_id)).used_count, 0)
        self.assertEqual((await DeliveryCode.get(id=code_id)).reserved_count, 0)
        old_reservation = await StorageReservation.get(token=token)
        self.assertEqual(old_reservation.status, 'cleanup')
        # 旧签名过期前保留清理记录，避免取消后又写入同一对象造成永久残留。
        self.assertGreater(old_reservation.expires_at, await get_now())
        retry = await self.client.post('/presign/upload/init', headers=headers, json={
            'file_name': 'retry.txt', 'file_size': 5, 'expire_style': 'day',
        })
        self.assertEqual(retry.status_code, 200, retry.text)
