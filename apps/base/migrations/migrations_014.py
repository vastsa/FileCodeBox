"""移除重复口令摘要及预设账号归属；缺少原文的旧授权停用但保留收件关联。"""

from tortoise.transactions import in_transaction


async def migrate():
    # SQLite 不能直接删除带唯一约束的旧列，使用事务内重建保留主键及全部业务字段。
    async with in_transaction() as conn:
        columns = {row["name"] for row in await conn.execute_query_dict("PRAGMA table_info(deliverycode)")}
        if "code_digest" not in columns:
            return
        # 异常旧数据先中止升级，不能猜测同一口令应该属于哪条授权；错误不输出口令。
        duplicates = await conn.execute_query_dict(
            "SELECT MIN(id) AS first_id FROM deliverycode "
            "WHERE code_value IS NOT NULL AND code_value != '' GROUP BY code_value HAVING COUNT(*) > 1"
        )
        if duplicates:
            ids = ", ".join(str(row["first_id"]) for row in duplicates)
            raise RuntimeError("寄件码原文存在重复，请先为相关记录重新设置不同口令，首条记录 ID：" + ids)
        await conn.execute_query('''
            CREATE TABLE deliverycode_without_digest (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code_value VARCHAR(64) NULL UNIQUE,
                auth_version INT NOT NULL DEFAULT 1,
                name VARCHAR(100) NOT NULL,
                note VARCHAR(2000) NOT NULL DEFAULT '',
                tags JSON NOT NULL DEFAULT '[]',
                storage_type VARCHAR(20) NOT NULL,
                target_path VARCHAR(200) NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                max_uploads INT NOT NULL,
                used_count INT NOT NULL DEFAULT 0,
                reserved_count INT NOT NULL DEFAULT 0,
                enabled INT NOT NULL DEFAULT 1,
                deleted INT NOT NULL DEFAULT 0,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        await conn.execute_query('''
            INSERT INTO deliverycode_without_digest (
                id, code_value, auth_version, name, note, tags, storage_type, target_path,
                expires_at, max_uploads, used_count, reserved_count, enabled, deleted, created_at
            )
            SELECT id, NULLIF(code_value, ''),
                auth_version + CASE WHEN code_value IS NULL OR code_value = '' THEN 1 ELSE 0 END,
                name, note, tags, storage_type, target_path, expires_at, max_uploads,
                used_count, reserved_count,
                CASE WHEN code_value IS NULL OR code_value = '' THEN 0 ELSE enabled END,
                deleted, created_at
            FROM deliverycode
        ''')
        # ID 保持不变；已存在的 FileCodes.delivery_id 以及历史计数不会丢失。
        await conn.execute_query("DROP TABLE deliverycode")
        await conn.execute_query("ALTER TABLE deliverycode_without_digest RENAME TO deliverycode")
