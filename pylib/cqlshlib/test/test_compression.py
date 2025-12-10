#  Licensed to the Apache Software Foundation (ASF) under one
#  or more contributor license agreements.  See the NOTICE file
#  distributed with this work for additional information
#  regarding copyright ownership.  The ASF licenses this file
#  to you under the Apache License, Version 2.0 (the
#  "License"); you may not use this file except in compliance
#  with the License.  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

import sys
import pytest
from unittest.mock import patch, MagicMock


def test_read_options_default_compression(tmp_path, cqlsh_module):
    """Test that compression is enabled by default"""
    # Create a minimal cqlshrc file
    temp_cqlshrc = tmp_path / 'cqlshrc'
    temp_cqlshrc.write_text('[connection]\n')
    
    with patch.object(cqlsh_module, 'CONFIG_FILE', str(temp_cqlshrc)):
        options, hostname, port = cqlsh_module.read_options([], {})
        
        # Verify no_compression defaults to False (compression enabled)
        assert options.no_compression is False


def test_read_options_with_no_compression_in_cqlshrc(tmp_path, cqlsh_module):
    """Test that no_compression can be read from cqlshrc"""
    # Create a temporary cqlshrc file
    temp_cqlshrc = tmp_path / 'cqlshrc'
    temp_cqlshrc.write_text('[connection]\nno_compression = true\n')
    
    with patch.object(cqlsh_module, 'CONFIG_FILE', str(temp_cqlshrc)):
        options, hostname, port = cqlsh_module.read_options([], {})
        
        # Verify no_compression option was read correctly
        assert options.no_compression is True


def test_read_options_with_cli_no_compression(tmp_path, cqlsh_module):
    """Test that --no-compression command line option works"""
    temp_cqlshrc = tmp_path / 'cqlshrc'
    temp_cqlshrc.write_text('[connection]\n')
    
    with patch.object(cqlsh_module, 'CONFIG_FILE', str(temp_cqlshrc)):
        options, hostname, port = cqlsh_module.read_options(['--no-compression'], {})
        
        # Verify no_compression was set from command line
        assert options.no_compression is True


def test_shell_compression_disabled_when_no_compression_true(cqlsh_module):
    """Test that Shell passes compression=False to Cluster when no_compression=True"""
    # Patch Cluster in the cqlsh module namespace
    with patch.object(cqlsh_module, 'Cluster') as mock_cluster:
        mock_cluster_instance = MagicMock()
        mock_cluster.return_value = mock_cluster_instance
        mock_session = MagicMock()
        mock_cluster_instance.connect.return_value = mock_session
        mock_cluster_instance.cql_version = '3.4.5'
        mock_cluster_instance.protocol_version = 4
        mock_cluster_instance.metadata.keyspaces = []
        
        # Mock the session.execute to return different results based on the query
        def execute_side_effect(query):
            if 'system.local' in query:
                return [{'cql_version': '3.4.5', 'release_version': '4.0.0'}]
            elif 'system.versions' in query:
                # Simulate Scylla-specific table returning a row
                return [{'version': '5.0.0'}]
            return []
        
        mock_session.execute.side_effect = execute_side_effect
        
        # Create Shell with no_compression=True
        shell = cqlsh_module.Shell('localhost', 9042, no_compression=True, encoding='utf-8')
        
        # Verify Cluster was called
        mock_cluster.assert_called_once()
        
        # Verify compression was set to False in kwargs
        call_kwargs = mock_cluster.call_args[1]
        assert 'compression' in call_kwargs
        assert call_kwargs['compression'] is False


def test_shell_compression_enabled_by_default(cqlsh_module):
    """Test that compression parameter is not set when no_compression=False (driver default)"""
    with patch.object(cqlsh_module, 'Cluster') as mock_cluster:
        mock_cluster_instance = MagicMock()
        mock_cluster.return_value = mock_cluster_instance
        mock_session = MagicMock()
        mock_cluster_instance.connect.return_value = mock_session
        mock_cluster_instance.cql_version = '3.4.5'
        mock_cluster_instance.protocol_version = 4
        mock_cluster_instance.metadata.keyspaces = []

        # Mock the session.execute to return different results based on the query
        def execute_side_effect(query):
            if 'system.local' in query:
                return [{'cql_version': '3.4.5', 'release_version': '4.0.0'}]
            elif 'system.versions' in query:
                # Simulate Scylla-specific table returning a row
                return [{'version': '5.0.0'}]
            return []

        mock_session.execute.side_effect = execute_side_effect

        # Create Shell with no_compression=False (default)
        shell = cqlsh_module.Shell('localhost', 9042, no_compression=False, encoding='utf-8')

        # Verify Cluster was called
        mock_cluster.assert_called_once()

        # Verify compression was NOT set (driver uses its default behavior)
        call_kwargs = mock_cluster.call_args[1]
        assert 'compression' not in call_kwargs
