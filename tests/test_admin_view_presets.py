"""Admin view-preset CRUD coverage: normalize boundaries, cap enforcement,
delete-missing 404. Presets are stored as a KeyValue JSON blob (the D5
lock-guarded write path), so the roundtrip also exercises that lock.
"""
import pytest

from tests.test_admin_write_paths import _login


@pytest.mark.asyncio
class TestViewPresetCRUD:
    async def test_save_list_update_delete_roundtrip(self, initialized_client):
        token = await _login(initialized_client)
        headers = {"Authorization": f"Bearer {token}"}

        created = await initialized_client.post(
            "/admin/file/view-presets",
            json={"name": "我的视图", "filters": {"status": "active", "size": 25}},
            headers=headers,
        )
        assert created.status_code == 200, created.text
        preset = created.json()["detail"]
        assert preset["name"] == "我的视图"

        # 更新（带同 id 再保存）
        updated = await initialized_client.patch(
            "/admin/file/view-presets",
            json={
                "id": preset["id"],
                "name": "改名视图",
                "filters": {"status": "expired"},
            },
            headers=headers,
        )
        assert updated.status_code == 200
        assert updated.json()["detail"]["name"] == "改名视图"

        listing = (
            await initialized_client.get(
                "/admin/file/view-presets", headers=headers
            )
        ).json()["detail"]
        names = [p["name"] for p in listing["presets"]]
        assert "改名视图" in names
        assert "我的视图" not in names  # 同 id 保存是更新不是新增

        deleted = await initialized_client.request(
            "DELETE",
            "/admin/file/view-presets",
            json={"id": preset["id"]},
            headers=headers,
        )
        assert deleted.status_code == 200
        listing_after = (
            await initialized_client.get(
                "/admin/file/view-presets", headers=headers
            )
        ).json()["detail"]
        assert "改名视图" not in [p["name"] for p in listing_after["presets"]]

    async def test_empty_name_rejected_400(self, initialized_client):
        token = await _login(initialized_client)
        response = await initialized_client.post(
            "/admin/file/view-presets",
            json={"name": "   "},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 400

    async def test_long_name_truncated_to_32(self, initialized_client):
        token = await _login(initialized_client)
        headers = {"Authorization": f"Bearer {token}"}
        created = await initialized_client.post(
            "/admin/file/view-presets",
            json={"name": "n" * 50},
            headers=headers,
        )
        assert created.status_code == 200
        assert len(created.json()["detail"]["name"]) == 32

    async def test_filters_normalized_and_clamped(self, initialized_client):
        token = await _login(initialized_client)
        headers = {"Authorization": f"Bearer {token}"}
        created = await initialized_client.post(
            "/admin/file/view-presets",
            json={
                "name": "filter-check",
                "filters": {
                    "status": "not-a-status",
                    "type": "alien",
                    "health": "bogus",
                    "sortBy": "hacker_field",
                    "sortOrder": "sideways",
                    "size": 99999,
                    "keyword": "k" * 200,
                },
            },
            headers=headers,
        )
        assert created.status_code == 200
        filters = created.json()["detail"]["filters"]
        assert filters["status"] == "all"
        assert filters["type"] == "all"
        assert filters["health"] == "all"
        assert filters["sort_by"] == "created_at"
        assert filters["sort_order"] == "desc"
        assert filters["size"] == 100
        assert len(filters["keyword"]) == 80

    async def test_preset_cap_24_enforced(self, initialized_client):
        token = await _login(initialized_client)
        headers = {"Authorization": f"Bearer {token}"}
        ids = []
        for i in range(24):
            created = await initialized_client.post(
                "/admin/file/view-presets",
                json={"name": f"cap-{i}"},
                headers=headers,
            )
            assert created.status_code == 200, f"第 {i + 1} 个预设应成功"
            ids.append(created.json()["detail"]["id"])

        overflow = await initialized_client.post(
            "/admin/file/view-presets",
            json={"name": "cap-overflow"},
            headers=headers,
        )
        assert overflow.status_code == 400

        # 清理到上限以内，避免污染其他用例
        for preset_id in ids:
            await initialized_client.request(
                "DELETE",
                "/admin/file/view-presets",
                json={"id": preset_id},
                headers=headers,
            )

    async def test_delete_missing_preset_404(self, initialized_client):
        token = await _login(initialized_client)
        response = await initialized_client.request(
            "DELETE",
            "/admin/file/view-presets",
            json={"id": "no-such-preset"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404
