"""保留管理员可查看的寄件码原文，既有摘要及口令有效性保持不变。"""

from tortoise import connections


async def migrate():
    conn = connections.get("default")
    # 可重复执行；旧数据保持 NULL，不能伪造或替换用户此前分发的口令。
    columns = await conn.execute_query_dict("PRAGMA table_info(deliverycode)")
    if not any(column["name"] == "code_value" for column in columns):
        await conn.execute_script("ALTER TABLE deliverycode ADD COLUMN code_value VARCHAR(64) NULL;")
