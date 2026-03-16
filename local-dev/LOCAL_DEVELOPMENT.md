# Local Development Guide for MTGO-DB

This guide will help you set up and run the MTGO-DB Flask application locally for testing before deploying to AWS.

## Prerequisites

- Python 3.10 - 3.12
- pip (Python package installer)
- Redis (for background tasks)

## Quick Start

1. **Run the setup script:**
   ```bash
   python local-dev/setup_local.py
   ```

2. **Update configuration:**
   Edit `local-dev/local_config.cfg` with your settings (see Configuration section below)

3. **Start the application:**
   ```bash
   python app.py
   ```

4. **Open your browser:**
   Navigate to `http://localhost:8000`

## Manual Setup

If you prefer to set up manually:

### 1. Install Dependencies

```bash
python -m pip install -r local-dev/requirements-local.txt
```

### 2. Install Redis

**Windows:**
- Download from https://redis.io/download
- Or use WSL2 with Ubuntu

**macOS:**
```bash
brew install redis
brew services start redis
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt-get update
sudo apt-get install redis-server
sudo systemctl start redis
```

### 3. Create Directories

```bash
mkdir local-dev/data/uploads
mkdir local-dev/data/logs
```

### 4. Configure the Application

Edit `local-dev/local_config.cfg` with your settings:

```ini
# Email settings (for testing, you can use Mailtrap.io)
MAIL_SERVER = 'smtp.gmail.com'
MAIL_USERNAME = 'your-email@gmail.com'
MAIL_PASSWORD = 'your-app-password'

# Database (SQLite for local development)
SQLALCHEMY_DATABASE_URI = 'sqlite:///local_database.db'

# Redis settings
CELERY_BROKER_URL = 'redis://localhost:6379/0'
CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'
```

### 5. Run the Application

```bash
python app.py
```

## Configuration Options

### Email Configuration

For local testing, you can use:
- **Gmail**: Use an app password (not your regular password)
- **Mailtrap.io**: Free email testing service
- **Local SMTP**: Use a local mail server

### Database

The local configuration uses SQLite, which is perfect for development:
- No setup required
- File-based database
- Automatically created when you first run the app

### Background Tasks (Celery)

The app uses Celery for background tasks. For local development:
- Redis is used as the message broker
- Tasks run locally
  - You can monitor tasks in several ways:
    1. **Web Interface**: Visit `/tasks` in your app for basic monitoring
    2. **Worker Logs**: Check the Celery worker logs in the terminal

## Development Workflow

### Running in Development Mode

The app automatically detects the environment:
- **Local/Development**: Uses `static/local_config.cfg`
- **Production**: Uses `auxiliary/config.cfg` and environment variables

### Debug Mode

When running locally, debug mode is enabled:
- Automatic reloading on code changes
- Detailed error messages
- Debug toolbar (if installed)

### Database Changes

When you modify models:
1. Stop the application
2. Delete `local_database.db` (if you want to start fresh)
3. Restart the application (tables will be recreated)

## Testing Features

### Email Testing

To test email functionality:
1. Set up Mailtrap.io account
2. Update `local_config.cfg` with Mailtrap credentials
3. Test registration/email confirmation features

### File Upload Testing

The app supports file uploads:
1. Files are stored in the `local-dev/data/uploads/` directory locally
2. In production, files are stored in Azure Blob Storage

### Background Tasks

To test background tasks, you need both Flask and Celery worker running:

#### Option 1: All-in-One Start (Recommended)
```bash
python local-dev/start_all.py
```

#### Option 2: Manual Start
1. Ensure Redis is running
2. Start Celery worker: `python local-dev/start_celery.py`
3. Start Flask app: `python app.py` 


Tasks will be processed in the background automatically.

## Troubleshooting

### Common Issues

**Redis Connection Error:**
```
Connection refused to Redis
```
- Make sure Redis is installed and running
- Check if Redis is running on port 6379

**Import Errors:**
```
ModuleNotFoundError: No module named 'flask'
```
- Make sure you've installed the requirements: `pip install -r requirements-local.txt`

**Database Errors:**
```
SQLAlchemy errors
```
- Delete `local_database.db` and restart the app
- Check that the database path is writable

**Port Already in Use:**
```
Address already in use
```
- Change the port in `app.py` or kill the process using port 8000

### Getting Help

1. Check the application logs for error messages
2. Ensure all dependencies are installed correctly
3. Verify Redis is running
4. Check file permissions for uploads and logs directories

## Preparing for AWS Deployment

When you're ready to deploy to AWS:

1. **Update production configuration:**
   - Edit `auxiliary/config.cfg` for production settings
   - Set environment variables for sensitive data

2. **Use production requirements:**
   - Use `requirements.txt` instead of `requirements-local.txt`
   - Install all dependencies including Azure SDK

3. **Set up AWS services:**
   - RDS for PostgreSQL database
   - ElastiCache for Redis
   - S3 for file storage
   - SES for email

4. **Environment variables:**
   - Set `FLASK_ENV=production`
   - Configure all production environment variables

## File Structure

```
MTGO-DB/
├── app.py                    # Main application file
├── requirements.txt         # Production dependencies
├── modules/                 # Application modules
├── static/                  # Static files and configs
│   └── config.cfg          # Production configuration
├── templates/              # HTML templates
└── local-dev/              # Local development files
    ├── README.md           # Local development guide
    ├── local_config.cfg    # Local configuration
    ├── requirements-local.txt # Local dependencies
    ├── setup_local.py      # Local development setup
    ├── start_celery.py     # Celery worker script
    ├── LOCAL_DEVELOPMENT.md # Detailed local guide
    └── data/               # Local data storage
        ├── uploads/        # Local file uploads
        └── logs/           # Application logs
``` 