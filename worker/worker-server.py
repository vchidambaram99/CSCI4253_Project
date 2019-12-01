#
# Worker server
#

import os
import argparse
import pickle
import io
import requests
import json
import heapq

import locale
locale.setlocale(locale.LC_ALL, 'C')
locale.setlocale(locale.LC_CTYPE, 'C')
locale.setlocale(locale.LC_NUMERIC, 'C')

import pika
import redis
import numpy as np
import wave
import deepspeech
import time
from google.cloud import storage

a = time.time()
alphabet = "deepspeech-0.5.1-models/alphabet.txt"
model = deepspeech.Model("deepspeech-0.5.1-models/output_graph.pbmm",26,9,alphabet,500)
model.enableDecoderWithLM(alphabet,"deepspeech-0.5.1-models/lm.binary", "deepspeech-0.5.1-models/trie", 0.75, 1.85)
print("Loaded DeepSpeech Model:",time.time()-a)

connection = pika.BlockingConnection(pika.ConnectionParameters(
	host="rabbitmq.default.svc.cluster.local"))
channel = connection.channel()
channel.exchange_declare(exchange="worker", exchange_type="direct")
channel.queue_declare("work_queue")
channel.queue_bind(exchange="worker", queue="work_queue", routing_key="audio")

rdb = [redis.Redis(host="redis.default.svc.cluster.local", port='6379', db=i) for i in range(0,2)]

hostname = requests.get(url="http://metadata.google.internal/computeMetadata/v1/instance/hostname", headers={"Metadata-Flavor": "Google"}).text.split(".")[0]

storage_client = storage.Client()
try: bucket = storage_client.create_bucket("erudite-variety_buckets_default")
except:
	print("Bucket default already exists")
	bucket = storage_client.get_bucket("erudite-variety_buckets_default")

def print_meta(metadata):
	print("".join(item.character for item in metadata.items))

def get_meta(bytes):
	wav = wave.open(io.BytesIO(bytes),'rb')
	framerate = fin.getframerate()
	audio = np.frombuffer(wav.readframes(wav.getnframes()), np.int16)
	a = time.time()
	meta = model.sttWithMetadata(audio,framerate)
	print("Inference:",time.time()-a)
	return meta

def word_stamp(meta): #TODO check?
	start = 0
	words = []
	for i in range(0, len(meta.items)):
		if(meta.items[i].character==' '):
			word = ''.join([c.character for c in meta.items[start:i]])
			words.append("{}#{}#{}".format(word, meta.items[start].start_time, meta.items[i].start_time))
			start = i+1
	word = ''.join([c.character for c in meta.items[start:len(meta.items)]])
	words.append("{}#{}#{}".format(word, meta.items[start].start_time, meta.items[len(meta.items)-1].start_time))
	return ' '.join(words)

def search(transcript, req): #TODO check?
	json = req[4]
	topn = json["topn"]
	transcript = transcript.split()
	words = json["words"].split()
	for i in range(len(words)): words[i] = words[i]+"#"
	if(json["type"]=="fuzzy"):
		word_data = [] # [(word index, start time, end time)]
		for item in transcript:
			for i in range(len(words)):
				if(item.startswith(words[i])):
					s = item.split("#")
					word_data.append((i, float(s[1]), float(s[2])))
					break
		if(len(word_data)==0)
			return ["None"]
		start_idx = [None]*len(word_data)
		scores = np.zeros(len(word_data))
		for i in range(len(word_data)):
			if(i == 0): end = -1
			else: end = start_idx[i-1]-1
			matched = [False]*len(words)
			match = 0
			for j in range(i, end, -1):
				if(not matched[word_data[j][0]]):
					match += 1
				counts[word_data[j][0]] = True
				s = req["alpha"]*(word_data[i][2]-word_data[j][1])+match
				if(s >= scores[i]):
					scores[i] = s
					start_idx[i] = j
		largest = heapq.nlargest(topn, zip(scores, enumerate(start_idx)), lambda x: x[0])
		return ["{}#{}#{}#{}".format(req[1], word_data[item[1][1]][1], word_data[item[1][0]][2], item[0]) for item in largest]
	elif(json["type"]=="exact"):
		matches = []
		for i in range(len(transcript)-len(words)+1):
			b = True
			for j in range(len(words)):
				if(not transcript[i+j].startswith(words[j])):
					b = False
					break
			if(b):
				start = transcript[i].split("#")[1]
				end = transcript[i+len(words)-1].split("#")[2]
				matches.append("{}#{}#{}#{}".format(req[1],start,end,1))
			if(len(matches)>=topn and topn > 0):
				break
		return matches
	else:
		return ["Error"]

def msg_callback(ch, method, properties, body):
	try:
		req = pickle.loads(body)
		if(req[0]=="transcribe"):
			filename = req[1]+".txt"
			meta = get_meta(req[2])
			transcript = word_stamp(meta)
			print(transcript)
			blob = bucket.get_blob(filename)
			if(blob != None):
				raise Exception("Transcription file for ({}) already exists".format(req[1]))
			blob = bucket.blob(filename)
			blob.upload_from_string(transcript)
		elif(req[0]=="search"):
			redis_key = "-".join(req[2:4])
			blob = bucket.get_blob(req[1])
			if(blob == None):
				rdb[1].rpush(redis_key, "Error")
				rdb[1].pexpire(redis_key, 600000)
				raise Exception("File with name ({}) doesn't exist".format(req[1]))
			transcript = blob.download_as_string().decode("utf-8")
			results = search(transcript, req)
			rdb[1].rpush(redis_key, *results)
			rdb[1].pexpire(redis_key, 600000)
		else:
			print("Worker({}) recieved unknown command: {}",hostname,req[0])
	except Exception as e:
		print("Worker({}) callback failed: {}".format(hostname, str(e)))
	ch.basic_ack(delivery_tag=method.delivery_tag)

def main():
	channel.basic_consume(queue="work_queue", on_message_callback=msg_callback)
	channel.start_consuming()

if __name__=="__main__":
	main()
