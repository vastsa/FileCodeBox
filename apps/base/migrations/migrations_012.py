"""为寄件码补充管理备注、标签和授权版本，兼容已部署的 SQLite 数据库。"""

from tortoise import connections


async def migrate():
    """按列存在性增量迁移，重复启动不会修改已有数据。"""
    conn = connections.get("default")
    columns = await conn.execute_query_dict("PRAGMA table_info(deliverycode)")
    names = {column["name"] for column in columns}
    if "note" not in names:
        await conn.execute_script("ALTER TABLE deliverycode ADD COLUMN note VARCHAR(2000) NOT NULL DEFAULT '';" )
    if "tags" not in names:
        await conn.execute_script("ALTER TABLE deliverycode ADD COLUMN tags JSON NOT NULL DEFAULT '[]';")
    if "auth_version" not in names:
        await conn.execute_script("ALTER TABLE deliverycode ADD COLUMN auth_version INT NOT NULL DEFAULT 1;")
