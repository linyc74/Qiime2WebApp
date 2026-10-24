import time
import subprocess
from rq import Queue
from redis import Redis
from sqlalchemy import create_engine, text, Engine


POSTGRES_HOST = 'localhost'
POSTGRES_PORT = 5432
POSTGRES_USER = 'postgres'
POSTGRES_DB = 'qiime2_web_app'
POSTGRES_URL = f'postgresql+psycopg2://{POSTGRES_USER}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}'
REDIS_HOST = 'localhost'
REDIS_PORT = 6379
REDIS_QUEUE = 'qiime2'  # start the redis queue worker in another terminal: `rq worker -w rq.worker.SpawnWorker qiime2`


class Worker:

    user_id: int

    def __init__(self, user_id: int):
        self.user_id = user_id

    def submit_job(self, job_timestamp: str, cmd: str):
        db = create_engine(POSTGRES_URL)
        with db.connect() as conn:
            ret = conn.execute(
                text('''
                    INSERT INTO jobs (user_id, timestamp, status)
                    VALUES (:user_id, :timestamp, :status)
                    RETURNING id
                '''),
                {'user_id': self.user_id, 'timestamp': job_timestamp, 'status': 'waiting'}
            )
            job_id = ret.scalar_one()
            conn.commit()

        q = Queue(
            name=REDIS_QUEUE,
            connection=Redis(host=REDIS_HOST, port=REDIS_PORT)
        )
        job = q.enqueue(
            run_command,
            job_id,
            cmd,
            job_timeout='24h',
        )


def run_command(job_id: int, cmd: str):
    db = create_engine(POSTGRES_URL)

    with db.connect() as conn:
        conn.execute(
            text('UPDATE jobs SET status = :status, started_at = NOW() WHERE id = :job_id'),
            {'status': 'running', 'job_id': job_id}
        )
        conn.commit()
    
    ret = subprocess.run(cmd, shell=True, check=False)

    status = 'completed' if ret.returncode == 0 else 'failed'
    with db.connect() as conn:
        conn.execute(
            text('UPDATE jobs SET status = :status, ended_at = NOW() WHERE id = :job_id'),
            {'status': status, 'job_id': job_id}
        )
        conn.commit()
