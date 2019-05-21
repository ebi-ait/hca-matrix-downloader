import urllib.request
import subprocess
import requests
import argparse
import hca.dss
import json
import time
import os

def parse_args():
	parser = argparse.ArgumentParser()
	parser.add_argument('-p', '--project', help="The project's Short Name, as seen in the HCA Data Browser entry, wrapped in quotes.")
	args = parser.parse_args()
	return args

def main():
	#load up project name
	args = parse_args()
	#set up DSS connection to download the sample info needed by the matrix API
	dsscli = hca.dss.DSSClient()
	#format the query, thankfully the only thing that changes is the project short name on input
	es_query = json.loads('{"query":{"bool":{"must":[{"match":{"files.project_json.project_core.project_short_name":"'+args.project+'"}},{"match":{"files.analysis_process_json.process_type.text":"analysis"}}]}}}')
	#try to download the manifest and extract the fqids, which the matrix API needs
	manifest = ['bundle_uuid\tbundle_version\n']
	try:
		for entry in dsscli.post_search.iterate(es_query=es_query, replica='aws'):
			entry_split = entry['bundle_fqid'].split('.')
			manifest.append(entry_split[0]+'\t'+entry_split[1]+'.'+entry_split[2]+'\n')
	except TypeError:
		#if the short name does not exist in the system, the above code bit tosses a TypeError
		raise ValueError("The specified project Short Name was not found in the database")
	#upload the fqid information to an external site for matrix API access
	#using file.io here. this is not ideal, but will have to do as a stop-gap
	#as the matrix API supposedly will get upgraded at some point
	with open('ids.txt','w') as fid:
		fid.writelines(manifest)
	res = subprocess.run('curl -F "file=@ids.txt" https://file.io', shell=True, stdout=subprocess.PIPE)
	os.remove('ids.txt')
	#so we have our manifest in URL form, like the matrix API wants us to
	#fire up a matrix API query
	manifest_url = json.loads(res.stdout.decode('utf-8'))['link']
	url = 'https://matrix.data.humancellatlas.org/v0/matrix'
	headers = {'Accept': 'application/json', 'Content-Type': 'application/json'}
	data = json.dumps({"bundle_fqids_url": manifest_url, "format": "loom"})
	r = requests.post(url, data=data, headers=headers)
	#now we have to keep checking if the matrix is available for download
	request_id = json.loads(r.content)['request_id']
	r = requests.get(url+'/'+request_id)
	while json.loads(r.content)['status'] == 'In Progress':
		time.sleep(30)
		r = requests.get(url+'/'+request_id)
	#the matrix is available. download it. done.
	urllib.request.urlretrieve(json.loads(r.content)["matrix_location"], "download.loom")

if __name__ == "__main__":
	main()
