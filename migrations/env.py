import logging
from logging.config import fileConfig

from flask import current_app

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
fileConfig(config.config_file_name)
logger = logging.getLogger('alembic.env')


def _normalize_identifier(value):
    if value is None:
        return ""
    # Normalize quoting/brackets so we can match table names robustly.
    return str(value).strip().strip('"').strip("'")

def _is_vapi_table(name, schema=None):
    normalized_name = _normalize_identifier(name).lower()
    normalized_schema = _normalize_identifier(schema).lower()

    if normalized_schema in {"vapi", "[vapi]"}:
        return True

    candidates = {normalized_name}
    if normalized_schema:
        candidates.add(f"{normalized_schema}.{normalized_name}")

    for candidate in candidates:
        if candidate.startswith("[vapi].") or candidate.startswith("vapi."):
            return True
    return False

def include_name(name, type_, parent_names):
    """Exclude external vapi dataset objects from Alembic operations."""
    if type_ == "table":
        schema_name = parent_names.get("schema_name") if parent_names else None
        if _is_vapi_table(name, schema=schema_name):
            return False
    return True

def include_object(object_, name, type_, reflected, compare_to):
    """Exclude external vapi dataset objects from autogenerate diffs."""
    table_name = None
    schema_name = None

    if type_ == "table":
        table_name = name
        schema_name = getattr(object_, "schema", None)
    else:
        table = getattr(object_, "table", None)
        if table is not None:
            table_name = getattr(table, "name", None)
            schema_name = getattr(table, "schema", None)

    if _is_vapi_table(table_name, schema=schema_name):
        return False

    return True

def get_engine():
    try:
        # this works with Flask-SQLAlchemy<3 and Alchemical
        return current_app.extensions['migrate'].db.get_engine()
    except (TypeError, AttributeError):
        # this works with Flask-SQLAlchemy>=3
        return current_app.extensions['migrate'].db.engine


def get_engine_url():
    try:
        return get_engine().url.render_as_string(hide_password=False).replace(
            '%', '%%')
    except AttributeError:
        return str(get_engine().url).replace('%', '%%')


# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
config.set_main_option('sqlalchemy.url', get_engine_url())
target_db = current_app.extensions['migrate'].db

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def get_metadata():
    if hasattr(target_db, 'metadatas'):
        return target_db.metadatas[None]
    return target_db.metadata


def run_migrations_offline():
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
        target_metadata=get_metadata(),
        literal_binds=True,
        include_name=include_name,
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """

    # this callback is used to prevent an auto-migration from being generated
    # when there are no changes to the schema
    # reference: http://alembic.zzzcomputing.com/en/latest/cookbook.html
    def process_revision_directives(context, revision, directives):
        if getattr(config.cmd_opts, 'autogenerate', False):
            script = directives[0]
            if script.upgrade_ops.is_empty():
                directives[:] = []
                logger.info('No changes in schema detected.')

    conf_args = current_app.extensions['migrate'].configure_args
    if conf_args.get("process_revision_directives") is None:
        conf_args["process_revision_directives"] = process_revision_directives
    if conf_args.get("include_name") is None:
        conf_args["include_name"] = include_name
    if conf_args.get("include_object") is None:
        conf_args["include_object"] = include_object

    connectable = get_engine()

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=get_metadata(),
            **conf_args
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
