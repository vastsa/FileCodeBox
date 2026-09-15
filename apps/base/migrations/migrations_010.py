"""将新的寄件授权上传关联到普通取件记录，保留历史私有收件。"""

from tortoise import connections


async def migrate():
    conn = connections.get("default")
    columns = await conn.execute_query_dict("PRAGMA table_info(deliveryfile)")
    if not any(column["name"] == "share_id" for column in columns):
        await conn.execute_script("ALTER TABLE deliveryfile ADD COLUMN share_id INT NULL;")
    await conn.execute_script("CREATE INDEX IF NOT EXISTS idx_deliveryfile_share_id ON deliveryfile(share_id);")
