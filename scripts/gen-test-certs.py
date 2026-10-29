#!/usr/bin/env python3
"""
Generate a throwaway CA plus server and client certs (PEM) for the SSL tests.

Only the openssl binary, on purpose: no keytool/JKS, so no Java needed. Python, not bash,
so it runs the same on Windows, where Git Bash rewrites -subj "/CN=..." as a path.
The req + x509 -req form works with LibreSSL (macOS) too.
"""
import os
import subprocess
import sys


def openssl(*args):
    subprocess.run(('openssl',) + args, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main(out):
    os.makedirs(out, exist_ok=True)
    os.chdir(out)
    openssl('req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1', '-subj', '/CN=cqlsh-test-ca',
            '-keyout', 'ca.key', '-out', 'ca.pem')
    for name in ('server', 'client'):
        openssl('req', '-newkey', 'rsa:2048', '-nodes', '-subj', '/CN=cqlsh-test-' + name,
                '-keyout', name + '.key', '-out', name + '.csr')
        openssl('x509', '-req', '-days', '1', '-in', name + '.csr', '-CA', 'ca.pem', '-CAkey', 'ca.key',
                '-CAcreateserial', '-out', name + '.pem')
        os.remove(name + '.csr')
    os.remove('ca.srl')
    for name in os.listdir('.'):
        # readable by the scylla user inside the container
        os.chmod(name, 0o644)


if __name__ == '__main__':
    if len(sys.argv) != 2:
        sys.exit('usage: %s <output-dir>' % sys.argv[0])
    main(sys.argv[1])
