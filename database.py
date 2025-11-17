import os
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2 import sql

from dotenv import load_dotenv

load_dotenv()

DB_NAME = os.getenv("DB_NAME", "hub_controller")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")
DB_HOST = os.getenv("DB_HOST", "shared_postgres")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_TABLE_NAME = os.getenv("DB_TABLE_NAME", "event_event")
# Maximum historical window the application is allowed to expose.
# Accepted format is any PostgreSQL interval literal, e.g. "30 days", "4 weeks", "1 year"
# A temporary view (defined per-connection) will be created to transparently
# filter the underlying data set to this window.
DATA_TIME_WINDOW = os.getenv("DATA_TIME_WINDOW", "30 days")


def query_database(query):
    """
    Connects to the PostgreSQL database and executes the given SQL query.

    Parameters:
        sql (str): The SQL query string with placeholders.

    Returns:
        list or dict: A list of records (as dictionaries) if the query succeeds,
                      or an error message dictionary if the query fails.
    """
    try:
        connection = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD
        )
        cursor = connection.cursor(cursor_factory=RealDictCursor)

        try:
            cursor.execute(
                sql.SQL(
                    """
                    CREATE OR REPLACE TEMP VIEW {table_name} AS
                    SELECT *
                    FROM public.{table_name}
                    WHERE start_time >= now() - interval %s
                    """
                ).format(table_name=sql.Identifier(DB_TABLE_NAME)),
                [DATA_TIME_WINDOW],
            )
            connection.commit()
        except Exception as e:
            # If creating the view fails we still want to surface the error
            # back to the caller rather than silently continuing.
            cursor.close()
            connection.close()
            return {"error": f"Failed to enforce data window: {e}"}
        cursor.execute(sql.SQL(query))
        results = cursor.fetchall()
        connection.commit()
        cursor.close()
        connection.close()
        return results
    except Exception as e:
        return {"error": str(e)}
