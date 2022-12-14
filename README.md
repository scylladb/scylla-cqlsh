# scylla-cqlsh

Command line tool to connect to [scylladb](http://www.scylladb.com) (or Apache Cassandra)

A fork of the cqlsh tool from https://github.com/apache/cassandra

![Libraries.io dependency status for latest release](https://img.shields.io/librariesio/release/pypi/scylla-cqlsh)
![GitHub branch checks state](https://img.shields.io/github/checks-status/scylladb/scylla-cqlsh/master)
![PyPI](https://img.shields.io/pypi/v/scylla-cqlsh)

# Quickstart

```bash
pip install scylla-cqlsh

cqlsh ${SCYLLA_HOST} -e 'SELECT * FROM system.local'

# or just using it interactively
cqlsh ${SCYLLA_HOST} 

# or using it with scylla-cloud
cqlsh --cloudconf [path to connection bundle downloaded]

# running with docker image interactively
docker run -it scylladb/scylla-cqlsh ${SCYLLA_HOST}
```



# Contributing

Feel free to open a PR/issues with suggestion and improvement
Try covering you suggested change with a test, and the instruction 
for running tests are below

## Testing

Dependent 
* python 2.7/3.x (recommend virtualenv)
* minimum java8

```bash
pip install -e .
pip install -r pylib/requirements.txt

# run scylla with docker
docker run  -d scylladb/scylla:latest --cluster-name test

export DOCKER_ID=$(docker run -d scylladb/scylla:latest --cluster-name test)
export CQL_TEST_HOST=$(docker inspect --format='{{ .NetworkSettings.IPAddress }}' ${DOCKER_ID})
while ! nc -z ${CQL_TEST_HOST} 9042; do   
  sleep 0.1 # wait for 1/10 of the second before check again
done
          
 
# run scylla with CCM
ccm create cqlsh_cluster -n 1 --scylla --version unstable/master:latest
ccm start

pytest
```


## Creation of the repo

A reference on how this we forked out of cassandra repo
So we can repeat the process if we want to bring change back it

```bash
git clone  -b trunk --single-branch git@github.com:apache/cassandra.git
sudo apt-get install git-filter-repo
cd cassandra

git filter-repo --path bin/cqlsh --path bin/cqlsh.py --path pylib/
```
