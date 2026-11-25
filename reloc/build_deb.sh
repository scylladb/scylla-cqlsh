#!/bin/bash -e

. /etc/os-release
print_usage() {
    echo "build_deb.sh --reloc-pkg build/scylla-cqlsh-package.tar.gz --scylla-release 2027.1"
    echo "  --reloc-pkg specify relocatable package path"
    echo "  --scylla-release the scylla release (X.Y) whose scylla-python3 the package was built for"
    echo "  --builddir specify Debian package build path"
    exit 1
}

RELOC_PKG=build/scylla-cqlsh-package.tar.gz
BUILDDIR=build/debian
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
rm -rf "$BUILDDIR"/scylla-package "$BUILDDIR"/scylla-package.orig "$BUILDDIR"/debian
mkdir -p "$BUILDDIR"/scylla-package
tar -C "$BUILDDIR"/scylla-package -xpf $RELOC_PKG
cd "$BUILDDIR"/scylla-package

mv scylla-cqlsh/debian debian
sed -i -e "s/@SCYLLA_RELEASE@/$SCYLLA_PYTHON3_RELEASE/g" -e "s/@SCYLLA_NEXT_RELEASE@/$SCYLLA_PYTHON3_NEXT_RELEASE/g" debian/control
PKG_NAME=$(dpkg-parsechangelog --show-field Source)
# The .orig.tar.gz is named after the upstream version: no epoch, no Debian revision.
PKG_VERSION=$(dpkg-parsechangelog --show-field Version |sed -e 's/^[0-9]*://' -e 's/-[^-]*$//')
ln -fv $RELOC_PKG ../"$PKG_NAME"_"$PKG_VERSION".orig.tar.gz
debuild -rfakeroot -us -uc
