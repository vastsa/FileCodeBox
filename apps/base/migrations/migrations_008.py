"""新增寄件口令与独立收件记录；保留既有分享表及其权限语义。"""

from tortoise import connections


async def migrate():
    # 当前应用使用 SQLite；表定义与 Tortoise 模型保持一致，可重复执行。
    await connections.get("default").execute_script("""
        CREATE TABLE IF NOT EXISTS deliverycode (
            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            code_digest VARCHAR(64) NOT NULL UNIQUE,
            name VARCHAR(100) NOT NULL,
            owner_id VARCHAR(64) NOT NULL DEFAULT 'admin',
            storage_type VARCHAR(20) NOT NULL,
            target_path VARCHAR(200) NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            max_uploads INT NOT NULL,
            used_count INT NOT NULL DEFAULT 0,
            reserved_count INT NOT NULL DEFAULT 0,
            enabled INT NOT NULL DEFAULT 1,
            deleted INT NOT NULL DEFAULT 0,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_deliverycode_owner ON deliverycode(owner_id);
        CREATE TABLE IF NOT EXISTS deliveryfile (
            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            delivery_id INT NOT NULL,
            owner_id VARCHAR(64) NOT NULL DEFAULT 'admin',
            token VARCHAR(64) NOT NULL UNIQUE,
            filename VARCHAR(255) NOT NULL DEFAULT '',
            stored_name VARCHAR(255) NOT NULL DEFAULT '',
            file_path VARCHAR(200) NOT NULL,
            storage_type VARCHAR(20) NOT NULL,
            size BIGINT NOT NULL DEFAULT 0,
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_deliveryfile_code ON deliveryfile(delivery_id);
        CREATE INDEX IF NOT EXISTS idx_deliveryfile_owner ON deliveryfile(owner_id);
        CREATE INDEX IF NOT EXISTS idx_deliveryfile_status ON deliveryfile(status);
    """)
