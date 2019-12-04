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
import traceback

import locale
locale.setlocale(locale.LC_ALL, 'C')
locale.setlocale(locale.LC_CTYPE, 'C')
locale.setlocale(locale.LC_NUMERIC, 'C')

import pika
import redis
import numpy as np
import wave
import audioop
import time

import deepspeech
from google.cloud import storage
import google.cloud.logging

logger = google.cloud.logging.Client().logger("worker_logs")
storage_client = storage.Client()
try: bucket = storage_client.create_bucket("erudite-variety_buckets_default")
except:
	logger.log_text("Bucket default already exists", severity="DEBUG")
	bucket = storage_client.get_bucket("erudite-variety_buckets_default")

a = time.time()
alphabet = "deepspeech-0.5.1-models/alphabet.txt"
model = deepspeech.Model("deepspeech-0.5.1-models/output_graph.pbmm",26,9,alphabet,500)
model.enableDecoderWithLM(alphabet,"deepspeech-0.5.1-models/lm.binary", "deepspeech-0.5.1-models/trie", 0.75, 1.85)
logger.log_text("Loaded DeepSpeech Model:"+str(time.time()-a), severity="DEBUG")

connection = pika.BlockingConnection(pika.ConnectionParameters(
	host="rabbitmq.default.svc.cluster.local"))
channel = connection.channel()
channel.exchange_declare(exchange="worker", exchange_type="direct")
channel.queue_declare("work_queue")
channel.queue_bind(exchange="worker", queue="work_queue", routing_key="audio")

rdb = [redis.Redis(host="redis.default.svc.cluster.local", port='6379', db=i) for i in range(0,2)]

hostname = requests.get(url="http://metadata.google.internal/computeMetadata/v1/instance/hostname", headers={"Metadata-Flavor": "Google"}).text.split(".")[0]

def print_meta(metadata):
	logger.log_text("".join(item.character for item in metadata.items), severity="INFO")

def get_meta(bytes):
	wav = wave.open(io.BytesIO(bytes),'rb')
	framerate = wav.getframerate()
	audio_buf = wav.readframes(wav.getnframes())
	# Convert to 16KHz mono audio with 2-byte sample width
	if(wav.getsampwidth()==1):
		audio_buf = audioop.bias(audio_buf, 1, 128)
	audio_buf = audioop.lin2lin(audio_buf, wav.getsampwidth(), 2)
	if(wav.getnchannels()==2):
		audio_buf = audioop.tomono(audio_buf, 2, 0.5, 0.5)
	audio_buf = audioop.ratecv(audio_buf, 2, 1, framerate, 16000, None)[0]
	audio = np.frombuffer(audio_buf, np.int16)
	# Transcribe the audio
	a = time.time()
	meta = model.sttWithMetadata(audio,16000)
	logger.log_text("Inference:"+str(time.time()-a), severity="DEBUG")
	return meta

def word_stamp(meta): #TODO check?
	print_meta(meta)
	start = 0
	words = []
	for i in range(0, len(meta.items)):
		if(meta.items[i].character==' '):
			word = ''.join([c.character for c in meta.items[start:i]])
			words.append("{}#{}#{}".format(word, meta.items[start].start_time, meta.items[i].start_time))
			start = i+1
	if(start<len(meta.items)):
		word = ''.join([c.character for c in meta.items[start:len(meta.items)]])
		words.append("{}#{}#{}".format(word, meta.items[start].start_time, meta.items[-1].start_time))
	return ' '.join(words)

def sim_score(word1, word2):
	dp = np.zeros((len(word1), len(word2)))
	if(word1[0]==word2[0]): dp[0][0] = 1
	for i in range(1, len(word1)):
		dp[i,0] = 1 if word1[i]==word2[0] else dp[i-1,0]
	for i in range(1, len(word2)):
		dp[0,i] = 1 if word2[i]==word1[0] else dp[0,i-1]
	for i in range(1, len(word1)):
		for j in range(1, len(word2)):
			dp[i,j] = dp[i-1,j-1]+1 if word1[i]==word2[j] else max(dp[i-1,j],dp[i,j-1])
	score = 2*dp[-1,-1]/(len(word1)+len(word2))
	return score if score>0.5 else 0

def search(transcript, req): #TODO check?
	json = req[4]
	topn = json["topn"]
	transcript = transcript.split()
	words = json["words"].split()
	if(json["type"]=="fuzzy"):
		word_data = [] # [(sim_score, start time, end time)]
		for item in transcript:
			s = item.split("#")
			sim_scores = [sim_score(s[0], word) for word in words]
			word_data.append((max(sim_scores), float(s[1]), float(s[2])))
		logger.log_text("{}\n{}".format(list(zip(transcript, word_data)), words), severity="INFO")
		if(len(word_data)==0):
			return ["None"]
		start_idx = [None]*len(word_data)
		scores = np.zeros(len(word_data))
		scores[:] = -np.inf
		for i in range(len(word_data)):
			if(i == 0): end = -1
			else: end = start_idx[i-1]-1
			sim_sum = 0
			for j in range(i, end, -1):
				sim_sum += word_data[j][0]
				s = -json["alpha"]*(word_data[i][2]-word_data[j][1])+sim_sum
				if(s >= scores[i]):
					scores[i] = s
					start_idx[i] = j
		largest = list(zip(scores, enumerate(start_idx)))
		if(topn>0):
			largest = heapq.nlargest(topn, largest, lambda x: x[0])
		else:
			largest.sort(key=lambda x: x[0], reverse=True)
		return ["{}#{}#{}#{}".format(req[1], word_data[item[1][1]][1], word_data[item[1][0]][2], item[0]) for item in largest if item[0]>0]
	elif(json["type"]=="exact"):
		for i in range(len(words)): words[i] = words[i]+"#"
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
		logger.log_text("Worker recieved request to " + req[0], severity="DEBUG")
		if(req[0]=="transcribe"):
			filename = req[1]+".txt"
			meta = get_meta(req[2])
			transcript = word_stamp(meta)
			logger.log_text(transcript, severity="INFO")
			blob = bucket.get_blob(filename)
			if(blob != None):
				raise Exception("Transcription file for ({}) already exists".format(req[1]))
			blob = bucket.blob(filename)
			blob.upload_from_string(transcript)
		elif(req[0]=="search"):
			logger.log_text("Request: "+str(req), severity="INFO")
			redis_key = "{}-{}".format(req[2],req[3])
			blob = bucket.get_blob(req[1])
			if(blob == None):
				rdb[1].rpush(redis_key, "Error")
				rdb[1].expire(redis_key, 86400)
				raise Exception("File with name ({}) doesn't exist".format(req[1]))
			transcript = blob.download_as_string().decode("utf-8")
			results = search(transcript, req)
			results = results if len(results)>0 else ["None"]
			logger.log_text(redis_key+": "+str(results), severity="INFO")
			rdb[1].rpush(redis_key, *results)
			rdb[1].expire(redis_key, 86400)
		else:
			logger.log_text("Worker({}) recieved unknown command: {}".format(hostname,req[0]), severity="ERROR")
	except Exception as e:
		logger.log_text("Worker({}) callback failed: {}".format(hostname, traceback.format_exc()), severity="ERROR")
	ch.basic_ack(delivery_tag=method.delivery_tag)

def main():
	channel.basic_consume(queue="work_queue", on_message_callback=msg_callback)
	channel.start_consuming()

if __name__=="__main__":
	main()
