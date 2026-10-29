from redis import Redis
from rq import Queue

redis_conn = Redis(host="redis", port=6379)
queue = Queue("curves", connection=redis_conn)