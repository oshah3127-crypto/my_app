# Bank Account Management System (Streamlit version)
# Uses: functions, loops, if/else, file handling, classes and objects
# Run with:  streamlit run bank_app.py

import streamlit as st

FILE_NAME = "accounts.txt"


# ---------- Account class ----------
class Account:
    def __init__(self, acc_no, name, balance=0.0):
        self.acc_no = acc_no
        self.name = name
        self.balance = balance

    def deposit(self, amount):
        if amount <= 0:
            return False
        self.balance += amount
        return True

    def withdraw(self, amount):
        if amount <= 0 or amount > self.balance:
            return False
        self.balance -= amount
        return True


# ---------- Bank class ----------
class Bank:
    def __init__(self):
        self.accounts = []

    def create_account(self, name, initial_balance):
        if len(self.accounts) == 0:
            acc_no = 1001
        else:
            acc_no = max(acc.acc_no for acc in self.accounts) + 1
        account = Account(acc_no, name, initial_balance)
        self.accounts.append(account)
        return account

    def find_account(self, acc_no):
        for account in self.accounts:
            if account.acc_no == acc_no:
                return account
        return None

    def transfer(self, from_no, to_no, amount):
        sender = self.find_account(from_no)
        receiver = self.find_account(to_no)
        if sender is None or receiver is None:
            return False, "Account not found."
        if from_no == to_no:
            return False, "Cannot transfer to the same account."
        if not sender.withdraw(amount):
            return False, "Transfer failed: invalid amount or low balance."
        receiver.deposit(amount)
        return True, "Transfer successful."

    def delete_account(self, acc_no):
        account = self.find_account(acc_no)
        if account is None:
            return False
        self.accounts.remove(account)
        return True


# ---------- File handling ----------
def save_data(bank):
    file = open(FILE_NAME, "w")
    for acc in bank.accounts:
        file.write(f"{acc.acc_no},{acc.name},{acc.balance}\n")
    file.close()


def load_data(bank):
    open(FILE_NAME, "a").close()  # creates the file if it doesn't exist
    file = open(FILE_NAME, "r")
    for line in file:
        line = line.strip()
        if line == "":
            continue
        parts = line.split(",")
        bank.accounts.append(Account(int(parts[0]), parts[1], float(parts[2])))
    file.close()


# ---------- Streamlit UI ----------
st.set_page_config(page_title="Bank Account Management", page_icon="🏦")
st.title("🏦 Bank Account Management System")

# Load the bank only once per session
if "bank" not in st.session_state:
    bank = Bank()
    load_data(bank)
    st.session_state.bank = bank

bank = st.session_state.bank

menu = [
    "Create account",
    "Deposit",
    "Withdraw",
    "Transfer",
    "Check balance",
    "Show all accounts",
    "Delete account",
]
choice = st.sidebar.radio("Menu", menu)


def account_options():
    return [acc.acc_no for acc in bank.accounts]


def account_label(acc_no):
    acc = bank.find_account(acc_no)
    return f"{acc.acc_no} - {acc.name}"


if choice == "Create account":
    st.subheader("Create account")
    name = st.text_input("Account holder name")
    amount = st.number_input("Opening balance", min_value=0.0, step=100.0, format="%.2f")
    if st.button("Create"):
        if name.strip() == "":
            st.error("Invalid name.")
        else:
            acc = bank.create_account(name.strip().replace(",", " "), amount)
            save_data(bank)
            st.success(f"Account created. Your account number is {acc.acc_no}")

elif choice == "Deposit":
    st.subheader("Deposit")
    if len(bank.accounts) == 0:
        st.info("No accounts yet.")
    else:
        acc_no = st.selectbox("Account", account_options(), format_func=account_label)
        amount = st.number_input("Amount to deposit", min_value=0.0, step=100.0, format="%.2f")
        if st.button("Deposit"):
            acc = bank.find_account(acc_no)
            if acc.deposit(amount):
                save_data(bank)
                st.success(f"Deposited. New balance: {acc.balance:.2f}")
            else:
                st.error("Invalid amount.")

elif choice == "Withdraw":
    st.subheader("Withdraw")
    if len(bank.accounts) == 0:
        st.info("No accounts yet.")
    else:
        acc_no = st.selectbox("Account", account_options(), format_func=account_label)
        amount = st.number_input("Amount to withdraw", min_value=0.0, step=100.0, format="%.2f")
        if st.button("Withdraw"):
            acc = bank.find_account(acc_no)
            if acc.withdraw(amount):
                save_data(bank)
                st.success(f"Withdrawn. New balance: {acc.balance:.2f}")
            else:
                st.error("Invalid amount or insufficient balance.")

elif choice == "Transfer":
    st.subheader("Transfer")
    if len(bank.accounts) < 2:
        st.info("You need at least 2 accounts to make a transfer.")
    else:
        from_no = st.selectbox("From account", account_options(), format_func=account_label)
        to_no = st.selectbox("To account", account_options(), format_func=account_label)
        amount = st.number_input("Amount", min_value=0.0, step=100.0, format="%.2f")
        if st.button("Transfer"):
            ok, message = bank.transfer(from_no, to_no, amount)
            if ok:
                save_data(bank)
                st.success(message)
            else:
                st.error(message)

elif choice == "Check balance":
    st.subheader("Check balance")
    if len(bank.accounts) == 0:
        st.info("No accounts yet.")
    else:
        acc_no = st.selectbox("Account", account_options(), format_func=account_label)
        acc = bank.find_account(acc_no)
        st.write(f"**Account No:** {acc.acc_no}")
        st.write(f"**Name:** {acc.name}")
        st.write(f"**Balance:** {acc.balance:.2f}")

elif choice == "Show all accounts":
    st.subheader("All accounts")
    if len(bank.accounts) == 0:
        st.info("No accounts yet.")
    else:
        rows = []
        for acc in bank.accounts:
            rows.append(
                {
                    "Account No": acc.acc_no,
                    "Name": acc.name,
                    "Balance": f"{acc.balance:.2f}",
                }
            )
        st.table(rows)

elif choice == "Delete account":
    st.subheader("Delete account")
    if len(bank.accounts) == 0:
        st.info("No accounts yet.")
    else:
        acc_no = st.selectbox("Account", account_options(), format_func=account_label)
        confirm = st.checkbox("I am sure I want to delete this account")
        if st.button("Delete"):
            if not confirm:
                st.warning("Please tick the confirmation box first.")
            elif bank.delete_account(acc_no):
                save_data(bank)
                st.success("Account deleted.")
                st.rerun()
            else:
                st.error("Account not found.")
