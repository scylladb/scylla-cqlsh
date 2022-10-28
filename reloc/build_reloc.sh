#!/bin/bash -e
#
# Copyright (C) 2019 ScyllaDB
#

# SPDX-License-Identifier: Apache-2.0

print_usage() {
    echo "build_reloc.sh --dest build/scylla-python3-package.tar.gz"
    echo "  --dest specify destination path"
    echo "  --clean clean build directory"
    echo "  --nodeps    skip installing dependencies"
    echo "  --version V  product-version-release string (overriding SCYLLA-VERSION-GEN)"
    exit 1
}

CLEAN=
NODEPS=
VERSION_OVERRIDE=
while [ $# -gt 0 ]; do
    case "$1" in
        "--dest")
            DEST=$2
            shift 2
            ;;
        "--clean")
            CLEAN=yes
            shift 1
            ;;
        "--nodeps")
            NODEPS=yes
            shift 1
            ;;
        "--version")
            VERSION_OVERRIDE="$2"
            shift 2
            ;;
        *)
            print_usage
            ;;
    esac
done

VERSION=$(./SCYLLA-VERSION-GEN ${VERSION_OVERRIDE:+ --version "$VERSION_OVERRIDE"})
# the former command should generate build/SCYLLA-PRODUCT-FILE and some other version
# related files
PRODUCT=`cat build/SCYLLA-PRODUCT-FILE`
DEST=build/$PRODUCT-cqlsh-$VERSION.$(arch).tar.gz

if [ "$CLEAN" = "yes" ]; then
    rm -rf build
fi

if [ -z "$NODEPS" ]; then
    sudo ./install-dependencies.sh
fi

rm -rf cassandra
git clone -b trunk --single-branch https://github.com/apache/cassandra.git cassandra
cd cassandra
git filter-repo --path bin/cqlsh --path bin/cqlsh.py --path pylib/
cd -
sudo pip3 uninstall scylla-cqlsh -y || true
sudo pip3 install .

./SCYLLA-VERSION-GEN ${VERSION_OVERRIDE:+ --version "$VERSION_OVERRIDE"}
echo "cqlsh" > build/SCYLLA-PYTHON3-PIP-SYMLINKS-FILE
./dist/debian/debian_files_gen.py
./scripts/create-relocatable-package.py --output "$DEST" --pip-modules "scylla-cqlsh"
