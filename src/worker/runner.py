from redis import Redis
from rq import Queue
from db.engine import init_db

init_db() # если worker стартует первым

redis_conn = Redis(host="redis", port=6379)
queue = Queue("curves", connection=redis_conn)