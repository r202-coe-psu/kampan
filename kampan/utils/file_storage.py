import gridfs
import bson
from bson import ObjectId
from mongoengine import get_db
import io
from datetime import datetime
from typing import Optional, Dict, Any, Union, BinaryIO


class File:

    def __init__(
        self,
        bucket_name: str = "fs",
        chunk_size_bytes: int = 261120,
        collection_name: Optional[str] = None,
        file_id: Optional[Union[str, ObjectId]] = None,
    ):
        self.bucket_name = bucket_name
        self.chunk_size_bytes = chunk_size_bytes
        self.collection_name = collection_name
        self.file_id = file_id

        if collection_name:
            self.collection = collection_name
            if not self.collection.endswith("_fs"):
                self.collection = f"{collection_name}_fs"
        else:
            self.collection = None

        self.db = None
        self.fs = None

    def init(self):
        self.db = get_db()

        if self.collection:
            self.fs = gridfs.GridFS(self.db, collection=self.collection)
        else:
            self.fs = gridfs.GridFS(self.db)

    def get_gridfs(self) -> gridfs.GridFS:
        """ดึง GridFS instance"""
        if self.db is None or self.fs is None:
            self.init()
        return self.fs

    def put(
        self, data: Union[bytes, BinaryIO], metadata: Optional[Dict[str, Any]] = None
    ) -> ObjectId:

        fs = self.get_gridfs()

        if metadata is None:
            metadata = {}

        if "upload_date" not in metadata:
            metadata["upload_date"] = datetime.now()

        if isinstance(data, bytes):
            filename = metadata.get("filename", "unknown_file")
            content_type = metadata.get("content_type", "application/octet-stream")

            file_id = fs.put(
                data,
                filename=filename,
                content_type=content_type,
                metadata=metadata,
                chunk_size=self.chunk_size_bytes,
            )
        else:
            filename = getattr(
                data, "filename", metadata.get("filename", "unknown_file")
            )
            content_type = getattr(
                data,
                "content_type",
                metadata.get("content_type", "application/octet-stream"),
            )

            if hasattr(data, "read"):
                file_data = data.read()
                if hasattr(data, "seek"):
                    data.seek(0)
            else:
                file_data = data

            file_id = fs.put(
                file_data,
                filename=filename,
                content_type=content_type,
                metadata=metadata,
                chunk_size=self.chunk_size_bytes,
            )

        self.file_id = file_id
        return file_id

    def get(self):

        if not self.file_id:
            raise ValueError("file_id is required")

        fs = self.get_gridfs()

        try:
            if isinstance(self.file_id, str):
                file_id = ObjectId(self.file_id)
            else:
                file_id = self.file_id

            return fs.get(file_id)
        except gridfs.NoFile:
            return None

    def get_as_dict(self) -> Optional[Dict[str, Any]]:

        grid_out = self.get()
        if not grid_out:
            return None

        return {
            "file_stream": io.BytesIO(grid_out.read()),
            "filename": grid_out.filename,
            "content_type": grid_out.content_type,
            "metadata": grid_out.metadata or {},
            "length": grid_out.length,
            "upload_date": grid_out.upload_date,
            "md5": grid_out.md5,
            "file_id": grid_out._id,
        }

    def get_bytes(self) -> Optional[bytes]:

        grid_out = self.get()
        if not grid_out:
            return None
        return grid_out.read()

    def delete(self) -> bool:

        if not self.file_id:
            raise ValueError("file_id is required")

        fs = self.get_gridfs()

        try:
            if isinstance(self.file_id, str):
                file_id = ObjectId(self.file_id)
            else:
                file_id = self.file_id

            fs.delete(file_id)
            return True
        except gridfs.NoFile:
            return False

    def exists(self) -> bool:

        if not self.file_id:
            return False

        fs = self.get_gridfs()

        try:
            if isinstance(self.file_id, str):
                file_id = ObjectId(self.file_id)
            else:
                file_id = self.file_id

            return fs.exists(file_id)
        except:
            return False

    def get_info(self) -> Optional[Dict[str, Any]]:

        if not self.file_id:
            return None

        try:
            if isinstance(self.file_id, str):
                file_id = ObjectId(self.file_id)
            else:
                file_id = self.file_id

            file_doc = self.db.fs.files.find_one({"_id": file_id})

            if not file_doc:
                return None

            return {
                "_id": file_doc["_id"],
                "filename": file_doc["filename"],
                "content_type": file_doc.get("contentType"),
                "length": file_doc["length"],
                "upload_date": file_doc["uploadDate"],
                "metadata": file_doc.get("metadata", {}),
                "md5": file_doc.get("md5"),
            }
        except:
            return None

    @classmethod
    def list_files(
        cls,
        filter_metadata: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None,
        skip: Optional[int] = None,
        bucket_name: str = "fs",
        collection_name: Optional[str] = None,
    ) -> list:

        temp_file = cls(bucket_name=bucket_name, collection_name=collection_name)
        temp_file.init()

        query = {}
        if filter_metadata:
            for key, value in filter_metadata.items():
                query[f"metadata.{key}"] = value

        cursor = temp_file.db.fs.files.find(query)

        if skip:
            cursor = cursor.skip(skip)
        if limit:
            cursor = cursor.limit(limit)

        files = []
        for file_doc in cursor:
            files.append(
                {
                    "_id": file_doc["_id"],
                    "filename": file_doc["filename"],
                    "content_type": file_doc.get("contentType"),
                    "length": file_doc["length"],
                    "upload_date": file_doc["uploadDate"],
                    "metadata": file_doc.get("metadata", {}),
                }
            )

        return files


def save_file(
    data: Union[bytes, BinaryIO],
    filename: str,
    content_type: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    bucket_name: str = "fs",
    collection_name: Optional[str] = None,
) -> ObjectId:
    if metadata is None:
        metadata = {}

    metadata.update({"filename": filename, "content_type": content_type})

    file_obj = File(bucket_name=bucket_name, collection_name=collection_name)
    return file_obj.put(data, metadata)


def get_file(
    file_id: Union[str, ObjectId],
    bucket_name: str = "fs",
    collection_name: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    file_obj = File(
        bucket_name=bucket_name, collection_name=collection_name, file_id=file_id
    )
    return file_obj.get_as_dict()


def delete_file(
    file_id: Union[str, ObjectId],
    bucket_name: str = "fs",
    collection_name: Optional[str] = None,
) -> bool:
    file_obj = File(
        bucket_name=bucket_name, collection_name=collection_name, file_id=file_id
    )
    return file_obj.delete()


def file_exists(
    file_id: Union[str, ObjectId],
    bucket_name: str = "fs",
    collection_name: Optional[str] = None,
) -> bool:
    file_obj = File(
        bucket_name=bucket_name, collection_name=collection_name, file_id=file_id
    )
    return file_obj.exists()
