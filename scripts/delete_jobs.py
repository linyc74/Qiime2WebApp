import rq
import sys
import shutil
import argparse
from redis import Redis
from datetime import datetime
from rq.exceptions import NoSuchJobError
from os.path import abspath, dirname, isdir, join

sys.path.insert(0, dirname(dirname(abspath(__file__))))

from src.database import Database
from src.utils import to_valid_filename
from src.constant import REDIS_HOST, REDIS_PORT, USERS_DIR


PROG = 'python scripts/delete_jobs.py'
DESCRIPTION = 'Delete completed, failed, or cancelled jobs for a user relative to a specified time point.'
REQUIRED = [
    {
        'keys': ['--user-email'],
        'properties': {
            'type': str,
            'required': True,
            'help': 'email address of the user whose jobs should be deleted',
        }
    },
    {
        'keys': ['--time-point'],
        'properties': {
            'type': str,
            'required': True,
            'help': (
                'cutoff timestamp, e.g. "2026-11-01", "2026-11-01 14:30:00", '
                'or "2026-11-01_14-30-00.000"'
            ),
        }
    },
]
OPTIONAL = [
    {
        'keys': ['--when'],
        'properties': {
            'type': str,
            'required': False,
            'default': 'before',
            'choices': ['before', 'at', 'after'],
            'help': 'delete jobs "before" (<), "at" (=), or "after" (>) --time-point (default: %(default)s)',
        }
    },
    {
        'keys': ['--dry-run'],
        'properties': {
            'action': 'store_true',
            'help': 'preview matching jobs and directories without deleting anything',
        }
    },
    {
        'keys': ['-h', '--help'],
        'properties': {
            'action': 'help',
            'help': 'show this help message',
        }
    },
]


class EntryPoint:

    parser: argparse.ArgumentParser

    def main(self):
        self.set_parser()
        self.add_required_arguments()
        self.add_optional_arguments()
        self.run()

    def set_parser(self):
        self.parser = argparse.ArgumentParser(
            prog=PROG,
            description=DESCRIPTION,
            add_help=False,
            formatter_class=argparse.RawTextHelpFormatter)

    def add_required_arguments(self):
        group = self.parser.add_argument_group('required arguments')
        for item in REQUIRED:
            group.add_argument(*item['keys'], **item['properties'])

    def add_optional_arguments(self):
        group = self.parser.add_argument_group('optional arguments')
        for item in OPTIONAL:
            group.add_argument(*item['keys'], **item['properties'])

    def run(self):
        args = self.parser.parse_args()
        DeleteJobs().main(
            user_email=args.user_email,
            time_point=args.time_point,
            when=args.when,
            dry_run=args.dry_run)


class DeleteJobs:

    SUPPORTED_TIME_FORMATS = (
        '%Y-%m-%d',
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%dT%H:%M:%S',
        '%Y-%m-%d_%H-%M-%S',
        '%Y-%m-%d_%H:%M:%S',
        '%Y-%m-%d %H:%M:%S.%f',
        '%Y-%m-%dT%H:%M:%S.%f',
        '%Y-%m-%d_%H-%M-%S.%f',
        '%Y-%m-%d_%H:%M:%S.%f',
    )
    COMPARISON_OPERATORS = {
        'before': '<',
        'at': '=',
        'after': '>',
    }

    user_email: str
    time_point: str
    when: str
    dry_run: bool

    db: Database
    redis: Redis
    target_timestamp: str
    user_id: int
    user_dirname: str
    jobs: list[tuple[int, str, str, str | None]]
    active_jobs: list[tuple[int, str, str, str | None]]
    deletable_jobs: list[tuple[int, str, str, str | None]]

    def main(
            self,
            user_email: str,
            time_point: str,
            when: str,
            dry_run: bool):

        self.user_email = user_email
        self.time_point = time_point
        self.when = when
        self.dry_run = dry_run

        self.parse_time_point()

        self.db = Database()
        self.set_user()
        self.fetch_jobs()

        if not self.jobs:
            print(f'No jobs found for "{self.user_email}" {self.when} {self.target_timestamp}.')
            return

        self.partition_jobs()
        self.print_active_jobs()

        if not self.deletable_jobs:
            print('No completed, failed, or cancelled jobs to delete.')
            return

        if self.dry_run:
            self.print_dry_run()
        else:
            self.delete_jobs()

    def parse_time_point(self):
        cleaned = self.time_point.strip()
        for fmt in self.SUPPORTED_TIME_FORMATS:
            try:
                dt = datetime.strptime(cleaned, fmt)
                self.target_timestamp = dt.strftime('%Y-%m-%d_%H-%M-%S.%f')[:-3]
                return
            except ValueError:
                continue
        raise ValueError(
            f'Invalid --time-point "{self.time_point}". '
            'Expected YYYY-MM-DD with optional HH:MM:SS (e.g., "2026-11-01" or "2026-11-01 14:30:00").'
        )

    def set_user(self):
        ret = self.db.execute(
            '''
                SELECT id FROM users WHERE email = :email
            ''',
            {'email': self.user_email},
        )
        row = ret.fetchone()
        if row is None:
            raise ValueError(f'User with email "{self.user_email}" not found.')
        self.user_id = int(row[0])
        self.user_dirname = f'{self.user_id}_{to_valid_filename(self.user_email)}'

    def fetch_jobs(self):
        op = self.COMPARISON_OPERATORS[self.when]
        ret = self.db.execute(
            f'''
                SELECT id, timestamp, status, rq_job_id
                FROM jobs
                WHERE user_id = :user_id AND timestamp {op} :target_timestamp
                ORDER BY timestamp
            ''',
            {'user_id': self.user_id, 'target_timestamp': self.target_timestamp},
        )
        self.jobs = [
            (int(row[0]), str(row[1]), str(row[2]), row[3])
            for row in ret.fetchall()
        ]

    def partition_jobs(self):
        self.active_jobs = []
        self.deletable_jobs = []
        for job in self.jobs:
            _, _, status, _ = job
            if status in ('waiting', 'running'):
                self.active_jobs.append(job)
            else:
                self.deletable_jobs.append(job)

    def print_active_jobs(self):
        for job_id, timestamp, status, _ in self.active_jobs:
            print(f'Skipping active job {timestamp} (id={job_id}, status={status}).')

    def print_dry_run(self):
        print(
            f'[DRY RUN] Would delete {len(self.deletable_jobs)} job(s) '
            f'for "{self.user_email}" {self.when} {self.target_timestamp}:'
        )
        for job_id, timestamp, status, rq_job_id in self.deletable_jobs:
            dirs = self.get_job_dirs(timestamp=timestamp)
            dirs_str = ', '.join(dirs) if dirs else 'none on disk'
            print(f'  - Job {timestamp} (id={job_id}, status={status}, rq_job_id={rq_job_id}, dirs=[{dirs_str}])')

    def delete_jobs(self):
        self.redis = Redis(host=REDIS_HOST, port=REDIS_PORT)
        for job_id, timestamp, status, rq_job_id in self.deletable_jobs:
            removed_dirs = self.delete_job_dirs(timestamp=timestamp)
            rq_deleted = self.delete_rq_job(rq_job_id=rq_job_id)
            self.delete_job_record(job_id=job_id)
            dirs_str = ', '.join(removed_dirs) if removed_dirs else 'none'
            print(
                f'Deleted job {timestamp} '
                f'(id={job_id}, status={status}, rq_deleted={rq_deleted}, removed_dirs=[{dirs_str}]).'
            )
        print(f'Successfully deleted {len(self.deletable_jobs)} job(s).')

    def get_job_dirs(self, timestamp: str) -> list[str]:
        candidates = [
            join(USERS_DIR, self.user_dirname, 'jobs', timestamp),
            join(USERS_DIR, self.user_dirname, 'temp', timestamp),
        ]
        return [path for path in candidates if isdir(path)]

    def delete_job_dirs(self, timestamp: str) -> list[str]:
        removed: list[str] = []
        for path in self.get_job_dirs(timestamp=timestamp):
            shutil.rmtree(path)
            removed.append(path)
        return removed

    def delete_rq_job(self, rq_job_id: str | None) -> bool:
        if not rq_job_id:
            return False
        try:
            rq_job = rq.job.Job.fetch(id=rq_job_id, connection=self.redis)
            rq_job.delete()
            return True
        except NoSuchJobError:
            return False

    def delete_job_record(self, job_id: int):
        self.db.execute(
            '''
                DELETE FROM jobs WHERE id = :job_id
            ''',
            {'job_id': job_id},
        )


if __name__ == '__main__':
    EntryPoint().main()
