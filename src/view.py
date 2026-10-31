import os
import re
import csv
import hashlib
from nicegui import ui
from io import StringIO
from pathlib import Path
from os.path import join
from typing import Callable
from urllib.parse import urlencode
from datetime import datetime, timezone, timedelta
from .database import Database
from .job import Worker, JobInput
from .constant import VERSION, USERS_DIR


ILLUMINA_KEY_TO_OPTIONS = {
    'fq1-suffix': ['_R1.fastq.gz'],
    'fq2-suffix': ['_R2.fastq.gz'],
    'output': ['output'],
    'feature-classifier': ['nb', 'vsearch'],
    'nb-classifier-qza': ['silva-138-99-nb-classifier.qza'],
    'reference-sequence-qza': ['silva-138-99-seqs.qza'],
    'reference-taxonomy-qza': ['silva-138-99-tax.qza'],
    'vsearch-classifier-max-hits': ['10'],
    'threads': ['1', '4', '8'],
    'paired-end-mode': ['merge', 'pool'],
    'skip-otu': False,
    'otu-identity': ['0.97'],
    'dna-concentration-column': ['None'],
    'decontam-threshold': ['0.1'],
    'clip-r1-5-prime': ['17'],
    'clip-r2-5-prime': ['20'],
    'classifier-reads-per-batch': ['1000'],
    'max-expected-error-bases': ['8.0'],
    'alpha-metrics': ['all'],
    'beta-diversity-feature-level': [
        'feature',
        'species',
        'genus',
        'family',
        'order',
        'class',
        'phylum',
    ],
    'heatmap-read-fraction': ['0.95'],
    'n-taxa-barplot': ['20'],
    'colormap': [
        'Set1',
        'Set2',
        'Set3',
        'tab10',
        'tab20',
        'tab20b',
        'tab20c',
        'Pastel1',
        'Pastel2',
        'Paired',
        'Accent',
        'Dark2',
    ],
    'invert-colors': False,
    'publication-figure': False,
    'skip-differential-abundance': False,
    'differential-abundance-p-value': ['0.05'],
    'min-abundance-per-group': ['0.0']
}
PACBIO_KEY_TO_OPTIONS = {
    'fq1-suffix': ['.fastq.gz'],
    'output': ['output'],
    'feature-classifier': ['nb', 'vsearch'],
    'nb-classifier-qza': ['silva-138-99-nb-classifier.qza'],
    'reference-sequence-qza': ['silva-138-99-seqs.qza'],
    'reference-taxonomy-qza': ['silva-138-99-tax.qza'],
    'vsearch-classifier-max-hits': ['10'],
    'threads': ['1', '4', '8'],
    'skip-otu': False,
    'otu-identity': ['0.97'],
    'dna-concentration-column': ['None'],
    'decontam-threshold': ['0.1'],
    'classifier-reads-per-batch': ['1000'],
    'max-expected-error-bases': ['8.0'],
    'alpha-metrics': ['all'],
    'beta-diversity-feature-level': [
        'feature',
        'species',
        'genus',
        'family',
        'order',
        'class',
        'phylum',
    ],
    'heatmap-read-fraction': ['0.95'],
    'n-taxa-barplot': ['20'],
    'colormap': [
        'Set1',
        'Set2',
        'Set3',
        'tab10',
        'tab20',
        'tab20b',
        'tab20c',
        'Pastel1',
        'Pastel2',
        'Paired',
        'Accent',
        'Dark2',
    ],
    'invert-colors': False,
    'publication-figure': False,
    'skip-differential-abundance': False,
    'differential-abundance-p-value': ['0.05'],
    'min-abundance-per-group': ['0.0']
}
MODES = {
    'illumina': ILLUMINA_KEY_TO_OPTIONS,
    'pacbio': PACBIO_KEY_TO_OPTIONS
}


class PipelinePage:

    def __init__(self, user_id: int, on_logout: Callable | None = None):
        self.input = UserInput(user_id=user_id)
        self.worker = Worker()

        self.controls = {}
        self.dashboard = Dashboard(user_input=self.input, worker=self.worker)
        self.fastq_dialog = FastqDialog(user_input=self.input)

        ui.colors(primary='#12329A', secondary='#25636b')

        with ui.column().classes('w-full max-w-4xl mx-auto p-4 sm:p-8 gap-6'):

            with ui.row().classes('w-full items-center justify-between'):
                with ui.row().classes('items-baseline gap-2'):
                    ui.label('QIIME 2 App').classes('text-3xl font-semibold')
                    ui.label(VERSION).classes('text-sm text-slate-400')
                with ui.row().classes('gap-3'):
                    ui.button('Dashboard', icon='table_chart', on_click=self.dashboard.show).props('outline')
                    ui.button('Log out', icon='logout', on_click=on_logout).props('outline')
            
            ui.label(self.input.email).classes('text-sm text-slate-500')

            ui.toggle(
                {'illumina': 'Illumina Mode', 'pacbio': 'PacBio Mode'},
                value=self.input.mode,
                on_change=self.change_mode
            )

            self.form = ui.column().classes('w-full gap-4')
            self.render_form()

            with ui.row().classes('w-full gap-3 justify-end'):
                with ui.element('div'):
                    self.submit_button = ui.button('Submit', icon='send', on_click=self.submit)
                    self.submit_button.disable()
                    self.submit_tooltip = ui.tooltip('Please upload sample sheet.').classes('text-sm')

    def change_mode(self, event):
        self.input.mode = event.value
        self.render_form()

    def render_form(self):
        self.form.clear()
        self.controls = {}  # refresh UI controls

        with self.form:

            ui.button('FASTQ Files', icon='upload_file', on_click=self.fastq_dialog.show)

            ui.button('Upload Sample Sheet', icon='upload_file', on_click=self.sample_sheet_dialog)
            if self.input.sample_sheet_name:  # show sample sheet name if uploaded
                ui.label(self.input.sample_sheet_name).classes('text-sm text-slate-500')
                self.submit_button.enable()
                self.submit_tooltip.set_visibility(False)
            
            with ui.row().classes('w-full gap-3 justify-start'):
                ui.button('Load Parameters', icon='upload_file', on_click=self.load_parameter_dialog)
                ui.button('Save Parameters', icon='download', on_click=self.save_parameter_dialog)

            for key, options in MODES[self.input.mode].items():  # follow items and data types in the presets
                if isinstance(options, bool):
                    control = ui.checkbox(key).bind_value(self.input.values, key)  # use self.values to fill in
                else:
                    choices = list(options)  # create a new list
                    if self.input.values[key] not in choices:
                        choices.append(self.input.values[key])  # append to the new list if not present
                    control = ui.select(choices, label=key, new_value_mode='add-unique')  # create a select control, similar to ComboBox in PyQt5

                    # this is the most important line
                    # it couples the control with the data model (UserInput.values)
                    control.bind_value(self.input.values, key).props('outlined').classes('w-full')
                
                self.controls[key] = control

    def sample_sheet_dialog(self):
        with self.form.client, ui.dialog() as dialog, ui.card().classes('w-full max-w-lg'):
            ui.label('Upload Sample Sheet').classes('text-xl font-semibold')

            async def upload(event):
                if event.file.size() > 10_000_000:
                    ui.notify('Choose a sample sheet smaller than 10 MB.', type='negative')
                    return

                content = await event.file.text()

                self.input.sample_sheet_name = event.file.name
                self.input.sample_sheet_content = content

                self.render_form()  # refresh UI controls

                dialog.close()
                ui.notify('Sample sheet uploaded.', type='positive')

            ui.upload(
                label='Choose sample sheet',
                auto_upload=True,
                on_upload=upload,
                max_file_size=10_000_000,
                on_rejected=lambda: ui.notify('Choose a sample sheet smaller than 10 MB.', type='negative')
            ).classes('w-full')
            
            with ui.row().classes('w-full justify-end'):
                ui.button('Close', on_click=dialog.close).props('flat')
        
        dialog.open()

    def load_parameter_dialog(self):
        with self.form.client, ui.dialog() as dialog, ui.card().classes('w-full max-w-lg'):
            ui.label('Load Parameters').classes('text-xl font-semibold')

            async def load(event):
                try:
                    if event.file.size() > 1_000_000:
                        raise ValueError('Choose a parameter file smaller than 1 MB.')
                    self.input.load_parameters(name=event.file.name, text=await event.file.text())
                    self.render_form()
                    dialog.close()
                    ui.notify('Parameters loaded.', type='positive')
                except Exception as error:
                    ui.notify(f'Error loading parameters: {error}', type='negative')

            ui.upload(
                label='Choose parameter file',
                auto_upload=True,
                on_upload=load,
                max_file_size=1_000_000,
                on_rejected=lambda: ui.notify('Choose a parameter file smaller than 1 MB.', type='negative')
            ).props(
                'accept=".csv,.tsv,.tab,.txt"'
            ).classes(
                'w-full'
            )
            
            with ui.row().classes('w-full justify-end'):
                ui.button('Close', on_click=dialog.close).props('flat')
        
        dialog.open()

    def save_parameter_dialog(self):
        with self.form.client, ui.dialog() as dialog, ui.card().classes('w-full max-w-lg'):
            ui.label('Save Parameters').classes('text-xl font-semibold')
            file_format = ui.select(['.csv', '.tsv', '.tab', '.txt'], value='.csv', label='Format')

            def download():
                suffix = file_format.value
                ui.download(write_parameters(self.input.values, suffix), f'{self.input.mode}-parameters{suffix}')
                dialog.close()

            with ui.row():
                ui.button('Download', on_click=download)
                ui.button('Cancel', on_click=dialog.close).props('flat')

        dialog.open()

    def submit(self):
        if self.input.sample_sheet_name == '':
            ui.notify('Please upload a sample sheet.', type='negative')
            return
        
        job_input = self.input.create_job()
        self.worker.submit_job(job_input=job_input)

        ui.notify(f'Submitted job [{job_input.timestamp}].', type='positive')


class UserInput:
    """
    Current state (data model) for the user input, dynamically updated by the UI.
    """

    def __init__(self, user_id: int):
        self.user_id = user_id
        self.mode = 'illumina'
        self.db = Database()
        self.set_email()
        self.user_dirname = f'{self.user_id}_{to_valid_filename(self.email)}'  # user-specific directory name to store data
        self.sample_sheet_name = ''
        self.sample_sheet_content = ''

        self.values = {}  # dynamically updated by UI controls
        for key, options in MODES[self.mode].items():
            if isinstance(options, list):
                self.values[key] = options[0]
            else:
                self.values[key] = options

    def set_email(self):
        ret = self.db.execute(
            '''
                SELECT email FROM users WHERE id = :user_id
            ''',
            {'user_id': self.user_id}
        )
        self.email = ret.scalar_one()

    def get_output_dirname(self, job_timestamp: str) -> str:
        dirs = get_dirs(
            source=f'{USERS_DIR}/{self.user_dirname}/jobs/{job_timestamp}',
            isfullpath=False)

        if len(dirs) == 0:
            return '(not found)'

        return dirs[0]

    def load_parameters(self, name: str, text: str):
        parameters = read_parameters(name, text)
        updates = {}
        for key, default in MODES[self.mode].items():
            if isinstance(default, bool):
                value = parameters.get(key, False)
                if isinstance(value, str):
                    if value.lower() not in ('true', 'false'):
                        raise ValueError(f'{key} must be a flag, true, or false.')
                    value = value.lower() == 'true'
                updates[key] = value
            elif key in parameters:
                if not isinstance(parameters[key], str):
                    raise ValueError(f'{key} requires a value.')
                updates[key] = parameters[key]
        self.values.update(updates)

    def create_job(self) -> JobInput:
        return JobInput(
            user_id=self.user_id,
            user_dirname=self.user_dirname,
            sample_sheet_name=self.sample_sheet_name,
            sample_sheet_content=self.sample_sheet_content,
            parameters=self.values)


class Dashboard:

    def __init__(self, user_input: UserInput, worker: Worker):
        self.user_input = user_input
        self.worker = worker
        self.db = Database()
        self.table: ui.table | None = None

    def show(self):
        with ui.dialog() as dialog, ui.card().classes('w-full max-w-3xl'):
            ui.label('Dashboard').classes('text-xl font-semibold')

            self.table = ui.table(columns=[
                {'name': 'id',      'label': 'Job ID',       'field': 'id',      'align': 'left'},
                {'name': 'output',  'label': 'Output',       'field': 'output',  'align': 'left'},
                {'name': 'start',   'label': 'Start Time',   'field': 'start',   'align': 'left'},
                {'name': 'elapsed', 'label': 'Elapsed Time', 'field': 'elapsed', 'align': 'left'},
                {'name': 'status',  'label': 'Status',       'field': 'status',  'align': 'left'},
            ], rows=[], row_key='id', selection='multiple').classes('w-full')

            with ui.row().classes('w-full justify-end'):
                ui.button('Update', icon='refresh', on_click=self.update)
                ui.button('Cancel Jobs', icon='stop', color='negative', on_click=self.cancel_jobs)
                ui.button('Download', icon='download', on_click=self.download)
                ui.button('Close', on_click=dialog.close).props('flat')

        self.update()
        dialog.open()

    def update(self):
        ret = self.db.execute(
            '''
                SELECT timestamp, started_at, ended_at, status FROM jobs WHERE user_id = :user_id ORDER BY timestamp
            ''',
            {'user_id': self.user_input.user_id}
        )
        jobs: list[tuple] = ret.fetchall()
        rows: list[dict] = []
        for job in jobs:
            timestamp, started_at, ended_at, status = job

            output = self.user_input.get_output_dirname(timestamp)

            if status == 'waiting':
                elapsed = None
            elif status == 'running':
                elapsed = datetime.now(timezone.utc) - started_at
            elif status in ['completed', 'failed', 'cancelled']:
                if started_at is None or ended_at is None:
                    elapsed = None
                else:
                    elapsed = ended_at - started_at
            else:
                raise ValueError(f'Invalid status: {status}')

            if isinstance(started_at, datetime):
                started_at = started_at.strftime('%Y-%m-%d %H:%M:%S')

            if isinstance(elapsed, timedelta):
                elapsed = format_timedelta(elapsed)

            rows.append({
                'id': timestamp,
                'output': output,
                'start': started_at,
                'elapsed': elapsed,
                'status': status,
            })

        if self.table is not None:
            self.table.update_rows(rows)

    def download(self):
        if self.table is None or len(self.table.selected) == 0:
            ui.notify('Please select at least one job.', type='negative')
            return

        query = urlencode([('job_ids', row['id']) for row in self.table.selected])
        url = f'/download-jobs?{query}'  # example: /download-jobs?job_ids=2026-10-29_14-08-17.257&job_ids=2026-10-29_14-12-05.521
        ui.download(url, 'jobs.zip')
    
    def cancel_jobs(self):
        if self.table is None or len(self.table.selected) == 0:
            ui.notify('Please select jobs to cancel.', type='negative')
            return

        for row in self.table.selected:
            timestamp = row['id']

            ret = self.db.execute(
                '''
                    SELECT id FROM jobs WHERE timestamp = :timestamp
                ''',
                {'timestamp': timestamp}
            )
            job_id = ret.scalar_one()

            try:
                self.worker.cancel_job(job_id)
            except Exception as error:
                ui.notify(f'Error canceling job: {error}', type='negative')
                continue
            
        self.update()


class FastqDialog:

    def __init__(self, user_input: UserInput):
        self.user_input = user_input
        self.user_fastq_dir = f'{USERS_DIR}/{self.user_input.user_dirname}/fastq'
        self.table: ui.table | None = None

    def show(self):
        with ui.dialog() as dialog, ui.card().classes('w-full max-w-3xl'):
            ui.label('FASTQ Files').classes('text-xl font-semibold')

            with ui.row().classes('w-full justify-end'):
                ui.button('Upload', icon='upload_file', on_click=self.show_upload_dialog)
                ui.button('Delete', icon='delete', color='negative', on_click=self.delete)
                ui.button('Close', on_click=dialog.close).props('flat')

            self.table = ui.table(
                columns=[
                    {'name': 'name',     'label': 'File',          'field': 'name',     'align': 'left'},
                    {'name': 'size',     'label': 'Size',          'field': 'size',     'align': 'left'},
                    {'name': 'modified', 'label': 'Last Modified', 'field': 'modified', 'align': 'left'},
                ],
                rows=[],
                row_key='name',
                selection='multiple',
            ).classes('w-full')

        self.update()
        dialog.open()

    def update(self):
        os.makedirs(self.user_fastq_dir, exist_ok=True)
        rows: list[dict[str, str]] = []
        for filename in sorted(os.listdir(self.user_fastq_dir)):
            if filename.startswith('.'):
                continue
            filepath = join(self.user_fastq_dir, filename)
            if not os.path.isfile(filepath):
                continue
            stat = os.stat(filepath)
            rows.append({
                'name': filename,
                'size': format_file_size(stat.st_size),
                'modified': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
            })
        if self.table is not None:
            self.table.update_rows(rows)

    def delete(self):
        if self.table is None or len(self.table.selected) == 0:
            ui.notify('Please select at least one file.', type='negative')
            return

        deleted = 0
        for row in list(self.table.selected):
            filepath = join(self.user_fastq_dir, os.path.basename(row['name']))
            if os.path.isfile(filepath):
                os.remove(filepath)
                deleted += 1

        self.table.selected.clear()
        self.update()
        ui.notify(f'Deleted {deleted} file(s).', type='positive')

    def show_upload_dialog(self):
        with ui.dialog() as dialog, ui.card().classes('w-full max-w-2xl'):
            ui.label('Upload FASTQ Files').classes('text-xl font-semibold')
            ui.label(
                'Upload FASTQ files (.fastq, .fq, .fastq.gz, .fq.gz) and optional .md5 checksum files to verify integrity.'
            ).classes('text-sm text-slate-500')

            table = ui.table(
                columns=[
                    {'name': 'name',   'label': 'File',      'field': 'name',   'align': 'left'},
                    {'name': 'md5',    'label': 'MD5',       'field': 'md5',    'align': 'left'},
                    {'name': 'status', 'label': 'Integrity', 'field': 'status', 'align': 'left'},
                ],
                rows=[],
                row_key='name',
            ).classes('w-full')

            uploaded_md5: dict[str, str] = {}
            expected_md5: dict[str, str] = {}

            def refresh_table() -> None:
                all_files = sorted(set(uploaded_md5.keys()) | set(expected_md5.keys()))
                rows: list[dict[str, str]] = []
                for filename in all_files:
                    actual = uploaded_md5.get(filename, '')
                    expected = expected_md5.get(filename, '')
                    if actual and expected:
                        status = 'Verified (MD5 match)' if actual == expected else f'Mismatch (expected {expected})'
                    elif actual:
                        status = 'Uploaded (no .md5 reference)'
                    else:
                        status = 'Waiting for FASTQ file'
                    rows.append({'name': filename, 'md5': actual or '-', 'status': status})
                table.update_rows(rows)

            async def upload(event):
                filename = os.path.basename(event.file.name)
                os.makedirs(self.user_fastq_dir, exist_ok=True)

                if filename.lower().endswith('.md5') or filename.lower().endswith('.txt'):
                    text = await event.file.text()
                    parsed = parse_md5(filename, text)
                    if not parsed:
                        ui.notify(f'Could not parse MD5 entries from {filename}.', type='negative')
                        return
                    expected_md5.update(parsed)
                    refresh_table()
                    for target, exp_hash in parsed.items():
                        act_hash = uploaded_md5.get(target)
                        if act_hash is not None:
                            if act_hash == exp_hash:
                                ui.notify(f'{target}: MD5 verified.', type='positive')
                            else:
                                ui.notify(f'{target}: MD5 mismatch!', type='negative')
                    return

                filepath = join(self.user_fastq_dir, filename)
                await event.file.save(filepath)
                actual_hash = compute_file_md5(filepath)
                uploaded_md5[filename] = actual_hash
                refresh_table()
                self.update()

                exp_hash = expected_md5.get(filename)
                if exp_hash is not None:
                    if actual_hash == exp_hash:
                        ui.notify(f'{filename} uploaded and MD5 verified.', type='positive')
                    else:
                        ui.notify(f'{filename}: MD5 mismatch!', type='negative')
                else:
                    ui.notify(f'{filename} uploaded (MD5: {actual_hash}).', type='positive')

            ui.upload(
                label='Choose fastq or .md5 files',
                multiple=True,
                auto_upload=True,
                on_upload=upload,
            ).props(
                'accept=".fastq,.fq,.gz,.md5,.txt"'
            ).classes('w-full')

            with ui.row().classes('w-full justify-end'):
                ui.button('Close', on_click=dialog.close).props('flat')

        dialog.open()


def to_valid_filename(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", '_', s)


def format_timedelta(delta_t: timedelta) -> str:
    hours, remainder = divmod(int(delta_t.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f'{hours:02d}:{minutes:02d}:{seconds:02d}'


def format_file_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if size < 1024.0 or unit == 'TB':
            return f'{int(size)} {unit}' if unit == 'B' else f'{size:.1f} {unit}'
        size /= 1024.0
    return f'{size:.1f} TB'


def get_dirs(source: str, isfullpath: bool) -> list[str]:
    ret = []
    for path, dirs, files in os.walk(source):
        if path == source:
            ret = [d for d in dirs]

    if isfullpath:
        ret = [join(source, d) for d in ret]

    if len(ret) > 0:
        ret.sort()  # make the order consistent across OS platforms

    return ret


def parse_md5(name: str, text: str) -> dict[str, str]:
    """
    Parse MD5 checksum file content into a filename-to-hash dictionary.

    Supports both standard ``<md5>  <filename>`` (or ``MD5 (file) = <hash>``)
    and single-hash ``<md5>`` sidecar files (e.g. ``sample.fastq.gz.md5``).
    """
    result: dict[str, str] = {}
    for raw_line in text.lstrip('\ufeff').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#'):
            continue
        bsd_match = re.match(r'^MD5\s*\((.+)\)\s*=\s*([0-9a-fA-F]{32})$', line)
        if bsd_match:
            filename = os.path.basename(bsd_match.group(1).strip())
            result[filename] = bsd_match.group(2).lower()
            continue
        parts = line.split(None, 1)
        if len(parts) == 2 and re.fullmatch(r'[0-9a-fA-F]{32}', parts[0]):
            filename = os.path.basename(parts[1].lstrip('*').strip())
            result[filename] = parts[0].lower()
        elif len(parts) == 1 and re.fullmatch(r'[0-9a-fA-F]{32}', parts[0]):
            if name.lower().endswith('.md5') and len(name) > 4:
                result[name[:-4]] = parts[0].lower()
    return result


def compute_file_md5(filepath: str, chunk_size: int = 1024 * 1024) -> str:
    md5 = hashlib.md5()
    with open(filepath, 'rb') as f:
        while chunk := f.read(chunk_size):
            md5.update(chunk)
    return md5.hexdigest()


def read_parameters(name: str, text: str) -> dict:
    suffix = Path(name).suffix.lower()
    text = text.lstrip('\ufeff')
    if suffix in ('.csv', '.tsv', '.tab'):
        rows = csv.reader(StringIO(text), delimiter=',' if suffix == '.csv' else '\t')
    elif suffix == '.txt':
        rows = (line.split(':', 1) for line in text.splitlines())
    else:
        raise ValueError('Choose a CSV, TSV, TAB, or TXT parameter file.')
    result = {}
    for row in rows:
        if not row or not row[0].strip():
            continue
        if len(row) > 2:
            raise ValueError('Each parameter row must contain a key and at most one value.')
        key = row[0].strip()
        value = row[1].strip() if len(row) == 2 else ''
        result[key] = value if value else True
    return result


def write_parameters(parameters: dict, suffix: str) -> bytes:
    output = StringIO(newline='')
    writer = csv.writer(output, delimiter=',' if suffix == '.csv' else '\t', lineterminator='\n')
    for key, value in parameters.items():
        if value is False:
            continue
        row = [key] if value is True else [key, str(value)]
        if suffix == '.txt':
            output.write(': '.join(row) + '\n')
        else:
            writer.writerow(row)
    return output.getvalue().encode('utf-8')
