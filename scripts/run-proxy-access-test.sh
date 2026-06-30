#!/usr/bin/env bash

set -euo pipefail

: "${CQL_TEST_HOST:?CQL_TEST_HOST must point at the Scylla node IP}"
CQL_TEST_PORT="${CQL_TEST_PORT:-9042}"

proxy_container="cqlsh-proxy-access-${GITHUB_RUN_ID:-local}-$$"
direct_rule_added=0

cleanup() {
    if [ "${direct_rule_added}" = 1 ]; then
        sudo iptables -w -D OUTPUT -p tcp -d "${CQL_TEST_HOST}" --dport "${CQL_TEST_PORT}" -j REJECT >/dev/null 2>&1 || true
    fi
    docker rm -f "${proxy_container}" >/dev/null 2>&1 || true
}

trap cleanup EXIT

docker run -d --name "${proxy_container}" -p 127.0.0.1::9042 busybox sh -c \
    "while true; do nc -lp 9042 -e nc ${CQL_TEST_HOST} ${CQL_TEST_PORT}; done" >/dev/null

proxy_port="$(docker port "${proxy_container}" 9042/tcp | awk -F: '{print $NF; exit}')"

for _ in $(seq 1 100); do
    if nc -z 127.0.0.1 "${proxy_port}"; then
        proxy_ready=1
        break
    fi
    sleep 0.1
done

if [ "${proxy_ready:-0}" != 1 ]; then
    echo "Proxy did not start listening on 127.0.0.1:${proxy_port}" >&2
    exit 1
fi

sudo iptables -w -I OUTPUT -p tcp -d "${CQL_TEST_HOST}" --dport "${CQL_TEST_PORT}" -j REJECT
direct_rule_added=1

CQL_PROXY_TEST_HOST=127.0.0.1 \
CQL_PROXY_TEST_PORT="${proxy_port}" \
CQL_PROXY_TEST_BLOCKED_HOST="${CQL_TEST_HOST}" \
    pytest ./cqlshlib/test/test_proxy_access.py
