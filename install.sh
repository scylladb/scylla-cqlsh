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
  --nonroot                install Scylla without required root priviledge
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
if ! $nonroot; then
    retc="$root/$etcdir"
    rusr="$root/usr"
else
    retc="$rprefix/$etcdir"
fi

install -d -m755 "$rprefix"/share/cassandra/bin
if ! $nonroot; then
    install -d -m755 "$rusr"/bin
fi

thunk="#!/usr/bin/env bash
b=\"\$(basename \"\$0\")\"
bindir=\"$prefix/share/cassandra/bin\"
exec -a \"\$0\" \"\$bindir/\$b\" \"\$@\""


# scylla-cqlsh
install -d -m755 "$rprefix"/share/cassandra/lib
install -m644 lib/*.zip "$rprefix"/share/cassandra/lib
install -d -m755 "$rprefix"/share/cassandra/pylib
cp -rp pylib/cqlshlib "$rprefix"/share/cassandra/pylib

for i in bin/{cqlsh,cqlsh.py} ; do
    bn=$(basename $i)
    install -m755 $i "$rprefix"/share/cassandra/bin
    if ! $nonroot; then
        echo "$thunk" > "$rusr"/bin/$bn
        chmod 755 "$rusr"/bin/$bn
    fi
done
