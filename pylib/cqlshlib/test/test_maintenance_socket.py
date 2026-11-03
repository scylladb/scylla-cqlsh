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

# cqlsh against a Scylla node's Unix maintenance socket ($CQL_MAINTENANCE_SOCKET), the path
# scylladb's test_maintenance_mode, test_maintenance_socket and test_describe use with the driver
# directly. The socket isn't the node's address in system.peers/system.local, so a driver that
# only opens query pools to hosts it discovered (scylla-driver 3.29.8) can't run a single query.

import os

import pytest

from .run_cqlsh import call_cqlsh

SOCKET = os.environ.get('CQL_MAINTENANCE_SOCKET')

pytestmark = pytest.mark.skipif(not SOCKET, reason='maintenance socket test is opt-in')


def test_queries_over_maintenance_socket():
    output, result = call_cqlsh(host=SOCKET, tty=False,
                                input=b"SELECT cluster_name FROM system.local WHERE key = 'local';\n"
                                      b"DESCRIBE CLUSTER;\n")
    assert result == 0, output
    assert '(1 rows)' in output
    assert 'Murmur3Partitioner' in output
