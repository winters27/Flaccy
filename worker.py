import os
import redis
import os
import redis
from rq import Worker, Queue
from app import create_app

listen = ['default']

redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379')

conn = redis.from_url(redis_url)

if __name__ == '__main__':
    queues = [Queue(name, connection=conn) for name in listen]
    worker = Worker(queues, connection=conn)
    worker.work(with_scheduler=True)
