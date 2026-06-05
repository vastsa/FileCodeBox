import asyncio
import unittest

from core.storage import S3FileStorage


class FakeS3Client:
    def __init__(self, list_response):
        self.list_response = list_response
        self.head_calls = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def head_object(self, **kwargs):
        self.head_calls += 1
        raise RuntimeError("head not supported")

    async def list_objects_v2(self, **kwargs):
        return self.list_response


class S3FileExistsTests(unittest.TestCase):
    def test_file_exists_falls_back_to_list_objects(self):
        client = FakeS3Client({"Contents": [{"Key": "share/data/file.txt"}]})
        storage = S3FileStorage.__new__(S3FileStorage)
        storage.bucket_name = "bucket"
        storage._client = lambda: client

        exists = asyncio.run(storage.file_exists("share/data/file.txt"))

        self.assertTrue(exists)
        self.assertEqual(client.head_calls, 3)

    def test_file_exists_returns_false_when_missing(self):
        client = FakeS3Client({"Contents": [{"Key": "share/data/other.txt"}]})
        storage = S3FileStorage.__new__(S3FileStorage)
        storage.bucket_name = "bucket"
        storage._client = lambda: client

        exists = asyncio.run(storage.file_exists("share/data/file.txt"))

        self.assertFalse(exists)
