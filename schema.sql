-- Data-free PostgreSQL schema for the personal Virtual Bookshelf.
-- Create the database first, then run: psql "$DATABASE_URL" -f schema.sql

CREATE TABLE publishers (
    publisher_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name varchar(150) NOT NULL UNIQUE
);

CREATE TABLE authors (
    author_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    first_name varchar(100) NOT NULL,
    last_name varchar(100) NOT NULL,
    bio text
);

CREATE TABLE genres (
    genre_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name varchar(100) NOT NULL UNIQUE
);

CREATE TABLE shelves (
    shelf_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name varchar(100) NOT NULL,
    location varchar(100),
    shelf_number integer
);

CREATE TABLE books (
    book_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    isbn varchar(13) NOT NULL UNIQUE,
    title varchar(255) NOT NULL,
    publisher_id integer REFERENCES publishers(publisher_id) ON DELETE SET NULL,
    publication_year smallint,
    description text,
    cover_image text
);

CREATE TABLE book_authors (
    book_id integer NOT NULL REFERENCES books(book_id) ON DELETE CASCADE,
    author_id integer NOT NULL REFERENCES authors(author_id) ON DELETE CASCADE,
    PRIMARY KEY (book_id, author_id)
);

CREATE TABLE book_genres (
    book_id integer NOT NULL REFERENCES books(book_id) ON DELETE CASCADE,
    genre_id integer NOT NULL REFERENCES genres(genre_id) ON DELETE CASCADE,
    PRIMARY KEY (book_id, genre_id)
);

CREATE TABLE copies (
    copy_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    book_id integer NOT NULL REFERENCES books(book_id),
    shelf_id integer REFERENCES shelves(shelf_id) ON DELETE SET NULL,
    format varchar(50) NOT NULL,
    purchase_date date,
    purchase_price numeric(10, 2),
    condition varchar(50),
    notes text,
    date_added timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_books_title ON books (title);
CREATE INDEX idx_books_publisher_id ON books (publisher_id);
CREATE INDEX idx_book_authors_author_id ON book_authors (author_id);
CREATE INDEX idx_book_genres_genre_id ON book_genres (genre_id);
CREATE INDEX idx_copies_book_id ON copies (book_id);
CREATE INDEX idx_copies_shelf_id ON copies (shelf_id);
