import os
import subprocess
import time
import json
import urllib.request

def run():
    print("--- 1. WORKER LAUNCH & LOG ---")
    print("Command:")
    print("python run_worker.py")
    
    # Start worker
    worker = subprocess.Popen(
        ["python", "run_worker.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    
    # Give it a couple seconds to start up
    time.sleep(2)
    
    # Non-blocking read of what's produced so far
    import queue
    import threading
    
    q = queue.Queue()
    def enqueue_output(out, queue):
        for line in iter(out.readline, b''):
            queue.put(line)
        out.close()
        
    t = threading.Thread(target=enqueue_output, args=(worker.stdout, q))
    t.daemon = True
    t.start()
    
    worker_log = ""
    while not q.empty():
        worker_log += q.get_nowait()
    
    print("Startup log:")
    print(worker_log.strip())
    
    print("\n--- 2. IMAGE PREP ---")
    cmd_prep = ["python", "-c", "from PIL import Image; img = Image.open('test_photo3.jpg'); img.rotate(5).save('test_batch_borderline2.jpg')"]
    print("Command used for borderline case:")
    print(" ".join(cmd_prep))
    
    # Ensure test_photo3.jpg exists
    urllib.request.urlretrieve('https://picsum.photos/400/300?random=30', 'test_photo3.jpg')
    
    subprocess.run(cmd_prep, check=True)
    subprocess.run(["python", "-c", "import urllib.request as r; r.urlretrieve('https://picsum.photos/400/300?random=35', 'test_batch_new2.jpg')"], check=True)
    
    print("\n--- 3. BATCH POST ---")
    cmd_post = [
        "curl", "-s", "-X", "POST", "http://localhost:8000/images/batch-check",
        "-F", "files=@test_photo1.jpg",
        "-F", "files=@test_batch_new2.jpg",
        "-F", "files=@test_batch_borderline2.jpg"
    ]
    res_post = subprocess.run(cmd_post, capture_output=True, text=True)
    print(res_post.stdout.strip())
    
    try:
        job_id = json.loads(res_post.stdout.strip())["job_id"]
    except Exception as e:
        print("Failed to parse POST resp:", res_post.stdout)
        worker.terminate()
        return

    print("\n--- 4. IMMEDIATE POLL (PROVING ASYNC) ---")
    polls = []
    
    # Immediate poll
    res_poll = subprocess.run(["curl", "-s", f"http://localhost:8000/jobs/{job_id}"], capture_output=True, text=True)
    print(res_poll.stdout.strip())
    polls.append(res_poll.stdout.strip())
    
    print("\n--- 5. SUBSEQUENT POLLS ---")
    for _ in range(10):
        time.sleep(2)
        res_poll = subprocess.run(["curl", "-s", f"http://localhost:8000/jobs/{job_id}"], capture_output=True, text=True)
        out = res_poll.stdout.strip()
        print(out)
        if "complete" in out:
            break

    print("\n--- 6. WORKER LOG SINCE BATCH ---")
    time.sleep(1) # Let worker flush
    new_log = ""
    while not q.empty():
        new_log += q.get_nowait()
    print(new_log.strip())
    
    print("\n--- 7. DATABASE SNAPSHOT ---")
    res_psql = subprocess.run([
        r"C:\Program Files\PostgreSQL\16\bin\psql.exe",
        "-U", "argus", "-h", "127.0.0.1", "-d", "argus",
        "-c", "SELECT filename, status, reason_code, canonical_id FROM images ORDER BY created_at DESC LIMIT 3;"
    ], capture_output=True, text=True)
    print(res_psql.stdout)
    
    # Clean up
    worker.terminate()
    worker.wait()

if __name__ == "__main__":
    run()
