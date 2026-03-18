from __future__ import annotations


def get_json_schema() -> str:
    return """{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "Pakem Repository",
  "type": "object",
  "properties": {
    "repository": {
      "type": "object",
      "properties": {
        "root": {"type": "string"},
        "timestamp": {"type": "string"},
        "total_files": {"type": "integer"},
        "total_size": {"type": "integer"},
        "total_tokens": {"type": "integer"}
      },
      "required": ["root", "timestamp", "total_files", "total_size", "total_tokens"]
    },
    "directories": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "name": {"type": "string"},
          "path": {"type": "string"},
          "depth": {"type": "integer"}
        },
        "required": ["name", "path", "depth"]
      }
    },
    "files": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "name": {"type": "string"},
          "path": {"type": "string"},
          "size": {"type": "integer"},
          "tokens": {"type": "integer"},
          "type": {"type": "string"},
          "extension": {"type": "string"},
          "lines": {"type": "integer"},
          "depth": {"type": "integer"},
          "hash": {"type": "string"},
          "status": {"type": "string"},
          "content": {
            "type": "array",
            "items": {"type": "string"}
          }
        },
        "required": ["name", "path", "size", "tokens", "type", "extension", "lines", "depth", "content"]
      }
    }
  },
  "required": ["repository", "directories", "files"]
}
"""


def get_proto_schema() -> str:
    return """syntax = "proto3";

package pakem;

message Directory {
  string name = 1;
  string path = 2;
  int32 depth = 3;
}

message File {
  string name = 1;
  string path = 2;
  int64 size = 3;
  int64 tokens = 4;
  string type = 5;
  string extension = 6;
  int32 lines = 7;
  int32 depth = 8;
  string hash = 9;
  string status = 10;
  repeated string content = 11;
}

message Repository {
  string root = 1;
  string timestamp = 2;
  int64 total_files = 3;
  int64 total_size = 4;
  int64 total_tokens = 5;
  repeated Directory directories = 6;
  repeated File files = 7;
}
"""


def get_xml_schema() -> str:
    return """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<xs:schema xmlns:xs=\"http://www.w3.org/2001/XMLSchema\">
  <xs:element name=\"repository\">
    <xs:complexType>
      <xs:sequence>
        <xs:element name=\"directory\" minOccurs=\"0\" maxOccurs=\"unbounded\">
          <xs:complexType>
            <xs:attribute name=\"name\" type=\"xs:string\" use=\"required\"/>
            <xs:attribute name=\"path\" type=\"xs:string\" use=\"required\"/>
            <xs:attribute name=\"depth\" type=\"xs:int\" use=\"required\"/>
          </xs:complexType>
        </xs:element>
        <xs:element name=\"file\" minOccurs=\"0\" maxOccurs=\"unbounded\">
          <xs:complexType>
            <xs:sequence>
              <xs:element name=\"line\" minOccurs=\"0\" maxOccurs=\"unbounded\">
                <xs:complexType>
                  <xs:attribute name=\"index\" type=\"xs:int\" use=\"required\"/>
                  <xs:attribute name=\"length\" type=\"xs:int\" use=\"required\"/>
                  <xs:attribute name=\"indentation\" type=\"xs:int\" use=\"required\"/>
                </xs:complexType>
              </xs:element>
            </xs:sequence>
            <xs:attribute name=\"name\" type=\"xs:string\" use=\"required\"/>
            <xs:attribute name=\"path\" type=\"xs:string\" use=\"required\"/>
            <xs:attribute name=\"size\" type=\"xs:long\" use=\"required\"/>
            <xs:attribute name=\"tokens\" type=\"xs:long\" use=\"required\"/>
            <xs:attribute name=\"type\" type=\"xs:string\" use=\"required\"/>
            <xs:attribute name=\"extension\" type=\"xs:string\" use=\"required\"/>
            <xs:attribute name=\"lines\" type=\"xs:int\" use=\"required\"/>
            <xs:attribute name=\"depth\" type=\"xs:int\" use=\"required\"/>
            <xs:attribute name=\"hash\" type=\"xs:string\" use=\"optional\"/>
            <xs:attribute name=\"status\" type=\"xs:string\" use=\"optional\"/>
          </xs:complexType>
        </xs:element>
      </xs:sequence>
      <xs:attribute name=\"root\" type=\"xs:string\" use=\"required\"/>
      <xs:attribute name=\"timestamp\" type=\"xs:string\" use=\"required\"/>
      <xs:attribute name=\"total_files\" type=\"xs:long\" use=\"required\"/>
      <xs:attribute name=\"total_size\" type=\"xs:long\" use=\"required\"/>
      <xs:attribute name=\"total_tokens\" type=\"xs:long\" use=\"required\"/>
    </xs:complexType>
  </xs:element>
</xs:schema>
"""


def get_schema_text(format: str) -> str:
    format = format.lower()
    if format == "json":
        return get_json_schema()
    if format in ("proto", "protobuf"):
        return get_proto_schema()
    return get_xml_schema()
