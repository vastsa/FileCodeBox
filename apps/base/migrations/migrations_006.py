from tortoise import connections


async def migrate():
    conn = connections.get("default")
    await conn.execute_script(
        """
        CREATE TABLE IF NOT EXISTS storagereservation (
            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            token VARCHAR(64) NOT NULL UNIQUE,
            size BIGINT NOT NULL,
            expires_at TIMESTAMP NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_storagereservation_token
            ON storagereservation (token);
        CREATE INDEX IF NOT EXISTS idx_storagereservation_expires_at
            ON storagereservation (expires_at);
        """
    )
