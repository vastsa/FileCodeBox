"""仅为寄件分享保存授权指定的实际存储后端。"""

from tortoise import connections


async def migrate():
    """幂等增加字段，并仅用寄件关联补全可验证的旧记录。"""
    conn = connections.get("default")
    tables = {
        "filecodes": "storage_type",
    }
    for table, column in tables.items():
        columns = await conn.execute_query_dict(f"PRAGMA table_info({table})")
        if not any(item["name"] == column for item in columns):
            await conn.execute_script(
                f"ALTER TABLE {table} ADD COLUMN {column} VARCHAR(20) NULL;"
            )

    # 仅 DeliveryFile 的关联记录能证明旧分享的实际后端；其余历史数据保持未知。
    await conn.execute_script(
        """
        UPDATE filecodes
        SET storage_type = (
            SELECT storage_type FROM deliveryfile
            WHERE deliveryfile.share_id = filecodes.id
            LIMIT 1
        )
        WHERE storage_type IS NULL
          AND EXISTS (
            SELECT 1 FROM deliveryfile
            WHERE deliveryfile.share_id = filecodes.id
          );
        """
    )
