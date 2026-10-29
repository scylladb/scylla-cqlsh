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

# cqlsh against a node with client encryption on $CQL_SSL_TEST_PORT that requires a client
# certificate, using the certs scripts/gen-test-certs.py wrote to $CQL_SSL_TEST_CERTS.

import os

import pytest

from .cassconnect import cassandra_cursor, create_keyspace, remove_db, testcall_cqlsh as call_cqlsh_for_test

SSL_PORT = os.environ.get('CQL_SSL_TEST_PORT')
CERTS = os.environ.get('CQL_SSL_TEST_CERTS')

pytestmark = pytest.mark.skipif(not (SSL_PORT and CERTS), reason='SSL test is opt-in')


def cqlsh_over_ssl(tmp_path, cqlshrc, query, args=('--ssl',)):
    rc = tmp_path / 'cqlshrc'
    rc.write_text('[ssl]\n' + cqlshrc.format(certs=CERTS))
    env = os.environ.copy()
    env['COLUMNS'] = '100000'
    return call_cqlsh_for_test(keyspace=None, prompt=None, env=env, tty=False, port=SSL_PORT,
                               args=args + ('--cqlshrc', str(rc)), input=query + '\n')


CLIENT_CERT = 'userkey = {certs}/client.key\nusercert = {certs}/client.pem\n'
QUERY = "SELECT release_version FROM system.local WHERE key = 'local';"


def test_mutual_tls(tmp_path):
    output, result = cqlsh_over_ssl(tmp_path, 'certfile = {certs}/ca.pem\n' + CLIENT_CERT, QUERY)
    assert result == 0, output
    assert '(1 rows)' in output


def test_without_client_cert_is_rejected(tmp_path):
    output, result = cqlsh_over_ssl(tmp_path, 'certfile = {certs}/ca.pem\n', QUERY)
    assert result != 0
    assert 'CERTIFICATE_REQUIRED' in output


def test_wrong_ca_is_rejected(tmp_path):
    output, result = cqlsh_over_ssl(tmp_path, 'certfile = {certs}/client.pem\n' + CLIENT_CERT, QUERY)
    assert result != 0
    assert 'CERTIFICATE_VERIFY_FAILED' in output


def test_wrong_ca_without_validation(tmp_path):
    output, result = cqlsh_over_ssl(tmp_path, 'certfile = {certs}/client.pem\nvalidate = false\n' + CLIENT_CERT, QUERY)
    assert result == 0, output
    assert '(1 rows)' in output


def test_without_ssl_flag_fails(tmp_path):
    output, result = cqlsh_over_ssl(tmp_path, 'certfile = {certs}/ca.pem\n' + CLIENT_CERT, QUERY, args=())
    assert result != 0
    assert 'Unable to connect' in output


@pytest.fixture
def keyspace():
    with cassandra_cursor(ks=None) as c:
        ks = create_keyspace(c)
        c.execute('CREATE TABLE %s.t (k int PRIMARY KEY, v text)' % (ks,))
    yield ks
    remove_db()


def test_copy_round_trip(tmp_path, keyspace):
    # COPY workers open their own connections, rebuilding the SSL context from the cqlshrc
    csv = tmp_path / 't.csv'
    query = (f"INSERT INTO {keyspace}.t (k, v) VALUES (1, 'x');"
             f"COPY {keyspace}.t TO '{csv}';"
             f"TRUNCATE {keyspace}.t;"
             f"COPY {keyspace}.t FROM '{csv}';"
             f"SELECT * FROM {keyspace}.t;")
    output, result = cqlsh_over_ssl(tmp_path, 'certfile = {certs}/ca.pem\n' + CLIENT_CERT, query)
    assert result == 0, output
    assert '1 rows exported' in output
    assert '1 rows imported' in output
    assert '(1 rows)' in output
