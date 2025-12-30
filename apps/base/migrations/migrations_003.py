from tortoise import connections


async def create_presign_upload_session_table():
    conn = connections.get("default")
    await conn.execute_script(
        """
        CREATE TABLE IF NOT EXISTS presignuploadsession (
            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            upload_id VARCHAR(36) NOT NULL UNIQUE,
            file_name VARCHAR(255) NOT NULL,
            file_size BIGINT NOT NULL,
            save_path VARCHAR(512) NOT NULL,
            mode VARCHAR(10) NOT NULL,
            expire_value INT NOT NULL DEFAULT 1,
            expire_style VARCHAR(20) NOT NULL DEFAULT 'day',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_presignuploadsession_upload_id ON presignuploadsession (upload_id);
        """
    )


async def migrate():
    await create_presign_upload_session_table()
