import asyncio
import unittest

from fastapi import HTTPException
from tortoise import Tortoise

from apps.base.models import FileCodes, StorageReservation
from apps.base.quota import get_storage_usage, release_storage, reserve_storage
from core.settings import settings
from core.utils import get_now


class StorageQuotaTests(unittest.TestCase):
    def test_quota_reservations_are_atomic_and_reusable(self):
        asyncio.run(self._run_scenario())

    async def _run_scenario(self):
        original_config = dict(settings.user_config)
        settings.storageLimit = 100
        await Tortoise.init(
            config={
                "connections": {
                    "default": {
                        "engine": "tortoise.backends.sqlite",
                        "credentials": {"file_path": ":memory:"},
                    }
                },
                "apps": {
                    "models": {
                        "models": ["apps.base.models"],
                        "default_connection": "default",
                    }
                },
                "use_tz": False,
                "timezone": "Asia/Shanghai",
            }
        )
        await Tortoise.generate_schemas()
        try:
            await FileCodes.create(code="existing", size=60, expired_count=-1)

            results = await asyncio.gather(
                reserve_storage("upload-a", 30, 300),
                reserve_storage("upload-b", 30, 300),
                return_exceptions=True,
            )

            self.assertEqual(sum(result is None for result in results), 1)
            rejected = [result for result in results if isinstance(result, HTTPException)]
            self.assertEqual(len(rejected), 1)
            self.assertEqual(rejected[0].status_code, 507)

            usage = await get_storage_usage()
            self.assertEqual(usage["used"], 60)
            self.assertEqual(usage["reserved"], 30)
            self.assertEqual(usage["available"], 10)

            active = await StorageReservation.first()
            await release_storage(active.token)
            await reserve_storage("upload-c", 40, 300)
            self.assertEqual((await get_storage_usage())["available"], 0)

            settings.storageLimit = 0
            await reserve_storage("unlimited", 10_000, 300)
            self.assertFalse(
                await StorageReservation.filter(token="unlimited").exists()
            )

            settings.storageLimit = 100
            expired = await StorageReservation.get(token="upload-c")
            expired.expires_at = await get_now()
            await expired.save(update_fields=["expires_at"])
            await reserve_storage("upload-d", 40, 300)
            self.assertEqual((await get_storage_usage())["reserved"], 40)

            await release_storage("upload-d")
            same_token_results = await asyncio.gather(
                *(reserve_storage("same-upload", 40, 300) for _ in range(10)),
                return_exceptions=True,
            )
            self.assertTrue(all(result is None for result in same_token_results))
            self.assertEqual(
                await StorageReservation.filter(token="same-upload").count(), 1
            )
        finally:
            settings.user_config = original_config
            await Tortoise.close_connections()


if __name__ == "__main__":
    unittest.main()
