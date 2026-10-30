
import sqlite3
import os
from datetime import datetime

# Use the same folder as this Python file
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, "library_recovered.db")

# Automatically create a backup before restoring
if os.path.exists(DATABASE):
    backup_name = "library_backup_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".db"
    backup_path = os.path.join(BASE_DIR, backup_name)

    source = sqlite3.connect(DATABASE)
    backup = sqlite3.connect(backup_path)
    source.backup(backup)
    backup.close()
    source.close()

    print("Backup created:", backup_name)

conn = sqlite3.connect(DATABASE)
cur = conn.cursor()

# Create tables
cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    role TEXT NOT NULL
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS books (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    author TEXT NOT NULL,
    category TEXT NOT NULL,
    isbn TEXT,
    quantity INTEGER NOT NULL,
    available INTEGER NOT NULL
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS issue_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    book_id INTEGER NOT NULL,
    issue_date TEXT NOT NULL,
    due_date TEXT,
    return_date TEXT,
    fine INTEGER DEFAULT 0,
    status TEXT NOT NULL
)
""")

# Clear old records before inserting the restored records
cur.execute("DELETE FROM issue_records")
cur.execute("DELETE FROM books")
cur.execute("DELETE FROM users")

# Restore users
users = [
    (1, "Administrator", "admin", "admin123", "admin"),
    (2, "Librarian", "librarian", "lib123", "librarian"),
    (3, "Aqsa", "Student1", "1234", "student"),
    (4, "Rahul", "Student2", "12345", "student"),
    (5, "Reeta", "Student3", "CHANGE_ME", "student")
]

cur.executemany("""
INSERT INTO users (id, name, username, password, role)
VALUES (?, ?, ?, ?, ?)
""", users)

# Restore books
books = [
    (1, "Python Programming", "John Smith", "Programming", "123456", 5, 5),
    (2, "Data Structures and Algorithms", "Mark Allen", "Computer Science", "234567", 5, 5),
    (3, "Database Management System", "Korth", "Database", "345678", 5, 5),
    (4, "Computer Networks", "Andrew Tanenbaum", "Networking", "567890", 4, 3),
    (5, "Java Programming", "Herbert Schildt", "Programming", "89123", 5, 4)
]

cur.executemany("""
INSERT INTO books
(id, title, author, category, isbn, quantity, available)
VALUES (?, ?, ?, ?, ?, ?, ?)
""", books)

# Restore 8 issue/return history records
history = [
    (1, 5, 4, "2026-10-28", "2026-11-04", None, 0, "Issued"),
    (2, 3, 5, "2026-10-25", "2026-11-01", None, 0, "Issued"),
    (3, 3, 4, "2026-10-16", "2026-10-23", "2026-10-25", 20, "Returned"),
    (4, 3, 1, "2026-10-02", "2026-10-09", "2026-10-16", 70, "Returned"),
    (5, 4, 1, "2026-10-01", "2026-10-08", "2026-10-01", 0, "Returned"),
    (6, 3, 1, "2026-10-01", None, "2026-10-01", 0, "Returned"),
    (7, 3, 1, "2026-10-01", None, "2026-10-01", 0, "Returned"),
    (8, 3, 1, "2026-10-01", None, "2026-10-01", 0, "Returned")
]

cur.executemany("""
INSERT INTO issue_records
(id, user_id, book_id, issue_date, due_date, return_date, fine, status)
VALUES (?, ?, ?, ?, ?, ?, ?, ?)
""", history)

conn.commit()

# Verify restored data
print("\nDATABASE RESTORED SUCCESSFULLY!")
print("TOTAL USERS:", cur.execute("SELECT COUNT(*) FROM users").fetchone()[0])
print("TOTAL BOOKS:", cur.execute("SELECT COUNT(*) FROM books").fetchone()[0])
print("TOTAL HISTORY RECORDS:", cur.execute("SELECT COUNT(*) FROM issue_records").fetchone()[0])

# Set one issued book as overdue for testing
cur.execute("""
UPDATE issue_records
SET due_date = '2026-10-28'
WHERE id = 1 AND status = 'Issued'
""")

conn.commit()
conn.close()
