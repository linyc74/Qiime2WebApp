import os
from nicegui import ui
from os.path import join
from fastapi import Request
from typing import Callable
from urllib.parse import urlencode
from datetime import datetime, timezone, timedelta
from .job import Worker
from .database import Database
from .model import UserInput, MODES
from .auth import get_user, delete_session
from .constant import VERSION, PIPELINE_LABEL, USERS_DIR, BASE_URL
from .utils import format_timedelta, format_file_size, parse_md5, compute_file_md5, write_parameters


@ui.page('/')
async def home(request: Request):
    ui.colors(primary='#12329A')
    ui.add_css('body.body--dark { --q-primary: #3B82F6 !important; }')

    user: dict | None = await get_user(request)

    if user is None:
        with ui.column().classes('w-full max-w-4xl mx-auto p-4 sm:p-8 gap-6'):
            with ui.row().classes('w-full items-center justify-between'):
                with ui.row().classes('items-baseline gap-2'):
                    ui.label('QIIME 2 App').classes('text-3xl font-semibold')
                    ui.label(VERSION).classes('text-sm text-slate-400')
            ui.label(PIPELINE_LABEL).classes('text-sm text-slate-500')
            ui.label('Please sign in').classes('text-sm text-slate-500')
            with ui.row().classes('w-full gap-3'):
                ui.button(
                    'Sign in with Google',
                    icon='login',
                    on_click=lambda: ui.navigate.to(f'{BASE_URL}/login'),
                )
        return

    async def logout():
        await delete_session(request)
        ui.navigate.to('/')

    PipelinePage(user_id=user['user_id'], on_logout=logout)


class PipelinePage:

    def __init__(self, user_id: int, on_logout: Callable | None = None):
        self.input = UserInput(user_id=user_id)
        self.worker = Worker()

        self.controls = {}
        self.dashboard = Dashboard(user_input=self.input, worker=self.worker)
        self.fastq_dialog = FastqDialog(user_input=self.input)

        with ui.column().classes('w-full max-w-4xl mx-auto p-4 sm:p-8 gap-6'):

            with ui.row().classes('w-full items-center justify-between'):
                with ui.row().classes('items-baseline gap-2'):
                    ui.label('QIIME 2 App').classes('text-3xl font-semibold')
                    ui.label(VERSION).classes('text-sm text-slate-400')
                with ui.row().classes('gap-3'):
                    ui.button('Dashboard', icon='table_chart', on_click=self.dashboard.show).props('outline')
                    ui.button('Log out', icon='logout', on_click=on_logout).props('outline')
            
            with ui.row().classes('w-full items-center justify-between'):
                ui.label(self.input.email).classes('text-sm text-slate-500')
                ui.label(PIPELINE_LABEL).classes('text-sm text-slate-500')

            ui.toggle(
                {'illumina': 'Illumina Mode', 'pacbio': 'PacBio Mode'},
                value=self.input.mode,
                on_change=self.change_mode
            )

            self.form = ui.column().classes('w-full gap-4')
            self.render_form()

            with ui.row().classes('w-full gap-3 items-center justify-end'):
                ui.label(f'Runs {PIPELINE_LABEL}').classes('text-sm text-slate-400')
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

            default_key_to_options = MODES[self.input.mode]
            user_key_to_value = self.input.mode_to_key_to_value[self.input.mode]  # the data model dictionary to bind
            for key, options in default_key_to_options.items():  # follow the default to render UI
                if isinstance(options, bool):  # this is a flag
                    control = ui.checkbox(key).bind_value(user_key_to_value, key)  # ui control state bound to the data model dictionary
                else:  # list of options
                    choices = options.copy()
                    value = user_key_to_value[key]
                    if value not in choices:
                        choices.append(value)
                    control = ui.select(choices, label=key, new_value_mode='add-unique')
                control.bind_value(user_key_to_value, key).props('outlined').classes('w-full')  # ui control state bound to the data model dictionary
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
                key_to_value = self.input.mode_to_key_to_value[self.input.mode]
                ui.download(write_parameters(key_to_value, suffix), f'{self.input.mode}-parameters{suffix}')
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

        query = urlencode([('job_timestamps', row['id']) for row in self.table.selected])
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
