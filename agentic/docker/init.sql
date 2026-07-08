BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL,
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

CREATE TABLE users (
    id VARCHAR(255) NOT NULL,
    email VARCHAR(255) NOT NULL,
    name VARCHAR(255) DEFAULT ''::character varying NOT NULL,
    avatar VARCHAR(512) DEFAULT ''::character varying NOT NULL,
    password_hash VARCHAR(255) DEFAULT ''::character varying NOT NULL,
    password_salt VARCHAR(255) DEFAULT ''::character varying NOT NULL,
    password_algorithm VARCHAR(64) DEFAULT 'pbkdf2_sha256'::character varying NOT NULL,
    status VARCHAR(32) DEFAULT 'active'::character varying NOT NULL,
    last_login_at TIMESTAMP WITHOUT TIME ZONE,
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP(0) NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP(0) NOT NULL,
    CONSTRAINT pk_users_id PRIMARY KEY (id)
);

CREATE UNIQUE INDEX ux_users_email ON users (email);

CREATE TABLE sessions (
    id VARCHAR(255) NOT NULL,
    user_id VARCHAR(255) NOT NULL,
    sandbox_id VARCHAR(255),
    task_id VARCHAR(255),
    title VARCHAR(255) DEFAULT ''::character varying NOT NULL,
    unread_message_count INTEGER DEFAULT 0 NOT NULL,
    latest_message TEXT DEFAULT ''::text NOT NULL,
    latest_message_at TIMESTAMP WITHOUT TIME ZONE,
    events JSONB DEFAULT '[]'::jsonb NOT NULL,
    files JSONB DEFAULT '[]'::jsonb NOT NULL,
    memories JSONB DEFAULT '{}'::jsonb NOT NULL,
    status VARCHAR(255) DEFAULT 'pending'::character varying NOT NULL,
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP(0) NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP(0) NOT NULL,
    CONSTRAINT pk_sessions_id PRIMARY KEY (id),
    CONSTRAINT fk_sessions_user_id_users FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT
);

CREATE INDEX ix_sessions_user_latest_message_at ON sessions (user_id, latest_message_at);

CREATE TABLE files (
    id VARCHAR(255) NOT NULL,
    user_id VARCHAR(255) NOT NULL,
    filename VARCHAR(255) DEFAULT ''::character varying NOT NULL,
    filepath VARCHAR(255) DEFAULT ''::character varying NOT NULL,
    key VARCHAR(255) DEFAULT ''::character varying NOT NULL,
    extension VARCHAR(255) DEFAULT ''::character varying NOT NULL,
    mime_type VARCHAR(255) DEFAULT ''::character varying NOT NULL,
    size INTEGER DEFAULT 0 NOT NULL,
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP(0) NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP(0) NOT NULL,
    CONSTRAINT pk_files_id PRIMARY KEY (id),
    CONSTRAINT fk_files_user_id_users FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT
);

CREATE INDEX ix_files_user_created_at ON files (user_id, created_at);

INSERT INTO alembic_version (version_num) VALUES ('20260707_0001');

COMMIT;
