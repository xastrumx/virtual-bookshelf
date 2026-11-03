import hmac
import os
import secrets
from datetime import date
from decimal import Decimal, InvalidOperation

from flask import Flask, abort, flash, redirect, render_template, request, session, url_for
from db import close_db_connection, get_db_connection
from pathlib import Path
from uuid import uuid4
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY") or secrets.token_hex(32)
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024
app.teardown_appcontext(close_db_connection)

COVER_UPLOAD_FOLDER = Path(app.root_path) / "static" / "covers"

ALLOWED_COVER_EXTENSIONS = {
    "jpg",
    "jpeg",
    "png",
    "webp"
}

COPY_FORMATS = {
    "Hardcover",
    "Paperback",
    "Mass Market Paperback",
    "Audiobook",
    "Other",
}

COPY_CONDITIONS = {
    "New",
    "Like New",
    "Good",
    "Fair",
    "Poor",
}

COVER_SIGNATURES = {
    "jpg": lambda header: header.startswith(b"\xff\xd8\xff"),
    "jpeg": lambda header: header.startswith(b"\xff\xd8\xff"),
    "png": lambda header: header.startswith(b"\x89PNG\r\n\x1a\n"),
    "webp": lambda header: header.startswith(b"RIFF") and header[8:12] == b"WEBP",
}

COVER_UPLOAD_FOLDER.mkdir(
    parents=True,
    exist_ok=True
)

def save_cover_image(file):

    if not file or file.filename == "":
        return None

    filename = secure_filename(file.filename)

    if "." not in filename:
        raise ValueError("Cover images must include a JPG, PNG, or WEBP extension.")

    extension = filename.rsplit(".", 1)[1].lower()

    if extension not in ALLOWED_COVER_EXTENSIONS:
        raise ValueError("Cover images must be JPG, PNG, or WEBP files.")

    header = file.stream.read(12)
    file.stream.seek(0)

    if not COVER_SIGNATURES[extension](header):
        raise ValueError("The selected cover does not appear to be a valid image file.")

    unique_filename = f"{uuid4().hex}.{extension}"

    file_path = COVER_UPLOAD_FOLDER / unique_filename

    file.save(file_path)

    return f"covers/{unique_filename}"


def normalize_isbn(value):
    return value.strip().replace("-", "").replace(" ", "").upper()


def validate_book_values(title, isbn, publication_year):
    errors = []

    if not title:
        errors.append("Title is required.")
    elif len(title) > 255:
        errors.append("Title must be 255 characters or fewer.")

    valid_isbn = (
        len(isbn) == 13 and isbn.isdigit()
    ) or (
        len(isbn) == 10
        and isbn[:9].isdigit()
        and (isbn[-1].isdigit() or isbn[-1] == "X")
    )

    if not valid_isbn:
        errors.append("ISBN must contain 10 or 13 valid characters.")

    parsed_year = None

    if publication_year:
        if not publication_year.isdigit() or len(publication_year) != 4:
            errors.append("Publication year must be four digits.")
        else:
            parsed_year = int(publication_year)
            if parsed_year > date.today().year + 1:
                errors.append("Publication year cannot be more than one year in the future.")

    return errors, parsed_year


def parse_optional_id(value, field_name, errors):
    if not value:
        return None

    try:
        parsed_value = int(value)
    except (TypeError, ValueError):
        errors.append(f"Choose a valid {field_name}.")
        return None

    if parsed_value < 1:
        errors.append(f"Choose a valid {field_name}.")
        return None

    return parsed_value


def parse_optional_price(value, errors):
    if not value:
        return None

    try:
        price = Decimal(value)
    except InvalidOperation:
        errors.append("Purchase price must be a number.")
        return None

    if price < 0:
        errors.append("Purchase price cannot be negative.")
        return None

    if price > Decimal("99999999.99"):
        errors.append("Purchase price is too large.")
        return None

    return price


def parse_optional_date(value, errors):
    if not value:
        return None

    try:
        return date.fromisoformat(value)
    except ValueError:
        errors.append("Purchase date must be a valid date.")
        return None


def get_or_create_publisher(cursor, name):
    cursor.execute(
        "SELECT publisher_id FROM publishers WHERE LOWER(name) = LOWER(%s)",
        (name,)
    )
    publisher = cursor.fetchone()

    if publisher:
        return publisher["publisher_id"]

    cursor.execute(
        "INSERT INTO publishers (name) VALUES (%s) RETURNING publisher_id",
        (name,)
    )
    return cursor.fetchone()["publisher_id"]


def get_or_create_author(cursor, first_name, last_name):
    cursor.execute(
        """
        SELECT author_id
        FROM authors
        WHERE LOWER(first_name) = LOWER(%s)
          AND LOWER(last_name) = LOWER(%s)
        """,
        (first_name, last_name)
    )
    author = cursor.fetchone()

    if author:
        return author["author_id"]

    cursor.execute(
        """
        INSERT INTO authors (first_name, last_name)
        VALUES (%s, %s)
        RETURNING author_id
        """,
        (first_name, last_name)
    )
    return cursor.fetchone()["author_id"]


def get_or_create_genre(cursor, name):
    cursor.execute(
        "SELECT genre_id FROM genres WHERE LOWER(name) = LOWER(%s)",
        (name,)
    )
    genre = cursor.fetchone()

    if genre:
        return genre["genre_id"]

    cursor.execute(
        "INSERT INTO genres (name) VALUES (%s) RETURNING genre_id",
        (name,)
    )
    return cursor.fetchone()["genre_id"]


def get_or_create_shelf(cursor, name):
    cursor.execute(
        "SELECT shelf_id FROM shelves WHERE LOWER(name) = LOWER(%s)",
        (name,)
    )
    shelf = cursor.fetchone()

    if shelf:
        return shelf["shelf_id"]

    cursor.execute(
        "INSERT INTO shelves (name) VALUES (%s) RETURNING shelf_id",
        (name,)
    )
    return cursor.fetchone()["shelf_id"]


def remove_managed_cover(relative_path):
    if not relative_path:
        return

    cover_path = (Path(app.root_path) / "static" / relative_path).resolve()
    managed_folder = COVER_UPLOAD_FOLDER.resolve()

    if cover_path.is_relative_to(managed_folder) and cover_path.is_file():
        cover_path.unlink()


def csrf_token():
    token = session.get("_csrf_token")

    if token is None:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token

    return token


app.jinja_env.globals["csrf_token"] = csrf_token


@app.before_request
def protect_write_requests():
    if request.method == "POST":
        submitted_token = request.form.get("csrf_token", "")
        expected_token = session.get("_csrf_token", "")

        if not expected_token or not hmac.compare_digest(submitted_token, expected_token):
            abort(400, description="The form expired. Refresh the page and try again.")


@app.errorhandler(413)
def cover_too_large(_error):
    flash("The cover image is too large. Choose a file smaller than 5 MB.", "error")
    return redirect(request.referrer or url_for("add_book"))

# Library
@app.route("/library")
def library():      

    # Search / filters / pagination
    search = request.args.get("search", "").strip()
    genre_id = request.args.get("genre_id", type=int)
    publisher_id = request.args.get("publisher_id", type=int)
    shelf_id = request.args.get("shelf_id", type=int)
    book_format = request.args.get("format", "").strip()
    sort = request.args.get("sort", "title_asc").strip()

    if genre_id is not None and genre_id < 1:
        genre_id = None

    if publisher_id is not None and publisher_id < 1:
        publisher_id = None

    if shelf_id is not None and shelf_id < 1:
        shelf_id = None

    page = request.args.get("page", 1, type=int)

    if page < 1:
        page = 1

    per_page = 10


    connection = get_db_connection()
    cursor = connection.cursor()

    # Build filter conditions
    conditions = []
    parameters = []


    if search:

        conditions.append(
            """
            (
                b.title ILIKE %s
                OR b.isbn ILIKE %s
                OR p.name ILIKE %s
                OR a_filter.first_name ILIKE %s
                OR a_filter.last_name ILIKE %s
                OR CONCAT_WS(
                    ' ',
                    a_filter.first_name,
                    a_filter.last_name
                ) ILIKE %s
            )
            """
        )

        search_value = f"%{search}%"

        parameters.extend([
            search_value,
            search_value,
            search_value,
            search_value,
            search_value,
            search_value
        ])


    if genre_id:
        conditions.append("g_filter.genre_id = %s")
        parameters.append(genre_id)


    if publisher_id:
        conditions.append("p.publisher_id = %s")
        parameters.append(publisher_id)


    if shelf_id:
        conditions.append("s_filter.shelf_id = %s")
        parameters.append(shelf_id)


    if book_format:
        conditions.append("c_filter.format = %s")
        parameters.append(book_format)

    # Shared joins
    base_from = """
        FROM books b
        LEFT JOIN publishers p
            ON b.publisher_id = p.publisher_id
        LEFT JOIN book_authors ba_filter
            ON b.book_id = ba_filter.book_id
        LEFT JOIN authors a_filter
            ON ba_filter.author_id = a_filter.author_id
        LEFT JOIN book_genres bg_filter
            ON b.book_id = bg_filter.book_id
        LEFT JOIN genres g_filter
            ON bg_filter.genre_id = g_filter.genre_id
        LEFT JOIN copies c_filter
            ON b.book_id = c_filter.book_id
        LEFT JOIN shelves s_filter
            ON c_filter.shelf_id = s_filter.shelf_id
    """


    where_clause = ""

    if conditions:
        where_clause = " WHERE " + " AND ".join(conditions)

    # Count filtered books
    count_query = f"""
        SELECT COUNT(DISTINCT b.book_id) AS total_items

        {base_from}

        {where_clause}
    """


    cursor.execute(count_query, parameters)

    total_items = cursor.fetchone()["total_items"]


    total_pages = max(
        1,
        (total_items + per_page - 1) // per_page
    )


    if page > total_pages:
        page = total_pages


    offset = (page - 1) * per_page

    # Sorting
    sort_options = {
        "title_asc": "b.title ASC",
        "title_desc": "b.title DESC",
        "year_desc": "b.publication_year DESC NULLS LAST",
        "year_asc": "b.publication_year ASC NULLS LAST"
    }


    order_by = sort_options.get(
        sort,
        "b.title ASC"
    )

    # Get books for current page
    query = f"""
        SELECT DISTINCT
            b.book_id,
            b.title,
            b.isbn,
            b.publication_year,
            b.cover_image,
            p.name AS publisher_name,

            (
                SELECT STRING_AGG(
                    DISTINCT CONCAT_WS(
                        ' ',
                        a2.first_name,
                        a2.last_name
                    ),
                    ', '
                )
                FROM authors a2
                JOIN book_authors ba2
                    ON a2.author_id = ba2.author_id
                WHERE ba2.book_id = b.book_id
            ) AS authors,

            (
                SELECT STRING_AGG(
                    DISTINCT g2.name,
                    ', '
                )
                FROM genres g2
                JOIN book_genres bg2
                    ON g2.genre_id = bg2.genre_id
                WHERE bg2.book_id = b.book_id
            ) AS genres,

            (
                SELECT STRING_AGG(
                    DISTINCT c2.format,
                    ', '
                )
                FROM copies c2
                WHERE
                    c2.book_id = b.book_id
                    AND c2.format IS NOT NULL
            ) AS formats,

            (
                SELECT MIN(c3.date_added)
                FROM copies c3
                WHERE c3.book_id = b.book_id
            ) AS date_added


        {base_from}

        {where_clause}

        ORDER BY {order_by}

        LIMIT %s
        OFFSET %s
    """

    book_parameters = parameters + [
        per_page,
        offset
    ]

    cursor.execute(
        query,
        book_parameters
    )

    books = cursor.fetchall()

    # Filter dropdown data
    cursor.execute(
        """
        SELECT genre_id, name
        FROM genres
        ORDER BY name;
        """
    )

    genres = cursor.fetchall()


    cursor.execute(
        """
        SELECT publisher_id, name
        FROM publishers
        ORDER BY name;
        """
    )

    publishers = cursor.fetchall()


    cursor.execute(
        """
        SELECT shelf_id, name
        FROM shelves
        ORDER BY name;
        """
    )

    shelves = cursor.fetchall()


    cursor.execute(
        """
        SELECT DISTINCT format
        FROM copies
        WHERE format IS NOT NULL
        ORDER BY format;
        """
    )

    formats = cursor.fetchall()


    # Showing X-Y of Z

    if total_items == 0:

        start_item = 0
        end_item = 0

    else:

        start_item = offset + 1
        end_item = min(
            offset + len(books),
            total_items
        )


    return render_template(
        "library.html",

        books=books,

        search=search,

        genres=genres,
        genre_id=genre_id,

        publishers=publishers,
        publisher_id=publisher_id,

        shelves=shelves,
        shelf_id=shelf_id,

        formats=formats,
        book_format=book_format,

        sort=sort,

        page=page,
        total_pages=total_pages,

        total_items=total_items,
        start_item=start_item,
        end_item=end_item
    )

# Home/Stats
@app.route("/")
@app.route("/statistics")
def home():

    connection = get_db_connection()
    cursor = connection.cursor()

    # Total books
    cursor.execute(
        """
        SELECT COUNT(*) AS total_books
        FROM books;
        """
    )

    total_books = cursor.fetchone()["total_books"]

    # Total copies
    cursor.execute(
        """
        SELECT COUNT(*) AS total_copies
        FROM copies;
        """
    )

    total_copies = cursor.fetchone()["total_copies"]

    # Total authors
    cursor.execute(
        """
        SELECT COUNT(*) AS total_authors
        FROM authors;
        """
    )

    total_authors = cursor.fetchone()["total_authors"]

    # Total genres
    cursor.execute(
        """
        SELECT COUNT(*) AS total_genres
        FROM genres;
        """
    )

    total_genres = cursor.fetchone()["total_genres"]

    # Total publishers
    cursor.execute(
        """
        SELECT COUNT(*) AS total_publishers
        FROM publishers;
        """
    )

    total_publishers = cursor.fetchone()["total_publishers"]

    cursor.execute(
        """
        SELECT COALESCE(SUM(purchase_price), 0) AS total_spent
        FROM copies;
        """
    )

    total_spent = cursor.fetchone()["total_spent"]

    cursor.execute(
        """
        SELECT COALESCE(AVG(purchase_price), 0) AS average_price
        FROM copies;
        """
    )

    average_price = cursor.fetchone()["average_price"]

    cursor.execute(
        """
        SELECT 
            g.genre_id,
            g.name,
            COUNT(DISTINCT bg.book_id) AS book_count
        FROM genres g
        LEFT JOIN book_genres bg
            ON g.genre_id = bg.genre_id
        GROUP BY g.genre_id, g.name
        ORDER BY book_count DESC, g.name;
        """
    )

    books_per_genre = cursor.fetchall()

    cursor.execute(
        """
        SELECT 
            s.shelf_id,
            s.name,
            COUNT(c.copy_id) AS copy_count
        FROM shelves s
        LEFT JOIN copies c
            ON s.shelf_id = c.shelf_id
        GROUP BY s.shelf_id, s.name
        ORDER BY copy_count DESC, s.name;
        """
    )

    copies_per_shelf = cursor.fetchall()

    cursor.execute(
        """
        SELECT
            format,
            COUNT(copy_id) AS copy_count
        FROM copies
        WHERE format IS NOT NULL
        GROUP BY format
        ORDER BY copy_count DESC, format;
        """
    )

    copies_per_format = cursor.fetchall()

    cursor.execute(
        """
        SELECT 
            g.name,
            COUNT(bg.book_id) AS book_count
        FROM genres g
        JOIN book_genres bg
            ON g.genre_id = bg.genre_id
        GROUP BY g.genre_id, g.name
        ORDER BY book_count DESC, g.name
        LIMIT 1;
        """
    )

    most_common_genre = cursor.fetchone()

    cursor.execute(
        """
        SELECT
            s.name,
            COUNT(c.copy_id) AS copy_count
        FROM shelves s
        JOIN copies c
            ON s.shelf_id = c.shelf_id
        GROUP BY s.shelf_id, s.name
        ORDER BY copy_count DESC, s.name
        LIMIT 1;
        """
    )

    most_populated_shelf = cursor.fetchone()


    return render_template(
        "statistics.html",
        total_books=total_books,
        total_copies=total_copies,
        total_authors=total_authors,
        total_genres=total_genres,
        total_publishers=total_publishers,
        total_spent=total_spent,
        average_price=average_price,
        books_per_genre=books_per_genre,
        copies_per_shelf=copies_per_shelf,
        copies_per_format=copies_per_format,
        most_common_genre=most_common_genre,
        most_populated_shelf=most_populated_shelf
    )


# Add book
@app.route("/books/add", methods=["GET", "POST"])
def add_book():

    connection = get_db_connection()

    if request.method == "POST":
        # Read book data
        title = request.form["title"].strip()
        isbn = normalize_isbn(request.form["isbn"])
        publication_year = request.form["publication_year"].strip()
        description = request.form["description"].strip() or None
        cover_file = request.files.get("cover_image")
        cover_image = None
        publisher_id = request.form["publisher_id"]
        publisher_name = request.form.get("publisher_name", "").strip()

        # Read author data
        existing_author_ids = request.form.getlist('existing_author_ids')
        author_first_name = request.form.get('author_first_name', '').strip()
        author_last_name = request.form.get('author_last_name', '').strip()

        # Read genre data 
        existing_genre_ids = request.form.getlist('existing_genre_ids')
        genre_name = request.form.get('genre_name', '').strip()

        # Read physical copy data
        shelf_id = request.form.get('shelf_id')
        new_shelf_name = request.form.get('new_shelf_name', '').strip()
        format = request.form['format']
        purchase_date = request.form.get('purchase_date')
        purchase_price = request.form.get('purchase_price')
        condition = request.form.get('condition', '').strip()
        copy_notes = request.form.get('copy_notes', '').strip()

        # Validate and convert values
        errors, publication_year = validate_book_values(
            title,
            isbn,
            publication_year
        )
        publisher_id = parse_optional_id(publisher_id, "publisher", errors)
        shelf_id = parse_optional_id(shelf_id, "shelf", errors)
        existing_author_ids = [
            parse_optional_id(value, "author", errors)
            for value in existing_author_ids
        ]
        existing_genre_ids = [
            parse_optional_id(value, "genre", errors)
            for value in existing_genre_ids
        ]
        existing_author_ids = [value for value in existing_author_ids if value]
        existing_genre_ids = [value for value in existing_genre_ids if value]

        if bool(author_first_name) != bool(author_last_name):
            errors.append("Enter both the first and last name for a new author.")

        if not format:
            errors.append("Choose a format for the physical copy.")

        purchase_date = parse_optional_date(purchase_date, errors)
        purchase_price = parse_optional_price(purchase_price, errors)
        condition = condition if condition else None
        copy_notes = copy_notes if copy_notes else None

        if format not in COPY_FORMATS:
            errors.append("Choose a valid copy format.")

        if condition and condition not in COPY_CONDITIONS:
            errors.append("Choose a valid condition.")

        if len(publisher_name) > 150:
            errors.append("Publisher name must be 150 characters or fewer.")

        if len(new_shelf_name) > 100:
            errors.append("Shelf name must be 100 characters or fewer.")

        if len(genre_name) > 100:
            errors.append("Genre name must be 100 characters or fewer.")

        if len(author_first_name) > 100 or len(author_last_name) > 100:
            errors.append("Author names must be 100 characters or fewer.")

        if errors:
            flash(" ".join(errors), "error")
            return redirect(url_for("add_book"))

        cursor = connection.cursor()

        cursor.execute(
            "SELECT 1 FROM books WHERE isbn = %s",
            (isbn,)
        )

        if cursor.fetchone():
            flash("A book with that ISBN is already in your library.", "error")
            return redirect(url_for("add_book"))

        try:
            cover_image = save_cover_image(cover_file)
        except ValueError as error:
            flash(str(error), "error")
            return redirect(url_for("add_book"))

        if new_shelf_name:
            shelf_id = get_or_create_shelf(cursor, new_shelf_name)

        if publisher_name:
            publisher_id = get_or_create_publisher(cursor, publisher_name)

        # Insert book
        cursor.execute(
            """
            INSERT INTO books
                (title, isbn, publication_year, description, cover_image, publisher_id)
            VALUES
                (%s, %s, %s, %s, %s, %s)
            RETURNING book_id
            """,
            (
                title, 
                isbn,
                publication_year,
                description,
                cover_image,
                publisher_id
            ),
        )

        book_id = cursor.fetchone()['book_id']

        # Authors
        author_ids = []

        for author_id in existing_author_ids:
            author_ids.append(author_id)

        if author_first_name and author_last_name:
            author_ids.append(
                get_or_create_author(
                    cursor,
                    author_first_name,
                    author_last_name
                )
            )

        # Connect book to author
        for author_id in dict.fromkeys(author_ids):
            cursor.execute(
                """
                INSERT INTO book_authors (book_id, author_id)
                VALUES (%s, %s)
                """, (
                    book_id,
                    author_id
                )
            )

        # Genres
        genre_ids = []

        for genre_id in existing_genre_ids:
            genre_ids.append(genre_id)

        if genre_name:
            genre_ids.append(
                get_or_create_genre(cursor, genre_name)
            )

        for genre_id in dict.fromkeys(genre_ids):
            cursor.execute(
                """
                INSERT INTO book_genres (book_id, genre_id)
                VALUES (%s, %s)
                """,
                (
                    book_id,
                    genre_id
                )
            )

        # Create physical copy
        cursor.execute(
            """
            INSERT INTO copies
            (
                book_id,
                shelf_id,
                format,
                purchase_date,
                purchase_price,
                condition,
                notes
            )
            VALUES
                (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                book_id,
                shelf_id,
                format,
                purchase_date,
                purchase_price,
                condition,
                copy_notes
            )
        ) 

        connection.commit()

        flash(f'"{title}" was added to your library.', "success")
        return redirect(url_for("library"))

    cursor = connection.cursor()

    # Get publishers
    cursor.execute(
        """
        SELECT publisher_id, name
        FROM publishers
        ORDER BY name
        """
    )
    publishers = cursor.fetchall()

    # Get authors
    cursor.execute(
        """
        SELECT author_id, first_name, last_name
        FROM authors
        ORDER BY last_name, first_name
        """
    )

    authors = cursor.fetchall()

    # Get genres
    cursor.execute(
        """
        SELECT  genre_id, name
        FROM genres
        ORDER BY name
        """
    )

    genres = cursor.fetchall()

    cursor.execute(
        """
        SELECT shelf_id, name
        FROM shelves
        ORDER BY Name
        """
    )

    shelves = cursor.fetchall()

    return render_template(
        "add_book.html", 
        publishers=publishers, 
        authors=authors,
        genres=genres,
        shelves=shelves

    )

# Book details
@app.route("/books/<int:book_id>")
def book_details(book_id):
    connection = get_db_connection()
    cursor = connection.cursor()

    # Get book
    cursor.execute(
        """
        SELECT
            b.book_id,
            b.title,
            b.isbn,
            b.publication_year,
            b.description,
            b.cover_image,
            p.name AS publisher_name
        FROM books b
        LEFT JOIN publishers p
            ON b.publisher_id = p.publisher_id
        WHERE b.book_id = %s
        """,
        (book_id,)
    )

    book = cursor.fetchone()

    # Get authors
    cursor.execute(
        """
        SELECT 
            a.author_id,
            a.first_name,
            a.last_name
        FROM authors a
        JOIN book_authors ba
            ON a.author_id = ba.author_id
        WHERE ba.book_id = %s
        ORDER BY a.last_name, a.first_name
        """,
        (book_id,)
    )

    authors = cursor.fetchall()

    # Get genres
    cursor.execute(
        """
        SELECT 
            g.genre_id,
            g.name
        FROM genres g
        JOIN book_genres bg
            ON g.genre_id = bg.genre_id
        WHERE bg.book_id = %s
        ORDER BY g.name
        """,
        (book_id,)
    )

    genres = cursor.fetchall()

    # Get physical copies for the book
    cursor.execute(
        """
        SELECT
            c.copy_id,
            c.format,
            c.condition,
            c.purchase_date,
            c.purchase_price,
            c.notes,
            c.date_added,
            s.shelf_id,
            s.name AS shelf_name
        FROM copies c
        LEFT JOIN shelves s
            on c.shelf_id = s.shelf_id
        WHERE c.book_id = %s
        ORDER BY c.copy_id
        """,
        (book_id,)
    )

    copies = cursor.fetchall()

    if book is None:
        return "Book not found", 404

    return render_template(
        "book_details.html",
        book=book,
        authors=authors,
        genres=genres,
        copies=copies
    )


# Edit book
@app.route("/books/<int:book_id>/edit", methods=["GET", "POST"])
def edit_book(book_id):

    connection = get_db_connection()
    cursor = connection.cursor()


    # Save changes

    if request.method == "POST":

        # Read book data
        title = request.form["title"].strip()
        isbn = normalize_isbn(request.form["isbn"])
        publication_year_value = request.form["publication_year"].strip()
        description = request.form["description"].strip() or None

        publisher_name = request.form.get(
            "publisher_name",
            ""
        ).strip()

        author_first_name = request.form.get(
            "author_first_name",
            ""
        ).strip()

        author_last_name = request.form.get(
            "author_last_name",
            ""
        ).strip()

        existing_author_ids = request.form.getlist("existing_author_ids")
        existing_genre_ids = request.form.getlist("existing_genre_ids")
        genre_name = request.form.get("genre_name", "").strip()
        copy_id_value = request.form.get("copy_id", "")
        shelf_id_value = request.form.get("shelf_id", "")
        new_shelf_name = request.form.get("new_shelf_name", "").strip()
        copy_format = request.form.get("format", "").strip()
        purchase_date_value = request.form.get("purchase_date", "")
        purchase_price_value = request.form.get("purchase_price", "")
        condition = request.form.get("condition", "").strip() or None
        copy_notes = request.form.get("copy_notes", "").strip() or None

        errors, publication_year = validate_book_values(
            title,
            isbn,
            publication_year_value
        )
        author_ids = [
            parse_optional_id(value, "author", errors)
            for value in existing_author_ids
        ]
        genre_ids = [
            parse_optional_id(value, "genre", errors)
            for value in existing_genre_ids
        ]
        author_ids = [value for value in author_ids if value]
        genre_ids = [value for value in genre_ids if value]
        copy_id = parse_optional_id(copy_id_value, "copy", errors)
        shelf_id = parse_optional_id(shelf_id_value, "shelf", errors)
        purchase_price = parse_optional_price(purchase_price_value, errors)
        purchase_date = parse_optional_date(purchase_date_value, errors)

        if bool(author_first_name) != bool(author_last_name):
            errors.append("Enter both the first and last name for a new author.")

        if copy_id and not copy_format:
            errors.append("An existing physical copy must have a format.")

        if copy_format and copy_format not in COPY_FORMATS:
            errors.append("Choose a valid copy format.")

        if condition and condition not in COPY_CONDITIONS:
            errors.append("Choose a valid condition.")

        if len(publisher_name) > 150:
            errors.append("Publisher name must be 150 characters or fewer.")

        if len(new_shelf_name) > 100:
            errors.append("Shelf name must be 100 characters or fewer.")

        if len(genre_name) > 100:
            errors.append("Genre name must be 100 characters or fewer.")

        if len(author_first_name) > 100 or len(author_last_name) > 100:
            errors.append("Author names must be 100 characters or fewer.")

        if errors:
            flash(" ".join(errors), "error")
            return redirect(url_for("edit_book", book_id=book_id))


        # Current cover image

        cursor.execute(
            """
            SELECT cover_image
            FROM books
            WHERE book_id = %s
            """,
            (book_id,)
        )

        existing_book = cursor.fetchone()


        if existing_book is None:
            return "Book not found", 404

        cursor.execute(
            "SELECT 1 FROM books WHERE isbn = %s AND book_id <> %s",
            (isbn, book_id)
        )

        if cursor.fetchone():
            flash("Another book already uses that ISBN.", "error")
            return redirect(url_for("edit_book", book_id=book_id))


        # Cover image

        cover_file = request.files.get("cover_image")

        if cover_file and cover_file.filename:

            try:
                new_cover_image = save_cover_image(
                    cover_file
                )
            except ValueError as error:
                flash(str(error), "error")
                return redirect(url_for("edit_book", book_id=book_id))

            # Only replace if upload succeeded
            if new_cover_image:
                cover_image = new_cover_image
            else:
                cover_image = existing_book["cover_image"]

        else:

            # Keep existing cover
            cover_image = existing_book["cover_image"]


        # Publisher

        publisher_id = None


        if publisher_name:
            publisher_id = get_or_create_publisher(cursor, publisher_name)


        # Update book

        cursor.execute(
            """
            UPDATE books
            SET
                title = %s,
                isbn = %s,
                publication_year = %s,
                description = %s,
                cover_image = %s,
                publisher_id = %s
            WHERE book_id = %s
            """,
            (
                title,
                isbn,
                publication_year,
                description,
                cover_image,
                publisher_id,
                book_id
            )
        )


        # Authors

        if author_first_name and author_last_name:
            author_ids.append(
                get_or_create_author(
                    cursor,
                    author_first_name,
                    author_last_name
                )
            )

        cursor.execute(
            "DELETE FROM book_authors WHERE book_id = %s",
            (book_id,)
        )

        for author_id in dict.fromkeys(author_ids):
            cursor.execute(
                """
                INSERT INTO book_authors
                    (book_id, author_id)
                VALUES
                    (%s, %s)
                """,
                (
                    book_id,
                    author_id
                )
            )

        if genre_name:
            genre_ids.append(
                get_or_create_genre(cursor, genre_name)
            )

        cursor.execute(
            "DELETE FROM book_genres WHERE book_id = %s",
            (book_id,)
        )

        for genre_id in dict.fromkeys(genre_ids):
            cursor.execute(
                "INSERT INTO book_genres (book_id, genre_id) VALUES (%s, %s)",
                (book_id, genre_id)
            )

        if new_shelf_name:
            shelf_id = get_or_create_shelf(cursor, new_shelf_name)

        if copy_id:
            cursor.execute(
                """
                UPDATE copies
                SET shelf_id = %s,
                    format = %s,
                    purchase_date = %s,
                    purchase_price = %s,
                    condition = %s,
                    notes = %s
                WHERE copy_id = %s AND book_id = %s
                """,
                (
                    shelf_id,
                    copy_format,
                    purchase_date,
                    purchase_price,
                    condition,
                    copy_notes,
                    copy_id,
                    book_id
                )
            )
        elif copy_format:
            cursor.execute(
                """
                INSERT INTO copies
                    (book_id, shelf_id, format, purchase_date, purchase_price, condition, notes)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    book_id,
                    shelf_id,
                    copy_format,
                    purchase_date,
                    purchase_price,
                    condition,
                    copy_notes
                )
            )


        # Save

        connection.commit()

        if cover_image != existing_book["cover_image"]:
            remove_managed_cover(existing_book["cover_image"])

        flash(f'Changes to "{title}" were saved.', "success")
        return redirect(
            url_for(
                "book_details",
                book_id=book_id
            )
        )


    # Load current book

    cursor.execute(
        """
        SELECT
            b.book_id,
            b.title,
            b.isbn,
            b.publication_year,
            b.description,
            b.cover_image,
            b.publisher_id,
            p.name AS publisher_name
        FROM books b
        LEFT JOIN publishers p
            ON b.publisher_id = p.publisher_id
        WHERE b.book_id = %s
        """,
        (book_id,)
    )

    book = cursor.fetchone()

    if book is None:
        return "Book not found", 404


    cursor.execute(
        "SELECT author_id, first_name, last_name FROM authors ORDER BY last_name, first_name"
    )
    authors = cursor.fetchall()

    cursor.execute(
        "SELECT author_id FROM book_authors WHERE book_id = %s",
        (book_id,)
    )
    selected_author_ids = {row["author_id"] for row in cursor.fetchall()}

    cursor.execute(
        "SELECT genre_id, name FROM genres ORDER BY name"
    )
    genres = cursor.fetchall()

    cursor.execute(
        "SELECT genre_id FROM book_genres WHERE book_id = %s",
        (book_id,)
    )
    selected_genre_ids = {row["genre_id"] for row in cursor.fetchall()}

    cursor.execute(
        "SELECT shelf_id, name FROM shelves ORDER BY name"
    )
    shelves = cursor.fetchall()

    cursor.execute(
        """
        SELECT copy_id, shelf_id, format, purchase_date, purchase_price, condition, notes
        FROM copies
        WHERE book_id = %s
        ORDER BY copy_id
        LIMIT 1
        """,
        (book_id,)
    )
    copy = cursor.fetchone()

    cursor.execute(
        "SELECT COUNT(*) AS copy_count FROM copies WHERE book_id = %s",
        (book_id,)
    )
    copy_count = cursor.fetchone()["copy_count"]


    return render_template(
        "edit_book.html",
        book=book,
        authors=authors,
        selected_author_ids=selected_author_ids,
        genres=genres,
        selected_genre_ids=selected_genre_ids,
        shelves=shelves,
        copy=copy,
        copy_count=copy_count
    )

# Delete book
@app.route("/books/<int:book_id>/delete", methods=["POST"])
def delete_book(book_id):
    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute(
        "SELECT title, cover_image FROM books WHERE book_id = %s",
        (book_id,)
    )
    book = cursor.fetchone()

    if book is None:
        return "Book not found", 404

    # Delete physical copies first
    cursor.execute(
        """
        DELETE FROM copies
        WHERE book_id = %s
        """,
        (book_id,)
    )

    cursor.execute(
        """
        DELETE FROM books
        WHERE book_id = %s
        """,
        (book_id,)
    )

    connection.commit()

    remove_managed_cover(book["cover_image"])

    flash(f'"{book["title"]}" was removed from your library.', "success")
    return redirect(url_for("library"))

# Authors
@app.route("/authors")
def authors():
    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT 
            author_id,
            first_name,
            last_name
        FROM authors
        ORDER BY last_name, first_name
        """
    )

    authors = cursor.fetchall()

    return render_template(
        "authors.html",
        authors=authors
    )

@app.route("/authors/<int:author_id>")
def author_details(author_id):

    connection = get_db_connection()
    cursor = connection.cursor()

    # Get author
    cursor.execute(
        """
        SELECT
            author_id,
            first_name,
            last_name,
            bio
        FROM authors
        WHERE author_id = %s
        """,
        (author_id,)
    )

    author = cursor.fetchone()

    if author is None:
        return "Author not found", 404

    # Get books written by author
    cursor.execute(
        """
        SELECT 
            b.book_id,
            b.title,
            b.publication_year,
            b.cover_image
        FROM books b

        JOIN book_authors ba
            ON b.book_id = ba.book_id
        WHERE ba.author_id = %s
        ORDER BY
            b.publication_year NULLS LAST,
            b.title
        """,
        (author_id,)
    )

    books = cursor.fetchall()

    return render_template(
        "author_details.html",
        author=author,
        books=books
    )

# Bookshelf 
@app.route("/bookshelf")
def bookshelf():
    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT
            s.shelf_id,
            s.name AS shelf_name,
            c.copy_id,
            b.book_id,
            b.title,
            b.cover_image
        FROM shelves s
        LEFT JOIN copies c
            ON s.shelf_id = c.shelf_id
        LEFT JOIN books b
            ON c.book_id = b.book_id
        ORDER BY s.name, b.title
        """
    )

    rows = cursor.fetchall()

    shelves = {}

    for row in rows:

        shelf_id = row["shelf_id"]

        if shelf_id not in shelves:
            shelves[shelf_id] = {
                "shelf_id": shelf_id,
                "shelf_name": row["shelf_name"],
                "books": []
            }

        if row["book_id"] is not None:
            shelves[shelf_id]["books"].append({
                "copy_id": row["copy_id"],
                "book_id": row["book_id"],
                "title": row["title"],
                "cover_image": row["cover_image"]
            })

    return render_template(
        "bookshelf.html",
        shelves=shelves.values()
    )
        
if __name__ == "__main__":
    debug_enabled = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    app.run(debug=debug_enabled)
