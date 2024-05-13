#!/usr/bin/env python3
# -*- coding: utf-8 -*-
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

import datetime
import string
import os
import shutil
import re
from pathlib import Path

class DebianFilesTemplate(string.Template):
    delimiter = '%'

scriptdir = os.path.dirname(__file__)

with open(os.path.join(scriptdir, 'changelog.template')) as f:
    changelog_template = f.read()

with open(os.path.join(scriptdir, 'control.template')) as f:
    control_template = f.read()

with open('build/SCYLLA-PRODUCT-FILE') as f:
    product = f.read().strip()

with open('build/SCYLLA-VERSION-FILE') as f:
    version = f.read().strip()

with open('build/SCYLLA-RELEASE-FILE') as f:
    release = f.read().strip()

if os.path.exists('build/debian/debian'):
    shutil.rmtree('build/debian/debian')
shutil.copytree('dist/debian/debian', 'build/debian/debian')

s = DebianFilesTemplate(changelog_template)
now = datetime.datetime.now(tz=datetime.timezone.utc)
changelog_applied = s.substitute(product=product,
                                 version=version,
                                 release=release,
                                 revision='1',
                                 codename='stable',
                                 timestamp=now.strftime("%a, %d %b %Y %H:%M:%S %z"))

s = DebianFilesTemplate(control_template)
control_applied = s.substitute(product=product)

with open('build/debian/debian/changelog', 'w') as f:
    f.write(changelog_applied)

with open('build/debian/debian/control', 'w') as f:
    f.write(control_applied)

