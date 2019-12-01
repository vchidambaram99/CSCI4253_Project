import numpy as np
import wave
import deepspeech
import time

a = time.time()
alphabet = "deepspeech-0.5.1-models/alphabet.txt"
model = deepspeech.Model("deepspeech-0.5.1-models/output_graph.pbmm",26,9,alphabet,500)
model.enableDecoderWithLM(alphabet,"deepspeech-0.5.1-models/lm.binary", "deepspeech-0.5.1-models/trie", 0.75, 1.85)
print("Loaded:",time.time()-a)

def print_meta(metadata):
	print("".join(item.character for item in metadata.items))
	

def get_meta(filename):
	fin = wave.open(filename,'rb')
	fs = fin.getframerate()
	audio = np.frombuffer(fin.readframes(fin.getnframes()), np.int16)
	a = time.time()
	meta = model.sttWithMetadata(audio,fs)
	print("Inference:",time.time()-a)
	return meta

def word_stamp(meta):
	start = 0
	words = []
	for i in range(0, len(meta.items)):
		if(meta.items[i].character==' '):
			words.append((''.join([c.character for c in meta.items[start:i]]),meta.items[start].start_time))
			start = i+1
	words.append((''.join([c.character for c in meta.items[start:len(meta.items)]]),meta.items[start].start_time))
	return words
