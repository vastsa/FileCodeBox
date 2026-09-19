"""删除寄件码独立存储配置；既有文件和上传会话的位置不变。"""

from tortoise.transactions import in_transaction


async def migrate():
    # 重建仅授权数据的表，保留主键、计数和自增序列，不搬动任何已保存的文件。
    async with in_transaction() as conn:
        columns = {row["name"] for row in await conn.execute_query_dict("PRAGMA table_info(deliverycode)")}
        if not {"storage_type", "target_path"} & columns:
            return
        sequences = await conn.execute_query_dict("SELECT seq FROM sqlite_sequence WHERE name = 'deliverycode'")
        sequence = sequences[0]["seq"] if sequences else 0
        await conn.execute_query('''
            CREATE TABLE deliverycode_system_storage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code_value VARCHAR(64) NULL UNIQUE,
                auth_version INT NOT NULL DEFAULT 1,
                name VARCHAR(100) NOT NULL,
                note VARCHAR(2000) NOT NULL DEFAULT '',
                tags JSON NOT NULL DEFAULT '[]',
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
            INSERT INTO deliverycode_system_storage (
                id, code_value, auth_version, name, note, tags, expires_at,
                max_uploads, used_count, reserved_count, enabled, deleted, created_at
            ) SELECT id, code_value, auth_version, name, note, tags, expires_at,
                max_uploads, used_count, reserved_count, enabled, deleted, created_at
            FROM deliverycode
        ''')
        await conn.execute_query("DROP TABLE deliverycode")
        await conn.execute_query("ALTER TABLE deliverycode_system_storage RENAME TO deliverycode")
        # 不能因历史行曾被删除而复用旧 ID，避免错误接回历史收件关联。
        await conn.execute_query("UPDATE sqlite_sequence SET seq = MAX(seq, ?) WHERE name = 'deliverycode'", [sequence])
