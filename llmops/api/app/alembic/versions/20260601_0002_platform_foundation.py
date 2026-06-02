"""platform foundation settings files and model providers

Revision ID: 20260601_0002
Revises: 20260601_0001
Create Date: 2026-06-01 22:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260601_0002"
down_revision: str | None = "20260601_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def uuid_pk() -> sa.Column:
    return sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        server_default=sa.text("uuid_generate_v4()"),
        nullable=False,
    )


def timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP(0)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP(0)"), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "account_settings",
        uuid_pk(),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        *timestamps(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_account_settings")),
        sa.UniqueConstraint("account_id", "category", "key", name="uq_account_settings_account_category_key"),
    )
    op.create_index(
        "ix_account_settings_account_category",
        "account_settings",
        ["account_id", "category"],
        unique=False,
    )

    op.create_table(
        "files",
        uuid_pk(),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("type", sa.String(length=32), server_default=sa.text("'file'::character varying"), nullable=False),
        sa.Column("name", sa.String(length=255), server_default=sa.text("''::character varying"), nullable=False),
        sa.Column("extension", sa.String(length=64), server_default=sa.text("''::character varying"), nullable=False),
        sa.Column("mime_type", sa.String(length=255), server_default=sa.text("''::character varying"), nullable=False),
        sa.Column("size", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "storage_provider",
            sa.String(length=64),
            server_default=sa.text("'local'::character varying"),
            nullable=False,
        ),
        sa.Column("file_path", sa.String(length=512), server_default=sa.text("''::character varying"), nullable=False),
        sa.Column("hash", sa.String(length=255), server_default=sa.text("''::character varying"), nullable=False),
        sa.Column("source", sa.String(length=64), server_default=sa.text("'upload'::character varying"), nullable=False),
        sa.Column("status", sa.String(length=64), server_default=sa.text("'available'::character varying"), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        *timestamps(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_files")),
    )
    op.create_index("ix_files_account_parent", "files", ["account_id", "parent_id"], unique=False)
    op.create_index("ix_files_account_status", "files", ["account_id", "status"], unique=False)
    op.create_index("ix_files_account_source", "files", ["account_id", "source"], unique=False)

    op.execute(
        """
        INSERT INTO files (
            id, account_id, parent_id, type, name, extension, mime_type, size,
            storage_provider, file_path, hash, source, status, metadata, created_by,
            deleted_at, created_at, updated_at
        )
        SELECT
            id, account_id, NULL, 'file', name, extension, mime_type, size,
            'local', key, hash, 'upload', 'available', '{}'::jsonb, account_id,
            NULL, created_at, updated_at
        FROM upload_file
        ON CONFLICT (id) DO NOTHING
        """
    )

    op.create_table(
        "llm_providers",
        uuid_pk(),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("base_url", sa.String(length=512), server_default=sa.text("''::character varying"), nullable=False),
        sa.Column(
            "api_key_encrypted",
            sa.String(length=2048),
            server_default=sa.text("''::character varying"),
            nullable=False,
        ),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("is_default", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        *timestamps(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_llm_providers")),
        sa.UniqueConstraint("account_id", "provider", "name", name="uq_llm_providers_account_provider_name"),
    )
    op.create_index("ix_llm_providers_account_enabled", "llm_providers", ["account_id", "enabled"], unique=False)

    op.create_table(
        "llm_models",
        uuid_pk(),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("display_name", sa.String(length=128), server_default=sa.text("''::character varying"), nullable=False),
        sa.Column("model_type", sa.String(length=32), server_default=sa.text("'chat'::character varying"), nullable=False),
        sa.Column("features", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("context_window", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("max_output_tokens", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "default_parameters",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("is_default", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["provider_id"], ["llm_providers.id"], name=op.f("fk_llm_models_provider_id_llm_providers")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_llm_models")),
        sa.UniqueConstraint("provider_id", "model", name="uq_llm_models_provider_model"),
    )
    op.create_index("ix_llm_models_account_enabled", "llm_models", ["account_id", "enabled"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_llm_models_account_enabled", table_name="llm_models")
    op.drop_table("llm_models")
    op.drop_index("ix_llm_providers_account_enabled", table_name="llm_providers")
    op.drop_table("llm_providers")
    op.drop_index("ix_files_account_source", table_name="files")
    op.drop_index("ix_files_account_status", table_name="files")
    op.drop_index("ix_files_account_parent", table_name="files")
    op.drop_table("files")
    op.drop_index("ix_account_settings_account_category", table_name="account_settings")
    op.drop_table("account_settings")
