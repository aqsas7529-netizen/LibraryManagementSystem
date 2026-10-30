import os

from flask import Flask, render_template, request, redirect, session
import sqlite3
from functools import wraps
from datetime import date, timedelta

app = Flask(__name__)
app.secret_key = "library_management_secret"

DATABASE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "library_recovered.db"
)
FINE_PER_DAY = 10
ISSUE_DAYS = 7


# ==================================================
# DATABASE
# ==================================================

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn



def create_tables():
   
    conn = get_db()
   
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL
        )
    """)

    conn.execute("""
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

    conn.execute("""
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

    # Fix older databases by adding missing columns.
    columns = [
        row["name"]
        for row in conn.execute(
            "PRAGMA table_info(issue_records)"
        ).fetchall()
    ]

    if "due_date" not in columns:
        conn.execute(
            "ALTER TABLE issue_records ADD COLUMN due_date TEXT"
        )

    if "fine" not in columns:
        conn.execute(
            "ALTER TABLE issue_records ADD COLUMN fine INTEGER DEFAULT 0"
        )

    # Ensure default admin exists.
    admin = conn.execute(
        "SELECT id FROM users WHERE username = ?",
        ("admin",)
    ).fetchone()

    if admin is None:
        conn.execute("""
            INSERT INTO users (name, username, password, role)
            VALUES (?, ?, ?, ?)
        """, ("Administrator", "admin", "admin123", "admin"))

    # Ensure a librarian account exists.
    librarian = conn.execute(
        "SELECT id FROM users WHERE username = ?",
        ("librarian",)
    ).fetchone()

    if librarian is None:
        conn.execute("""
            INSERT INTO users (name, username, password, role)
            VALUES (?, ?, ?, ?)
        """, ("Librarian", "librarian", "lib123", "librarian"))

    conn.commit()
    conn.close()

create_tables()
# ==================================================
# AUTHENTICATION
# ==================================================

def login_required(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect("/login")
        return function(*args, **kwargs)
    return wrapper


# ==================================================
# AUTHORIZATION
# ==================================================

def roles_required(*allowed_roles):
    def decorator(function):
        @wraps(function)
        def wrapper(*args, **kwargs):
            if "user_id" not in session:
                return redirect("/login")

            if session.get("role") not in allowed_roles:
                return "Access denied: You are not authorized.", 403

            return function(*args, **kwargs)
        return wrapper
    return decorator


def admin_required(function):
    return roles_required("admin")(function)


def librarian_required(function):
    return roles_required("librarian")(function)


def staff_required(function):
    return roles_required("admin", "librarian")(function)


# ==================================================
# HOME / DASHBOARD
# ==================================================

@app.route("/")
@login_required
def index():
    role = session.get("role")

    if role == "student":
        return redirect("/books")

    conn = get_db()
    today = str(date.today())

    total_books = conn.execute(
        "SELECT COUNT(*) FROM books"
    ).fetchone()[0]

    available_books = conn.execute(
        "SELECT COALESCE(SUM(available), 0) FROM books"
    ).fetchone()[0]

    issued_books = conn.execute("""
        SELECT COUNT(*) FROM issue_records
        WHERE status = 'Issued'
    """).fetchone()[0]

    total_users = conn.execute(
        "SELECT COUNT(*) FROM users"
    ).fetchone()[0]

          
    overdue_books = conn.execute(
        """
        SELECT COUNT(*)
        FROM issue_records
        WHERE TRIM(status) = 'Issued'
          AND due_date IS NOT NULL
          AND DATE(due_date) < DATE(?)
        """,
        (today,)
    ).fetchone()[0]


    recent_transactions = conn.execute("""
        SELECT
            issue_records.issue_date,
            issue_records.due_date,
            issue_records.return_date,
            issue_records.status,
            users.name,
            books.title
        FROM issue_records
        JOIN users ON issue_records.user_id = users.id
        JOIN books ON issue_records.book_id = books.id
        ORDER BY issue_records.id DESC
        LIMIT 5
    """).fetchall()

    recent_books = conn.execute("""
        SELECT id, title, author, category, available, quantity
        FROM books
        ORDER BY id DESC
        LIMIT 5
    """).fetchall()

    conn.close()

    # Do not pass the admin username or account details to its dashboard.
    if role == "admin":
        return render_template(
            "index.html",
            total_books=total_books,
            available_books=available_books,
            issued_books=issued_books,
            total_users=total_users,
            overdue_books=overdue_books,
            recent_transactions=recent_transactions,
            recent_books=recent_books,
            role="admin"
        )

    # Librarian sees operational dashboard statistics.
    return render_template(
        "index.html",
        total_books=total_books,
        available_books=available_books,
        issued_books=issued_books,
        total_users=total_users,
        overdue_books=overdue_books,
        recent_transactions=recent_transactions,
        recent_books=recent_books,
        role="librarian"
    )


# ==================================================
# REGISTER STUDENT
# ==================================================

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not name or not username or not password:
            return render_template(
                "register.html",
                error="Please fill in all fields."
            )

        conn = get_db()

        existing_user = conn.execute(
            "SELECT id FROM users WHERE username = ?",
            (username,)
        ).fetchone()

        if existing_user:
            conn.close()
            return render_template(
                "register.html",
                error="Username already exists."
            )

        conn.execute("""
            INSERT INTO users (name, username, password, role)
            VALUES (?, ?, ?, 'student')
        """, (name, username, password))

        conn.commit()
        conn.close()

        return redirect("/login")

    return render_template("register.html")


# ==================================================
# LOGIN
# ==================================================

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        conn = get_db()

        user = conn.execute("""
            SELECT id, name, username, password, role
            FROM users
            WHERE username = ? AND password = ?
        """, (username, password)).fetchone()

        conn.close()

        if user:
            session.clear()
            session["user_id"] = user["id"]
            session["role"] = user["role"]
            print("LOGIN ROLE:", user["role"])
            print("LOGIN USERNAME:", user["username"])

            # Keep the username for session operations,
            # but do not display it on the admin dashboard.
            if user["role"] != "admin":
                session["username"] = user["username"]
                session["name"] = user["name"]

            return redirect("/")

        return render_template(
            "login.html",
            error="Invalid username or password."
        )

    return render_template("login.html")


# ==================================================
# LOGOUT
# ==================================================

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


# ==================================================
# VIEW / SEARCH BOOKS
# ==================================================

@app.route("/books")
@login_required
def books():
    search = request.args.get("search", "").strip()
    user_id = session["user_id"]

    conn = get_db()

    if search:
        book_list = conn.execute("""
            SELECT * FROM books
            WHERE title LIKE ?
               OR author LIKE ?
               OR category LIKE ?
               OR isbn LIKE ?
            ORDER BY id DESC
        """, tuple(["%" + search + "%"] * 4)).fetchall()
    else:
        book_list = conn.execute(
            "SELECT * FROM books ORDER BY id DESC"
        ).fetchall()

    issued_books = conn.execute("""
        SELECT book_id FROM issue_records
        WHERE user_id = ? AND status = 'Issued'
    """, (user_id,)).fetchall()

    issued_book_ids = [row["book_id"] for row in issued_books]

    conn.close()

    return render_template(
        "books.html",
        books=book_list,
        search=search,
        issued_book_ids=issued_book_ids,
        role=session.get("role")
    )


# ==================================================
# ADD BOOK
# ==================================================

@app.route("/add", methods=["GET", "POST"])
@staff_required
def add_book():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        author = request.form.get("author", "").strip()
        category = request.form.get("category", "").strip()
        isbn = request.form.get("isbn", "").strip()

        try:
            quantity = int(request.form.get("quantity", "0"))
        except ValueError:
            return render_template(
                "add_book.html",
                error="Quantity must be a valid number."
            )

        if not title or not author or not category or quantity < 0:
            return render_template(
                "add_book.html",
                error="Enter valid book details."
            )

        conn = get_db()
        conn.execute("""
            INSERT INTO books
                (title, author, category, isbn, quantity, available)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (title, author, category, isbn, quantity, quantity))

        conn.commit()
        conn.close()
        return redirect("/books")

    return render_template("add_book.html")


# ==================================================
# EDIT BOOK
# ==================================================

@app.route("/edit/<int:id>", methods=["GET", "POST"])
@staff_required
def edit_book(id):
    conn = get_db()

    book = conn.execute(
        "SELECT * FROM books WHERE id = ?",
        (id,)
    ).fetchone()

    if book is None:
        conn.close()
        return redirect("/books")

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        author = request.form.get("author", "").strip()
        category = request.form.get("category", "").strip()
        isbn = request.form.get("isbn", "").strip()

        try:
            quantity = int(request.form.get("quantity", "0"))
        except ValueError:
            conn.close()
            return render_template(
                "edit_book.html",
                book=book,
                error="Quantity must be a valid number."
            )

        issued_quantity = book["quantity"] - book["available"]
        available = quantity - issued_quantity

        if (
            not title or not author or not category
            or quantity < 0 or available < 0
        ):
            conn.close()
            return render_template(
                "edit_book.html",
                book=book,
                error="Invalid details or quantity is below books already issued."
            )

        conn.execute("""
            UPDATE books
            SET title = ?, author = ?, category = ?, isbn = ?,
                quantity = ?, available = ?
            WHERE id = ?
        """, (
            title, author, category, isbn,
            quantity, available, id
        ))

        conn.commit()
        conn.close()
        return redirect("/books")

    conn.close()
    return render_template("edit_book.html", book=book)


# ==================================================
# DELETE BOOK
# ==================================================

@app.route("/delete/<int:id>", methods=["POST"])
@admin_required
def delete_book(id):
    conn = get_db()

    transaction = conn.execute("""
        SELECT id FROM issue_records
        WHERE book_id = ?
        LIMIT 1
    """, (id,)).fetchone()

    if transaction:
        conn.close()
        return redirect("/books")

    conn.execute("DELETE FROM books WHERE id = ?", (id,))
    conn.commit()
    conn.close()

    return redirect("/books")


# ==================================================
# ISSUE BOOK
# Librarian issues books to students.
# ==================================================

@app.route("/issue/<int:id>", methods=["POST"])
@librarian_required
def issue_book(id):
    student_username = request.form.get("username", "").strip()

    # Also accept older forms that use the student field.
    if not student_username:
        student_username = request.form.get("student", "").strip()

    conn = get_db()

    student = conn.execute("""
        SELECT id FROM users
        WHERE username = ? AND role = 'student'
    """, (student_username,)).fetchone()

    if student is None:
        conn.close()
        return "Student username not found.", 400

    book = conn.execute(
        "SELECT * FROM books WHERE id = ?",
        (id,)
    ).fetchone()

    if book is None:
        conn.close()
        return "Book not found.", 404

    if book["available"] <= 0:
        conn.close()
        return "This book is not currently available.", 400

    duplicate = conn.execute("""
        SELECT id FROM issue_records
        WHERE user_id = ? AND book_id = ? AND status = 'Issued'
    """, (student["id"], id)).fetchone()

    if duplicate:
        conn.close()
        return "This student already has this book issued.", 400

    issue_date = date.today()
    due_date = issue_date + timedelta(days=ISSUE_DAYS)

    conn.execute("""
        UPDATE books SET available = available - 1
        WHERE id = ? AND available > 0
    """, (id,))

    conn.execute("""
        INSERT INTO issue_records
            (user_id, book_id, issue_date, due_date,
             return_date, fine, status)
        VALUES (?, ?, ?, ?, NULL, 0, 'Issued')
    """, (
        student["id"], id, str(issue_date), str(due_date)
    ))

    conn.commit()
    conn.close()
    return redirect("/books")


# ==================================================
# RETURN BOOK
# ==================================================

@app.route("/return/<int:id>", methods=["POST"])
@librarian_required
def return_book(id):
    conn = get_db()

    record = conn.execute("""
        SELECT * FROM issue_records
        WHERE id = ? AND status = 'Issued'
    """, (id,)).fetchone()

    # Backward compatibility if an old form sends a book ID.
    if record is None:
        record = conn.execute("""
            SELECT * FROM issue_records
            WHERE book_id = ? AND status = 'Issued'
            ORDER BY id DESC LIMIT 1
        """, (id,)).fetchone()

    if record is None:
        conn.close()
        return "No active issue record found.", 404

    return_date = date.today()
    fine = 0

    if record["due_date"]:
        due_date = date.fromisoformat(record["due_date"])
        late_days = (return_date - due_date).days
        if late_days > 0:
            fine = late_days * FINE_PER_DAY

    conn.execute("""
        UPDATE books SET available = available + 1
        WHERE id = ?
    """, (record["book_id"],))

    conn.execute("""
        UPDATE issue_records
        SET return_date = ?, fine = ?, status = 'Returned'
        WHERE id = ?
    """, (str(return_date), fine, record["id"]))

    conn.commit()
    conn.close()
    return redirect("/history")


# ==================================================
# STUDENT RETURN BOOK
# ==================================================

@app.route("/my-return/<int:id>", methods=["POST"])
@login_required
def student_return_book(id):
    # Only students can return their own books.
    if session.get("role") != "student":
        return "Only students can use this return option.", 403

    conn = get_db()

    record = conn.execute("""
        SELECT * FROM issue_records
        WHERE id = ?
          AND user_id = ?
          AND status = 'Issued'
    """, (id, session["user_id"])).fetchone()

    if record is None:
        conn.close()
        return "Issued book not found.", 404

    return_date = date.today()
    fine = 0

    if record["due_date"]:
        due_date = date.fromisoformat(record["due_date"])
        late_days = (return_date - due_date).days
        if late_days > 0:
            fine = late_days * FINE_PER_DAY

    conn.execute("""
        UPDATE issue_records
        SET return_date = ?, fine = ?, status = 'Returned'
        WHERE id = ?
    """, (str(return_date), fine, record["id"]))

    conn.execute("""
        UPDATE books
        SET available = available + 1
        WHERE id = ?
    """, (record["book_id"],))

    conn.commit()
    conn.close()

    return redirect("/my-books")

# ==================================================
# MY BOOKS
# ==================================================

@app.route("/my-books")
@login_required
def my_books():
    user_id = session["user_id"]

    conn = get_db()
    records = conn.execute("""
        SELECT
            issue_records.id,
            books.title,
            books.author,
            issue_records.issue_date,
            issue_records.due_date,
            issue_records.return_date,
            issue_records.fine,
            issue_records.status
        FROM issue_records
        JOIN books ON issue_records.book_id = books.id
        WHERE issue_records.user_id = ?
        ORDER BY issue_records.id DESC
    """, (user_id,)).fetchall()

    conn.close()

    return render_template("my_books.html", my_books=records)


# ==================================================
# REPORTS
# ==================================================

@app.route("/reports")
@admin_required
def reports():
    conn = get_db()
    today = str(date.today())

    total_books = conn.execute(
        "SELECT COUNT(*) FROM books"
    ).fetchone()[0]

    available_books = conn.execute(
        "SELECT COALESCE(SUM(available), 0) FROM books"
    ).fetchone()[0]

    issued_books = conn.execute("""
        SELECT COUNT(*) FROM issue_records WHERE status = 'Issued'
    """).fetchone()[0]

    returned_books = conn.execute("""
        SELECT COUNT(*) FROM issue_records WHERE status = 'Returned'
    """).fetchone()[0]

    overdue_books = conn.execute("""
        SELECT COUNT(*) FROM issue_records
        WHERE status = 'Issued'
        AND due_date IS NOT NULL AND due_date < ?
    """, (today,)).fetchone()[0]

    total_fine = conn.execute("""
        SELECT COALESCE(SUM(fine), 0) FROM issue_records
    """).fetchone()[0]

    conn.close()

    return render_template(
        "reports.html",
        total_books=total_books,
        available_books=available_books,
        issued_books=issued_books,
        returned_books=returned_books,
        overdue_books=overdue_books,
        total_fine=total_fine
    )


# ==================================================
# USERS
# ==================================================

@app.route("/users")
@admin_required
def users():
    conn = get_db()

    user_list = conn.execute("""
        SELECT id, name, username, role
        FROM users
        ORDER BY id DESC
    """).fetchall()

    conn.close()
    return render_template("users.html", users=user_list)


# ==================================================
# OVERDUE BOOKS
# ==================================================

@app.route("/overdue")
@staff_required
def overdue():
    conn = get_db()

    overdue_records = conn.execute("""
        SELECT
            issue_records.id,
            users.name,
            users.username,
            books.title,
            issue_records.issue_date,
            issue_records.due_date,
            CAST(
                julianday(date('now')) -
                julianday(issue_records.due_date)
                AS INTEGER
            ) AS days_overdue,
            (
                CAST(
                    julianday(date('now')) -
                    julianday(issue_records.due_date)
                    AS INTEGER
                ) * ?
            ) AS fine
        FROM issue_records
        JOIN users ON issue_records.user_id = users.id
        JOIN books ON issue_records.book_id = books.id
        WHERE issue_records.status = 'Issued'
          AND issue_records.due_date IS NOT NULL
          AND date(issue_records.due_date) < date('now')
        ORDER BY issue_records.due_date ASC
    """, (FINE_PER_DAY,)).fetchall()

    conn.close()

    return render_template(
        "overdue.html",
        overdue_books=overdue_records
    )

# ==================================================
# HISTORY
# ==================================================


@app.route("/history")
@roles_required("admin", "librarian")
def history():
    conn = get_db()

    records = conn.execute("""
        SELECT
            issue_records.id,
            users.name,
            users.username,
            books.title,
            issue_records.issue_date,
            issue_records.due_date,
            issue_records.return_date,
            issue_records.fine,
            issue_records.status
        FROM issue_records
        JOIN users ON issue_records.user_id = users.id
        JOIN books ON issue_records.book_id = books.id
        WHERE LOWER(TRIM(users.username)) != 'admin'
          AND LOWER(TRIM(users.name)) != 'administrator'
        ORDER BY issue_records.id DESC
    """).fetchall()

    conn.close()
   
    return render_template("history.html", history=records)


    return render_template("history.html", history=records)


# ==================================================
# RUN APPLICATION
# ==================================================

if __name__ == "__main__":
    app.run(debug=True)
