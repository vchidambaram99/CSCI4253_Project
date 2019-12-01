#!/bin/bash

git clone https://github.com/mozilla/DeepSpeech.git
sudo apt-get update
sudo apt-get install -y python3 python3-pip
pip3 install deepspeech
curl -LO https://github.com/mozilla/DeepSpeech/releases/download/v0.5.1/deepspeech-0.5.1-models.tar.gz
tar xvf deepspeech-0.5.1-models.tar.gz
curl -LO https://github.com/mozilla/DeepSpeech/releases/download/v0.5.1/audio-0.5.1.tar.gz
tar xvf audio-0.5.1.tar.gz

