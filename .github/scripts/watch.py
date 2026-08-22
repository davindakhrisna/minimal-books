import os
import time
import subprocess

WATCH_DIRS = ["contents"]
WATCH_FILES = [".github/books.yaml"]

def get_latest_mtime():
    latest = 0
    for file in WATCH_FILES:
        if os.path.exists(file):
            mtime = os.path.getmtime(file)
            if mtime > latest:
                latest = mtime
                
    for directory in WATCH_DIRS:
        if os.path.exists(directory):
            for root, _, files in os.walk(directory):
                for f in files:
                    mtime = os.path.getmtime(os.path.join(root, f))
                    if mtime > latest:
                        latest = mtime
    return latest

def run_generate():
    print("Changes detected! Regenerating OPDS feed...")
    subprocess.run(["python", ".github/scripts/generate_opds.py"])

if __name__ == "__main__":
    print("Watching for changes in 'contents/' and '.github/books.yaml'...")
    last_mtime = get_latest_mtime()
    
    try:
        while True:
            time.sleep(2)
            current_mtime = get_latest_mtime()
            if current_mtime > last_mtime:
                last_mtime = current_mtime
                run_generate()
    except KeyboardInterrupt:
        print("Watcher stopped.")
