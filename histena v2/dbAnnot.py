import sqlite3 as sq 
import os

conn = None
db = None
current_db_path = "annot.db"

def init(db_name=None):
    global conn, db, current_db_path
    if conn:
        conn.close()
    
    # Behavior: If no db_name provided, try to find ANY .db file in current dir
    if not db_name or not os.path.exists(db_name):
        dbs = [f for f in os.listdir('.') if f.endswith('.db')]
        if dbs:
            db_name = dbs[0]
        else:
            # If absolutely none exist, fallback to annot.db (will be created if init_db called)
            db_name = "annot.db"
            
    current_db_path = db_name
    conn = sq.connect(db_name, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    db = conn.cursor()

def create_new(name):
    path = name if name.endswith(".db") else name + ".db"
    if os.path.exists(path):
        raise Exception("El projecte ja existeix")
    
    new_conn = sq.connect(path)
    with open("initDB.sql", "r") as f:
        new_conn.executescript(f.read())
    new_conn.close()
    return path

def execute(sql, params=()):
    db.execute(sql, params)
    return db

def commit():
    conn.commit()

def fetch_all(sql, params=()):
    db.execute(sql, params)
    return db.fetchall()

def fetch_one(sql, params=()):
    db.execute(sql, params)
    return db.fetchone()

def last_id():
    return db.lastrowid
