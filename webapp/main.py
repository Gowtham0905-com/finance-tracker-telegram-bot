import logging
import csv
import io
from datetime import date

from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
import psycopg2

import database as db
import auth

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Expense Tracker Dashboard")



# ---------- Request/response schemas ----------

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ---------- Error handling ----------

@app.exception_handler(psycopg2.Error)
async def db_error_handler(request, exc):
    print("DATABASE ERROR:", repr(exc), flush=True)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Something went wrong. Please try again later."
        }
    )
# ---------- Auth routes ----------
# Note: there is no /api/signup route. Accounts are created via the
# Telegram bot's /start flow, which collects name, email, and password
# and writes them straight into the Users table using the same bcrypt
# hashing scheme as auth.py below. The website is login-only.

@app.post("/api/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    # form_data.username holds the Login ID the user set via the bot
    user = db.get_user_by_login_id(form_data.username)
    if not user or not user["password_hash"] or not auth.verify_password(form_data.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect login ID or password."
        )
    token = auth.create_access_token(user["user_id"])
    return Token(access_token=token)


# ---------- Dashboard data routes ----------

@app.get("/api/summary")
def summary(start: date = None, end: date = None, user_id: int = Depends(auth.get_current_user_id)):
    return db.get_summary(user_id, start, end)


@app.get("/api/expenses/by-category")
def expenses_by_category(start: date = None, end: date = None, user_id: int = Depends(auth.get_current_user_id)):
    return db.get_expense_by_category(user_id, start, end)


@app.get("/api/trend")
def monthly_trend(months: int = 6, user_id: int = Depends(auth.get_current_user_id)):
    return db.get_monthly_trend(user_id, months)


@app.get("/api/trend/daily")
def daily_trend(start: date, end: date, user_id: int = Depends(auth.get_current_user_id)):
    return db.get_daily_trend(user_id, start, end)


@app.get("/api/transactions")
def recent_transactions(limit: int = 20, start: date = None, end: date = None, user_id: int = Depends(auth.get_current_user_id)):
    return db.get_recent_transactions(user_id, limit, start, end)


# ---------- Report downloads (CSV) ----------

def _csv_response(rows: list[dict], fieldnames: list[str], filename: str):
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@app.get("/api/export/transactions.csv")
def export_transactions_csv(start: date = None, end: date = None, user_id: int = Depends(auth.get_current_user_id)):
    rows = db.get_all_transactions_for_export(user_id, start, end)
    label = f"{start}_to_{end}" if start and end else "all_time"
    return _csv_response(rows, ["date", "type", "label", "amount"], f"transactions_{label}.csv")


@app.get("/api/export/summary.csv")
def export_summary_csv(start: date = None, end: date = None, user_id: int = Depends(auth.get_current_user_id)):
    summary = db.get_summary(user_id, start, end)
    categories = db.get_expense_by_category(user_id, start, end)

    rows = [
        {"metric": "Total Income", "value": summary["total_income"]},
        {"metric": "Total Expense", "value": summary["total_expense"]},
        {"metric": "Balance", "value": summary["balance"]},
        {"metric": "", "value": ""},
        {"metric": "Category", "value": "Amount"},
    ] + [{"metric": c["category"], "value": c["total"]} for c in categories]

    label = f"{start}_to_{end}" if start and end else "all_time"
    return _csv_response(rows, ["metric", "value"], f"summary_{label}.csv")


# ---------- Serve frontend ----------

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def serve_login():
    return FileResponse("static/login.html")

@app.get("/dashboard")
def serve_dashboard():
    return FileResponse("static/dashboard.html")
