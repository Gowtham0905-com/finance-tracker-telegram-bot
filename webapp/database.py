import pyodbc
import os
from contextlib import contextmanager
from dotenv import load_dotenv

load_dotenv()  # reads variables from a .env file in this folder (see .env.example)

DATABASE_NAME = os.environ.get("DB_NAME", "Income_Expense_Project")
SERVER = os.environ.get("DB_SERVER", "localhost\\SQLEXPRESS")

@contextmanager
def get_db():
    """
    Usage:
        with get_db() as cursor:
            cursor.execute("SELECT ...")
            rows = cursor.fetchall()
    Connection is always closed, even if the query raises.
    """
    conn = pyodbc.connect(
        'DRIVER={ODBC Driver 17 for SQL Server};'
        f'SERVER={SERVER};'
        f'DATABASE={DATABASE_NAME};'
        'Trusted_Connection=yes;'
    )
    try:
        cursor = conn.cursor()
        yield cursor
        conn.commit()
    finally:
        conn.close()


# ---------- User lookups ----------

def get_user_by_login_id(login_id: str):
    with get_db() as cur:
        cur.execute(
            "SELECT UserID, Username, LoginID, PasswordHash FROM Users WHERE LoginID = ?",
            (login_id,)
        )
        row = cur.fetchone()
        if not row:
            return None
        return {"user_id": row[0], "name": row[1], "login_id": row[2], "password_hash": row[3]}


# Note: there is no create_web_user() here - accounts are only created
# via the Telegram bot's /start flow (see bot script), which enforces
# username uniqueness before writing to this table.


# ---------- Dashboard data ----------

def get_summary(user_id: int, start_date=None, end_date=None):
    """Total income, total expense, and balance for a user, optionally filtered by date range."""
    date_filter = ""
    params = [user_id]
    if start_date and end_date:
        date_filter = " AND ExpenseDate BETWEEN ? AND ?"

    with get_db() as cur:
        if start_date and end_date:
            cur.execute(
                "SELECT ISNULL(SUM(Amount), 0) FROM Expenses WHERE UserID = ? AND ExpenseDate BETWEEN ? AND ?",
                (user_id, start_date, end_date)
            )
        else:
            cur.execute("SELECT ISNULL(SUM(Amount), 0) FROM Expenses WHERE UserID = ?", (user_id,))
        total_expense = float(cur.fetchone()[0])

        if start_date and end_date:
            cur.execute(
                "SELECT ISNULL(SUM(Amount), 0) FROM Income WHERE UserID = ? AND IncomeDate BETWEEN ? AND ?",
                (user_id, start_date, end_date)
            )
        else:
            cur.execute("SELECT ISNULL(SUM(Amount), 0) FROM Income WHERE UserID = ?", (user_id,))
        total_income = float(cur.fetchone()[0])

    return {
        "total_income": total_income,
        "total_expense": total_expense,
        "balance": total_income - total_expense
    }


def get_expense_by_category(user_id: int, start_date=None, end_date=None):
    with get_db() as cur:
        if start_date and end_date:
            cur.execute(
                """SELECT Category, SUM(Amount) as Total
                   FROM Expenses
                   WHERE UserID = ? AND ExpenseDate BETWEEN ? AND ?
                   GROUP BY Category
                   ORDER BY Total DESC""",
                (user_id, start_date, end_date)
            )
        else:
            cur.execute(
                """SELECT Category, SUM(Amount) as Total
                   FROM Expenses
                   WHERE UserID = ?
                   GROUP BY Category
                   ORDER BY Total DESC""",
                (user_id,)
            )
        return [{"category": row[0], "total": float(row[1])} for row in cur.fetchall()]


def get_monthly_trend(user_id: int, months_back: int = 6):
    with get_db() as cur:
        cur.execute(
            """SELECT FORMAT(ExpenseDate, 'yyyy-MM') as Month, SUM(Amount) as Total
               FROM Expenses
               WHERE UserID = ? AND ExpenseDate >= DATEADD(MONTH, -?, GETDATE())
               GROUP BY FORMAT(ExpenseDate, 'yyyy-MM')
               ORDER BY Month""",
            (user_id, months_back)
        )
        expenses = {row[0]: float(row[1]) for row in cur.fetchall()}

        cur.execute(
            """SELECT FORMAT(IncomeDate, 'yyyy-MM') as Month, SUM(Amount) as Total
               FROM Income
               WHERE UserID = ? AND IncomeDate >= DATEADD(MONTH, -?, GETDATE())
               GROUP BY FORMAT(IncomeDate, 'yyyy-MM')
               ORDER BY Month""",
            (user_id, months_back)
        )
        income = {row[0]: float(row[1]) for row in cur.fetchall()}

    months = sorted(set(expenses) | set(income))
    return [
        {"month": m, "income": income.get(m, 0.0), "expense": expenses.get(m, 0.0)}
        for m in months
    ]


def get_daily_trend(user_id: int, start_date, end_date):
    """Day-by-day income/expense totals for a specific date range - used
    when the dashboard is filtered to a custom range, since a monthly
    bucket doesn't make sense for e.g. a 10-day window."""
    with get_db() as cur:
        cur.execute(
            """SELECT CONVERT(date, ExpenseDate) as Day, SUM(Amount) as Total
               FROM Expenses
               WHERE UserID = ? AND ExpenseDate BETWEEN ? AND ?
               GROUP BY CONVERT(date, ExpenseDate)
               ORDER BY Day""",
            (user_id, start_date, end_date)
        )
        expenses = {str(row[0]): float(row[1]) for row in cur.fetchall()}

        cur.execute(
            """SELECT CONVERT(date, IncomeDate) as Day, SUM(Amount) as Total
               FROM Income
               WHERE UserID = ? AND IncomeDate BETWEEN ? AND ?
               GROUP BY CONVERT(date, IncomeDate)
               ORDER BY Day""",
            (user_id, start_date, end_date)
        )
        income = {str(row[0]): float(row[1]) for row in cur.fetchall()}

    days = sorted(set(expenses) | set(income))
    return [
        {"day": d, "income": income.get(d, 0.0), "expense": expenses.get(d, 0.0)}
        for d in days
    ]


def get_all_transactions_for_export(user_id: int, start_date=None, end_date=None):
    """All transactions (no limit) for a date range, oldest first - used for CSV export."""
    date_filter_expense = " AND ExpenseDate BETWEEN ? AND ?" if start_date and end_date else ""
    date_filter_income = " AND IncomeDate BETWEEN ? AND ?" if start_date and end_date else ""

    with get_db() as cur:
        query = f"""SELECT 'Expense' as Type, Category as Label, Amount, ExpenseDate as TxnDate
                    FROM Expenses WHERE UserID = ?{date_filter_expense}
                    UNION ALL
                    SELECT 'Income' as Type, Source as Label, Amount, IncomeDate as TxnDate
                    FROM Income WHERE UserID = ?{date_filter_income}
                    ORDER BY TxnDate ASC"""
        params = [user_id]
        if start_date and end_date:
            params += [start_date, end_date]
        params.append(user_id)
        if start_date and end_date:
            params += [start_date, end_date]

        cur.execute(query, params)
        return [
            {"date": str(row[3]), "type": row[0], "label": row[1], "amount": float(row[2])}
            for row in cur.fetchall()
        ]
    date_filter_expense = " AND ExpenseDate BETWEEN ? AND ?" if start_date and end_date else ""
    date_filter_income = " AND IncomeDate BETWEEN ? AND ?" if start_date and end_date else ""

    with get_db() as cur:
        query = f"""SELECT 'Expense' as Type, Category as Label, Amount, ExpenseDate as TxnDate
                    FROM Expenses WHERE UserID = ?{date_filter_expense}
                    UNION ALL
                    SELECT 'Income' as Type, Source as Label, Amount, IncomeDate as TxnDate
                    FROM Income WHERE UserID = ?{date_filter_income}
                    ORDER BY TxnDate DESC
                    OFFSET 0 ROWS FETCH NEXT ? ROWS ONLY"""
        params = [user_id]
        if start_date and end_date:
            params += [start_date, end_date]
        params.append(user_id)
        if start_date and end_date:
            params += [start_date, end_date]
        params.append(limit)

        cur.execute(query, params)
        return [
            {"type": row[0], "label": row[1], "amount": float(row[2]), "date": str(row[3])}
            for row in cur.fetchall()
        ]
