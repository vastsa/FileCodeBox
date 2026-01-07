from tortoise import connections


async def add_save_path_to_uploadchunk():
    conn = connections.get("default")
    await conn.execute_script(
        """
        ALTER TABLE uploadchunk ADD COLUMN save_path VARCHAR(512) NULL;
        """
    )


async def migrate():
    await add_save_path_to_uploadchunk()
