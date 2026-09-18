"""Admin write-path coverage: batch/single delete, batch update, policy actions.

These are the data-modifying admin endpoints that previously had zero
automated coverage. Focus on aggregation semantics (partial failure keeps
going), validation rejections, and 404 handling for missing records.
"""
import datetime
import io

import pytest

from core.utils import get_now
from tests.conftest import TEST_ADMIN_PASSWORD


async def _login(client) -> str:
    response = await client.post(
        "/admin/login", json={"password": TEST_ADMIN_PASSWORD}
    )
    assert response.status_code == 200, response.text
    return response.json()["detail"]["token"]


async def _create_share(code: str, *, text: str = "x", **extra) -> int:
    from apps.base.models import FileCodes

    record = await FileCodes.create(
        code=code, text=text, size=1, prefix="Text", **extra
    )
    return record.id


@pytest.mark.asyncio
class TestBatchDelete:
    async def test_mixed_ids_aggregate_and_continue(self, initialized_client):
        """存在/缺失/重复 id 混合：删除继续进行，聚合准确，记录真实消失。"""
        token = await _login(initialized_client)
        id_a = await _create_share("bd-mix-a")
        id_b = await _create_share("bd-mix-b")
        missing_id = 987654

        response = await initialized_client.request(
            "DELETE",
            "/admin/file/batch-delete",
            json={"ids": [id_a, missing_id, id_b, id_a]},  # 含重复 id
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200, response.text
        detail = response.json()["detail"]
        assert sorted(detail["deleted"]) == sorted([id_a, id_b])
        assert detail["missing"] == [missing_id]
        assert detail["failed"] == []
        assert detail["deleted_count"] == 2

        from apps.base.models import FileCodes

        assert await FileCodes.filter(id=id_a).first() is None
        assert await FileCodes.filter(id=id_b).first() is None

    async def test_empty_ids_rejected_400(self, initialized_client):
        token = await _login(initialized_client)
        response = await initialized_client.request(
            "DELETE",
            "/admin/file/batch-delete",
            json={"ids": []},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 400


@pytest.mark.asyncio
class TestSingleDelete:
    async def test_missing_file_maps_to_404(self, initialized_client):
        """删除不存在的文件：register_tortoise(add_exception_handlers=True) 把
        tortoise DoesNotExist 映射为 404 JSON——钉死该行为防回归。"""
        token = await _login(initialized_client)
        response = await initialized_client.request(
            "DELETE",
            "/admin/file/delete",
            json={"id": 987654},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404
        assert "does not exist" in response.json()["detail"]

    async def test_existing_text_share_deleted(self, initialized_client):
        token = await _login(initialized_client)
        file_id = await _create_share("sd-exist")
        response = await initialized_client.request(
            "DELETE",
            "/admin/file/delete",
            json={"id": file_id},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        from apps.base.models import FileCodes

        assert await FileCodes.filter(id=file_id).first() is None


@pytest.mark.asyncio
class TestBatchUpdate:
    async def test_expired_count_update_and_missing_aggregate(self, initialized_client):
        token = await _login(initialized_client)
        id_a = await _create_share("bu-cnt-a")
        missing_id = 987655

        response = await initialized_client.request(
            "PATCH",
            "/admin/file/batch-update",
            json={"ids": [id_a, missing_id], "expired_count": 7},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200, response.text
        detail = response.json()["detail"]
        assert detail["updated"] == [id_a]
        assert detail["missing"] == [missing_id]

        from apps.base.models import FileCodes

        record = await FileCodes.get(id=id_a)
        assert record.expired_count == 7

    async def test_clear_expired_at_makes_permanent(self, initialized_client):
        token = await _login(initialized_client)
        file_id = await _create_share(
            "bu-clr",
            expired_at=await get_now() + datetime.timedelta(days=1),
            expired_count=3,
        )
        response = await initialized_client.request(
            "PATCH",
            "/admin/file/batch-update",
            json={"ids": [file_id], "clear_expired_at": True},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200, response.text

        from apps.base.models import FileCodes

        record = await FileCodes.get(id=file_id)
        assert record.expired_at is None
        assert record.expired_count == -1

    async def test_no_fields_selected_rejected_400(self, initialized_client):
        token = await _login(initialized_client)
        file_id = await _create_share("bu-none")
        response = await initialized_client.request(
            "PATCH",
            "/admin/file/batch-update",
            json={"ids": [file_id]},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 400


@pytest.mark.asyncio
class TestPolicyActions:
    async def test_make_permanent_clears_time_and_count(self, initialized_client):
        token = await _login(initialized_client)
        file_id = await _create_share(
            "pa-perm",
            expired_at=await get_now() + datetime.timedelta(days=1),
            expired_count=3,
        )
        response = await initialized_client.request(
            "PATCH",
            "/admin/file/policy-action",
            json={"id": file_id, "action": "make_permanent"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200, response.text

        from apps.base.models import FileCodes

        record = await FileCodes.get(id=file_id)
        assert record.expired_at is None
        assert record.expired_count == -1

    async def test_reset_download_limit_custom_value(self, initialized_client):
        token = await _login(initialized_client)
        file_id = await _create_share("pa-reset")
        response = await initialized_client.request(
            "PATCH",
            "/admin/file/policy-action",
            json={
                "id": file_id,
                "action": "reset_download_limit",
                "download_limit": 9,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200, response.text

        from apps.base.models import FileCodes

        assert (await FileCodes.get(id=file_id)).expired_count == 9

    async def test_reset_download_limit_zero_rejected_400(self, initialized_client):
        token = await _login(initialized_client)
        file_id = await _create_share("pa-zero")
        response = await initialized_client.request(
            "PATCH",
            "/admin/file/policy-action",
            json={
                "id": file_id,
                "action": "reset_download_limit",
                "download_limit": 0,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 400

    async def test_unknown_action_rejected_400(self, initialized_client):
        token = await _login(initialized_client)
        file_id = await _create_share("pa-unknown")
        response = await initialized_client.request(
            "PATCH",
            "/admin/file/policy-action",
            json={"id": file_id, "action": "nuke_everything"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 400

    async def test_policy_action_missing_file_404(self, initialized_client):
        token = await _login(initialized_client)
        response = await initialized_client.request(
            "PATCH",
            "/admin/file/policy-action",
            json={"id": 987656, "action": "make_permanent"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404

    async def test_batch_policy_action_aggregates_missing(self, initialized_client):
        token = await _login(initialized_client)
        id_a = await _create_share("bpa-a")
        response = await initialized_client.request(
            "PATCH",
            "/admin/file/batch-policy-action",
            json={"ids": [id_a, 987657], "action": "extend_24h"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200, response.text
        detail = response.json()["detail"]
        assert detail["updated"] == [id_a]
        assert detail["missing"] == [987657]


@pytest.mark.asyncio
class TestValidateFileSizeWithoutLength:
    async def test_upload_without_size_declaration_no_500(self, initialized_client):
        """无长度声明的上传（size=None 分支）不得 TypeError——上游原有缺陷。"""
        from apps.base.auth import _require_admin_payload  # noqa: F401
        from apps.base.services import validate_file_size
        from core.settings import settings
        from fastapi import UploadFile

        upload = UploadFile(file=io.BytesIO(b"no-length-payload"))  # size=None
        assert upload.size is None
        size = await validate_file_size(upload, settings.upload_size)
        assert size == len(b"no-length-payload")
