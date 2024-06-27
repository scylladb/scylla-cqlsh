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


def fix_binary(path, libpath):
    '''Makes one binary or shared library relocatable. To do that, we need to set RUNPATH to $ORIGIN/../lib64 so we get libraries
    from the relocatable directory and not from the system during runtime. We also want to copy the interpreter used so
    we can launch with it later.
    '''
    # it's a pity patchelf have to patch an actual binary.

    subprocess.check_call(['patchelf',
                           '--set-rpath',
                           libpath,
                           path])


def fix_sharedlib(binpath):
    fix_binary(binpath, '$ORIGIN/lib64')


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
ar.reloc_add('pylib')
ar.reloc_add('install.sh')
ar.reloc_add('build/debian/debian', arcname='debian')


# clear scylla-driver out of the package
# we assume that scylla-python3 already have it (and all it's .so are relocatable,
# and pointing the correct lib folder)
cqlsh_bin = pathlib.Path('bin/cqlsh').resolve()
subprocess.check_call(["mv", cqlsh_bin, f'{cqlsh_bin}.zip'])
subprocess.run(["zip", "--delete", cqlsh_bin, "site-packages/cassandra/*"])
subprocess.check_call(["mv", f'{cqlsh_bin}.zip', cqlsh_bin])

ar.reloc_add('bin/cqlsh')