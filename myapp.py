"""
Bank Account Management System
--------------------------------
Single-file Streamlit app. Pure Python (sqlite3 is built into Python).

Run:
    pip install streamlit
    streamlit run bank_app.py
"""

import csv
import hashlib
import io
import random
import re
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime

import streamlit as st

# ----------------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------------
DB_PATH = "bank.db"
ADMIN_PASSWORD = "admin123"          # change this!
MAX_FAILED_ATTEMPTS = 3
MIN_BALANCE = {"Savings": 500_00, "Current": 0}   # in paise


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
def money(paise: int) -> str:
    return f"₹{paise / 100:,.2f}"


def to_paise(amount: float) -> int:
    return int(round(amount * 100))


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def hash_pin(pin: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", pin.encode(), bytes.fromhex(salt), 100_000
    ).hex()


# ----------------------------------------------------------------------------
# Database layer
# ----------------------------------------------------------------------------
@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with db() as c:
        c.execute(
            """CREATE TABLE IF NOT EXISTS accounts (
                acc_no TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                phone TEXT NOT NULL,
                acc_type TEXT NOT NULL,
                pin_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                balance INTEGER NOT NULL DEFAULT 0,
                failed INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL
            )"""
        )
        c.execute(
            """CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                acc_no TEXT NOT NULL,
                type TEXT NOT NULL,
                amount INTEGER NOT NULL,
                balance_after INTEGER NOT NULL,
                note TEXT,
                created_at TEXT NOT NULL
            )"""
        )


def add_txn(c, acc_no, ttype, amount, balance_after, note=""):
    c.execute(
        "INSERT INTO transactions (acc_no, type, amount, balance_after, note, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (acc_no, ttype, amount, balance_after, note, now()),
    )


def get_account(acc_no):
    with db() as c:
        return c.execute("SELECT * FROM accounts WHERE acc_no = ?", (acc_no,)).fetchone()


def create_account(name, phone, acc_type, pin, initial):
    with db() as c:
        while True:
            acc_no = "AC" + "".join(str(random.randint(0, 9)) for _ in range(10))
            if not c.execute("SELECT 1 FROM accounts WHERE acc_no = ?", (acc_no,)).fetchone():
                break
        salt = secrets.token_hex(16)
        c.execute(
            "INSERT INTO accounts (acc_no, name, phone, acc_type, pin_hash, salt, balance, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (acc_no, name, phone, acc_type, hash_pin(pin, salt), salt, initial, now()),
        )
        if initial > 0:
            add_txn(c, acc_no, "DEPOSIT", initial, initial, "Initial deposit")
    return acc_no


def authenticate(acc_no, pin):
    """Returns (ok, message)."""
    with db() as c:
        row = c.execute("SELECT * FROM accounts WHERE acc_no = ?", (acc_no,)).fetchone()
        if not row:
            return False, "Account not found."
        if row["status"] == "closed":
            return False, "This account is closed."
        if row["failed"] >= MAX_FAILED_ATTEMPTS:
            return False, "Account locked after too many wrong PINs. Contact admin."
        if hash_pin(pin, row["salt"]) == row["pin_hash"]:
            c.execute("UPDATE accounts SET failed = 0 WHERE acc_no = ?", (acc_no,))
            return True, "OK"
        c.execute("UPDATE accounts SET failed = failed + 1 WHERE acc_no = ?", (acc_no,))
        left = MAX_FAILED_ATTEMPTS - (row["failed"] + 1)
        return False, f"Wrong PIN. {left} attempt(s) left." if left else "Wrong PIN. Account locked."


def deposit(acc_no, amount):
    with db() as c:
        bal = c.execute("SELECT balance FROM accounts WHERE acc_no = ?", (acc_no,)).fetchone()["balance"]
        new = bal + amount
        c.execute("UPDATE accounts SET balance = ? WHERE acc_no = ?", (new, acc_no))
        add_txn(c, acc_no, "DEPOSIT", amount, new, "Cash deposit")
    return True, f"Deposited {money(amount)}. New balance: {money(new)}"


def withdraw(acc_no, amount):
    with db() as c:
        row = c.execute("SELECT balance, acc_type FROM accounts WHERE acc_no = ?", (acc_no,)).fetchone()
        new = row["balance"] - amount
        min_bal = MIN_BALANCE[row["acc_type"]]
        if new < min_bal:
            return False, f"Insufficient funds. Minimum balance for {row['acc_type']} is {money(min_bal)}."
        c.execute("UPDATE accounts SET balance = ? WHERE acc_no = ?", (new, acc_no))
        add_txn(c, acc_no, "WITHDRAW", amount, new, "Cash withdrawal")
    return True, f"Withdrawn {money(amount)}. New balance: {money(new)}"


def transfer(sender, receiver, amount, note):
    if sender == receiver:
        return False, "You cannot transfer to your own account."
    with db() as c:
        s = c.execute("SELECT * FROM accounts WHERE acc_no = ?", (sender,)).fetchone()
        r = c.execute("SELECT * FROM accounts WHERE acc_no = ?", (receiver,)).fetchone()
        if not r or r["status"] != "active":
            return False, "Receiver account not found or inactive."
        s_new = s["balance"] - amount
        if s_new < MIN_BALANCE[s["acc_type"]]:
            return False, f"Insufficient funds. Minimum balance for {s['acc_type']} is {money(MIN_BALANCE[s['acc_type']])}."
        r_new = r["balance"] + amount
        c.execute("UPDATE accounts SET balance = ? WHERE acc_no = ?", (s_new, sender))
        c.execute("UPDATE accounts SET balance = ? WHERE acc_no = ?", (r_new, receiver))
        add_txn(c, sender, "TRANSFER_OUT", amount, s_new, f"To {receiver} ({r['name']})" + (f" - {note}" if note else ""))
        add_txn(c, receiver, "TRANSFER_IN", amount, r_new, f"From {sender} ({s['name']})" + (f" - {note}" if note else ""))
    return True, f"Sent {money(amount)} to {r['name']} ({receiver})."


def get_history(acc_no, limit=500):
    with db() as c:
        return c.execute(
            "SELECT * FROM transactions WHERE acc_no = ? ORDER BY id DESC LIMIT ?",
            (acc_no, limit),
        ).fetchall()


def change_pin(acc_no, new_pin):
    salt = secrets.token_hex(16)
    with db() as c:
        c.execute(
            "UPDATE accounts SET pin_hash = ?, salt = ?, failed = 0 WHERE acc_no = ?",
            (hash_pin(new_pin, salt), salt, acc_no),
        )


def close_account(acc_no):
    with db() as c:
        c.execute("UPDATE accounts SET status = 'closed' WHERE acc_no = ?", (acc_no,))


# ----------------------------------------------------------------------------
# UI helpers
# ----------------------------------------------------------------------------
def flash(kind, msg):
    st.session_state["flash"] = (kind, msg)
    st.rerun()


def show_flash():
    if "flash" in st.session_state:
        kind, msg = st.session_state.pop("flash")
        getattr(st, kind)(msg)


def logout():
    for k in ("acc_no", "admin"):
        st.session_state.pop(k, None)
    st.rerun()


def txn_rows(rows):
    out = []
    for r in rows:
        sign = "+" if r["type"] in ("DEPOSIT", "TRANSFER_IN") else "-"
        out.append(
            {
                "Date": r["created_at"],
                "Type": r["type"].replace("_", " ").title(),
                "Amount": f"{sign}{money(r['amount'])}",
                "Balance": money(r["balance_after"]),
                "Note": r["note"] or "",
            }
        )
    return out


def inject_css():
    st.markdown(
        """
        <style>
        .hero {
            background: linear-gradient(135deg, #1e3c72, #2a5298);
            padding: 1.4rem 1.6rem; border-radius: 14px; color: white;
            margin-bottom: 1.2rem;
        }
        .hero h1 { margin: 0; font-size: 1.9rem; color: white; }
        .hero p { margin: .2rem 0 0; opacity: .85; }
        div[data-testid="stMetric"] {
            background: rgba(120,120,120,.08); padding: .9rem 1rem;
            border-radius: 12px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def hero(title, subtitle=""):
    st.markdown(
        f'<div class="hero"><h1>{title}</h1><p>{subtitle}</p></div>',
        unsafe_allow_html=True,
    )


# ----------------------------------------------------------------------------
# Pages: auth
# ----------------------------------------------------------------------------
def auth_page():
    hero("🏦 Simple Bank", "Secure, simple and fast banking — running locally")
    show_flash()
    tab_login, tab_open, tab_admin = st.tabs(["🔐 Login", "🆕 Open Account", "🛠️ Admin"])

    with tab_login:
        with st.form("login_form"):
            acc_no = st.text_input("Account Number", placeholder="AC1234567890").strip().upper()
            pin = st.text_input("4-digit PIN", type="password", max_chars=4)
            if st.form_submit_button("Login", use_container_width=True, type="primary"):
                ok, msg = authenticate(acc_no, pin)
                if ok:
                    st.session_state["acc_no"] = acc_no
                    st.rerun()
                else:
                    st.error(msg)

    with tab_open:
        with st.form("open_form"):
            name = st.text_input("Full Name").strip()
            phone = st.text_input("Mobile Number (10 digits)", max_chars=10).strip()
            acc_type = st.selectbox("Account Type", list(MIN_BALANCE.keys()))
            c1, c2 = st.columns(2)
            pin = c1.text_input("Set 4-digit PIN", type="password", max_chars=4)
            pin2 = c2.text_input("Confirm PIN", type="password", max_chars=4)
            initial = st.number_input(
                "Initial Deposit (₹)  — Savings needs min ₹500",
                min_value=0.0, step=100.0, format="%.2f",
            )
            if st.form_submit_button("Create Account", use_container_width=True, type="primary"):
                errors = []
                if len(name) < 3:
                    errors.append("Enter a valid name (min 3 characters).")
                if not re.fullmatch(r"[6-9]\d{9}", phone):
                    errors.append("Enter a valid 10-digit mobile number.")
                if not re.fullmatch(r"\d{4}", pin):
                    errors.append("PIN must be exactly 4 digits.")
                if pin != pin2:
                    errors.append("PINs do not match.")
                if to_paise(initial) < MIN_BALANCE[acc_type]:
                    errors.append(f"Minimum opening deposit for {acc_type} is {money(MIN_BALANCE[acc_type])}.")
                if errors:
                    for e in errors:
                        st.error(e)
                else:
                    acc_no = create_account(name, phone, acc_type, pin, to_paise(initial))
                    st.balloons()
                    flash("success", f"Account created! Your account number is **{acc_no}** — save it safely.")

    with tab_admin:
        with st.form("admin_form"):
            pw = st.text_input("Admin Password", type="password")
            if st.form_submit_button("Enter Admin Panel", use_container_width=True):
                if pw == ADMIN_PASSWORD:
                    st.session_state["admin"] = True
                    st.rerun()
                else:
                    st.error("Wrong admin password.")


# ----------------------------------------------------------------------------
# Pages: customer
# ----------------------------------------------------------------------------
def page_dashboard(acc):
    hero(f"Welcome, {acc['name']} 👋", f"{acc['acc_type']} Account • {acc['acc_no']}")
    rows = get_history(acc["acc_no"])
    credited = sum(r["amount"] for r in rows if r["type"] in ("DEPOSIT", "TRANSFER_IN"))
    debited = sum(r["amount"] for r in rows if r["type"] in ("WITHDRAW", "TRANSFER_OUT"))

    c1, c2, c3 = st.columns(3)
    c1.metric("Available Balance", money(acc["balance"]))
    c2.metric("Total Credited", money(credited))
    c3.metric("Total Debited", money(debited))

    if rows:
        st.subheader("Balance Trend")
        st.line_chart([r["balance_after"] / 100 for r in reversed(rows)])
        st.subheader("Recent Transactions")
        st.dataframe(txn_rows(rows[:5]), use_container_width=True, hide_index=True)
    else:
        st.info("No transactions yet. Make your first deposit!")


def page_deposit(acc):
    hero("💰 Deposit", "Add money to your account")
    show_flash()
    with st.form("deposit_form", clear_on_submit=True):
        amt = st.number_input("Amount (₹)", min_value=1.0, step=100.0, format="%.2f")
        if st.form_submit_button("Deposit", type="primary", use_container_width=True):
            ok, msg = deposit(acc["acc_no"], to_paise(amt))
            flash("success" if ok else "error", msg)


def page_withdraw(acc):
    hero("💸 Withdraw", f"Minimum balance to maintain: {money(MIN_BALANCE[acc['acc_type']])}")
    show_flash()
    with st.form("withdraw_form", clear_on_submit=True):
        amt = st.number_input("Amount (₹)", min_value=1.0, step=100.0, format="%.2f")
        pin = st.text_input("Confirm PIN", type="password", max_chars=4)
        if st.form_submit_button("Withdraw", type="primary", use_container_width=True):
            ok, msg = authenticate(acc["acc_no"], pin)
            if not ok:
                st.error(msg)
            else:
                ok, msg = withdraw(acc["acc_no"], to_paise(amt))
                flash("success" if ok else "error", msg)


def page_transfer(acc):
    hero("🔁 Transfer Money", "Send money to another account instantly")
    show_flash()
    with st.form("transfer_form", clear_on_submit=True):
        to = st.text_input("Receiver Account Number", placeholder="AC1234567890").strip().upper()
        amt = st.number_input("Amount (₹)", min_value=1.0, step=100.0, format="%.2f")
        note = st.text_input("Note (optional)", max_chars=60)
        pin = st.text_input("Confirm PIN", type="password", max_chars=4)
        if st.form_submit_button("Send Money", type="primary", use_container_width=True):
            ok, msg = authenticate(acc["acc_no"], pin)
            if not ok:
                st.error(msg)
            else:
                ok, msg = transfer(acc["acc_no"], to, to_paise(amt), note.strip())
                flash("success" if ok else "error", msg)


def page_statement(acc):
    hero("📄 Account Statement", "View, filter and download your transactions")
    rows = get_history(acc["acc_no"])
    if not rows:
        st.info("No transactions yet.")
        return
    types = sorted({r["type"] for r in rows})
    chosen = st.multiselect("Filter by type", types, default=types, format_func=lambda t: t.replace("_", " ").title())
    filtered = [r for r in rows if r["type"] in chosen]
    data = txn_rows(filtered)
    st.dataframe(data, use_container_width=True, hide_index=True)

    if data:
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=data[0].keys())
        writer.writeheader()
        writer.writerows(data)
        st.download_button(
            "⬇️ Download CSV", buf.getvalue(),
            file_name=f"statement_{acc['acc_no']}.csv", mime="text/csv",
        )


def page_settings(acc):
    hero("⚙️ Settings", "Account details & security")
    show_flash()
    st.write(f"**Name:** {acc['name']}  \n**Mobile:** {acc['phone']}  \n"
             f"**Type:** {acc['acc_type']}  \n**Opened on:** {acc['created_at']}")

    st.subheader("Change PIN")
    with st.form("pin_form", clear_on_submit=True):
        old = st.text_input("Current PIN", type="password", max_chars=4)
        new = st.text_input("New PIN", type="password", max_chars=4)
        new2 = st.text_input("Confirm New PIN", type="password", max_chars=4)
        if st.form_submit_button("Update PIN"):
            ok, msg = authenticate(acc["acc_no"], old)
            if not ok:
                st.error(msg)
            elif not re.fullmatch(r"\d{4}", new):
                st.error("New PIN must be exactly 4 digits.")
            elif new != new2:
                st.error("New PINs do not match.")
            else:
                change_pin(acc["acc_no"], new)
                flash("success", "PIN updated successfully.")

    st.subheader("Close Account")
    with st.expander("⚠️ Danger zone"):
        st.warning("Balance must be ₹0.00 before closing. This cannot be undone.")
        with st.form("close_form"):
            pin = st.text_input("Confirm PIN", type="password", max_chars=4, key="close_pin")
            sure = st.checkbox("I understand and want to close my account")
            if st.form_submit_button("Close My Account"):
                ok, msg = authenticate(acc["acc_no"], pin)
                if not ok:
                    st.error(msg)
                elif not sure:
                    st.error("Please tick the confirmation box.")
                elif acc["balance"] != 0:
                    st.error(f"Withdraw your balance first ({money(acc['balance'])}).")
                else:
                    close_account(acc["acc_no"])
                    logout()


def user_app():
    acc = get_account(st.session_state["acc_no"])
    if not acc or acc["status"] != "active":
        logout()
        return

    with st.sidebar:
        st.markdown(f"### 👤 {acc['name']}")
        st.caption(f"{acc['acc_no']} • {acc['acc_type']}")
        st.metric("Balance", money(acc["balance"]))
        menu = st.radio(
            "Menu",
            ["🏠 Dashboard", "💰 Deposit", "💸 Withdraw", "🔁 Transfer", "📄 Statement", "⚙️ Settings"],
            label_visibility="collapsed",
        )
        st.divider()
        if st.button("🚪 Logout", use_container_width=True):
            logout()

    pages = {
        "🏠 Dashboard": page_dashboard,
        "💰 Deposit": page_deposit,
        "💸 Withdraw": page_withdraw,
        "🔁 Transfer": page_transfer,
        "📄 Statement": page_statement,
        "⚙️ Settings": page_settings,
    }
    pages[menu](acc)


# ----------------------------------------------------------------------------
# Pages: admin
# ----------------------------------------------------------------------------
def admin_page():
    hero("🛠️ Admin Panel", "Manage all bank accounts")
    show_flash()
    with st.sidebar:
        st.markdown("### Admin")
        if st.button("🚪 Logout", use_container_width=True):
            logout()

    with db() as c:
        accounts = c.execute("SELECT * FROM accounts ORDER BY created_at DESC").fetchall()
        txns = c.execute("SELECT * FROM transactions ORDER BY id DESC LIMIT 200").fetchall()

    active = [a for a in accounts if a["status"] == "active"]
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Accounts", len(accounts))
    c2.metric("Active Accounts", len(active))
    c3.metric("Total Deposits Held", money(sum(a["balance"] for a in active)))

    tab1, tab2, tab3 = st.tabs(["Accounts", "All Transactions", "Unlock Accounts"])

    with tab1:
        search = st.text_input("Search by name / account number").strip().lower()
        data = [
            {
                "Acc
