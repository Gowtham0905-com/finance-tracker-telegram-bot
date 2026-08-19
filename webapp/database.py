import os
from contextlib import contextmanager

from dotenv import load_dotenv
import psycopg2

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")


@contextmanager
def get_db():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not configured in .env")

    conn = psycopg2.connect(DATABASE_URL)

    try:
        cursor = conn.cursor()
        yield cursor
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


# ============================================================
# USER LOOKUPS
# ============================================================

def get_user_by_login_id(login_id: str):
    with get_db() as cur:
        cur.execute(
            '''
            SELECT "UserID", "Username", "LoginID", "PasswordHash"
            FROM "users"
            WHERE "LoginID" = %s
            ''',
            (login_id,)
        )

        row = cur.fetchone()

        if not row:
            return None

        return {
            "user_id": row[0],
            "name": row[1],
            "login_id": row[2],
            "password_hash": row[3]
        }


# ============================================================
# DASHBOARD SUMMARY
# ============================================================

def get_summary(user_id: int, start_date=None, end_date=None):
    """
    Returns total income, total expense and balance.
    Optional start/end dates can be supplied.
    """

    with get_db() as cur:

        if start_date and end_date:
            cur.execute(
                '''
                SELECT COALESCE(SUM("Amount"), 0)
                FROM "expenses"
                WHERE "UserID" = %s
                  AND "ExpenseDate" BETWEEN %s AND %s
                ''',
                (user_id, start_date, end_date)
            )
        else:
            cur.execute(
                '''
                SELECT COALESCE(SUM("Amount"), 0)
                FROM "expenses"
                WHERE "UserID" = %s
                ''',
                (user_id,)
            )

        total_expense = float(cur.fetchone()[0] or 0)

        if start_date and end_date:
            cur.execute(
                '''
                SELECT COALESCE(SUM("Amount"), 0)
                FROM "income"
                WHERE "UserID" = %s
                  AND "IncomeDate" BETWEEN %s AND %s
                ''',
                (user_id, start_date, end_date)
            )
        else:
            cur.execute(
                '''
                SELECT COALESCE(SUM("Amount"), 0)
                FROM "income"
                WHERE "UserID" = %s
                ''',
                (user_id,)
            )

        total_income = float(cur.fetchone()[0] or 0)

    return {
        "total_income": total_income,
        "total_expense": total_expense,
        "balance": total_income - total_expense
    }


# ============================================================
# EXPENSES BY CATEGORY
# ============================================================

def get_expense_by_category(user_id: int, start_date=None, end_date=None):

    with get_db() as cur:

        if start_date and end_date:
            cur.execute(
                '''
                SELECT
                    "Category",
                    SUM("Amount") AS "Total"
                FROM "expenses"
                WHERE "UserID" = %s
                  AND "ExpenseDate" BETWEEN %s AND %s
                GROUP BY "Category"
                ORDER BY "Total" DESC
                ''',
                (user_id, start_date, end_date)
            )
        else:
            cur.execute(
                '''
                SELECT
                    "Category",
                    SUM("Amount") AS "Total"
                FROM "expenses"
                WHERE "UserID" = %s
                GROUP BY "Category"
                ORDER BY "Total" DESC
                ''',
                (user_id,)
            )

        return [
            {
                "category": row[0] or "Uncategorized",
                "total": float(row[1] or 0)
            }
            for row in cur.fetchall()
        ]


# ============================================================
# MONTHLY TREND
# ============================================================

def get_monthly_trend(user_id: int, months_back: int = 6):

    with get_db() as cur:

        cur.execute(
            '''
            SELECT
                TO_CHAR("ExpenseDate", 'YYYY-MM') AS "Month",
                SUM("Amount") AS "Total"
            FROM "expenses"
            WHERE "UserID" = %s
              AND "ExpenseDate" >=
                  CURRENT_DATE - (%s * INTERVAL '1 month')
            GROUP BY TO_CHAR("ExpenseDate", 'YYYY-MM')
            ORDER BY "Month"
            ''',
            (user_id, months_back)
        )

        expenses = {
            row[0]: float(row[1] or 0)
            for row in cur.fetchall()
        }

        cur.execute(
            '''
            SELECT
                TO_CHAR("IncomeDate", 'YYYY-MM') AS "Month",
                SUM("Amount") AS "Total"
            FROM "income"
            WHERE "UserID" = %s
              AND "IncomeDate" >=
                  CURRENT_DATE - (%s * INTERVAL '1 month')
            GROUP BY TO_CHAR("IncomeDate", 'YYYY-MM')
            ORDER BY "Month"
            ''',
            (user_id, months_back)
        )

        income = {
            row[0]: float(row[1] or 0)
            for row in cur.fetchall()
        }

    months = sorted(set(expenses) | set(income))

    return [
        {
            "month": month,
            "income": income.get(month, 0.0),
            "expense": expenses.get(month, 0.0)
        }
        for month in months
    ]


# ============================================================
# DAILY TREND
# ============================================================

def get_daily_trend(user_id: int, start_date, end_date):

    with get_db() as cur:

        cur.execute(
            '''
            SELECT
                "ExpenseDate" AS "Day",
                SUM("Amount") AS "Total"
            FROM "expenses"
            WHERE "UserID" = %s
              AND "ExpenseDate" BETWEEN %s AND %s
            GROUP BY "ExpenseDate"
            ORDER BY "ExpenseDate"
            ''',
            (user_id, start_date, end_date)
        )

        expenses = {
            str(row[0]): float(row[1] or 0)
            for row in cur.fetchall()
        }

        cur.execute(
            '''
            SELECT
                "IncomeDate" AS "Day",
                SUM("Amount") AS "Total"
            FROM "income"
            WHERE "UserID" = %s
              AND "IncomeDate" BETWEEN %s AND %s
            GROUP BY "IncomeDate"
            ORDER BY "IncomeDate"
            ''',
            (user_id, start_date, end_date)
        )

        income = {
            str(row[0]): float(row[1] or 0)
            for row in cur.fetchall()
        }

    days = sorted(set(expenses) | set(income))

    return [
        {
            "day": day,
            "income": income.get(day, 0.0),
            "expense": expenses.get(day, 0.0)
        }
        for day in days
    ]


# ============================================================
# RECENT TRANSACTIONS
# ============================================================

def get_recent_transactions(
    user_id: int,
    limit: int = 20,
    start_date=None,
    end_date=None
):

    # Protect the LIMIT value from invalid input.
    limit = max(1, min(int(limit), 100))

    with get_db() as cur:

        if start_date and end_date:

            query = '''
                SELECT
                    "Type",
                    "Label",
                    "Amount",
                    "TxnDate"
                FROM (
                    SELECT
                        'Expense' AS "Type",
                        "Category" AS "Label",
                        "Amount",
                        "ExpenseDate" AS "TxnDate"
                    FROM "expenses"
                    WHERE "UserID" = %s
                      AND "ExpenseDate" BETWEEN %s AND %s

                    UNION ALL

                    SELECT
                        'Income' AS "Type",
                        "Source" AS "Label",
                        "Amount",
                        "IncomeDate" AS "TxnDate"
                    FROM "income"
                    WHERE "UserID" = %s
                      AND "IncomeDate" BETWEEN %s AND %s
                ) AS transactions
                ORDER BY "TxnDate" DESC
                LIMIT %s
            '''

            params = (
                user_id,
                start_date,
                end_date,
                user_id,
                start_date,
                end_date,
                limit
            )

        else:

            query = '''
                SELECT
                    "Type",
                    "Label",
                    "Amount",
                    "TxnDate"
                FROM (
                    SELECT
                        'Expense' AS "Type",
                        "Category" AS "Label",
                        "Amount",
                        "ExpenseDate" AS "TxnDate"
                    FROM "expenses"
                    WHERE "UserID" = %s

                    UNION ALL

                    SELECT
                        'Income' AS "Type",
                        "Source" AS "Label",
                        "Amount",
                        "IncomeDate" AS "TxnDate"
                    FROM "income"
                    WHERE "UserID" = %s
                ) AS transactions
                ORDER BY "TxnDate" DESC
                LIMIT %s
            '''

            params = (
                user_id,
                user_id,
                limit
            )

        cur.execute(query, params)

        return [
            {
                "type": row[0],
                "label": row[1],
                "amount": float(row[2]),
                "date": str(row[3])
            }
            for row in cur.fetchall()
        ]


# ============================================================
# CSV EXPORT
# ============================================================

def get_all_transactions_for_export(
    user_id: int,
    start_date=None,
    end_date=None
):
    """
    Returns all transactions for CSV export.
    Oldest first.
    """

    with get_db() as cur:

        if start_date and end_date:

            query = '''
                SELECT
                    "Type",
                    "Label",
                    "Amount",
                    "TxnDate"
                FROM (
                    SELECT
                        'Expense' AS "Type",
                        "Category" AS "Label",
                        "Amount",
                        "ExpenseDate" AS "TxnDate"
                    FROM "expenses"
                    WHERE "UserID" = %s
                      AND "ExpenseDate" BETWEEN %s AND %s

                    UNION ALL

                    SELECT
                        'Income' AS "Type",
                        "Source" AS "Label",
                        "Amount",
                        "IncomeDate" AS "TxnDate"
                    FROM "income"
                    WHERE "UserID" = %s
                      AND "IncomeDate" BETWEEN %s AND %s
                ) AS transactions
                ORDER BY "TxnDate" ASC
            '''

            params = (
                user_id,
                start_date,
                end_date,
                user_id,
                start_date,
                end_date
            )

        else:

            query = '''
                SELECT
                    "Type",
                    "Label",
                    "Amount",
                    "TxnDate"
                FROM (
                    SELECT
                        'Expense' AS "Type",
                        "Category" AS "Label",
                        "Amount",
                        "ExpenseDate" AS "TxnDate"
                    FROM "expenses"
                    WHERE "UserID" = %s

                    UNION ALL

                    SELECT
                        'Income' AS "Type",
                        "Source" AS "Label",
                        "Amount",
                        "IncomeDate" AS "TxnDate"
                    FROM "income"
                    WHERE "UserID" = %s
                ) AS transactions
                ORDER BY "TxnDate" ASC
            '''

            params = (
                user_id,
                user_id
            )

        cur.execute(query, params)

        return [
            {
                "date": str(row[3]),
                "type": row[0],
                "label": row[1],
                "amount": float(row[2])
            }
            for row in cur.fetchall()
        ]