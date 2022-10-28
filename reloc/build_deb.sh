#!/bin/bash -e

. /etc/os-release
print_usage() {
    echo "build_deb.sh --reloc-pkg build/scylla-python3-package.tar.gz"
    echo "  --reloc-pkg specify relocatable package path"
    echo "  --builddir specify debuild directory"
    exit 1
}

RELOC_PKG=build/scylla-cqlsh.$(arch).tar.gz
BUILDDIR=build/debian
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
rm -rf "$BUILDDIR"/scylla-cqlsh-package "$BUILDDIR"/scylla-cqlsh-package.orig "$BUILDDIR"/debian
mkdir -p "$BUILDDIR"/scylla-cqlsh-package
tar -C "$BUILDDIR"/scylla-cqlsh-package -xpf "$RELOC_PKG"
cd "$BUILDDIR"/scylla-cqlsh-package

PRODUCT=$(cat scylla-cqlsh/SCYLLA-PRODUCT-FILE)
RELOC_PKG_FULLPATH=$(readlink -f $RELOC_PKG)
RELOC_PKG_BASENAME=$(basename $RELOC_PKG)
SCYLLA_VERSION=$(cat scylla-cqlsh/SCYLLA-VERSION-FILE)
SCYLLA_RELEASE=$(cat scylla-cqlsh/SCYLLA-RELEASE-FILE)

ln -fv $RELOC_PKG_FULLPATH ../$PRODUCT-cqlsh_${SCYLLA_VERSION/\.rc/~rc}-$SCYLLA_RELEASE.orig.tar.gz

mv scylla-cqlsh/debian debian
debuild -rfakeroot -us -uc
