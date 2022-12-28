#!/bin/bash -e

. /etc/os-release

print_usage() {
    echo "build_reloc.sh --clean --nodeps"
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
DEST="build/$PRODUCT-cqlsh-$VERSION.noarch.tar.gz"

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


python3 -m pip install build==0.8.0 wheel==0.37.1 -t ./build/cqlsh_build
PYTHONPATH=$(pwd)/build/cqlsh_build python3 -m build -s
PYTHONPATH=$(pwd)/build/cqlsh_build python3 -m pip download --constraint ./requirements.txt --no-binary :all: . --no-build-isolation -d ./build/pypi_packages

for package in $(ls ./build/pypi_packages/*.tar.gz)
do
   PACKAGE_NAME=$(basename ${package} .tar.gz)
   TMP_PACKAGE_DIR="./build/${PACKAGE_NAME}"
   ZIP_PACKAGE=$(pwd)"/lib/${PACKAGE_NAME}.zip"
   mkdir -p $TMP_PACKAGE_DIR
   tar xvzf ${package} --strip-components 1 -C $TMP_PACKAGE_DIR
   cd ${TMP_PACKAGE_DIR}
      mkdir -p $(dirname ${ZIP_PACKAGE})
      zip -r ${ZIP_PACKAGE} *
   cd -
done

dist/debian/debian_files_gen.py
scripts/create-relocatable-package.py --version $VERSION "$DEST"
