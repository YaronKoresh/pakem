from __future__ import annotations

from google.protobuf import descriptor_pb2, descriptor_pool, message_factory
from google.protobuf.message import Message


def _build_descriptor() -> descriptor_pb2.FileDescriptorProto:
    fd = descriptor_pb2.FileDescriptorProto()
    fd.name = "pakem.proto"
    fd.package = "pakem"

    dir_msg = fd.message_type.add()
    dir_msg.name = "Directory"
    dir_msg.field.add(
        name="name",
        number=1,
        type=descriptor_pb2.FieldDescriptorProto.TYPE_STRING,
    )
    dir_msg.field.add(
        name="path",
        number=2,
        type=descriptor_pb2.FieldDescriptorProto.TYPE_STRING,
    )
    dir_msg.field.add(
        name="depth",
        number=3,
        type=descriptor_pb2.FieldDescriptorProto.TYPE_INT32,
    )

    file_msg = fd.message_type.add()
    file_msg.name = "File"
    file_msg.field.add(
        name="name",
        number=1,
        type=descriptor_pb2.FieldDescriptorProto.TYPE_STRING,
    )
    file_msg.field.add(
        name="path",
        number=2,
        type=descriptor_pb2.FieldDescriptorProto.TYPE_STRING,
    )
    file_msg.field.add(
        name="size",
        number=3,
        type=descriptor_pb2.FieldDescriptorProto.TYPE_INT64,
    )
    file_msg.field.add(
        name="tokens",
        number=4,
        type=descriptor_pb2.FieldDescriptorProto.TYPE_INT64,
    )
    file_msg.field.add(
        name="type",
        number=5,
        type=descriptor_pb2.FieldDescriptorProto.TYPE_STRING,
    )
    file_msg.field.add(
        name="extension",
        number=6,
        type=descriptor_pb2.FieldDescriptorProto.TYPE_STRING,
    )
    file_msg.field.add(
        name="lines",
        number=7,
        type=descriptor_pb2.FieldDescriptorProto.TYPE_INT32,
    )
    file_msg.field.add(
        name="depth",
        number=8,
        type=descriptor_pb2.FieldDescriptorProto.TYPE_INT32,
    )
    file_msg.field.add(
        name="hash",
        number=9,
        type=descriptor_pb2.FieldDescriptorProto.TYPE_STRING,
    )
    file_msg.field.add(
        name="status",
        number=10,
        type=descriptor_pb2.FieldDescriptorProto.TYPE_STRING,
    )
    file_msg.field.add(
        name="content",
        number=11,
        type=descriptor_pb2.FieldDescriptorProto.TYPE_STRING,
        label=descriptor_pb2.FieldDescriptorProto.LABEL_REPEATED,
    )

    repo_msg = fd.message_type.add()
    repo_msg.name = "Repository"
    repo_msg.field.add(
        name="root",
        number=1,
        type=descriptor_pb2.FieldDescriptorProto.TYPE_STRING,
    )
    repo_msg.field.add(
        name="timestamp",
        number=2,
        type=descriptor_pb2.FieldDescriptorProto.TYPE_STRING,
    )
    repo_msg.field.add(
        name="total_files",
        number=3,
        type=descriptor_pb2.FieldDescriptorProto.TYPE_INT64,
    )
    repo_msg.field.add(
        name="total_size",
        number=4,
        type=descriptor_pb2.FieldDescriptorProto.TYPE_INT64,
    )
    repo_msg.field.add(
        name="total_tokens",
        number=5,
        type=descriptor_pb2.FieldDescriptorProto.TYPE_INT64,
    )
    repo_msg.field.add(
        name="directories",
        number=6,
        type=descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE,
        type_name="Directory",
        label=descriptor_pb2.FieldDescriptorProto.LABEL_REPEATED,
    )
    repo_msg.field.add(
        name="files",
        number=7,
        type=descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE,
        type_name="File",
        label=descriptor_pb2.FieldDescriptorProto.LABEL_REPEATED,
    )

    return fd


def get_repository_message_class() -> type[Message]:
    pool = descriptor_pool.DescriptorPool()
    fd = _build_descriptor()
    pool.Add(fd)

    return message_factory.GetMessageClass(
        pool.FindMessageTypeByName("pakem.Repository")
    )
