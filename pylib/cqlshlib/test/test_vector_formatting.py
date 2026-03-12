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
Tests for vector type formatting in cqlsh.
"""

import unittest
from cqlshlib.formatting import CqlType, format_by_type
from cqlshlib.displaying import NO_COLOR_MAP, get_str


class TestCqlTypeVectorParsing(unittest.TestCase):
    """Test that vector<type, N> CQL types are parsed correctly."""

    def test_vector_float_5_has_single_subtype(self):
        """vector<float, 5> should have a single sub_type of 'float', not two sub_types [float, 5]."""
        cqltype = CqlType('vector<float, 5>')
        self.assertEqual(cqltype.type_name, 'vector')
        self.assertEqual(len(cqltype.sub_types), 1)
        self.assertEqual(cqltype.sub_types[0].type_name, 'float')

    def test_vector_int_3_has_single_subtype(self):
        """vector<int, 3> should have a single sub_type of 'int'."""
        cqltype = CqlType('vector<int, 3>')
        self.assertEqual(cqltype.type_name, 'vector')
        self.assertEqual(len(cqltype.sub_types), 1)
        self.assertEqual(cqltype.sub_types[0].type_name, 'int')

    def test_vector_get_n_sub_types(self):
        """get_n_sub_types should work for vector types with any number of elements."""
        cqltype = CqlType('vector<float, 5>')
        sub_types = cqltype.get_n_sub_types(5)
        self.assertEqual(len(sub_types), 5)
        for st in sub_types:
            self.assertEqual(st.type_name, 'float')

    def test_frozen_vector(self):
        """frozen<vector<float, 3>> should also parse correctly."""
        cqltype = CqlType('frozen<vector<float, 3>>')
        self.assertEqual(cqltype.type_name, 'vector')
        self.assertEqual(len(cqltype.sub_types), 1)
        self.assertEqual(cqltype.sub_types[0].type_name, 'float')


class TestVectorValueFormatting(unittest.TestCase):
    """Test that vector values format correctly without raising exceptions."""

    def test_format_vector_float_5(self):
        """
        Reproducer for the VECTOR-563: formatting a vector<float, 5> value should not raise
        'Unexpected number of subtypes 5 - [float, 5]'.
        """
        cqltype = CqlType('vector<float, 5>')
        val = [0.10999999940395355, 0.3499999940395355, 0.550000011920929,
               0.7699999809265137, 0.9200000166893005]
        # This should not raise an exception
        result = format_by_type(val, cqltype=cqltype, encoding='utf-8',
                                colormap=NO_COLOR_MAP, addcolor=False)
        result_str = get_str(result)
        self.assertEqual(result_str, '[0.11, 0.35, 0.55, 0.77, 0.92]')

    def test_format_vector_int_3(self):
        """Formatting vector<int, 3> should work."""
        cqltype = CqlType('vector<int, 3>')
        val = [1, 2, 3]
        result = format_by_type(val, cqltype=cqltype, encoding='utf-8',
                                colormap=NO_COLOR_MAP, addcolor=False)
        result_str = get_str(result)
        self.assertEqual(result_str, '[1, 2, 3]')

    def test_format_empty_vector(self):
        """Formatting an empty vector should work."""
        cqltype = CqlType('vector<float, 5>')
        val = []
        result = format_by_type(val, cqltype=cqltype, encoding='utf-8',
                                colormap=NO_COLOR_MAP, addcolor=False)
        self.assertIsNotNone(result)
        self.assertEqual(get_str(result), '[]')

    def test_format_vector_single_element(self):
        """Formatting vector<float, 1> should work."""
        cqltype = CqlType('vector<float, 1>')
        val = [0.5]
        result = format_by_type(val, cqltype=cqltype, encoding='utf-8',
                                colormap=NO_COLOR_MAP, addcolor=False)
        result_str = get_str(result)
        self.assertEqual(result_str, '[0.5]')


if __name__ == '__main__':
    unittest.main()
