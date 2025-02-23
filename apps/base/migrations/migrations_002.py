from tortoise import connections


async def create_upload_chunk_and_update_file_codes_table():
    conn = connections.get("default")
    await conn.execute_script(
        """
        ALTER TABLE "filecodes" ADD "file_hash" VARCHAR(128);
        ALTER TABLE "filecodes" ADD "is_chunked" BOOL NOT NULL DEFAULT False;
        ALTER TABLE "filecodes" ADD "upload_id" VARCHAR(128);
        CREATE TABLE "uploadchunk" (
            id  INTEGER  not null   primary key autoincrement,
            "upload_id" VARCHAR(36) NOT NULL,
            "chunk_index" INT NOT NULL,
            "chunk_hash" VARCHAR(128) NOT NULL,
            "total_chunks" INT NOT NULL,
            "file_size" BIGINT NOT NULL,
            "chunk_size" INT NOT NULL,
            "created_at" TIMESTAMPTZ NOT NULL,
            "file_name" VARCHAR(255) NOT NULL,
            "completed" BOOL NOT NULL
        );
    """
    )


async def migrate():
    await create_upload_chunk_and_update_file_codes_table()
