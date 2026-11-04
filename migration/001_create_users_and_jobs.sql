CREATE TABLE public.users (
    id bigint GENERATED ALWAYS AS IDENTITY,
    email character varying(255) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT users_pkey PRIMARY KEY (id),
    CONSTRAINT users_email_key UNIQUE (email)
);

CREATE TABLE public.jobs (
    id bigint GENERATED ALWAYS AS IDENTITY,
    user_id bigint NOT NULL,
    status character varying(20),
    started_at timestamp with time zone,
    ended_at timestamp with time zone,
    "timestamp" character varying(23) NOT NULL,
    rq_job_id character varying(255),
    CONSTRAINT jobs_pkey PRIMARY KEY (id),
    CONSTRAINT jobs_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users (id)
);
