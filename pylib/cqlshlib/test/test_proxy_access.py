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

import os

import pytest

from .cassconnect import testcall_cqlsh as call_cqlsh_for_test


@pytest.mark.skipif(
    not os.environ.get('CQL_PROXY_TEST_HOST'),
    reason='proxy access test is opt-in')
def test_proxy_access_without_rewriting_broadcast_address():
    env = os.environ.copy()
    env['COLUMNS'] = '100000'
    env.setdefault('LC_CTYPE', 'en_US.utf8')

    query = "SELECT broadcast_address FROM system.local WHERE key = 'local';"
    output, result = call_cqlsh_for_test(
        keyspace=None,
        prompt=None,
        env=env,
        tty=False,
        host=os.environ['CQL_PROXY_TEST_HOST'],
        port=os.environ.get('CQL_PROXY_TEST_PORT', '9042'),
        input=query + '\n')

    assert result == 0, output
    assert 'broadcast_address' in output

    blocked_host = os.environ.get('CQL_PROXY_TEST_BLOCKED_HOST')
    if blocked_host:
        assert blocked_host in output
