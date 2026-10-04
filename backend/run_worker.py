"""Standalone RQ worker launcher — run this instead of `rq worker`."""
from rq import Queue
from rq.worker import SimpleWorker
from rq.timeouts import BaseDeathPenalty
from redis import Redis


class NoDeathPenalty(BaseDeathPenalty):
    """No-op death penalty for Windows where SIGALRM doesn't exist."""
    def setup_death_penalty(self):
        pass
    def cancel_death_penalty(self):
        pass


conn = Redis.from_url("redis://localhost:6379/0")
queues = [Queue(connection=conn)]

if __name__ == "__main__":
    w = SimpleWorker(queues, connection=conn)
    w.death_penalty_class = NoDeathPenalty
    print("Argus RQ worker started (SimpleWorker/Windows, no-timeout). Listening on queue: default")
    w.work(with_scheduler=False)
