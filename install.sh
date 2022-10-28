#!/bin/bash
#
# Copyright (C) 2019 ScyllaDB
#

# SPDX-License-Identifier: Apache-2.0

set -e

print_usage() {
    cat <<EOF
Usage: install.sh [options]

Options:
  --root /path/to/root     alternative install root (default /)
  --prefix /prefix         directory prefix (default /usr)
  --nonroot                shortcut of '--disttype nonroot'
  --help                   this helpful message
EOF
    exit 1
}

root=/
nonroot=false

while [ $# -gt 0 ]; do
    case "$1" in
        "--root")
            root="$2"
            shift 2
            ;;
        "--prefix")
            prefix="$2"
            shift 2
            ;;
        "--nonroot")
            nonroot=true
            shift 1
            ;;
        "--help")
            shift 1
	    print_usage
            ;;
        *)
            print_usage
            ;;
    esac
done

relocate_python3() {
    local script="$2"
    local scriptname="$(basename "$script")"
    local installdir="$1"
    local install="$installdir/$scriptname"
    local relocateddir="$installdir/libexec"
    local pythoncmd=$(realpath -ms --relative-to "$installdir" "$rpython3")
    local pythonpath="$(dirname "$pythoncmd")"

    if [ ! -x "$script" ]; then
        cp "$script" "$install"
        return
    fi
    mkdir -p "$relocateddir"
    cp "$script" "$relocateddir"
    cat > "$install"<<EOF
#!/usr/bin/env bash
[[ -z "\$LD_PRELOAD" ]] || { echo "\$0: not compatible with LD_PRELOAD" >&2; exit 110; }
export LC_ALL=en_US.UTF-8
x="\$(readlink -f "\$0")"
b="\$(basename "\$x")"
d="\$(dirname "\$x")"
CENTOS_SSL_CERT_FILE="/etc/pki/tls/cert.pem"
if [ -f "\${CENTOS_SSL_CERT_FILE}" ]; then
  c=\${CENTOS_SSL_CERT_FILE}
fi
DEBIAN_SSL_CERT_FILE="/etc/ssl/certs/ca-certificates.crt"
if [ -f "\${DEBIAN_SSL_CERT_FILE}" ]; then
  c=\${DEBIAN_SSL_CERT_FILE}
fi
PYTHONPATH="\${d}:\${d}/libexec:\$PYTHONPATH" PATH="\${d}/../bin:\${d}/$pythonpath:\${PATH}" SSL_CERT_FILE="\${c}" exec -a "\$0" "\${d}/libexec/\${b}" "\$@"
EOF
    chmod +x "$install"
}

if [ -z "$prefix" ]; then
    if $nonroot; then
        prefix=~/scylladb
    else
        prefix=/opt/scylladb
    fi
fi

rprefix=$(realpath -m "$root/$prefix")
python3="$prefix/python3/bin/python3"
rpython3=$(realpath -m "$root/$python3")
if ! $nonroot; then
    rusr=$(realpath -m "$root/usr")
fi

install -d -m755 "$rprefix"/python3/bin
cp -r ./bin/* "$rprefix"/python3/bin
install -d -m755 "$rprefix"/python3/lib64
cp -r ./lib64/* "$rprefix"/python3/lib64

PYSCRIPTS=$(find bin -maxdepth 1 -type f -exec grep -Pls '\A#!/usr/bin/env python3' {} +)
PYSYMLINKS="$(cat ./SCYLLA-PYTHON3-PIP-SYMLINKS-FILE)"
for i in $PYSCRIPTS; do
    relocate_python3 "$rprefix"/python3/bin "$i"
done

if ! $nonroot; then
    install -m755 -d "$rusr/bin"
    for i in $PYSYMLINKS; do
        ln -srf "$rprefix/python3/bin/$i" "$rusr/bin/$i"
    done
fi
