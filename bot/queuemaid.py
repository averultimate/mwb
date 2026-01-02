import json
import os

FILE_NAME = "queue.json"

def save_queue(adds, dels):
	data = {"pending_adds": list(adds), "pending_dels": list(dels)}
	with open(FILE_NAME, 'w') as f:
		json.dump(data, f)

def load_queue():
	if not os.path.exists(FILE_NAME):
		return set(), set()
	with open(FILE_NAME, 'r') as f:
		data = json.load(f)
		return set(data.get("pending_adds", [])), set(data.get("pending_dels", []))
