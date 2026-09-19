"""收件归入普通文件表；旧私有文件保持私有，未完成上传迁入短期容量预留。"""

import os
import uuid
from tortoise.transactions import in_transaction


async def migrate():
    # 整体事务保证迁移失败可以回滚，影子表仅在全部记录转移成功后移除。
    async with in_transaction() as conn:
        additions = {
            "filecodes": {"delivery_id": "INT NULL", "is_private": "INT NOT NULL DEFAULT 0"},
            "storagereservation": {
                "delivery_id": "INT NULL", "auth_version": "INT NOT NULL DEFAULT 1",
                "status": "VARCHAR(20) NOT NULL DEFAULT 'pending'",
                "filename": "VARCHAR(255) NOT NULL DEFAULT ''",
                "stored_name": "VARCHAR(255) NOT NULL DEFAULT ''",
                "file_path": "VARCHAR(255) NOT NULL DEFAULT ''",
                "storage_type": "VARCHAR(20) NULL",
            },
        }
        for table, fields in additions.items():
            names = {row["name"] for row in await conn.execute_query_dict(f"PRAGMA table_info({table})")}
            for name, declaration in fields.items():
                if name not in names:
                    await conn.execute_query(f"ALTER TABLE {table} ADD COLUMN {name} {declaration}")
        await conn.execute_query("CREATE INDEX IF NOT EXISTS idx_filecodes_delivery_id ON filecodes(delivery_id)")
        await conn.execute_query("CREATE INDEX IF NOT EXISTS idx_reservation_delivery_id ON storagereservation(delivery_id)")
        exists = await conn.execute_query_dict("SELECT name FROM sqlite_master WHERE type='table' AND name='deliveryfile'")
        if not exists:
            return
        # 分批读取避免升级时将全部文件记录载入内存。
        cursor = 0
        while True:
            rows = await conn.execute_query_dict("SELECT * FROM deliveryfile WHERE id > ? ORDER BY id LIMIT 100", [cursor])
            if not rows:
                break
            for row in rows:
                cursor = row["id"]
                if row["status"] == "deleted":
                    continue
                code_id = row["delivery_id"]
                # 旧版可能已物理删除耗尽口令；补只读历史壳以保留按码查收件的入口。
                await conn.execute_query(
                    "INSERT OR IGNORE INTO deliverycode (id, code_digest, name, storage_type, target_path, expires_at, max_uploads, enabled, deleted) "
                    "VALUES (?, ?, ?, ?, '', CURRENT_TIMESTAMP, 1, 0, 0)",
                    [code_id, uuid.uuid4().hex, "历史寄件（授权已撤销）", row["storage_type"]],
                )
                if row.get("share_id") is not None:
                    await conn.execute_query(
                        "UPDATE filecodes SET delivery_id = ?, storage_type = ?, upload_id = ? WHERE id = ?",
                        [code_id, row["storage_type"], row["token"], row["share_id"]],
                    )
                elif row["status"] == "stored":
                    prefix, suffix = os.path.splitext(row["filename"])
                    await conn.execute_query(
                        "INSERT INTO filecodes (code, prefix, suffix, uuid_file_name, file_path, size, expired_count, used_count, is_chunked, created_at, storage_type, delivery_id, is_private, upload_id) "
                        "VALUES (?, ?, ?, ?, ?, ?, -1, 0, 0, ?, ?, ?, 1, ?)",
                        [uuid.uuid4().hex, prefix, suffix, row["stored_name"], row["file_path"], row["size"], row["created_at"], row["storage_type"], code_id, row["token"]],
                    )
                elif row["status"] in {"pending", "finalizing", "cleanup"}:
                    # 升级前未完成的上传统一取消并清理，不允许旧会话跨模型继续提交。
                    await conn.execute_query("DELETE FROM storagereservation WHERE token IN (?, ?, ?)",
                                             ["delivery:" + row["token"], "chunk:" + row["token"], "presign:" + row["token"]])
                    await conn.execute_query(
                        "INSERT OR IGNORE INTO storagereservation (token, size, expires_at, delivery_id, status, filename, stored_name, file_path, storage_type) "
                        "VALUES (?, ?, CURRENT_TIMESTAMP, ?, 'cleanup', ?, ?, ?, ?)",
                        [row["token"], row["size"], code_id, row["filename"], row["stored_name"], row["file_path"], row["storage_type"]],
                    )
        await conn.execute_query("UPDATE deliverycode SET reserved_count = 0")
        await conn.execute_query("UPDATE deliverycode SET enabled = 0 WHERE used_count >= max_uploads OR deleted = 1")
        await conn.execute_query("DROP TABLE deliveryfile")
