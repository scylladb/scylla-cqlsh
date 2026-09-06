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

"""
SSL/TLS configuration method tests.

Tests different ways to configure SSL in cqlsh:
- Command-line flags (--ssl)
- Configuration file (.cqlshrc)
- Environment variables
- Configuration precedence
"""

import pytest
import subprocess
import os
import tempfile
from pathlib import Path


class TestSSLConfigurationMethods:
    """Test different SSL configuration methods."""
    
    def test_ssl_via_command_line_flag(self, scylla_ssl_container):
        """Test SSL configuration via --ssl command line flag."""
        # Find cqlsh script
        cqlsh_path = Path(__file__).parent.parent.parent.parent.parent / 'bin' / 'cqlsh.py'
        
        # Run cqlsh with --ssl flag
        env = os.environ.copy()
        env['SSL_CERTFILE'] = scylla_ssl_container.ssl_certificates['ca_cert']
        env['SSL_VALIDATE'] = 'false'
        
        result = subprocess.run([
            'python3', str(cqlsh_path),
            scylla_ssl_container.host,
            str(scylla_ssl_container.port),
            '--ssl',
            '-e', 'SELECT release_version FROM system.local;'
        ], capture_output=True, text=True, env=env, timeout=30)
        
        # Check that connection worked
        assert result.returncode == 0 or 'release_version' in result.stdout, \
            f"cqlsh failed: {result.stderr}"
    
    def test_ssl_via_cqlshrc(self, scylla_ssl_container, ssl_context):
        """Test SSL configuration via .cqlshrc file."""
        cqlsh_path = Path(__file__).parent.parent.parent.parent.parent / 'bin' / 'cqlsh.py'
        
        # Use the cqlshrc from ssl_context
        env = os.environ.copy()
        env['CQLSHRC'] = ssl_context.cqlshrc_path
        
        result = subprocess.run([
            'python3', str(cqlsh_path),
            scylla_ssl_container.host,
            str(scylla_ssl_container.port),
            '-e', 'SELECT cluster_name FROM system.local;'
        ], capture_output=True, text=True, env=env, timeout=30)
        
        # Check that connection worked
        assert result.returncode == 0 or 'cluster_name' in result.stdout, \
            f"cqlsh with cqlshrc failed: {result.stderr}"
    
    def test_ssl_via_environment_variables(self, scylla_ssl_container, ssl_env_vars):
        """Test SSL configuration via environment variables."""
        cqlsh_path = Path(__file__).parent.parent.parent.parent.parent / 'bin' / 'cqlsh.py'
        
        # Prepare environment with SSL settings
        env = os.environ.copy()
        env.update(ssl_env_vars)
        
        result = subprocess.run([
            'python3', str(cqlsh_path),
            scylla_ssl_container.host,
            str(scylla_ssl_container.port),
            '--ssl',  # Still need --ssl flag to enable SSL
            '-e', 'SELECT key FROM system.local;'
        ], capture_output=True, text=True, env=env, timeout=30)
        
        # Check that connection worked
        assert result.returncode == 0 or 'key' in result.stdout or 'local' in result.stdout, \
            f"cqlsh with env vars failed: {result.stderr}"


class TestSSLConfigurationPrecedence:
    """Test configuration precedence (env > cqlshrc > defaults)."""
    
    def test_env_vars_override_cqlshrc(self, scylla_ssl_container):
        """Test that environment variables override cqlshrc settings."""
        cqlsh_path = Path(__file__).parent.parent.parent.parent.parent / 'bin' / 'cqlsh.py'
        
        # Create a cqlshrc with WRONG CA cert path
        with tempfile.NamedTemporaryFile(mode='w', suffix='.cqlshrc', delete=False) as f:
            f.write("""
[connection]
hostname = localhost
port = 9042
ssl = true

[ssl]
validate = true
certfile = /tmp/nonexistent-ca-cert.pem
""")
            wrong_cqlshrc = f.name
        
        try:
            # Set env var with CORRECT CA cert (should override cqlshrc)
            env = os.environ.copy()
            env['CQLSHRC'] = wrong_cqlshrc
            env['SSL_CERTFILE'] = scylla_ssl_container.ssl_certificates['ca_cert']
            env['SSL_VALIDATE'] = 'false'  # Disable validation for this test
            
            result = subprocess.run([
                'python3', str(cqlsh_path),
                scylla_ssl_container.host,
                str(scylla_ssl_container.port),
                '--ssl',
                '-e', 'SELECT * FROM system.local;'
            ], capture_output=True, text=True, env=env, timeout=30)
            
            # Connection should work because env var overrides cqlshrc
            assert result.returncode == 0 or 'local' in result.stdout, \
                f"Env var override failed: {result.stderr}"
        finally:
            os.unlink(wrong_cqlshrc)
    
    def test_cli_flags_override_all(self, scylla_ssl_container):
        """Test that CLI flags have highest precedence."""
        cqlsh_path = Path(__file__).parent.parent.parent.parent.parent / 'bin' / 'cqlsh.py'
        
        # Create cqlshrc that says DON'T use SSL
        with tempfile.NamedTemporaryFile(mode='w', suffix='.cqlshrc', delete=False) as f:
            f.write("""
[connection]
hostname = localhost
port = 9042
ssl = false

[ssl]
validate = false
""")
            no_ssl_cqlshrc = f.name
        
        try:
            # Use --ssl flag which should override cqlshrc
            env = os.environ.copy()
            env['CQLSHRC'] = no_ssl_cqlshrc
            env['SSL_CERTFILE'] = scylla_ssl_container.ssl_certificates['ca_cert']
            env['SSL_VALIDATE'] = 'false'
            
            result = subprocess.run([
                'python3', str(cqlsh_path),
                scylla_ssl_container.host,
                str(scylla_ssl_container.port),
                '--ssl',  # This should override cqlshrc ssl=false
                '-e', 'SELECT * FROM system.local;'
            ], capture_output=True, text=True, env=env, timeout=30)
            
            # Connection should work because --ssl flag overrides
            assert result.returncode == 0 or 'local' in result.stdout, \
                f"CLI flag override failed: {result.stderr}"
        finally:
            os.unlink(no_ssl_cqlshrc)

