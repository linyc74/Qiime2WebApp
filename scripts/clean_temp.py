import os
import sys
import shutil
import argparse
from os import listdir
from os.path import abspath, dirname, isdir, islink, join

sys.path.insert(0, dirname(dirname(abspath(__file__))))

from src.database import Database
from src.constant import USERS_DIR
from src.utils import to_valid_filename


PROG = 'python scripts/clean_temp.py'
DESCRIPTION = 'Purge temporary files and directories in user temp/ directories while skipping active jobs.'
OPTIONAL = [
    {
        'keys': ['--user-email'],
        'properties': {
            'type': str,
            'required': False,
            'default': None,
            'help': 'email address of a specific user to clean (default: all users)',
        }
    },
    {
        'keys': ['--dry-run'],
        'properties': {
            'action': 'store_true',
            'help': 'preview temporary paths that would be deleted without removing anything',
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
        self.add_optional_arguments()
        self.run()

    def set_parser(self):
        self.parser = argparse.ArgumentParser(
            prog=PROG,
            description=DESCRIPTION,
            add_help=False,
            formatter_class=argparse.RawTextHelpFormatter)

    def add_optional_arguments(self):
        group = self.parser.add_argument_group('optional arguments')
        for item in OPTIONAL:
            group.add_argument(*item['keys'], **item['properties'])

    def run(self):
        args = self.parser.parse_args()
        CleanTemp().main(
            user_email=args.user_email,
            dry_run=args.dry_run)


class CleanTemp:

    user_email: str | None
    dry_run: bool

    db: Database
    users: list[tuple[int, str, str]]
    active_jobs_by_user: dict[int, dict[str, tuple[int, str]]]
    skipped_items: list[tuple[str, str, int, str]]
    deletable_paths: list[str]

    def main(
            self,
            user_email: str | None,
            dry_run: bool):

        self.user_email = user_email
        self.dry_run = dry_run

        self.db = Database()
        self.fetch_users()

        if not self.users:
            print('No users found in the database.')
            return

        self.fetch_active_jobs()
        self.collect_temp_entries()
        self.print_skipped_items()

        if not self.deletable_paths:
            print('No temporary files or directories to clean.')
            return

        if self.dry_run:
            self.print_dry_run()
        else:
            self.delete_temp_entries()

    def fetch_users(self):
        if self.user_email is not None:
            ret = self.db.execute(
                '''
                    SELECT id, email FROM users WHERE email = :email
                ''',
                {'email': self.user_email},
            )
            row = ret.fetchone()
            if row is None:
                raise ValueError(f'User with email "{self.user_email}" not found.')
            user_id = int(row[0])
            email = str(row[1])
            self.users = [(user_id, email, f'{user_id}_{to_valid_filename(email)}')]
            return

        ret = self.db.execute(
            '''
                SELECT id, email FROM users ORDER BY id
            ''',
            {},
        )
        self.users = [
            (int(row[0]), str(row[1]), f'{int(row[0])}_{to_valid_filename(str(row[1]))}')
            for row in ret.fetchall()
        ]

    def fetch_active_jobs(self):
        self.active_jobs_by_user = {}
        for user_id, _, _ in self.users:
            ret = self.db.execute(
                '''
                    SELECT id, timestamp, status
                    FROM jobs
                    WHERE user_id = :user_id AND status IN ('waiting', 'running')
                    ORDER BY timestamp
                ''',
                {'user_id': user_id},
            )
            self.active_jobs_by_user[user_id] = {
                str(row[1]): (int(row[0]), str(row[2]))
                for row in ret.fetchall()
            }

    def collect_temp_entries(self):
        self.skipped_items = []
        self.deletable_paths = []

        for user_id, email, user_dirname in self.users:
            temp_dir = join(USERS_DIR, user_dirname, 'temp')
            if not isdir(temp_dir):
                continue

            active_map = self.active_jobs_by_user.get(user_id, {})
            for name in sorted(listdir(temp_dir)):
                path = join(temp_dir, name)
                if name in active_map:
                    job_id, status = active_map[name]
                    self.skipped_items.append((email, path, job_id, status))
                else:
                    self.deletable_paths.append(path)

    def print_skipped_items(self):
        for email, path, job_id, status in self.skipped_items:
            print(f'Skipping active job temp entry {path} (user="{email}", id={job_id}, status={status}).')

    def print_dry_run(self):
        print(f'[DRY RUN] Would delete {len(self.deletable_paths)} temporary entry/entries:')
        for path in self.deletable_paths:
            print(f'  - {path}')

    def delete_temp_entries(self):
        for path in self.deletable_paths:
            self.remove_path(path=path)
            print(f'Deleted {path}.')
        print(f'Successfully deleted {len(self.deletable_paths)} temporary entry/entries.')

    def remove_path(self, path: str):
        if isdir(path) and not islink(path):
            shutil.rmtree(path)
        else:
            os.remove(path)


if __name__ == '__main__':
    EntryPoint().main()
