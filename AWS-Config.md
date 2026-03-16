# AWS Configuration - Mox Data

This document describes how the `Mox-Data.com` project is wired to AWS in production and how local access is handled.

## AWS Services Used

- **Amazon RDS (PostgreSQL)**: primary application database.
- **Amazon ElastiCache for Redis** (or equivalent Redis endpoint): Celery broker/result backend in production.
- **Amazon S3** (optional in runtime): file storage when `S3_BUCKET_NAME` is set.
- **AWS Secrets Manager**: stores database/application secrets (for example, `moxdata/db-uri`).
- **AWS Systems Manager (SSM)**: secure port-forwarding/tunneling to private resources (RDS) via bastion EC2.

## Runtime Configuration Model

Application config is loaded in `app.py`:

- If `FLASK_ENV` is `development` or `local`: reads `local-dev/local_config.cfg`
- Otherwise (`production`): tries `auxiliary/config.cfg`, then falls back to environment variables
- Environment variables always override loaded file values when present

## Required/Important Environment Variables

The app reads these values at runtime:

- `SECRET_KEY`
- `SQLALCHEMY_DATABASE_URI`
- `CELERY_BROKER_URL`
- `CELERY_RESULT_BACKEND`
- `URL_SAFETIMEDSERIALIZER`
- `EMAIL_CONFIRMATION_SALT`
- `RESET_PASSWORD_SALT`
- `MAIL_SERVER`
- `MAIL_PORT`
- `MAIL_USE_TLS`
- `MAIL_USE_SSL`
- `MAIL_USERNAME`
- `MAIL_PASSWORD`
- `MAIL_DEFAULT_SENDER`
- `AWS_REGION` (used for S3 client initialization)
- `S3_BUCKET_NAME` (enables S3 mode)
- `S3_PREFIX` (optional key prefix in S3)

## Database Configuration

- SQLAlchemy uses `SQLALCHEMY_DATABASE_URI`.
- Typical production URI format:
  - `postgresql+psycopg2://<user>:<password>@<host>:5432/<database>`
- Local development defaults to SQLite in `local-dev/local_config.cfg`.

### Secrets Manager

- Secret commonly referenced during operations: `moxdata/db-uri`
- Store DB credentials/URI in Secrets Manager and inject into environment for app/container runtime.
- Never commit secret values to source control.

## Celery/Redis Configuration

- Celery app is initialized in `app.py` using:
  - `CELERY_BROKER_URL`
  - `CELERY_RESULT_BACKEND`
- Local development uses `redis://localhost:6379/0` (often via Docker Redis).
- Production should point to managed Redis (for example ElastiCache).
- If using TLS Redis, use `rediss://...`; app enables TLS options automatically when scheme is `rediss://`.

## S3 File Storage Behavior

In `modules/views.py`:

- If `S3_BUCKET_NAME` is set, app uses S3 via `boto3` client.
- If not set, app falls back to local file storage (`local-dev/data/uploads/...`).
- `AWS_REGION` is used when creating the S3 client.

## Container/Deployment Notes

`Dockerfile` currently defines:

- Base image: `python:3.11-slim`
- `FLASK_ENV=production`
- `PORT=8080`
- Installs `requirements.txt` and runs `gunicorn` serving `app:app`

## Schema Management (Production)

Production schema updates should be applied explicitly with migrations, not by app startup.

- Migration tool: `Flask-Migrate` (Alembic)
- Migration files: `migrations/versions/`
- Baseline revision: `53d5e7b403c0`

Typical workflow:

```bash
# After changing SQLAlchemy models
python -m flask --app app.py db migrate -m "Describe schema change"
python -m flask --app app.py db upgrade
```

Local/dev convenience still uses `db.create_all()` on startup for SQLite bootstrap only.

## Recommended RDS Access Pattern

Use private RDS + SSM tunnel instead of exposing RDS publicly.

### SSM Tunnel Flow

1. Launch/choose EC2 bastion in same VPC as RDS.
2. Attach IAM role with `AmazonSSMManagedInstanceCore`.
3. Ensure instance is online in SSM:
   - `aws ssm describe-instance-information --region us-west-2 --output table`
4. Add RDS SG inbound rule:
   - Type `PostgreSQL`, Port `5432`, Source = bastion EC2 security group
5. Start tunnel from local machine:

```bash
aws ssm start-session \
  --target <INSTANCE_ID> \
  --document-name AWS-StartPortForwardingSessionToRemoteHost \
  --parameters '{"host":["mox-data-database.cr3z2pjgv3bk.us-west-2.rds.amazonaws.com"],"portNumber":["5432"],"localPortNumber":["5432"]}' \
  --region us-west-2
```

6. Connect pgAdmin using:
   - Host: `127.0.0.1`
   - Port: `5432`
   - Database: `postgres` (or target DB)
   - SSL mode: `require`

## Security Guidance

- Keep RDS private when possible.
- Prefer SG-to-SG rules (bastion SG -> RDS SG) over public IP CIDR rules.
- If temporary public inbound access is ever enabled, remove it immediately after use.
- Rotate credentials stored in Secrets Manager regularly.
- Do not store real secret values in tracked files.
