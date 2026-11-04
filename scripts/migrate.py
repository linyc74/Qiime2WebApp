import re
import sys
import argparse
from os import listdir
from sqlalchemy import text
from os.path import abspath, dirname, isfile, join

sys.path.insert(0, dirname(dirname(abspath(__file__))))

from src.database import Database


PROG = 'python scripts/migrate.py'
DESCRIPTION = 'Apply pending SQL files in the "migration/" directory in filename order.'
OPTIONAL = [
    {
        'keys': ['--dry-run'],
        'properties': {
            'action': 'store_true',
            'help': 'list pending migrations without applying them',
        }
    },
    {
        'keys': ['--baseline'],
        'properties': {
            'action': 'store_true',
            'help': 'record every current migration file as applied without executing it',
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
MIGRATION_TABLE_NAME = 'schema_migrations'


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
        Migrate().main(
            dry_run=args.dry_run,
            baseline=args.baseline)


class Migrate:

    MIGRATION_PATTERN = re.compile(r'^\d{3}_[a-z0-9_]+\.sql$')

    dry_run: bool
    baseline: bool

    db: Database
    directory: str
    versions: list[str]
    applied: set[str]
    pending: list[str]

    def main(
            self,
            dry_run: bool,
            baseline: bool):

        self.dry_run = dry_run
        self.baseline = baseline

        self.check_arguments()
        self.set_migration_dir()
        self.list_migration_files()

        if not self.versions:
            print(f'No migration files found in {self.directory}.')
            return

        self.db = Database()
        self.ensure_schema_migrations()
        self.fetch_applied()
        self.pending = [v for v in self.versions if v not in self.applied]

        if not self.pending:
            print('No pending migrations.')
            return

        if self.dry_run:
            self.print_pending()
        elif self.baseline:
            self.baseline_migrations()
        else:
            self.apply_migrations()

    def check_arguments(self):
        if self.dry_run and self.baseline:
            raise ValueError('--dry-run and --baseline cannot be used together.')

    def set_migration_dir(self):
        """
        The relative path of migrate.py and SQL files:

        .
        ├── migration/
        │   ├── 001_create_users_and_jobs.sql
        │   └── 002_some_migration.sql
        └── scripts/
            └── migrate.py
        """
        self.directory = join(dirname(dirname(abspath(__file__))), 'migration')

    def list_migration_files(self):
        self.versions = sorted(
            name for name in listdir(self.directory)
            if name.endswith('.sql') and isfile(join(self.directory, name))
        )
        for name in self.versions:
            if self.MIGRATION_PATTERN.fullmatch(name) is None:
                raise ValueError(
                    f'Invalid migration filename "{name}". '
                    'Expected a name like 001_create_users_and_jobs.sql.'
                )

    def ensure_schema_migrations(self):
        self.db.execute(
            f'''
                CREATE TABLE IF NOT EXISTS {MIGRATION_TABLE_NAME} (
                    version character varying(255) PRIMARY KEY,
                    applied_at timestamp with time zone NOT NULL DEFAULT now()
                )
            ''',
            {},
        )

    def fetch_applied(self):
        ret = self.db.execute(
            f'''
                SELECT version FROM {MIGRATION_TABLE_NAME}
            ''',
            {},
        )
        self.applied = {str(row[0]) for row in ret.fetchall()}

    def print_pending(self):
        print(f'{len(self.pending)} pending migration(s):')
        for version in self.pending:
            print(f'  - {version}')

    def baseline_migrations(self):
        for version in self.pending:
            self.db.execute(
                f'''
                    INSERT INTO {MIGRATION_TABLE_NAME} (version)
                    VALUES (:version)
                    ON CONFLICT (version) DO NOTHING
                ''',
                {'version': version},
            )
            print(f'Baselined {version}.')

    def apply_migrations(self):
        for version in self.pending:
            self.apply_one(version=version)
            print(f'Applied {version}.')

    def apply_one(self, version: str):
        path = join(self.directory, version)
        with open(path, encoding='utf-8') as f:
            sql = f.read()

        with self.db.engine.begin() as conn:
            conn.exec_driver_sql(sql)
            conn.execute(
                text(
                    f'''
                        INSERT INTO {MIGRATION_TABLE_NAME} (version)
                        VALUES (:version)
                    '''
                ),
                {'version': version},
            )


if __name__ == '__main__':
    EntryPoint().main()
