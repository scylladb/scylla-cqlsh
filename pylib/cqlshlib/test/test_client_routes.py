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

import pytest
from unittest.mock import MagicMock, patch


class FakeClientRouteProxy(object):

    def __init__(self, connection_id, connection_addr_override=None):
        self.connection_id = connection_id
        self.connection_addr_override = connection_addr_override


class FakeClientRoutesConfig(object):

    def __init__(self, proxies, advanced_shard_awareness=False):
        self.proxies = proxies
        self.advanced_shard_awareness = advanced_shard_awareness


def patch_client_routes_driver(cqlsh_module):
    return patch.multiple(
        cqlsh_module,
        ClientRouteProxy=FakeClientRouteProxy,
        ClientRoutesConfig=FakeClientRoutesConfig)


def test_parse_client_routes_accepts_ids_and_overrides(cqlsh_module):
    assert cqlsh_module.parse_client_routes('conn-a=proxy-a.example.com,\nconn-b') == [
        ('conn-a', 'proxy-a.example.com'),
        ('conn-b', None),
    ]


def test_parse_client_routes_rejects_empty_connection_id(cqlsh_module):
    with pytest.raises(ValueError, match='empty connection id'):
        cqlsh_module.parse_client_routes('=proxy-a.example.com')


def test_parse_client_routes_rejects_empty_address_override(cqlsh_module):
    with pytest.raises(ValueError, match='empty address override'):
        cqlsh_module.parse_client_routes('conn-a=')


def test_read_options_uses_client_routes_from_cqlshrc(tmp_path, cqlsh_module):
    temp_cqlshrc = tmp_path / 'cqlshrc'
    temp_cqlshrc.write_text(
        '[connection]\n'
        'hostname = seed.example.com\n'
        '[client_routes]\n'
        'proxies = conn-a=proxy-a.example.com,\n'
        '          conn-b\n'
        'advanced_shard_awareness = true\n')

    with patch_client_routes_driver(cqlsh_module), \
            patch.object(cqlsh_module, 'CONFIG_FILE', str(temp_cqlshrc)):
        options, hostname, port = cqlsh_module.read_options([], {})

    assert hostname == 'seed.example.com'
    assert options.client_routes == [
        ('conn-a', 'proxy-a.example.com'),
        ('conn-b', None),
    ]
    assert options.client_routes_config.advanced_shard_awareness is True
    assert [p.connection_id for p in options.client_routes_config.proxies] == ['conn-a', 'conn-b']
    assert options.client_routes_config.proxies[0].connection_addr_override == 'proxy-a.example.com'
    assert options.client_routes_config.proxies[1].connection_addr_override is None


def test_read_options_client_route_cli_replaces_cqlshrc(tmp_path, cqlsh_module):
    temp_cqlshrc = tmp_path / 'cqlshrc'
    temp_cqlshrc.write_text(
        '[connection]\n'
        '[client_routes]\n'
        'proxies = config-conn=config-proxy.example.com\n')

    with patch_client_routes_driver(cqlsh_module), \
            patch.object(cqlsh_module, 'CONFIG_FILE', str(temp_cqlshrc)):
        options, hostname, port = cqlsh_module.read_options(
            ['--client-route', 'cli-conn=cli-proxy.example.com'], {})

    assert hostname == 'cli-proxy.example.com'
    assert options.contact_points == ('cli-proxy.example.com',)
    assert options.client_routes == [('cli-conn', 'cli-proxy.example.com')]
    assert [p.connection_id for p in options.client_routes_config.proxies] == ['cli-conn']


def test_read_options_requires_driver_support_when_routes_enabled(tmp_path, cqlsh_module):
    temp_cqlshrc = tmp_path / 'cqlshrc'
    temp_cqlshrc.write_text('[connection]\n')

    with patch.object(cqlsh_module, 'ClientRouteProxy', None), \
            patch.object(cqlsh_module, 'ClientRoutesConfig', None), \
            patch.object(cqlsh_module, 'CONFIG_FILE', str(temp_cqlshrc)), \
            pytest.raises(SystemExit):
        cqlsh_module.read_options(['--client-route', 'conn-a'], {})


def test_read_options_allows_old_driver_when_routes_disabled(tmp_path, cqlsh_module):
    temp_cqlshrc = tmp_path / 'cqlshrc'
    temp_cqlshrc.write_text('[connection]\n')

    with patch.object(cqlsh_module, 'ClientRouteProxy', None), \
            patch.object(cqlsh_module, 'ClientRoutesConfig', None), \
            patch.object(cqlsh_module, 'CONFIG_FILE', str(temp_cqlshrc)):
        options, hostname, port = cqlsh_module.read_options([], {})

    assert options.client_routes == []
    assert options.client_routes_config is None


def test_shell_passes_client_routes_config_to_cluster(cqlsh_module):
    client_routes_config = FakeClientRoutesConfig(
        [FakeClientRouteProxy('conn-a', 'proxy-a.example.com')])

    with patch.object(cqlsh_module, 'Cluster') as mock_cluster:
        mock_cluster_instance = MagicMock()
        mock_cluster.return_value = mock_cluster_instance
        mock_session = MagicMock()
        mock_cluster_instance.connect.return_value = mock_session
        mock_cluster_instance.cql_version = '3.4.5'
        mock_cluster_instance.protocol_version = 4
        mock_cluster_instance.metadata.keyspaces = []

        def execute_side_effect(query):
            if 'system.local' in query:
                return [{'cql_version': '3.4.5', 'release_version': '4.0.0'}]
            if 'system.versions' in query:
                return [{'version': '5.0.0'}]
            return []

        mock_session.execute.side_effect = execute_side_effect

        cqlsh_module.Shell(
            'proxy-a.example.com',
            9042,
            client_routes_config=client_routes_config,
            contact_points=('proxy-a.example.com', 'proxy-b.example.com'),
            encoding='utf-8')

    call_kwargs = mock_cluster.call_args[1]
    assert call_kwargs['contact_points'] == ('proxy-a.example.com', 'proxy-b.example.com')
    assert call_kwargs['client_routes_config'] is client_routes_config
    profile = call_kwargs['execution_profiles'][cqlsh_module.EXEC_PROFILE_DEFAULT]
    assert isinstance(profile.load_balancing_policy, cqlsh_module.RoundRobinPolicy)


def test_login_reconnect_preserves_client_routes(cqlsh_module):
    client_routes_config = object()
    contact_points = ('proxy-a.example.com', 'proxy-b.example.com')
    profile = cqlsh_module.ExecutionProfile(load_balancing_policy=cqlsh_module.RoundRobinPolicy())

    shell = MagicMock()
    shell.contact_points = contact_points
    shell.port = 9042
    shell.conn.cql_version = '3.4.5'
    shell.conn.protocol_version = 4
    shell.conn.connect_timeout = 5
    shell.conn.ssl_context = 'ssl-context'
    shell.conn.ssl_options = {'server_hostname': 'proxy-a.example.com'}
    shell.client_routes_config = client_routes_config
    shell.no_compression = False
    shell.profiles = {cqlsh_module.EXEC_PROFILE_DEFAULT: profile}
    shell.current_keyspace = 'testks'
    shell.session.max_trace_wait = 10

    parsed = MagicMock()
    parsed.get_binding.side_effect = lambda name: {
        'username': 'alice',
        'password': "'secret'",
    }[name]

    with patch.object(cqlsh_module, 'Cluster') as mock_cluster:
        session = MagicMock()
        mock_cluster.return_value.connect.return_value = session

        cqlsh_module.Shell.do_login(shell, parsed)

    call_kwargs = mock_cluster.call_args[1]
    assert call_kwargs['contact_points'] == contact_points
    assert call_kwargs['client_routes_config'] is client_routes_config
    assert call_kwargs['execution_profiles'] is shell.profiles
    profile = call_kwargs['execution_profiles'][cqlsh_module.EXEC_PROFILE_DEFAULT]
    assert isinstance(profile.load_balancing_policy, cqlsh_module.RoundRobinPolicy)
    mock_cluster.return_value.connect.assert_called_once_with('testks')
    assert shell.conn is mock_cluster.return_value
    assert shell.session is session


def test_source_subshell_preserves_client_routes(cqlsh_module, tmp_path):
    client_routes_config = object()
    contact_points = ('proxy-a.example.com', 'proxy-b.example.com')
    source_file = tmp_path / 'source.cql'
    source_file.write_text('COPY test.tbl TO STDOUT;\n')

    parent_shell = MagicMock()
    parent_shell.hostname = 'proxy-a.example.com'
    parent_shell.port = 9042
    parent_shell.color = False
    parent_shell.username = None
    parent_shell.encoding = 'utf-8'
    parent_shell.conn.connect_timeout = 5
    parent_shell.session.default_timeout = 10
    parent_shell.cql_version = '3.4.5'
    parent_shell.current_keyspace = 'testks'
    parent_shell.tracing_enabled = False
    parent_shell.display_nanotime_format = cqlsh_module.DEFAULT_NANOTIME_FORMAT
    parent_shell.display_timestamp_format = cqlsh_module.DEFAULT_TIMESTAMP_FORMAT
    parent_shell.display_date_format = cqlsh_module.DEFAULT_DATE_FORMAT
    parent_shell.display_float_precision = cqlsh_module.DEFAULT_FLOAT_PRECISION
    parent_shell.display_double_precision = cqlsh_module.DEFAULT_DOUBLE_PRECISION
    parent_shell.display_timezone = None
    parent_shell.max_trace_wait = cqlsh_module.DEFAULT_MAX_TRACE_WAIT
    parent_shell.ssl = False
    parent_shell.auth_provider = None
    parent_shell.client_routes_config = client_routes_config
    parent_shell.contact_points = contact_points
    parent_shell.coverage = False
    parent_shell.cql_unprotect_value.return_value = str(source_file)

    parsed = MagicMock()
    parsed.get_binding.return_value = str(source_file)

    original_shell = cqlsh_module.Shell
    with patch.object(cqlsh_module, 'Shell') as mock_shell:
        subshell = MagicMock()
        mock_shell.return_value = subshell

        original_shell.do_source(parent_shell, parsed)

    call_kwargs = mock_shell.call_args[1]
    assert call_kwargs['use_conn'] is parent_shell.conn
    assert call_kwargs['client_routes_config'] is client_routes_config
    assert call_kwargs['contact_points'] == contact_points
    subshell.cmdloop.assert_called_once_with()
