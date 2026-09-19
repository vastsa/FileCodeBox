"""Admin read-path coverage: detail, metadata, preview, admin download,
activities filtering, local file lists/delete, and verify.

These endpoints previously had zero automated coverage. Negative paths
first: missing records, truncation limits, wrong-type rejections.
"""

import pytest

from tests.test_admin_write_paths import _create_share, _login


@pytest.mark.asyncio
class TestFileDetail:
    async def test_detail_returns_policy_storage_metadata(self, initialized_client):
        token = await _login(initialized_client)
        file_id = await _create_share("dt-exist")
        response = await initialized_client.get(
            "/admin/file/detail",
            params={"id": file_id},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200, response.text
        detail = response.json()["detail"]
        assert detail["code"] == "dt-exist"
        assert detail["is_text"] is True
        assert {"policy", "storage", "metadata", "timeline"} <= set(detail.keys())

    async def test_detail_missing_file_404(self, initialized_client):
        token = await _login(initialized_client)
        for method, kwargs in (
            ("get", {"params": {"id": 987658}}),
            ("post", {"json": {"id": 987658}}),
        ):
            response = await initialized_client.request(
                method,
                "/admin/file/detail",
                headers={"Authorization": f"Bearer {token}"},
                **kwargs,
            )
            assert response.status_code == 404, method


@pytest.mark.asyncio
class TestFileMetadata:
    async def test_note_and_tags_roundtrip_with_truncation(self, initialized_client):
        token = await _login(initialized_client)
        file_id = await _create_share("md-round")

        # note 超长被截断到 2000；tags 超 12 个被截、单个超 24 字符被截、去重
        long_note = "n" * 3000
        tags = [f"tag{i}" for i in range(15)] + ["x" * 30, "dup", "dup"]
        response = await initialized_client.post(
            "/admin/file/metadata",
            json={"id": file_id, "note": long_note, "tags": tags},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200, response.text

        detail = (
            await initialized_client.get(
                "/admin/file/detail",
                params={"id": file_id},
                headers={"Authorization": f"Bearer {token}"},
            )
        ).json()["detail"]
        metadata = detail["metadata"]
        assert len(metadata["note"]) == 2000
        assert len(metadata["tags"]) == 12
        assert all(len(tag) <= 24 for tag in metadata["tags"])
        assert metadata["updated_at"] is not None

    async def test_metadata_missing_file_404(self, initialized_client):
        token = await _login(initialized_client)
        response = await initialized_client.post(
            "/admin/file/metadata",
            json={"id": 987659, "note": "x"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404


@pytest.mark.asyncio
class TestFilePreview:
    async def test_text_preview_truncates_with_max_chars(self, initialized_client):
        token = await _login(initialized_client)
        file_id = await _create_share("pv-trunc", text="abcdefgh" * 10)
        response = await initialized_client.get(
            "/admin/file/preview",
            params={"id": file_id, "max_chars": 10},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200, response.text
        detail = response.json()["detail"]
        assert detail["content"] == "abcdefghab"
        assert detail["truncated"] is True
        assert detail["preview_length"] == 10
        assert detail["max_chars"] == 10

    async def test_preview_non_text_rejected_400(self, initialized_client):
        token = await _login(initialized_client)
        from apps.base.models import FileCodes

        file_id = (
            await FileCodes.create(
                code="pv-file", prefix="doc", suffix=".bin", size=1
            )
        ).id
        response = await initialized_client.get(
            "/admin/file/preview",
            params={"id": file_id},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 400

    async def test_preview_missing_file_404(self, initialized_client):
        token = await _login(initialized_client)
        response = await initialized_client.get(
            "/admin/file/preview",
            params={"id": 987660},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404


@pytest.mark.asyncio
class TestAdminDownload:
    async def test_text_share_download_returns_content(self, initialized_client):
        token = await _login(initialized_client)
        file_id = await _create_share("dl-text", text="admin-download-body")
        response = await initialized_client.get(
            "/admin/file/download",
            params={"id": file_id},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert b"admin-download-body" in response.content

    async def test_missing_file_download_404(self, initialized_client):
        token = await _login(initialized_client)
        response = await initialized_client.get(
            "/admin/file/download",
            params={"id": 987661},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404


@pytest.mark.asyncio
class TestActivities:
    async def test_recorded_action_is_listed_and_filtered(self, initialized_client):
        """删一个文件产生活动事件；action 过滤必须生效。"""
        token = await _login(initialized_client)
        file_id = await _create_share("act-del")
        await initialized_client.request(
            "DELETE",
            "/admin/file/delete",
            json={"id": file_id},
            headers={"Authorization": f"Bearer {token}"},
        )

        listed = await initialized_client.get(
            "/admin/activities",
            params={"action": "file.delete"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert listed.status_code == 200
        activities = listed.json()["detail"]["activities"]
        assert any(
            a["action"] == "file.delete" and a["target_id"] == file_id
            for a in activities
        )

        other = await initialized_client.get(
            "/admin/activities",
            params={"action": "nonexistent.action"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert other.json()["detail"]["activities"] == []

    async def test_limit_upper_bound_clamped_to_80(self, initialized_client):
        token = await _login(initialized_client)
        response = await initialized_client.get(
            "/admin/activities",
            params={"limit": 5000},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert response.json()["detail"]["limit"] == 80


@pytest.mark.asyncio
class TestLocalFileEndpoints:
    async def test_lists_and_delete_roundtrip(self, initialized_client):
        """data/local 列表与删除（走端点层；存储层语义由 WebDAV 轮覆盖）。"""
        import shutil
        from core.settings import data_root

        token = await _login(initialized_client)
        local_dir = data_root / "local" / "e2e-probe"
        local_dir.mkdir(parents=True, exist_ok=True)
        try:
            (local_dir / "probe.txt").write_bytes(b"local-probe")

            listed = await initialized_client.get(
                "/admin/local/lists",
                params={"path": "e2e-probe"},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert listed.status_code == 200, listed.text
            items = listed.json()["detail"]["items"]
            assert any(item["name"] == "probe.txt" for item in items)

            deleted = await initialized_client.request(
                "DELETE",
                "/admin/local/delete",
                json={"filename": "e2e-probe/probe.txt"},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert deleted.status_code == 200
            assert not (local_dir / "probe.txt").exists()
        finally:
            shutil.rmtree(data_root / "local" / "e2e-probe", ignore_errors=True)

    async def test_local_delete_traversal_rejected(self, initialized_client):
        token = await _login(initialized_client)
        response = await initialized_client.request(
            "DELETE",
            "/admin/local/delete",
            json={"filename": "../../filecodebox.db"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 400

    async def test_local_delete_missing_404(self, initialized_client):
        token = await _login(initialized_client)
        response = await initialized_client.request(
            "DELETE",
            "/admin/local/delete",
            json={"filename": "ghost.txt"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404


@pytest.mark.asyncio
class TestVerify:
    async def test_valid_token_passes(self, initialized_client):
        token = await _login(initialized_client)
        response = await initialized_client.get(
            "/admin/verify", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200

    async def test_garbage_token_rejected_401(self, initialized_client):
        response = await initialized_client.get(
            "/admin/verify", headers={"Authorization": "Bearer garbage.token.here"}
        )
        assert response.status_code == 401
