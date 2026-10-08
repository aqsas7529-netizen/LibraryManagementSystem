from flask import Flask, render_template, request, redirect, session
import sqlite3
from functools import wraps
from datetime import date, timedelta

app = Flask(__name__)

app.secret_key = "library_management_secret"

DATABASE = "library.db"

FINE_PER_DAY = 10


# ==================================================
# DATABASE
# ==================================================

def get_db():

    conn = sqlite3.connect(DATABASE)

    conn.row_factory = sqlite3.Row

    return conn


def create_tables():

    conn = get_db()

    # ================= USERS =================

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            name TEXT NOT NULL,

            username TEXT UNIQUE NOT NULL,

            password TEXT NOT NULL,

            role TEXT NOT NULL
        )
    """)


    # ================= BOOKS =================

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


    # ================= ISSUE RECORDS =================

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


    # ================= OLD DATABASE FIX =================

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


    # ================= DEFAULT ADMIN =================

    admin = conn.execute(
        "SELECT * FROM users WHERE username = ?",
        ("admin",)
    ).fetchone()


    if admin is None:

        conn.execute("""
            INSERT INTO users
            (name, username, password, role)
            VALUES (?, ?, ?, ?)
        """, (
            "Administrator",
            "admin",
            "admin123",
            "admin"
        ))


    conn.commit()

    conn.close()


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

def admin_required(function):

    @wraps(function)
    def wrapper(*args, **kwargs):

        if "user_id" not in session:

            return redirect("/login")


        if session.get("role") != "admin":

            return redirect("/")


        return function(*args, **kwargs)

    return wrapper


# ==================================================
# DASHBOARD
# ==================================================

@app.route("/")
@login_required
def index():

    conn = get_db()


    # ================= LIBRARY STATISTICS =================

    total_books = conn.execute(
        "SELECT COUNT(*) FROM books"
    ).fetchone()[0]


    available_books = conn.execute(
        "SELECT COALESCE(SUM(available), 0) FROM books"
    ).fetchone()[0]


    issued_books = conn.execute("""
        SELECT COUNT(*)
        FROM issue_records
        WHERE status = 'Issued'
    """).fetchone()[0]


    total_users = conn.execute(
        "SELECT COUNT(*) FROM users"
    ).fetchone()[0]


    today = str(date.today())


    overdue_books = conn.execute("""
        SELECT COUNT(*)
        FROM issue_records
        WHERE status = 'Issued'
        AND due_date IS NOT NULL
        AND due_date < ?
    """, (today,)).fetchone()[0]


    # ================= RECENT TRANSACTIONS =================

    recent_transactions = conn.execute("""
        SELECT

            issue_records.issue_date,

            issue_records.return_date,

            issue_records.status,

            users.name,

            books.title

        FROM issue_records

        JOIN users
        ON issue_records.user_id = users.id

        JOIN books
        ON issue_records.book_id = books.id

        ORDER BY issue_records.id DESC

        LIMIT 5

    """).fetchall()


    # ================= RECENTLY ADDED BOOKS =================

    recent_books = conn.execute("""
        SELECT

            id,

            title,

            author,

            category,

            available,

            quantity

        FROM books

        ORDER BY id DESC

        LIMIT 5

    """).fetchall()


    conn.close()


    return render_template(

        "index.html",

        total_books=total_books,

        available_books=available_books,

        issued_books=issued_books,

        total_users=total_users,

        overdue_books=overdue_books,

        recent_transactions=recent_transactions,

        recent_books=recent_books
    )


# ==================================================
# REGISTER
# ==================================================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form["name"]

        username = request.form["username"]

        password = request.form["password"]


        conn = get_db()


        existing_user = conn.execute(
            "SELECT * FROM users WHERE username = ?",
            (username,)
        ).fetchone()


        if existing_user:

            conn.close()

            return render_template(
                "register.html",
                error="Username already exists"
            )


        conn.execute("""
            INSERT INTO users
            (name, username, password, role)

            VALUES (?, ?, ?, ?)

        """, (
            name,
            username,
            password,
            "student"
        ))


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

        username = request.form["username"]

        password = request.form["password"]


        conn = get_db()


        user = conn.execute("""
            SELECT *

            FROM users

            WHERE username = ?

            AND password = ?

        """, (
            username,
            password
        )).fetchone()


        conn.close()


        if user:

            session["user_id"] = user["id"]

            session["username"] = user["username"]

            session["role"] = user["role"]


            return redirect("/")


        return render_template(
            "login.html",
            error="Invalid username or password"
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

    search = request.args.get("search", "")

    user_id = session["user_id"]


    conn = get_db()


    if search:

        books = conn.execute("""
            SELECT *

            FROM books

            WHERE title LIKE ?

            OR author LIKE ?

            OR category LIKE ?

            OR isbn LIKE ?

            ORDER BY id DESC

        """, (
            "%" + search + "%",
            "%" + search + "%",
            "%" + search + "%",
            "%" + search + "%"
        )).fetchall()


    else:

        books = conn.execute(
            "SELECT * FROM books ORDER BY id DESC"
        ).fetchall()


    # ================= CURRENT USER ISSUED BOOKS =================

    issued_books = conn.execute("""
        SELECT book_id

        FROM issue_records

        WHERE user_id = ?

        AND status = 'Issued'

    """, (user_id,)).fetchall()


    issued_book_ids = [

        row["book_id"]

        for row in issued_books

    ]


    conn.close()


    return render_template(

        "books.html",

        books=books,

        search=search,

        issued_book_ids=issued_book_ids

    )


# ==================================================
# ADD BOOK
# ==================================================

@app.route("/add", methods=["GET", "POST"])
@admin_required
def add_book():

    if request.method == "POST":

        title = request.form["title"]

        author = request.form["author"]

        category = request.form["category"]

        isbn = request.form["isbn"]

        quantity = int(request.form["quantity"])


        conn = get_db()


        conn.execute("""
            INSERT INTO books
            (
                title,
                author,
                category,
                isbn,
                quantity,
                available
            )

            VALUES (?, ?, ?, ?, ?, ?)

        """, (
            title,
            author,
            category,
            isbn,
            quantity,
            quantity
        ))


        conn.commit()

        conn.close()


        return redirect("/books")


    return render_template("add_book.html")


# ==================================================
# EDIT BOOK
# ==================================================

@app.route("/edit/<int:id>", methods=["GET", "POST"])
@admin_required
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

        title = request.form["title"]

        author = request.form["author"]

        category = request.form["category"]

        isbn = request.form["isbn"]

        quantity = int(request.form["quantity"])


        issued = book["quantity"] - book["available"]


        available = quantity - issued


        if available < 0:

            available = 0


        conn.execute("""
            UPDATE books

            SET title = ?,

                author = ?,

                category = ?,

                isbn = ?,

                quantity = ?,

                available = ?

            WHERE id = ?

        """, (
            title,
            author,
            category,
            isbn,
            quantity,
            available,
            id
        ))


        conn.commit()

        conn.close()


        return redirect("/books")


    conn.close()


    return render_template(
        "edit_book.html",
        book=book
    )


# ==================================================
# DELETE BOOK
# ==================================================

@app.route("/delete/<int:id>")
@admin_required
def delete_book(id):

    conn = get_db()


    # Prevent deletion if transaction history exists

    transaction = conn.execute("""
        SELECT id

        FROM issue_records

        WHERE book_id = ?

        LIMIT 1

    """, (id,)).fetchone()


    if transaction:

        conn.close()

        return redirect("/books")


    conn.execute(
        "DELETE FROM books WHERE id = ?",
        (id,)
    )


    conn.commit()

    conn.close()


    return redirect("/books")


# ==================================================
# ISSUE BOOK
# ==================================================

@app.route("/issue/<int:id>")
@login_required
def issue_book(id):

    user_id = session["user_id"]


    conn = get_db()


    # ================= CHECK DUPLICATE ISSUE =================

    existing_issue = conn.execute("""
        SELECT *

        FROM issue_records

        WHERE user_id = ?

        AND book_id = ?

        AND status = 'Issued'

    """, (
        user_id,
        id
    )).fetchone()


    if existing_issue:

        conn.close()

        return redirect("/books")


    # ================= GET BOOK =================

    book = conn.execute(
        "SELECT * FROM books WHERE id = ?",
        (id,)
    ).fetchone()


    # ================= CHECK AVAILABILITY =================

    if book and book["available"] > 0:

        issue_date = date.today()

        due_date = issue_date + timedelta(days=7)


        # Reduce available quantity

        conn.execute("""
            UPDATE books

            SET available = available - 1

            WHERE id = ?

        """, (id,))


        # Create issue record

        conn.execute("""
            INSERT INTO issue_records
            (
                user_id,
                book_id,
                issue_date,
                due_date,
                return_date,
                fine,
                status
            )

            VALUES (?, ?, ?, ?, ?, ?, ?)

        """, (
            user_id,
            id,
            str(issue_date),
            str(due_date),
            None,
            0,
            "Issued"
        ))


        conn.commit()


    conn.close()


    return redirect("/books")


# ==================================================
# RETURN BOOK
# ==================================================

@app.route("/return/<int:id>")
@login_required
def return_book(id):

    user_id = session["user_id"]


    conn = get_db()


    record = conn.execute("""
        SELECT *

        FROM issue_records

        WHERE user_id = ?

        AND book_id = ?

        AND status = 'Issued'

        ORDER BY id DESC

        LIMIT 1

    """, (
        user_id,
        id
    )).fetchone()


    if record:

        return_date = date.today()

        fine = 0


        # ================= CALCULATE FINE =================

        if record["due_date"]:

            due_date = date.fromisoformat(
                record["due_date"]
            )


            late_days = (
                return_date - due_date
            ).days


            if late_days > 0:

                fine = late_days * FINE_PER_DAY


        # ================= INCREASE AVAILABLE =================

        conn.execute("""
            UPDATE books

            SET available = available + 1

            WHERE id = ?

        """, (id,))


        # ================= UPDATE ISSUE RECORD =================

        conn.execute("""
            UPDATE issue_records

            SET return_date = ?,

                fine = ?,

                status = ?

            WHERE id = ?

        """, (
            str(return_date),
            fine,
            "Returned",
            record["id"]
        ))


        conn.commit()


    conn.close()


    return redirect("/books")


# ==================================================
# MY BOOKS
# ==================================================

@app.route("/my-books")
@login_required
def my_books():

    user_id = session["user_id"]


    conn = get_db()


    my_books = conn.execute("""
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

        JOIN books

        ON issue_records.book_id = books.id

        WHERE issue_records.user_id = ?

        ORDER BY issue_records.id DESC

    """, (user_id,)).fetchall()


    conn.close()


    return render_template(
        "my_books.html",
        my_books=my_books
    )


# ==================================================
# REPORTS
# ==================================================

@app.route("/reports")
@admin_required
def reports():

    conn = get_db()


    total_books = conn.execute(
        "SELECT COUNT(*) FROM books"
    ).fetchone()[0]


    available_books = conn.execute(
        "SELECT COALESCE(SUM(available), 0) FROM books"
    ).fetchone()[0]


    issued_books = conn.execute("""
        SELECT COUNT(*)

        FROM issue_records

        WHERE status = 'Issued'

    """).fetchone()[0]


    returned_books = conn.execute("""
        SELECT COUNT(*)

        FROM issue_records

        WHERE status = 'Returned'

    """).fetchone()[0]


    today = str(date.today())


    overdue_books = conn.execute("""
        SELECT COUNT(*)

        FROM issue_records

        WHERE status = 'Issued'

        AND due_date IS NOT NULL

        AND due_date < ?

    """, (today,)).fetchone()[0]


    total_fine = conn.execute("""
        SELECT COALESCE(SUM(fine), 0)

        FROM issue_records

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


    users = conn.execute("""
        SELECT

            id,

            name,

            username,

            role

        FROM users

        ORDER BY id DESC

    """).fetchall()


    conn.close()


    return render_template(
        "users.html",
        users=users
    )


# ==================================================
# HISTORY
# ==================================================

@app.route("/history")
@admin_required
def history():

    conn = get_db()


    history = conn.execute("""
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

        JOIN users

        ON issue_records.user_id = users.id

        JOIN books

        ON issue_records.book_id = books.id

        ORDER BY issue_records.id DESC

    """).fetchall()


    conn.close()


    return render_template(
        "history.html",
        history=history
    )


# ==================================================
# RUN APPLICATION
# ==================================================

if __name__ == "__main__":

    create_tables()

    app.run(debug=True)