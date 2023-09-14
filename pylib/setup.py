#!/usr/bin/python
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


import sys
import warnings
from distutils.core import setup, Extension


def get_extensions():
    if "--no-compile" in sys.argv:
        return []

    try:
        from Cython.Build import cythonize
        extensions = [Extension(name='copyutil',
                                sources=["cqlshlib/copyutil.py"],
                                define_macros=[("CYTHON_LIMITED_API", "1")])]
        return cythonize(extensions,
                         compiler_directives={'language_level': '3str'})
    except ImportError:
        warnings.warn("installing cython could speed things up for you; `pip install cython`")


setup(
    name="scylla-cqlsh",
    install_requires=[
        "scylla-driver >= 3.25.10",
    ],
    ext_modules=get_extensions(),
    license="Apache",
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Environment :: Console",
        "Topic :: Database :: Front-Ends",
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python :: 3",
    ]
)
