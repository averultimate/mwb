import json
from pathlib import Path

QUEUE_FILE = Path("queue.json")

def save_queue(pending_adds, pending_dels, contributors):
	data = {
		"pending_adds": sorted(pending_adds),
		"pending_dels": sorted(pending_dels),
		"contributors": sorted(contributors),
	}
	QUEUE_FILE.write_text(json.dumps(data, indent=2))


def load_queue():
	if not QUEUE_FILE.exists():
		return set(), set(), set()

	data = json.loads(QUEUE_FILE.read_text())
	return (
		set(data.get("pending_adds", [])),
		set(data.get("pending_dels", [])),
		set(data.get("contributors", [])),
	)
