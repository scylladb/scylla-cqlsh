#!/bin/bash -e

. /etc/os-release
print_usage() {
    echo "build_rpm.sh --reloc-pkg build/scylla-python3-package.tar.gz"
    echo "  --reloc-pkg specify relocatable package path"
    echo "  --builddir specify rpmbuild directory"
    exit 1
}
RELOC_PKG=build/scylla-cqlsh.$(arch).tar.gz
BUILDDIR=build/redhat
while [ $# -gt 0 ]; do
    case "$1" in
        "--reloc-pkg")
            RELOC_PKG=$2
            shift 2
            ;;
        "--builddir")
            BUILDDIR="$2"
            shift 2
            ;;
        *)
            print_usage
            ;;
    esac
done

if [ ! -e $RELOC_PKG ]; then
    echo "$RELOC_PKG does not exist."
    echo "Run ./reloc/build_reloc.sh first."
    exit 1
fi
RELOC_PKG=$(readlink -f $RELOC_PKG)
RPMBUILD=$(readlink -f $BUILDDIR)
mkdir -p $BUILDDIR/scylla-cqlsh
tar -C $BUILDDIR -xpf $RELOC_PKG scylla-cqlsh/SCYLLA-RELOCATABLE-FILE scylla-cqlsh/SCYLLA-RELEASE-FILE scylla-cqlsh/SCYLLA-VERSION-FILE scylla-cqlsh/SCYLLA-PRODUCT-FILE scylla-cqlsh/SCYLLA-PYTHON3-PIP-SYMLINKS-FILE scylla-cqlsh/dist/redhat
cd $BUILDDIR/scylla-cqlsh

RELOC_PKG_BASENAME=$(basename "$RELOC_PKG")
SCYLLA_VERSION=$(cat SCYLLA-VERSION-FILE)
SCYLLA_RELEASE=$(cat SCYLLA-RELEASE-FILE)
PRODUCT=$(cat SCYLLA-PRODUCT-FILE)
PIP_SYMLINKS=$(cat SCYLLA-PYTHON3-PIP-SYMLINKS-FILE)

RPMBUILD=$(readlink -f ../)
mkdir -p "$RPMBUILD"/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS}

parameters=(
    -D"name $PRODUCT-cqlsh"
    -D"version $SCYLLA_VERSION"
    -D"release $SCYLLA_RELEASE"
    -D"target /opt/scylladb/python3"
    -D"reloc_pkg $RELOC_PKG_BASENAME"
)
if [ -n "$PIP_SYMLINKS" ]; then
    parameters+=(-D"has_bindir true")
fi

ln -fv "$RELOC_PKG" "$RPMBUILD"/SOURCES/
cp dist/redhat/cqlsh.spec "$RPMBUILD"/SPECS/
rpmbuild "${parameters[@]}" --nodebuginfo -ba --define '_binary_payload w2.xzdio' --define "_build_id_links none" --define "_topdir ${RPMBUILD}" "$RPMBUILD"/SPECS/cqlsh.spec
