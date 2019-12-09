#!/bin/bash

gcloud config set compute/zone us-west1-a
gcloud container clusters create mykube --preemptible --enable-autoscaling --min-nodes=2 --max-nodes=5 --num-nodes=3

cd rabbitmq
./rabbitmq-launch.sh
cd ..

cd redis
./redis-launch.sh
cd ..

cd rest
./rest-launch.sh
cd ..

cd worker
./worker-launch.sh
cd ..
