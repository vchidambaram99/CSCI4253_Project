#!/bin/bash

gcloud config set compute/zone us-west1-a
gcloud container clusters create --preemptible mykube

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

cd logger
./logger-launch.sh
cd ..
