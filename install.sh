#!/bin/bash

# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

set -e

print_usage() {
    cat <<EOF
Usage: install.sh [options]

Options:
  --root /path/to/root     alternative install root (default /)
  --prefix /prefix         directory prefix (default /usr)
  --etcdir /etc            specify etc directory path (default /etc)
  --nonroot                install Scylla without required root privilege
  --help                   this helpful message
EOF
    exit 1
}

root=/
etcdir=/etc
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
        "--etcdir")
            etcdir="$2"
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
    local relocateddir="$installdir/../libexec"
    local pythoncmd=$(realpath -ms --relative-to "$installdir" "$rpython3")
    local pythonpath="$(dirname "$pythoncmd")"

    if [ ! -x "$script" ]; then
        install -m755 "$script" "$install"
        return
    fi
    install -d -m755 "$relocateddir"
    install -m755 "$script" "$relocateddir"
    cat > "$install"<<EOF
#!/usr/bin/env bash
[[ -z "\$LD_PRELOAD" ]] || { echo "\$0: not compatible with LD_PRELOAD" >&2; exit 110; }
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
PYTHONPATH="\${d}:\${d}/../libexec:\$PYTHONPATH" PATH="\${d}/../bin:\${d}/$pythonpath:\${PATH}" SSL_CERT_FILE="\${c}" exec -a "\$0" "\${d}/../libexec/\${b}" "\$@"
EOF
    chmod 755 "$install"
}

if [ -z "$prefix" ]; then
    if $nonroot; then
        prefix=~/scylladb
    else
        prefix=/opt/scylladb
    fi
fi

scylla_version=$(cat SCYLLA-VERSION-FILE)
scylla_release=$(cat SCYLLA-RELEASE-FILE)

rprefix=$(realpath -m "$root/$prefix")
python3=$prefix/python3/bin/python3
rpython3=$(realpath -m "$root/$python3")
if ! $nonroot; then
    retc="$root/$etcdir"
    rusr="$root/usr"
else
    retc="$rprefix/$etcdir"
fi

install -d -m755 "$rprefix"/share/cassandra/bin
install -d -m755 "$rprefix"/share/cassandra/libexec
if ! $nonroot; then
    install -d -m755 "$rusr"/bin
fi

# scylla-cqlsh
install -d -m755 "$rprefix"/share/cassandra/lib
install -m644 lib/*.zip "$rprefix"/share/cassandra/lib
install -d -m755 "$rprefix"/share/cassandra/pylib
cp -rp pylib/cqlshlib "$rprefix"/share/cassandra/pylib

for i in bin/{cqlsh,cqlsh.py} ; do
    bn=$(basename $i)
    relocate_python3 "$rprefix"/share/cassandra/bin "$i"
    if ! $nonroot; then
        ln -srf "$rprefix"/share/cassandra/bin/"$bn" "$rusr"/bin/"$bn"
    fi
done
