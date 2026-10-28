#!/usr/bin/env python3

#
# Copyright (C) 2018 ScyllaDB
#

#
# This file is part of Scylla.
#
# Scylla is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Scylla is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Scylla.  If not, see <http://www.gnu.org/licenses/>.
#

import argparse
import os
import subprocess
import tarfile
import pathlib


def erase_uid(tarinfo):
    tarinfo.uid = tarinfo.gid = 0
    tarinfo.uname = tarinfo.gname = 'root'
    return tarinfo

RELOC_PREFIX='scylla-cqlsh'
def reloc_add(self, name, arcname=None):
    if arcname:
        return self.add(name, arcname="{}/{}".format(RELOC_PREFIX, arcname), filter=erase_uid)
    else:
        return self.add(name, arcname="{}/{}".format(RELOC_PREFIX, name), filter=erase_uid)

tarfile.TarFile.reloc_add = reloc_add


def fix_sharedlibs(sitepackages):
    '''The bundled .so files run on scylla-python3's own glibc, so point them at its lib64, the same
    way scylla-python3 does for its own site-packages. Otherwise e.g. libpthread.so.0 comes from the system.
    '''
    for so in pathlib.Path(sitepackages).rglob('*.so*'):
        with open(so, 'rb') as f:
            if f.read(4) != b'\x7fELF':
                continue
        installed_dir = pathlib.Path('share/cassandra/lib/site-packages') / so.parent.relative_to(sitepackages)
        relpath = os.path.relpath('python3/lib64', installed_dir)
        subprocess.check_call(['patchelf', '--add-rpath', f'$ORIGIN/{relpath}', so])


ap = argparse.ArgumentParser(description='Create a relocatable scylla package.')
ap.add_argument('--version', required=True,
                help='Tools version')
ap.add_argument('dest',
                help='Destination file (tar format)')

args = ap.parse_args()

version = args.version
output = args.dest

ar = tarfile.open(output, mode='w|gz')
# relocatable package format version = 2
with open('build/.relocatable_package_version', 'w') as f:
    f.write('2\n')
ar.add('build/.relocatable_package_version', arcname='.relocatable_package_version', filter=erase_uid)

pathlib.Path('build/SCYLLA-RELOCATABLE-FILE').touch()
ar.reloc_add('build/SCYLLA-RELOCATABLE-FILE', arcname='SCYLLA-RELOCATABLE-FILE')
ar.reloc_add('build/SCYLLA-RELEASE-FILE', arcname='SCYLLA-RELEASE-FILE')
ar.reloc_add('build/SCYLLA-VERSION-FILE', arcname='SCYLLA-VERSION-FILE')
ar.reloc_add('build/SCYLLA-PRODUCT-FILE', arcname='SCYLLA-PRODUCT-FILE')
ar.reloc_add('dist/debian')
ar.reloc_add('dist/redhat')
ar.reloc_add('bin/cqlsh.py')
ar.reloc_add('bin/cqlsh.py', arcname='bin/cqlsh')
fix_sharedlibs('build/site-packages')
ar.reloc_add('build/site-packages', arcname='lib/site-packages')
ar.reloc_add('install.sh')
ar.reloc_add('build/debian/debian', arcname='debian')

