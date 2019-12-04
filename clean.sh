#!/bin/bash

echo "y" | gcloud container clusters delete mykube &
gsutil -m rm gs://erudite-variety_buckets_default/** &
