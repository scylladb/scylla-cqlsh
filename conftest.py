import sys
from unittest.mock import patch

import pytest

@pytest.fixture(scope="module")
def cqlsh_module():
    """Import cqlsh module once with mocked sys.argv"""
    # Mock sys.argv to prevent the module from parsing command-line args during import
    with patch.object(sys, 'argv', ['cqlsh']):
        # Import from cqlsh.cqlsh to get the actual cqlsh.py module
        import cqlsh.cqlsh as cqlsh_module
        return cqlsh_module