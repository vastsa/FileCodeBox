from tortoise import connections

# 高频查询字段索引。真实部署的 schema 全部由迁移建立
# （init_db 不调用 generate_schemas），因此索引必须写在迁移里；
# apps/base/models.py 中的 index/Meta 仅用于测试的 generate_schemas 路径。
#
# - filecodes(expired_at)：过期扫描（delete_expire_files）与后台过期统计。
# - filecodes(created_at)：后台默认倒序列表、首页最近记录、今日/昨日统计。
# - uploadchunk(upload_id, chunk_index)：分片状态检查与合并；其前缀同时
#   覆盖仅按 upload_id 的删除/清理查询（原先没有对应索引）。
# 已知缺口：clean_incomplete_uploads 的 chunk_index=-1 AND created_at<? 用不上
# 该复合索引，待清理任务改为分批查询后再评估。


async def migrate():
    conn = connections.get("default")
    await conn.execute_script(
        """
        CREATE INDEX IF NOT EXISTS idx_filecodes_expired_at
            ON filecodes (expired_at);
        CREATE INDEX IF NOT EXISTS idx_filecodes_created_at
            ON filecodes (created_at);
        CREATE INDEX IF NOT EXISTS idx_uploadchunk_upload_chunk
            ON uploadchunk (upload_id, chunk_index);
        """
    )
