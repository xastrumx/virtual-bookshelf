import os

import psycopg
from dotenv import load_dotenv
from flask import g, has_app_context
from psycopg.rows import dict_row

load_dotenv()

def create_db_connection():
    return psycopg.connect(
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        row_factory=dict_row
    )


def get_db_connection():
    if not has_app_context():
        return create_db_connection()

    if "db_connection" not in g:
        g.db_connection = create_db_connection()

    return g.db_connection


def close_db_connection(_exception=None):
    connection = g.pop("db_connection", None)

    if connection is not None:
        connection.close()
