# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from cassandra.metadata import RegisteredTableExtension
import io
import struct


# Add a handler for schema extensions to at least print 
# the info when doing "desc <table>".
#
# The end result will not be cut-and-paste usable; we'd need to modify the
# driver for this. But it is something.
class MapExtensionReader:
    def __init__(self, ext_blob):
        self.bytes = io.BytesIO(ext_blob)        

    def read_string(self):
        # strings are little endian 32-bit len  bytes
        utf_length = struct.unpack('<I', self.bytes.read(4))[0]
        return self.bytes.read(utf_length).decode()

    def read_pair(self):
        # each map::value_type is written as <string><string>
        key = self.read_string()
        val = self.read_string()
        return key, val

    def read_map(self):
        # num elements
        len = struct.unpack('<I', self.bytes.read(4))[0]
        res = {}
        # x value_type pairs
        for x in range(0, len):
            p = self.read_pair()
            res[p[0]] = p[1]
        return res


# Extension for CDC info
class CdcExt(RegisteredTableExtension):
    name = 'cdc'

    @classmethod
    def after_table_cql(cls, table_meta, ext_key, ext_blob):
        # For cdc options, the blob is actually 
        # a serialized unorderd_map<string, string>. 
        mer = MapExtensionReader(ext_blob)
        return "%s = %s" % (ext_key, mer.read_map())


# Extension for alternator's `scylla_tags`
class ScyllaTagsExt(RegisteredTableExtension):
    name = 'scylla_tags'

    @classmethod
    def after_table_cql(cls, table_meta, ext_key, ext_blob):
        # For scylla_tags, the blob is actually 
        # a serialized unorderd_map<string, string>. 
        mer = MapExtensionReader(ext_blob)
        return "%s = %s" % (ext_key, mer.read_map())

