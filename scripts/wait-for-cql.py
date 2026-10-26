#!/usr/bin/env python3
"""
Wait until a CQL node answers a query, not just accepts TCP: Docker port forwarders
(colima, WSL) accept connections long before the node behind them is up.
"""
import sys
import time

from cassandra import OperationTimedOut
from cassandra.cluster import Cluster, NoHostAvailable
# the driver's default libev reactor crashes on Windows; asyncio works everywhere
from cassandra.io.asyncioreactor import AsyncioConnection

host = sys.argv[1] if len(sys.argv) > 1 else '127.0.0.1'
deadline = time.time() + 600
while True:
    cluster = Cluster([host], connection_class=AsyncioConnection)
    try:
        print(cluster.connect().execute('SELECT release_version FROM system.local').one())
        break
    except (NoHostAvailable, OperationTimedOut):
        if time.time() > deadline:
            raise
        time.sleep(2)
    finally:
        cluster.shutdown()
