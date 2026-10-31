import os
import rq
import time
import subprocess
from redis import Redis
from os.path import join
from datetime import datetime
from .database import Database


REDIS_HOST = 'localhost'
REDIS_PORT = 6379
REDIS_QUEUE = 'qiime2_web_app'  # start the redis queue worker in another terminal: `rq worker -w rq.worker.SpawnWorker qiime2_web_app`

QIIME2_PIPELINE = 'qiime2_pipeline-2.12.0'
QIIME2_CONDA_ENV = 'qiime2-amplicon-2024.2'
FASTQ_DIR = './data/fastq'
RESOURCE_DIR = './data/resource'
JOB_DIR = './data/jobs'


class JobInput:

    def __init__(
            self,
            user_id: int,
            user_dirname: str,
            sample_sheet_name: str,
            sample_sheet_content: str,
            parameters: dict):
        """
        Construct everything needed to submit a job.
        """

        self.user_id = user_id
        self.user_dirname = user_dirname
        self.sample_sheet_name = sample_sheet_name
        self.sample_sheet_content = sample_sheet_content
        self.parameters = parameters

        self.timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S.%f')[:-3]  # down to milliseconds
        self.outdir = join(JOB_DIR, self.user_dirname, self.timestamp, self.parameters['output'])

        self.build_cmd()

    def build_cmd(self):
        lines = [
            f'python {QIIME2_PIPELINE}',
            f'--fq-dir="{join(FASTQ_DIR, self.user_dirname)}"',
            f'--sample-sheet="{join(self.outdir, self.sample_sheet_name)}"',
        ]

        for key, value in self.parameters.items():

            if isinstance(value, bool):
                lines.append(f'--{key}')

            elif key == 'output':
                lines.append(f'--outdir="{self.outdir}"')                
            
            elif key in ['nb-classifier-qza', 'reference-sequence-qza', 'reference-taxonomy-qza']:
                lines.append(f'--{key}="{join(RESOURCE_DIR, value)}"')

            else:
                lines.append(f'--{key}="{value}"')
                
        lines.append(f'> "{join(self.outdir, "progress.txt")}" 2>&1')

        self.cmd = ' \\\n  '.join(lines)


class Worker:

    def __init__(self):
        self.db = Database()
        self.redis = Redis(host=REDIS_HOST, port=REDIS_PORT)
        self.queue = rq.Queue(name=REDIS_QUEUE, connection=self.redis)

    def submit_job(self, job_input: JobInput):
        j = job_input

        # create job record in database
        ret = self.db.execute(
            '''
                INSERT INTO jobs (user_id, timestamp, status)
                VALUES (:user_id, :timestamp, :status)
                RETURNING id
            ''',
            {'user_id': j.user_id, 'timestamp': j.timestamp, 'status': 'waiting'}
        )
        job_id = ret.scalar_one()

        # create output directory and write sample sheet
        os.makedirs(j.outdir, exist_ok=True)
        with open(join(j.outdir, j.sample_sheet_name), 'w') as f:
            f.write(j.sample_sheet_content)

        # enqueue job
        rq_job = self.queue.enqueue(
            run_command,
            job_id,
            j.cmd,
            job_timeout='24h',
        )

        # update database with Redis job ID
        self.db.execute(
            '''
                UPDATE jobs SET rq_job_id = :rq_job_id WHERE id = :job_id
            ''',
            {'rq_job_id': rq_job.id, 'job_id': job_id}
        )
    
    def cancel_job(self, job_id: int):
        # get rq_job_id, status from database
        ret = self.db.execute(
            '''
                SELECT rq_job_id, status FROM jobs WHERE id = :job_id
            ''',
            {'job_id': job_id}
        )
        rq_job_id, status = ret.fetchone()

        if status in['completed', 'failed', 'cancelled']:  # do nothing
            print(f'Job {job_id} ({rq_job_id}) is already {status}.')

        elif status == 'waiting':  # cancel job if it was waiting, i.e. no started_at yet
            rq_job = rq.job.Job.fetch(id=rq_job_id, connection=self.redis)
            rq_job.cancel()
            self.db.execute(
                '''
                    UPDATE jobs SET status = 'cancelled' WHERE id = :job_id
                ''',
                {'job_id': job_id}
            )

        else:  # job was running, i.e. that has started_at but no ended_at, add ended_at
            rq.command.send_stop_job_command(job_id=rq_job_id, connection=self.redis)
            self.db.execute(
                '''
                    UPDATE jobs SET status = 'cancelled', ended_at = NOW() WHERE id = :job_id
                ''',
                {'job_id': job_id}
            )


def run_command(job_id: int, cmd: str):
    db = Database()

    db.execute(
        '''
            UPDATE jobs SET status = :status, started_at = NOW() WHERE id = :job_id
        ''',
        {'status': 'running', 'job_id': job_id}
    )

    full_cmds = [
        f'eval "$(conda shell.bash hook)"',
        f'conda activate {QIIME2_CONDA_ENV}',
        'export QT_QPA_PLATFORM=offscreen',
        'export UNIFRAC_USE_GPU=N',
        cmd,
    ]

    ret = subprocess.run(' && '.join(full_cmds), shell=True, executable='/bin/bash', check=False)

    status = 'completed' if ret.returncode == 0 else 'failed'
    db.execute(
        '''
            UPDATE jobs SET status = :status, ended_at = NOW() WHERE id = :job_id
        ''',
        {'status': status, 'job_id': job_id}
    )
