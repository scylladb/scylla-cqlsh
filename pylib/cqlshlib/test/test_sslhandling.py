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
import shutil
import ssl
import subprocess
import sys

import pytest

from cqlshlib.sslhandling import ssl_settings
from .basecase import cassandra_dir

MISSING = '/nonexistent/cert.pem'


@pytest.fixture(scope='session')
def certs(tmp_path_factory):
    if not shutil.which('openssl'):
        pytest.skip('generating test certs needs openssl')
    out = tmp_path_factory.mktemp('certs')
    subprocess.run([sys.executable, os.path.join(cassandra_dir, 'scripts', 'gen-test-certs.py'), str(out)], check=True)
    return out


def write_cqlshrc(tmp_path, content):
    path = tmp_path / 'cqlshrc'
    path.write_text(content)
    return str(path)


def test_ssl_section_certfile(tmp_path, certs):
    rc = write_cqlshrc(tmp_path, f'[ssl]\ncertfile = {certs}/ca.pem\n')
    ctx = ssl_settings('host1', rc, env={})
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert ctx.check_hostname is False


def test_certfiles_section_beats_ssl_section(tmp_path, certs):
    # a losing option pointing at a missing file would make loading it fail
    rc = write_cqlshrc(tmp_path, f'[ssl]\ncertfile = {MISSING}\n[certfiles]\nhost1 = {certs}/ca.pem\n')
    ssl_settings('host1', rc, env={})


def test_env_certfile_beats_cqlshrc(tmp_path, certs):
    rc = write_cqlshrc(tmp_path, f'[ssl]\ncertfile = {MISSING}\n[certfiles]\nhost1 = {MISSING}\n')
    ssl_settings('host1', rc, env={'SSL_CERTFILE': f'{certs}/ca.pem'})


def test_certfile_tilde_is_expanded(tmp_path, certs, monkeypatch):
    shutil.copy(certs / 'ca.pem', tmp_path / 'ca.pem')
    monkeypatch.setenv('HOME', str(tmp_path))
    rc = write_cqlshrc(tmp_path, '[ssl]\ncertfile = ~/ca.pem\n')
    ssl_settings('host1', rc, env={})


def test_validate_without_certfile_exits(tmp_path):
    rc = write_cqlshrc(tmp_path, '[ssl]\n')
    with pytest.raises(SystemExit, match='Validation is enabled'):
        ssl_settings('host1', rc, env={})


def test_validate_false_needs_no_certfile(tmp_path):
    rc = write_cqlshrc(tmp_path, '[ssl]\nvalidate = false\n')
    ctx = ssl_settings('host1', rc, env={})
    assert ctx.verify_mode == ssl.CERT_NONE


def test_env_validate_beats_cqlshrc(tmp_path):
    rc = write_cqlshrc(tmp_path, '[ssl]\nvalidate = true\n')
    ctx = ssl_settings('host1', rc, env={'SSL_VALIDATE': 'false'})
    assert ctx.verify_mode == ssl.CERT_NONE


def test_check_hostname(tmp_path, certs):
    rc = write_cqlshrc(tmp_path, f'[ssl]\ncertfile = {certs}/ca.pem\ncheck_hostname = true\n')
    assert ssl_settings('host1', rc, env={}).check_hostname is True


def test_check_hostname_without_validate_exits(tmp_path):
    rc = write_cqlshrc(tmp_path, '[ssl]\nvalidate = false\ncheck_hostname = true\n')
    with pytest.raises(SystemExit, match='hostname checking'):
        ssl_settings('host1', rc, env={})


def test_client_cert_is_loaded(tmp_path, certs):
    rc = write_cqlshrc(tmp_path, f'[ssl]\ncertfile = {certs}/ca.pem\n'
                                 f'userkey = {certs}/client.key\nusercert = {certs}/client.pem\n')
    ssl_settings('host1', rc, env={})


def test_client_key_not_matching_cert_fails(tmp_path, certs):
    rc = write_cqlshrc(tmp_path, f'[ssl]\ncertfile = {certs}/ca.pem\n'
                                 f'userkey = {certs}/server.key\nusercert = {certs}/client.pem\n')
    with pytest.raises(ssl.SSLError):
        ssl_settings('host1', rc, env={})


@pytest.mark.parametrize('option', ['userkey', 'usercert'])
def test_only_one_of_userkey_usercert_warns(tmp_path, certs, capsys, option):
    rc = write_cqlshrc(tmp_path, f'[ssl]\ncertfile = {certs}/ca.pem\n{option} = {MISSING}\n')
    ssl_settings('host1', rc, env={})
    assert 'should be both configured' in capsys.readouterr().out


def test_ssl_version_is_ignored_with_warning(tmp_path, capsys):
    rc = write_cqlshrc(tmp_path, '[ssl]\nvalidate = false\n')
    ctx = ssl_settings('host1', rc, env={'SSL_VERSION': 'TLSv1_2'})
    assert ctx.protocol == ssl.PROTOCOL_TLS_CLIENT
    assert 'ignored' in capsys.readouterr().out
