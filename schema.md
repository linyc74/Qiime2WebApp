# PostgreSQL Database Schema

Database name: `qiime2_web_app`  

## Tables

| Name | Description |
| :--- | :--- |
| `users` | Registered users authenticated via Google OAuth |
| `jobs` | Pipeline execution jobs |

### `users`

| Column | Type | Nullable | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `id` | `bigint` | `NOT NULL` | `generated always as identity` | Primary key |
| `email` | `character varying(255)` | `NOT NULL` | | User email address (unique) |
| `created_at` | `timestamp with time zone` | `NOT NULL` | `now()` | Account creation timestamp |

- **Primary Key**: `users_pkey` (`btree (id)`)
- **Unique Constraint**: `users_email_key` (`btree (email)`)
- **Referenced By**: `jobs.user_id` via foreign key `jobs_user_id_fkey` (`REFERENCES users(id)`)

### `jobs`

Tracks `qiime2_pipeline` job submissions, Redis Queue (`rq`) job IDs, execution timestamps, and statuses (`waiting`, `running`, `completed`, `failed`, `cancelled`).

Note that the `timestamp` column serves as an alternate human readable ID, which is used for UI dashboard and file path. `timestamp` is a string without blank space and special characters.

| Column | Type | Nullable | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `id` | `bigint` | `NOT NULL` | `generated always as identity` | Primary key |
| `user_id` | `bigint` | `NOT NULL` | | Foreign key referencing `users(id)` |
| `status` | `character varying(20)` | `NULL` | | Job status (`waiting`, `running`, `completed`, `failed`, `cancelled`) |
| `started_at` | `timestamp with time zone` | `NULL` | | Timestamp when job execution started |
| `ended_at` | `timestamp with time zone` | `NULL` | | Timestamp when job completed, failed, or was cancelled while running |
| `timestamp` | `character varying(23)` | `NOT NULL` | | Job directory timestamp (`YYYY-MM-DD_HH-MM-SS.mmm`) |
| `rq_job_id` | `character varying(255)` | `NULL` | | Redis Queue (`rq`) job identifier |

- **Primary Key**: `jobs_pkey` (`btree (id)`)
- **Foreign Key**: `jobs_user_id_fkey` (`FOREIGN KEY (user_id) REFERENCES users(id)`)

---

## SQL

```sql
CREATE TABLE public.users (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email character varying(255) NOT NULL UNIQUE,
    created_at timestamp with time zone NOT NULL DEFAULT now()
);

CREATE TABLE public.jobs (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id bigint NOT NULL REFERENCES public.users(id),
    status character varying(20),
    started_at timestamp with time zone,
    ended_at timestamp with time zone,
    timestamp character varying(23) NOT NULL,
    rq_job_id character varying(255)
);
```
