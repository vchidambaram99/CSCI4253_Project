#!/bin/bash

apt-get update
apt-get install -y python3 python3-pip git curl
pip3 install numpy pika pillow redis requests google-cloud-storage google-cloud-logging

git clone https://github.com/mozilla/DeepSpeech.git
pip3 install deepspeech
curl -LO https://github.com/mozilla/DeepSpeech/releases/download/v0.5.1/deepspeech-0.5.1-models.tar.gz
tar xvf deepspeech-0.5.1-models.tar.gz
