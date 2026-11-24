#!/bin/bash -e

. /etc/os-release
print_usage() {
    echo "build_rpm.sh --reloc-pkg build/scylla-cqlsh-package.tar.gz --scylla-release 2027.1"
    echo "  --reloc-pkg specify relocatable package path"
    echo "  --scylla-release the scylla release (X.Y) whose scylla-python3 the package was built for"
    echo "  --builddir specify rpmbuild directory"
    exit 1
}
RELOC_PKG=build/scylla-cqlsh-package.tar.gz
BUILDDIR=build/redhat
while [ $# -gt 0 ]; do
    case "$1" in
        "--reloc-pkg")
            RELOC_PKG=$2
            shift 2
            ;;
        "--scylla-release")
            SCYLLA_PYTHON3_RELEASE=$2
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

# The bundled compiled modules only run on the python they were built for, so the package
# takes the scylla-python3 of that one scylla release, and no other.
if [[ ! "$SCYLLA_PYTHON3_RELEASE" =~ ^([0-9]+)\.([0-9]+)$ ]]; then
    echo "--scylla-release X.Y is required"
    print_usage
fi
SCYLLA_PYTHON3_NEXT_RELEASE=${BASH_REMATCH[1]}.$((10#${BASH_REMATCH[2]} + 1))

RELOC_PKG=$(readlink -f $RELOC_PKG)
RPMBUILD=$(readlink -f $BUILDDIR)
mkdir -p "$BUILDDIR"
tar -C "$BUILDDIR" -xpf $RELOC_PKG scylla-cqlsh/SCYLLA-RELEASE-FILE scylla-cqlsh/SCYLLA-RELOCATABLE-FILE scylla-cqlsh/SCYLLA-VERSION-FILE scylla-cqlsh/SCYLLA-PRODUCT-FILE scylla-cqlsh/dist/redhat
cd "$BUILDDIR"/scylla-cqlsh

RELOC_PKG_BASENAME=$(basename "$RELOC_PKG")
SCYLLA_VERSION=$(cat SCYLLA-VERSION-FILE)
SCYLLA_RELEASE=$(cat SCYLLA-RELEASE-FILE)
VERSION=$SCYLLA_VERSION-$SCYLLA_RELEASE
PRODUCT=$(cat SCYLLA-PRODUCT-FILE)

mkdir -p $RPMBUILD/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS}

ln -fv $RELOC_PKG $RPMBUILD/SOURCES/

parameters=(
    -D"version $SCYLLA_VERSION"
    -D"release $SCYLLA_RELEASE"
    -D"product $PRODUCT"
    -D"reloc_pkg $RELOC_PKG_BASENAME"
    -D"scylla_release $SCYLLA_PYTHON3_RELEASE"
    -D"scylla_next_release $SCYLLA_PYTHON3_NEXT_RELEASE"
)

cp dist/redhat/scylla-cqlsh.spec $RPMBUILD/SPECS
# this rpm can be install on both fedora / centos7, so drop distribution name from the file name
rpmbuild -ba "${parameters[@]}" --define '_binary_payload w2.xzdio' --define "_topdir $RPMBUILD" --undefine "dist" $RPMBUILD/SPECS/scylla-cqlsh.spec
