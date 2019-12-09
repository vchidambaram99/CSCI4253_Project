# CSCI4253 Project

This is the repository for my CSCI4253 project. It is a cloud service that transcribes audio using Mozilla's [Deepspeech](https://github.com/mozilla/DeepSpeech), and makes it searchable (with timestamps) through a REST API. It creates a Kubernetes cluster on Google Cloud, and sets up worker nodes and rest nodes that communicate through a RabbitMQ broker.
