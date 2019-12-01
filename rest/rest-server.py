# Web server script

import os
import argparse
import io
import json
import pickle
import requests
import time
import heapq

import pika
import redis
from flask import Flask, request, Response
from werkzeug.routing import BaseConverter

from google.cloud import storage

connection = pika.BlockingConnection(pika.ConnectionParameters(
	host="rabbitmq.default.svc.cluster.local",
	heartbeat=0))
channel = connection.channel()
channel.exchange_declare(exchange="worker", exchange_type="direct")
channel.queue_declare("work_queue")
channel.queue_bind(exchange="worker", queue="work_queue", routing_key="audio")

rdb = [redis.Redis(host="redis.default.svc.cluster.local", port='6379', db=i) for i in range(0,2)] # TODO

hostname = requests.get(url="http://metadata.google.internal/computeMetadata/v1/instance/hostname", headers={"Metadata-Flavor": "Google"}).text.split(".")[0]

storage_client = storage.Client()
try: bucket = storage_client.create_bucket("erudite-variety_buckets_default")
except:
	print("Bucket default already exists")
	bucket = storage_client.get_bucket("erudite-variety_buckets_default")

class PathConverter(BaseConverter):
    regex = r"([a-zA-Z0-9._]/?)+"
    weight = 200

app = Flask(__name__)
app.url_map.converters['path'] = PathConverter

@app.route("/upload/<path:filename>", methods=["PUT", "POST"])
def upload(filename):
	if(not filename.endswith(".wav")):
		return Response(response=json.dumps({"error": "Please upload a .wav file"}), status=400, mimetype="application/json")
	blob = bucket.get_blob(filename)
	if(blob != None):
		return Response(response=json.dumps({"error": "This filename already exists"}), status=400, mimetype="application/json")
	blob = bucket.blob(filename)
	blob.upload_from_string(request.data) #TODO add argument
	channel.basic_publish(exchange="worker", routing_key="audio", body=pickle.dumps(("transcribe",filename,request.data)))
	return Response(response=json.dumps({"success": filename}), status=200, mimetype="application/json")

@app.route("/transcript/<path:filename>", methods=["GET"])
def transcript(filename):
	if(bucket.get_blob(filename) != None):
		blob = None
		timeout = 0
		while(timeout<60):
			blob = bucket.get_blob(filename+".txt")
			if(blob==None):
				time.sleep(1)
				timeout += 1
			else: break
		if(timeout==60): return Response(response=json.dumps({"error": "Waiting for transcription timed out, please try again later."}), status=400, mimetype="application/json")
		else: return Response(response=blob.download_as_string(), status=200, mimetype="text/plain")
	return Response(response=json.dumps({"error": "This filename doesn't exist"}), status=400, mimetype="application/json")

@app.route("/delete/<path:filepath>", methods=["POST"])
def delete(filepath):
	deleted = []
	for blob in Client.list_blobs(bucket, prefix=filepath):
		deleted.append(blob.name)
		blob.delete()
	return Response(response=json.dumps({"deleted": deleted}), status=200, mimetype="application/json")

@app.route("/list/<path:filepath>", methods=["GET"])
def list(filepath):
	blobs = []
	for blob in Client.list_blobs(bucket, prefix=filepath):
		blobs.append(blob.name)
	return Response(response=json.dumps({"blobs": blobs}), status=200, mimetype="application/json")

@app.route("/search/<path:filepath>", methods=["GET"])
def search(filepath):
	req_json = json.loads(request.data)
	request_id = rdb[0].incr("request_id") #TODO check that this returns a value
	num = 0
	for blob in Client.list_blobs(bucket, prefix=filepath):
		if(blob.name.endswith(".txt")): #TODO additional checks (to emulate paths instead of prefixes)
			channel.basic_publish(exchange="worker", routing_key="audio", body=pickle.dumps(("search",blob.name,request_id,num,req_json)))
			num += 1
	search_results = []
	for i in range(0, num):
		redis_key = "{}-{}".format(request_id, num)
		while(True):
			if(rdb[1].exists(redis_key)):
				results = rdb[1].lrange(redis_key,0,-1)
				for res in results:
					if(res == "None" or res == "Error"): #TODO error handling?
						continue
					else:
						search_results.append(res.split("#"))
				break
			time.sleep(1)
			req_json["timeout"] -= 1000
			if(req_json["timeout"]<=0):
				break
	#TODO aggregate search results into output
	top = heapq.nlargest(req_json["topn"], search_results, lambda x: float(x[3]))
	return Response(response=json.dumps({"results": top}), status=200, mimetype="application/json")
