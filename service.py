import os
import json
import requests

class Client:
	def __init__(self, hostname):
		self.addr = "http://{}:5000".format(hostname)

	def upload(self, filepath, outpath=None):
		if(outpath==None):
			outpath = filepath
		addr = "{}/upload/{}".format(self.addr, outpath)
		with open(filepath,'rb') as file:
			response = requests.post(addr, data=file.read())
			return json.loads(response.text)

	def upload_folder(self, folder, outfolder=None):
		if(not folder.endswith("/")): folder += "/"
		if(outfolder==None):
			outfolder = folder
		if(not outfolder.endswith("/")): outfolder += "/"
		b = (outfolder == folder)
		outputs = []
		for (dirpath, dirnames, filenames) in os.walk(folder):
			outpath = dirpath if b else dirpath.replace(folder, outfolder, 1)
			if(not outpath.endswith("/")): outpath += "/"
			if(not dirpath.endswith("/")): dirpath += "/"
			for fname in filenames:
				infile_name = dirpath+fname
				outputs.append((infile_name, self.upload(infile_name, outpath+fname)))
		return outputs

	def download(self, filepath, outfile, start=0, end=-1): #outfile is a file-like object or string
		addr = "{}/download/{}".format(self.addr, filepath)
		req_dict = {"start": start, "end": end}
		if(type(outfile)==str):
			outfile = open(outfile,'wb')
		response = requests.get(addr, data=json.dumps(req_dict))
		try:
			res_dict = json.loads(response.text)
			return res_dict
		except: #TODO consider case when it fails with server error
			outfile.write(response.content)
			return None

	def transcript(self, filepath):
		addr = "{}/transcript/{}".format(self.addr, filepath)
		response = requests.get(addr)
		ret = json.loads(response.text)
		if("error" in ret):
			raise FileNotFoundError(ret["error"])
		return ret

	def list(self, endpoint=""):
		addr = "{}/list/{}".format(self.addr, endpoint)
		response = requests.get(addr)
		return json.loads(response.text)

	def delete(self, endpoint):
		addr = "{}/delete/{}".format(self.addr, endpoint)
		response = requests.post(addr)
		return json.loads(response.text)

	def search(self, endpoint, words, **kwargs):
		addr = "{}/search/{}".format(self.addr, endpoint)
		req_dict = {"words": words}
		if(kwargs.get("type", "fuzzy")=="exact"):
			req_dict["type"] = "exact"
		else:
			req_dict["type"] = "fuzzy"
			req_dict["alpha"] = kwargs.get("alpha", 1.5)
		req_dict["topn"] = kwargs.get("topn", -1)
		req_dict["timeout"] = kwargs.get("timeout", -1)
		response = requests.get(addr, data=json.dumps(req_dict))
		return json.loads(response.text)

	def oldsearch(self, request_id, **kwargs):
		addr = "{}/oldsearch/{}".format(self.addr, request_id)
		req_dict = {}
		req_dict["topn"] = kwargs.get("topn", -1)
		req_dict["timeout"] = kwargs.get("timeout", -1)
		response = requests.get(addr, data=json.dumps(req_dict))
		return json.loads(response.text)
