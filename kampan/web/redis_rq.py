import redis
from rq import Worker, Queue, Connection
from rq.job import Job

listen = ["default"]


class RedisQueue:
    def __init__(self, redis_url=""):
        self.redis_url = redis_url

        if self.redis_url:
            self.init_app(self.redis_url)

    def init_app(self, redis_url):
        self.redis_url = redis_url
        self.conn = redis.from_url(redis_url)
        self.queue = Queue(connection=self.conn)

    def get_job(self, job_key):
        job = None
        try:
            job = Job.fetch(job_key, connection=self.conn)
        except Exception as e:
            print(e)
        return job


redis_queue = RedisQueue()


def init_rq(app):
    redis_url = app.config["REDIS_URL"]
    redis_queue.init_app(redis_url)
