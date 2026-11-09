# Virtual Bookshelf

Virtual Bookshelf is a full-stack Flask application for cataloging, organizing, and exploring a physical book collection. It combines detailed collection management with a visual, responsive interface backed by PostgreSQL.

## Highlights

- Add, view, edit, and delete books
- Associate multiple authors and genres with each title
- Track shelf location, format, condition, purchase details, and personal notes
- Upload and display custom cover images
- Search, filter, sort, and paginate the collection
- Browse dedicated author pages and a visual bookshelf
- Explore collection statistics across genres, shelves, formats, and spending

## Tech stack

- **Backend:** Python, Flask, Psycopg
- **Database:** PostgreSQL
- **Frontend:** Jinja templates, HTML, CSS, and JavaScript

## Getting started

### Prerequisites

- Python 3.11 or newer
- PostgreSQL

### Installation

Clone the repository and enter the project directory:

```bash
git clone https://github.com/xastrumx/virtual-bookshelf.git
cd virtual-bookshelf
```

Create a virtual environment and install the dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Create the local environment file from the included template:

```bash
cp .env.example .env
```

Update `.env` with the credentials for your PostgreSQL database, then apply the schema:

```bash
psql -d virtual_bookshelf -f schema.sql
```

Start the application:

```bash
python app.py
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000) in a browser.

## Project structure

```text
virtual-bookshelf/
├── app.py             # Application routes and collection workflows
├── db.py              # PostgreSQL connection management
├── schema.sql         # Relational database schema
├── templates/         # Jinja page templates
├── static/css/        # Page and component styles
└── static/covers/     # Local user-uploaded covers
```

## Privacy and local data

The repository contains a data-free schema and placeholder environment values only. Local database credentials, database exports, uploaded covers, virtual environments, caches, and private notes are excluded through `.gitignore`. Keep those files local and never force-add them to version control.

## Security note

Virtual Bookshelf is designed as a single-user local application and does not currently include authentication. Add an authentication layer and production-ready deployment configuration before exposing a running instance to a network or the public internet.

## Future improvements

- Support independently managed copies of the same title
- Add automated test coverage
- Add cover replacement and removal controls
- Continue responsive-design and accessibility improvements
- Add authentication for shared or hosted deployments
