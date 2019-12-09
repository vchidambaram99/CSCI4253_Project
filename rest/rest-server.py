# Web server script

import os
import argparse
import io
import json
import pickle
import requests
import time
import heapq
import wave

import pika
import redis
from flask import Flask, request, Response
from werkzeug.routing import BaseConverter

from google.cloud import storage
import google.cloud.logging

connection = None
while(True):
	try:
		connection = pika.BlockingConnection(pika.ConnectionParameters(
			host="rabbitmq.default.svc.cluster.local",
			heartbeat=0))
		break
	except: time.sleep(1)
channel = connection.channel()
channel.exchange_declare(exchange="worker", exchange_type="direct", durable=True)
channel.queue_declare("work_queue", durable=True)
channel.queue_bind(exchange="worker", queue="work_queue", routing_key="audio")

rdb = [redis.Redis(host="redis.default.svc.cluster.local", port='6379', db=i) for i in range(0,2)] # TODO

hostname = requests.get(url="http://metadata.google.internal/computeMetadata/v1/instance/hostname", headers={"Metadata-Flavor": "Google"}).text.split(".")[0]

logger = google.cloud.logging.Client().logger("rest_logs")
storage_client = storage.Client()
try: bucket = storage_client.create_bucket("erudite-variety_buckets_default")
except:
	logger.log_text("Bucket default already exists", severity="DEBUG")
	bucket = storage_client.get_bucket("erudite-variety_buckets_default")

class PathConverter(BaseConverter):
    regex = r"([a-zA-Z0-9._]/?)*"
    weight = 200

app = Flask(__name__)
app.url_map.converters['path'] = PathConverter

@app.route("/upload/<path:filename>", methods=["PUT", "POST"])
def upload(filename):
	data = request.data # to help with issue in python requests library
	if(not filename.endswith(".wav")):
		return Response(response=json.dumps({"error": "Please upload a .wav file"}), status=400, mimetype="application/json")
	blob = bucket.get_blob(filename)
	if(blob != None):
		return Response(response=json.dumps({"error": "This filename already exists"}), status=400, mimetype="application/json")
	blob = bucket.blob(filename)
	blob.upload_from_string(data)
	channel.basic_publish(exchange="worker", routing_key="audio", body=pickle.dumps(("transcribe",filename)), properties=pika.BasicProperties(delivery_mode=2))
	return Response(response=json.dumps({"success": filename}), status=200, mimetype="application/json")

@app.route("/download/<path:filename>", methods=["GET"])
def download(filename):
	req_json = json.loads(request.data)
	if(not filename.endswith(".wav")):
		return Response(response=json.dumps({"error": "Please select a .wav file or use the transcript endpoint"}), status=400, mimetype="application/json")
	blob = bucket.get_blob(filename)
	if(blob == None):
		return Response(response=json.dumps({"error": "This filename doesn't exist"}), status=400, mimetype="application/json")
	blob = bucket.blob(filename)
	wav = wave.open(io.BytesIO(blob.download_as_string()), 'rb')
	framerate = wav.getframerate()
	start = req_json.get("start", 0)
	end = req_json.get("end", -1)
	if(end*framerate>=wav.getnframes()): end = -1
	outfile = io.BytesIO()
	writer = wave.open(outfile, 'wb')
	writer.setnchannels(wav.getnchannels())
	writer.setsampwidth(wav.getsampwidth())
	writer.setframerate(framerate)
	frames = wav.readframes(int(start*framerate))
	if(end!=-1):
		writer.writeframes(wav.readframes(wav.getnframes()))
	else:
		writer.writeframes(wav.readframes(int((end-start)*framerate)))
	return Response(response=outfile.getvalue(), status=200)

@app.route("/transcript/<path:filename>", methods=["GET"])
def transcript(filename):
	timeout = json.loads(request.data)["timeout"]
	forever = timeout<0
	if(bucket.get_blob(filename) != None):
		blob = None
		while(timeout>0 or forever):
			blob = bucket.get_blob(filename+".txt")
			if(blob==None):
				time.sleep(0.1)
				timeout -= 0.1
			else: break
		if(timeout<=0 and not forever): return Response(response=json.dumps({"error": "Waiting for transcription timed out, please try again later."}), status=400, mimetype="application/json")
		else: return Response(response=json.dumps({"transcript": blob.download_as_string().decode("utf-8")}), status=200, mimetype="application/json")
	return Response(response=json.dumps({"error": "This filename doesn't exist"}), status=400, mimetype="application/json")

@app.route("/delete/<path:filepath>", methods=["POST"])
def delete(filepath):
	deleted = []
	for blob in storage_client.list_blobs(bucket, prefix=filepath):
		deleted.append(blob.name)
		blob.delete()
	return Response(response=json.dumps({"deleted": deleted}), status=200, mimetype="application/json")

@app.route("/list/<path:filepath>", methods=["GET"])
def list(filepath):
	blobs = []
	for blob in storage_client.list_blobs(bucket, prefix=filepath):
		blobs.append(blob.name)
	return Response(response=json.dumps({"blobs": blobs}), status=200, mimetype="application/json")

def process_search(request_id, num, timeout, topn):
	search_results = []
	for i in range(0, num):
		redis_key = "{}-{}".format(request_id, i)
		logger.log_text("Waiting for search: "+redis_key, severity="DEBUG")
		while(True):
			if(rdb[1].exists(redis_key)):
				logger.log_text("Redis_key {} exists".format(redis_key), severity="DEBUG")
				results = [r.decode('utf-8') for r in rdb[1].lrange(redis_key,0,-1)]
				logger.log_text("Search results for {}: {}".format(redis_key, results), severity="DEBUG")
				for res in results:
					if(res == "None" or res == "Error"): #TODO error handling?
						continue
					else:
						logger.log_text("REST, search {}: {}".format(redis_key, str(res)),severity="INFO")
						search_results.append(res.split("#"))
				break
			if(timeout<=0):
				break
			time.sleep(0.1)
			timeout -= 0.1
	logger.log_text("Unsorted results for {}: {}".format(request_id, search_results), severity="INFO")
	if(topn>0):
		search_results = heapq.nlargest(topn, search_results, lambda x: float(x[3]))
	else:
		search_results.sort(key=lambda x: float(x[3]), reverse=True)
	return search_results

@app.route("/search/<path:filepath>", methods=["GET"])
def search(filepath):
	req_json = json.loads(request.data)
	request_id = rdb[0].incr("request_id")
	ret_dict = {"request_id": request_id}
	logger.log_text("Search Request: "+str(request_id), severity="INFO")
	num = 0
	for blob in storage_client.list_blobs(bucket, prefix=filepath):
		if(blob.name.endswith(".txt")): #TODO additional checks (to emulate paths instead of prefixes)
			channel.basic_publish(exchange="worker", routing_key="audio", body=pickle.dumps(("search",blob.name,request_id,num,req_json)), properties=pika.BasicProperties(delivery_mode=2))
			num += 1
	rdb[1].set(str(request_id), num, ex=86400)
	ret_dict["results"] = process_search(request_id, num, req_json["timeout"], req_json["topn"])
	return Response(response=json.dumps(ret_dict), status=200, mimetype="application/json")

@app.route("/oldsearch/<int:request_id>", methods=["GET"])
def search_op(request_id):
	req_json = json.loads(request.data)
	if(not rdb[1].exists(request_id)):
		return Response(response=json.dumps({"error": "This request id doesn't exist, it is either invalid or has timed out."}), status=400, mimetype="application/json")
	num = int(rdb[1].get(request_id))
	ret_dict = {"results": process_search(request_id, num, req_json["timeout"], req_json["topn"])}
	return Response(response=json.dumps(ret_dict), status=200, mimetype="application/json")
