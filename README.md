# scylla-cqlsh

A fork of the cqlsh from https://github.com/apache/cassandra

## Creation of the repo:

```bash
git clone  -b trunk --single-branch git@github.com:apache/cassandra.git
sudo apt-get install git-filter-repo
cd cassandra

git filter-repo --path bin/cqlsh --path bin/cqlsh.py --path pylib/
```


# Testing:

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
