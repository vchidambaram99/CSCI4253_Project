#!/bin/bash
#
# This is the script you need to provide to launch a redis instance
#

docker build -t gcr.io/erudite-variety-251120/worker:1.0 .
gcloud auth configure-docker
docker push gcr.io/erudite-variety-251120/worker:1.0
kubectl apply -f ./deployment.yaml
