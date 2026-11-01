import sys
import shutil
import argparse
from datetime import datetime
from os.path import abspath, dirname, isdir, join
import rq
from redis import Redis
from rq.exceptions import NoSuchJobError

sys.path.insert(0, dirname(dirname(abspath(__file__))))

from src.constant import REDIS_HOST, REDIS_PORT, USERS_DIR
from src.database import Database
from src.utils import to_valid_filename


SUPPORTED_TIME_FORMATS: tuple[str, ...] = (
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

COMPARISON_OPERATORS: dict[str, str] = {
    'before': '<',
    'at': '=',
    'after': '>',
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments.

    Args:
        argv: Optional list of argument strings. Defaults to sys.argv[1:].

    Returns:
        Parsed argument namespace.
    """
    parser = argparse.ArgumentParser(
        description='Delete completed, failed, or cancelled jobs for a user relative to a specified time point.'
    )
    parser.add_argument(
        '--user-email',
        type=str,
        required=True,
        help='Email address of the user whose jobs should be deleted.',
    )
    parser.add_argument(
        '--time-point',
        type=str,
        required=True,
        help=(
            'Cutoff timestamp (deletes jobs strictly before this time). '
            'Examples: "2026-11-01", "2026-11-01 14:30:00", "2026-11-01_14-30-00.000".'
        ),
    )
    parser.add_argument(
        '--when',
        type=str,
        choices=tuple(COMPARISON_OPERATORS.keys()),
        default='before',
        help='Delete jobs "before" (<), "at" (=), or "after" (>) --time-point (default: "before").',
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview matching jobs and directories without deleting anything.',
    )
    return parser.parse_args(argv)


def parse_time_point(time_point: str) -> str:
    """Parse a flexible date/time string into the job timestamp format.

    Args:
        time_point: Date or datetime string (hours:minutes:seconds optional).

    Returns:
        Normalized timestamp string formatted as ``YYYY-MM-DD_HH-MM-SS.mmm``.

    Raises:
        ValueError: If ``time_point`` does not match any supported format.
    """
    cleaned = time_point.strip()
    for fmt in SUPPORTED_TIME_FORMATS:
        try:
            dt = datetime.strptime(cleaned, fmt)
            return dt.strftime('%Y-%m-%d_%H-%M-%S.%f')[:-3]
        except ValueError:
            continue
    raise ValueError(
        f'Invalid --time-point "{time_point}". '
        'Expected YYYY-MM-DD with optional HH:MM:SS (e.g., "2026-11-01" or "2026-11-01 14:30:00").'
    )


def get_user_id(db: Database, email: str) -> int | None:
    """Look up a user ID by email address.

    Args:
        db: Database instance.
        email: User email address.

    Returns:
        The integer user ID if found, otherwise None.
    """
    ret = db.execute(
        '''
            SELECT id FROM users WHERE email = :email
        ''',
        {'email': email},
    )
    row = ret.fetchone()
    return int(row[0]) if row is not None else None


def fetch_jobs(
        db: Database,
        user_id: int,
        target_timestamp: str,
        when: str = 'before') -> list[tuple[int, str, str, str | None]]:
    """Fetch jobs for a user matching the temporal relation to ``target_timestamp``.

    Args:
        db: Database instance.
        user_id: User primary key ID.
        target_timestamp: Timestamp string in ``YYYY-MM-DD_HH-MM-SS.mmm`` format.
        when: Temporal relation, one of ``'before'``, ``'at'``, or ``'after'``.

    Returns:
        List of tuples ``(id, timestamp, status, rq_job_id)`` ordered by timestamp.

    Raises:
        ValueError: If ``when`` is not a valid comparison key.
    """
    if when not in COMPARISON_OPERATORS:
        raise ValueError(f'Unsupported comparison mode: {when}')
    op = COMPARISON_OPERATORS[when]
    ret = db.execute(
        f'''
            SELECT id, timestamp, status, rq_job_id
            FROM jobs
            WHERE user_id = :user_id AND timestamp {op} :target_timestamp
            ORDER BY timestamp
        ''',
        {'user_id': user_id, 'target_timestamp': target_timestamp},
    )
    return [
        (int(row[0]), str(row[1]), str(row[2]), row[3])
        for row in ret.fetchall()
    ]


def get_job_dirs(user_dirname: str, timestamp: str) -> list[str]:
    """Return existing filesystem directories associated with a job.

    Args:
        user_dirname: User directory name (``<user_id>_<sanitized_email>``).
        timestamp: Job timestamp identifier.

    Returns:
        List of existing directory paths (under ``jobs/`` and ``temp/``).
    """
    candidates = [
        join(USERS_DIR, user_dirname, 'jobs', timestamp),
        join(USERS_DIR, user_dirname, 'temp', timestamp),
    ]
    return [path for path in candidates if isdir(path)]


def delete_job_dirs(user_dirname: str, timestamp: str) -> list[str]:
    """Delete the output and temporary directories for a job if they exist.

    Args:
        user_dirname: User directory name (``<user_id>_<sanitized_email>``).
        timestamp: Job timestamp identifier.

    Returns:
        List of directory paths that were removed.
    """
    removed: list[str] = []
    for path in get_job_dirs(user_dirname, timestamp):
        shutil.rmtree(path)
        removed.append(path)
    return removed


def delete_rq_job(redis_conn: Redis, rq_job_id: str | None) -> bool:
    """Delete a Redis Queue job record if present.

    Args:
        redis_conn: Active Redis connection.
        rq_job_id: Redis Queue job ID, or None.

    Returns:
        True if the job was found and deleted in Redis, False otherwise.
    """
    if not rq_job_id:
        return False
    try:
        rq_job = rq.job.Job.fetch(id=rq_job_id, connection=redis_conn)
        rq_job.delete()
        return True
    except NoSuchJobError:
        return False


def delete_job_record(db: Database, job_id: int) -> None:
    """Delete a job row from the PostgreSQL ``jobs`` table.

    Args:
        db: Database instance.
        job_id: Primary key ID of the job in ``jobs``.
    """
    db.execute(
        '''
            DELETE FROM jobs WHERE id = :job_id
        ''',
        {'job_id': job_id},
    )


def main(argv: list[str] | None = None) -> None:
    """CLI entry point for deleting user jobs relative to a time point.

    Args:
        argv: Optional list of CLI arguments.
    """
    args = parse_args(argv)

    try:
        target_timestamp = parse_time_point(args.time_point)
    except ValueError as err:
        print(f'Error: {err}', file=sys.stderr)
        sys.exit(1)

    db = Database()
    user_id = get_user_id(db, args.user_email)
    if user_id is None:
        print(f'Error: User with email "{args.user_email}" not found.', file=sys.stderr)
        sys.exit(1)

    user_dirname = f'{user_id}_{to_valid_filename(args.user_email)}'
    jobs = fetch_jobs(db, user_id, target_timestamp, when=args.when)

    if not jobs:
        print(f'No jobs found for "{args.user_email}" {args.when} {target_timestamp}.')
        return

    active_jobs: list[tuple[int, str, str, str | None]] = []
    deletable_jobs: list[tuple[int, str, str, str | None]] = []

    for job in jobs:
        _, _, status, _ = job
        if status in ('waiting', 'running'):
            active_jobs.append(job)
        else:
            deletable_jobs.append(job)

    for job_id, timestamp, status, _ in active_jobs:
        print(f'Skipping active job {timestamp} (id={job_id}, status={status}).')

    if not deletable_jobs:
        print('No completed, failed, or cancelled jobs to delete.')
        return

    if args.dry_run:
        print(
            f'[DRY RUN] Would delete {len(deletable_jobs)} job(s) '
            f'for "{args.user_email}" {args.when} {target_timestamp}:'
        )
        for job_id, timestamp, status, rq_job_id in deletable_jobs:
            dirs = get_job_dirs(user_dirname, timestamp)
            dirs_str = ', '.join(dirs) if dirs else 'none on disk'
            print(f'  - Job {timestamp} (id={job_id}, status={status}, rq_job_id={rq_job_id}, dirs=[{dirs_str}])')
        return

    redis_conn = Redis(host=REDIS_HOST, port=REDIS_PORT)
    deleted_count = 0

    for job_id, timestamp, status, rq_job_id in deletable_jobs:
        removed_dirs = delete_job_dirs(user_dirname, timestamp)
        rq_deleted = delete_rq_job(redis_conn, rq_job_id)
        delete_job_record(db, job_id)
        deleted_count += 1
        dirs_str = ', '.join(removed_dirs) if removed_dirs else 'none'
        print(
            f'Deleted job {timestamp} '
            f'(id={job_id}, status={status}, rq_deleted={rq_deleted}, removed_dirs=[{dirs_str}]).'
        )

    print(f'Successfully deleted {deleted_count} job(s).')


if __name__ == '__main__':
    main()
