import sqlite3
import os


def init_db():
    # removes all databases
    for file in os.listdir("./MESsy/DB"):
        if os.path.isfile(os.path.join("./MESsy/DB", file)) and ".sqlite3" in file:
            os.remove(os.path.join("./MESsy/DB", file))


# writes the DB and initializes it
    with sqlite3.connect("./MESsy/DB/DB.sqlite3") as conn:
        cursor = conn.cursor()
        with open("./MESsy/SQL/init_db.sql", "r") as fp_init:
            cursor.executescript(fp_init.read())


if __name__ == "__main__":
    init_db()
