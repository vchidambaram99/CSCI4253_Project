#!/bin/bash
#
# This is the script you need to provide to launch a redis instance
# and and service
#

kubectl apply -f ./deployment.yaml -f ./service.yaml
