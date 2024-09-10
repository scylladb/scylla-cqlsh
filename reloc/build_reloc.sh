#!/bin/bash -e

. /etc/os-release

print_usage() {
    echo "build_reloc.sh --clean --nodeps"
    echo "  --clean clean build directory"
    echo "  --nodeps    skip installing dependencies"
    echo "  --version V  product-version-release string (overriding SCYLLA-VERSION-GEN)"
    echo "  --verbose more chatty. I am quiet by default"
    exit 1
}

CLEAN=
NODEPS=
VERSION_OVERRIDE=
VERBOSE=false
while [ $# -gt 0 ]; do
    case "$1" in
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
        "--verbose")
            VERBOSE=true
            shift 1
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
DEST="build/$PRODUCT-cqlsh-$VERSION.$(uname -m).tar.gz"

is_redhat_variant() {
    [ -f /etc/redhat-release ]
}
is_debian_variant() {
    [ -f /etc/debian_version ]
}


if [ ! -e reloc/build_reloc.sh ]; then
    echo "run build_reloc.sh in top of scylla dir"
    exit 1
fi

if [ "$CLEAN" = "yes" ]; then
    rm -rf build target
fi

if [ -f "$DEST" ]; then
    rm "$DEST"
fi

if [ -z "$NODEPS" ]; then
    sudo ./install-dependencies.sh
fi

printf "version=%s" $VERSION > build.properties

if $VERBOSE; then
    TAR_EXTRA_OPTS="--verbose"
else
    PIP_EXTRA_OPTS="--quiet"
    ZIP_EXTRA_OPTS="--quiet"
fi

python3 -m pip install ${PIP_EXTRA_OPTS} shiv==1.0.6 build==0.10.0 wheel==0.37.1 -t ./build/cqlsh_build

CQLSH_NO_CYTHON=true PYTHONPATH=$(pwd)/build/cqlsh_build python3 -m shiv -c cqlsh -o bin/cqlsh -- . -c requirements.txt

dist/debian/debian_files_gen.py
scripts/create-relocatable-package.py --version $VERSION "$DEST"
