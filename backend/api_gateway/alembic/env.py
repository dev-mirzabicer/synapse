from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool
from sqlalchemy import create_engine

from alembic import context

import sys
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
# env_path = Path(__file__).resolve().parents[3] / ".env"
# load_dotenv(env_path)

# Add the 'shared' module to the Python path so we can import our models
sys.path.insert(0, "/app/shared")
from app.models.base import Base
from app.models.chat import * # Import all models to register them


# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Override the sqlalchemy.url with the loaded environment variable
# config.set_main_option("sqlalchemy.url", os.getenv("DATABASE_URL"))

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    # Get the original async database URL from the environment variable
    # This is the single source of truth from our .env file
    async_db_url = os.getenv("DATABASE_URL")
    if not async_db_url:
        raise ValueError("DATABASE_URL environment variable is not set")

    # Create a synchronous version of the URL for Alembic
    # We replace the 'asyncpg' driver with the default 'psycopg2'
    sync_db_url = async_db_url.replace("postgresql+asyncpg", "postgresql")

    # Pass this synchronous URL to connectable
    connectable = create_engine(sync_db_url)

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
