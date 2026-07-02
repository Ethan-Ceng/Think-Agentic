BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL,
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

CREATE TABLE sessions (
    id VARCHAR(255) NOT NULL,
    sandbox_id VARCHAR(255),
    task_id VARCHAR(255),
    title VARCHAR(255) DEFAULT ''::character varying NOT NULL,
    unread_message_count INTEGER DEFAULT 0 NOT NULL,
    latest_message TEXT DEFAULT ''::text NOT NULL,
    latest_message_at TIMESTAMP WITHOUT TIME ZONE,
    events JSONB DEFAULT '[]'::jsonb NOT NULL,
    files JSONB DEFAULT '[]'::jsonb NOT NULL,
    memories JSONB DEFAULT '{}'::jsonb NOT NULL,
    status VARCHAR(255) DEFAULT ''::character varying NOT NULL,
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP(0) NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP(0) NOT NULL,
    CONSTRAINT pk_sessions_id PRIMARY KEY (id)
);

CREATE TABLE files (
    id VARCHAR(255) NOT NULL,
    filename VARCHAR(255) DEFAULT ''::character varying NOT NULL,
    filepath VARCHAR(255) DEFAULT ''::character varying NOT NULL,
    key VARCHAR(255) DEFAULT ''::character varying NOT NULL,
    extension VARCHAR(255) DEFAULT ''::character varying NOT NULL,
    mime_type VARCHAR(255) DEFAULT ''::character varying NOT NULL,
    size INTEGER DEFAULT 0 NOT NULL,
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP(0) NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP(0) NOT NULL,
    CONSTRAINT pk_files_id PRIMARY KEY (id)
);

INSERT INTO alembic_version (version_num) VALUES ('0e0d242438bc');

COMMIT;
