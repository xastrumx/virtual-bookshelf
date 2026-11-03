# Virtual Bookshelf

A private, single-user Flask application for cataloging a personal book collection in PostgreSQL.

## Current features

- Add, view, edit, and delete books
- Store one or more authors and genres per book
- Track a physical copy's shelf, format, condition, purchase details, and notes
- Upload cover images
- Search, filter, sort, and paginate the library
- Browse authors and a visual bookshelf
- View collection statistics

This project intentionally has no accounts or login system. Run it only on your own computer. If it is ever exposed to a local network or the internet, add authentication first.

## Local setup

Requirements:

- Python 3.11 or newer
- PostgreSQL

Create and activate a virtual environment, then install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Copy the environment template and enter the credentials for your local PostgreSQL database:

```bash
cp .env.example .env
```

For a new, empty database, apply the included schema:

```bash
psql -d virtual_bookshelf -f schema.sql
```

Start the application:

```bash
source .venv/bin/activate
python app.py
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000). The development server binds to this computer only by default.

## Backups

The collection has two parts, and both must be backed up:

1. PostgreSQL data
2. Uploaded covers in `static/covers`

Example database backup:

```bash
pg_dump -Fc -d virtual_bookshelf -f virtual_bookshelf.dump
```

Example database restore into an empty database:

```bash
pg_restore --clean --if-exists -d virtual_bookshelf virtual_bookshelf.dump
```

Copy the entire `static/covers` directory into the same backup location as the database dump. Keep backups outside this project folder, ideally in a location that is itself backed up.

## Personal-use maintenance

- Keep `.env` private; it contains the database password.
- Leave `FLASK_DEBUG=false` for normal use.
- Back up the database and cover directory after large cataloging sessions.
- Run `python -m py_compile app.py db.py` after code changes for a quick syntax check.

## Optional future improvements

- Manage multiple physical copies of one title independently
- Add automated tests
- Add cover removal/replacement controls
- Continue responsive and accessibility polish
- Add authentication only if the app becomes shared or remotely accessible
