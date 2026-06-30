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

import unittest
from unittest.mock import patch

import cassandra.cluster

from cqlshlib.util import control_connection_query_fallback_kwargs


class ControlConnectionQueryFallbackTest(unittest.TestCase):

    def test_returns_no_kwargs_for_driver_without_fallback(self):
        original = getattr(cassandra.cluster, 'ControlConnectionQueryFallback', None)
        had_fallback = hasattr(cassandra.cluster, 'ControlConnectionQueryFallback')
        if had_fallback:
            delattr(cassandra.cluster, 'ControlConnectionQueryFallback')

        try:
            self.assertEqual(control_connection_query_fallback_kwargs(), {})
        finally:
            if had_fallback:
                cassandra.cluster.ControlConnectionQueryFallback = original

    def test_enables_fallback_for_driver_with_fallback(self):
        class ControlConnectionQueryFallback(object):
            Fallback = object()

        with patch.object(cassandra.cluster, 'ControlConnectionQueryFallback',
                          ControlConnectionQueryFallback, create=True):
            self.assertEqual(
                control_connection_query_fallback_kwargs(),
                {'allow_control_connection_query_fallback': ControlConnectionQueryFallback.Fallback})
