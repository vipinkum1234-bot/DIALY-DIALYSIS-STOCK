import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, date
import plotly.express as px
import os

# ==================== CONFIG ====================
st.set_page_config(
    page_title="Dialysis Stock Manager",
    page_icon="💉",
    layout="wide",
    initial_sidebar_state="expanded"
)

DB_PATH = "dialysis_stock.db"

# ==================== DATABASE ====================
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            unit TEXT DEFAULT 'pcs',
            min_stock REAL DEFAULT 10,
            current_stock REAL DEFAULT 0,
            created_at TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS suppliers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT,
            address TEXT,
            gstin TEXT,
            created_at TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS purchase_bills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            supplier_id INTEGER,
            bill_no TEXT,
            bill_date TEXT,
            total_amount REAL DEFAULT 0,
            paid_amount REAL DEFAULT 0,
            notes TEXT,
            created_at TEXT,
            FOREIGN KEY (supplier_id) REFERENCES suppliers(id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS stock_in (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER,
            quantity REAL,
            rate REAL DEFAULT 0,
            amount REAL DEFAULT 0,
            supplier_id INTEGER,
            bill_id INTEGER,
            entry_date TEXT,
            notes TEXT,
            created_at TEXT,
            FOREIGN KEY (item_id) REFERENCES items(id),
            FOREIGN KEY (supplier_id) REFERENCES suppliers(id),
            FOREIGN KEY (bill_id) REFERENCES purchase_bills(id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS stock_out (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER,
            quantity REAL,
            entry_date TEXT,
            reason TEXT,
            notes TEXT,
            created_at TEXT,
            FOREIGN KEY (item_id) REFERENCES items(id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bill_id INTEGER,
            amount REAL,
            payment_date TEXT,
            mode TEXT,
            reference TEXT,
            notes TEXT,
            created_at TEXT,
            FOREIGN KEY (bill_id) REFERENCES purchase_bills(id)
        )
    """)

    # Default items
    default_items = [
        ("Dialyzer", "pcs", 20),
        ("Blood Tubing", "set", 30),
        ("NS (Normal Saline)", "bottle", 50),
        ("Heparin", "vial", 40),
        ("Fistula Needle", "pcs", 50),
        ("CAPD Fluid", "bag", 30),
        ("AV Fistula Needle", "pcs", 40),
        ("Dialysis Concentrate", "can", 15),
        ("Gloves", "box", 20),
        ("Syringe 10ml", "pcs", 100),
    ]

    for name, unit, min_s in default_items:
        c.execute(
            "INSERT OR IGNORE INTO items (name, unit, min_stock, current_stock, created_at) VALUES (?, ?, ?, 0, ?)",
            (name, unit, min_s, datetime.now().isoformat())
        )

    conn.commit()
    conn.close()

init_db()

# ==================== HELPERS ====================
def get_items():
    conn = get_conn()
    df = pd.read_sql("SELECT * FROM items ORDER BY name", conn)
    conn.close()
    return df

def get_suppliers():
    conn = get_conn()
    df = pd.read_sql("SELECT * FROM suppliers ORDER BY name", conn)
    conn.close()
    return df

def update_item_stock(item_id, qty_change):
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE items SET current_stock = current_stock + ? WHERE id = ?", (qty_change, item_id))
    conn.commit()
    conn.close()

def format_inr(amount):
    try:
        return f"₹{float(amount):,.2f}"
    except:
        return "₹0.00"

# ==================== SIDEBAR ====================
st.sidebar.title("💉 Dialysis Stock")
st.sidebar.markdown("---")

menu = st.sidebar.radio(
    "मेनू चुनें",
    [
        "📊 Dashboard",
        "📦 Stock In",
        "📤 Stock Out",
        "📋 Current Stock",
        "🧾 Purchase Bills",
        "💰 Payments",
        "🏪 Suppliers",
        "➕ Items Master",
        "📈 Reports"
    ]
)

st.sidebar.markdown("---")
st.sidebar.info("Dialysis Inventory & Supplier Manager\nCloud Ready Web App")

# ==================== DASHBOARD ====================
if menu == "📊 Dashboard":
    st.title("📊 Dashboard")
    st.markdown("### Dialysis Center Stock Overview")

    items = get_items()
    suppliers = get_suppliers()

    col1, col2, col3, col4 = st.columns(4)

    total_items = len(items)
    low_stock = len(items[items["current_stock"] <= items["min_stock"]]) if not items.empty else 0

    conn = get_conn()
    pending = pd.read_sql(
        "SELECT SUM(total_amount - paid_amount) as pending FROM purchase_bills WHERE total_amount > paid_amount",
        conn
    )
    pending_amt = pending["pending"].iloc[0] if pending["pending"].iloc[0] else 0

    today_out = pd.read_sql(
        "SELECT COUNT(*) as cnt FROM stock_out WHERE entry_date = ?",
        conn, params=(date.today().isoformat(),)
    )
    today_out_cnt = today_out["cnt"].iloc[0]
    conn.close()

    col1.metric("कुल आइटम", total_items)
    col2.metric("⚠️ Low Stock", low_stock, delta_color="inverse")
    col3.metric("बकाया पेमेंट", format_inr(pending_amt))
    col4.metric("आज Stock Out", today_out_cnt)

    st.markdown("---")

    # Low stock table
    if not items.empty:
        low_df = items[items["current_stock"] <= items["min_stock"]][["name", "current_stock", "min_stock", "unit"]]
        if not low_df.empty:
            st.subheader("⚠️ Low Stock Alert")
            st.dataframe(low_df, use_container_width=True, hide_index=True)
        else:
            st.success("सभी आइटम का स्टॉक पर्याप्त है ✅")

    # Recent stock out
    st.subheader("हाल ही का Stock Out")
    conn = get_conn()
    recent = pd.read_sql("""
        SELECT so.entry_date, i.name, so.quantity, i.unit, so.reason
        FROM stock_out so
        JOIN items i ON so.item_id = i.id
        ORDER BY so.id DESC LIMIT 10
    """, conn)
    conn.close()
    if not recent.empty:
        st.dataframe(recent, use_container_width=True, hide_index=True)
    else:
        st.info("अभी कोई Stock Out नहीं हुआ")

# ==================== STOCK IN ====================
elif menu == "📦 Stock In":
    st.title("📦 Stock In (माल आना)")

    items = get_items()
    suppliers = get_suppliers()

    if items.empty:
        st.warning("पहले Items Master में आइटम ऐड करें")
    else:
        with st.form("stock_in_form", clear_on_submit=True):
            col1, col2 = st.columns(2)

            item_names = items["name"].tolist()
            selected_item = col1.selectbox("आइटम चुनें *", item_names)
            qty = col1.number_input("क्वांटिटी *", min_value=0.01, step=1.0, value=1.0)
            rate = col1.number_input("रेट (₹)", min_value=0.0, step=0.5, value=0.0)

            supplier_names = ["-- कोई नहीं --"] + suppliers["name"].tolist() if not suppliers.empty else ["-- कोई नहीं --"]
            selected_supplier = col2.selectbox("सप्लायर", supplier_names)
            entry_date = col2.date_input("तारीख", value=date.today())
            bill_no = col2.text_input("बिल नंबर (अगर है)")
            notes = st.text_area("नोट्स")

            submitted = st.form_submit_button("✅ Stock In सेव करें", use_container_width=True)

            if submitted:
                item_id = int(items[items["name"] == selected_item]["id"].iloc[0])
                amount = qty * rate

                supplier_id = None
                if selected_supplier != "-- कोई नहीं --" and not suppliers.empty:
                    supplier_id = int(suppliers[suppliers["name"] == selected_supplier]["id"].iloc[0])

                bill_id = None
                conn = get_conn()
                c = conn.cursor()

                # If bill_no given, create or link bill
                if bill_no and supplier_id:
                    c.execute(
                        "INSERT INTO purchase_bills (supplier_id, bill_no, bill_date, total_amount, paid_amount, created_at) VALUES (?, ?, ?, ?, 0, ?)",
                        (supplier_id, bill_no, entry_date.isoformat(), amount, datetime.now().isoformat())
                    )
                    bill_id = c.lastrowid

                c.execute("""
                    INSERT INTO stock_in (item_id, quantity, rate, amount, supplier_id, bill_id, entry_date, notes, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (item_id, qty, rate, amount, supplier_id, bill_id, entry_date.isoformat(), notes, datetime.now().isoformat()))

                conn.commit()
                conn.close()

                update_item_stock(item_id, qty)
                st.success(f"✅ {qty} {selected_item} स्टॉक में ऐड हो गया!")
                st.balloons()

        st.markdown("---")
        st.subheader("हाल ही के Stock In")
        conn = get_conn()
        recent_in = pd.read_sql("""
            SELECT si.entry_date, i.name, si.quantity, i.unit, si.rate, si.amount, s.name as supplier
            FROM stock_in si
            JOIN items i ON si.item_id = i.id
            LEFT JOIN suppliers s ON si.supplier_id = s.id
            ORDER BY si.id DESC LIMIT 15
        """, conn)
        conn.close()
        if not recent_in.empty:
            st.dataframe(recent_in, use_container_width=True, hide_index=True)

# ==================== STOCK OUT ====================
elif menu == "📤 Stock Out":
    st.title("📤 Stock Out (माल इस्तेमाल)")

    items = get_items()
    if items.empty:
        st.warning("पहले Items ऐड करें")
    else:
        with st.form("stock_out_form", clear_on_submit=True):
            col1, col2 = st.columns(2)

            item_names = items["name"].tolist()
            selected_item = col1.selectbox("आइटम चुनें *", item_names)

            current = items[items["name"] == selected_item]["current_stock"].iloc[0]
            unit = items[items["name"] == selected_item]["unit"].iloc[0]
            col1.info(f"वर्तमान स्टॉक: **{current} {unit}**")

            qty = col1.number_input("क्वांटिटी *", min_value=0.01, step=1.0, value=1.0)
            entry_date = col2.date_input("तारीख", value=date.today())
            reason = col2.selectbox("कारण", ["Patient Dialysis", "Wastage", "Expired", "Transfer", "Other"])
            notes = st.text_area("नोट्स / Patient ID")

            submitted = st.form_submit_button("✅ Stock Out सेव करें", use_container_width=True)

            if submitted:
                if qty > current:
                    st.error(f"❌ पर्याप्त स्टॉक नहीं है! उपलब्ध: {current}")
                else:
                    item_id = int(items[items["name"] == selected_item]["id"].iloc[0])
                    conn = get_conn()
                    c = conn.cursor()
                    c.execute("""
                        INSERT INTO stock_out (item_id, quantity, entry_date, reason, notes, created_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (item_id, qty, entry_date.isoformat(), reason, notes, datetime.now().isoformat()))
                    conn.commit()
                    conn.close()

                    update_item_stock(item_id, -qty)
                    st.success(f"✅ {qty} {selected_item} स्टॉक से कम हो गया!")

        st.markdown("---")
        st.subheader("हाल ही के Stock Out")
        conn = get_conn()
        recent_out = pd.read_sql("""
            SELECT so.entry_date, i.name, so.quantity, i.unit, so.reason, so.notes
            FROM stock_out so
            JOIN items i ON so.item_id = i.id
            ORDER BY so.id DESC LIMIT 15
        """, conn)
        conn.close()
        if not recent_out.empty:
            st.dataframe(recent_out, use_container_width=True, hide_index=True)

# ==================== CURRENT STOCK ====================
elif menu == "📋 Current Stock":
    st.title("📋 Current Stock Status")

    items = get_items()
    if items.empty:
        st.info("कोई आइटम नहीं मिला")
    else:
        # Status column
        def status(row):
            if row["current_stock"] <= 0:
                return "🔴 Out of Stock"
            elif row["current_stock"] <= row["min_stock"]:
                return "🟡 Low Stock"
            else:
                return "🟢 OK"

        items["Status"] = items.apply(status, axis=1)
        display_df = items[["name", "current_stock", "min_stock", "unit", "Status"]].rename(columns={
            "name": "आइटम",
            "current_stock": "वर्तमान स्टॉक",
            "min_stock": "न्यूनतम स्टॉक",
            "unit": "यूनिट"
        })

        st.dataframe(display_df, use_container_width=True, hide_index=True)

        # Chart
        fig = px.bar(
            items, x="name", y="current_stock",
            color="Status",
            title="Current Stock Levels",
            labels={"name": "Item", "current_stock": "Stock"}
        )
        st.plotly_chart(fig, use_container_width=True)

# ==================== PURCHASE BILLS ====================
elif menu == "🧾 Purchase Bills":
    st.title("🧾 Purchase Bills (खरीद बिल)")

    suppliers = get_suppliers()
    items = get_items()

    tab1, tab2 = st.tabs(["नया बिल बनाएं", "सभी बिल देखें"])

    with tab1:
        if suppliers.empty:
            st.warning("पहले सप्लायर ऐड करें (Suppliers मेनू से)")
        else:
            with st.form("bill_form", clear_on_submit=True):
                col1, col2 = st.columns(2)
                supplier = col1.selectbox("सप्लायर *", suppliers["name"].tolist())
                bill_no = col1.text_input("बिल नंबर *")
                bill_date = col2.date_input("बिल तारीख", value=date.today())
                total_amount = col2.number_input("कुल बिल अमाउंट (₹) *", min_value=0.0, step=100.0)
                notes = st.text_area("नोट्स")

                submitted = st.form_submit_button("✅ बिल सेव करें", use_container_width=True)

                if submitted:
                    if not bill_no or total_amount <= 0:
                        st.error("बिल नंबर और अमाउंट जरूरी है")
                    else:
                        supplier_id = int(suppliers[suppliers["name"] == supplier]["id"].iloc[0])
                        conn = get_conn()
                        c = conn.cursor()
                        c.execute("""
                            INSERT INTO purchase_bills (supplier_id, bill_no, bill_date, total_amount, paid_amount, notes, created_at)
                            VALUES (?, ?, ?, ?, 0, ?, ?)
                        """, (supplier_id, bill_no, bill_date.isoformat(), total_amount, notes, datetime.now().isoformat()))
                        conn.commit()
                        conn.close()
                        st.success("✅ बिल सेव हो गया!")

    with tab2:
        conn = get_conn()
        bills = pd.read_sql("""
            SELECT pb.id, pb.bill_no, pb.bill_date, s.name as supplier,
                   pb.total_amount, pb.paid_amount,
                   (pb.total_amount - pb.paid_amount) as balance,
                   pb.notes
            FROM purchase_bills pb
            JOIN suppliers s ON pb.supplier_id = s.id
            ORDER BY pb.id DESC
        """, conn)
        conn.close()

        if not bills.empty:
            bills["total_amount"] = bills["total_amount"].apply(format_inr)
            bills["paid_amount"] = bills["paid_amount"].apply(format_inr)
            bills["balance"] = bills["balance"].apply(format_inr)
            st.dataframe(bills, use_container_width=True, hide_index=True)
        else:
            st.info("अभी कोई बिल नहीं है")

# ==================== PAYMENTS ====================
elif menu == "💰 Payments":
    st.title("💰 Payments (सप्लायर पेमेंट)")

    conn = get_conn()
    pending_bills = pd.read_sql("""
        SELECT pb.id, pb.bill_no, s.name as supplier, pb.bill_date,
               pb.total_amount, pb.paid_amount,
               (pb.total_amount - pb.paid_amount) as balance
        FROM purchase_bills pb
        JOIN suppliers s ON pb.supplier_id = s.id
        WHERE pb.total_amount > pb.paid_amount
        ORDER BY pb.bill_date
    """, conn)
    conn.close()

    tab1, tab2 = st.tabs(["नया पेमेंट दर्ज करें", "पेमेंट हिस्ट्री"])

    with tab1:
        if pending_bills.empty:
            st.success("🎉 कोई बकाया बिल नहीं है!")
        else:
            st.subheader("बकाया बिल")
            display_pending = pending_bills.copy()
            display_pending["total_amount"] = display_pending["total_amount"].apply(format_inr)
            display_pending["paid_amount"] = display_pending["paid_amount"].apply(format_inr)
            display_pending["balance"] = display_pending["balance"].apply(format_inr)
            st.dataframe(display_pending[["bill_no", "supplier", "bill_date", "total_amount", "paid_amount", "balance"]],
                         use_container_width=True, hide_index=True)

            with st.form("payment_form", clear_on_submit=True):
                bill_options = {
                    f"{row['bill_no']} | {row['supplier']} | बाकी: {format_inr(row['balance'])}": row["id"]
                    for _, row in pending_bills.iterrows()
                }
                selected = st.selectbox("बिल चुनें *", list(bill_options.keys()))
                amount = st.number_input("पेमेंट अमाउंट (₹) *", min_value=0.01, step=100.0)
                pay_date = st.date_input("पेमेंट तारीख", value=date.today())
                mode = st.selectbox("पेमेंट मोड", ["Cash", "UPI", "NEFT/RTGS", "Cheque", "Other"])
                reference = st.text_input("रेफरेंस / UTR / Cheque No.")
                notes = st.text_area("नोट्स")

                submitted = st.form_submit_button("✅ पेमेंट सेव करें", use_container_width=True)

                if submitted:
                    bill_id = bill_options[selected]
                    conn = get_conn()
                    c = conn.cursor()

                    # Insert payment
                    c.execute("""
                        INSERT INTO payments (bill_id, amount, payment_date, mode, reference, notes, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (bill_id, amount, pay_date.isoformat(), mode, reference, notes, datetime.now().isoformat()))

                    # Update bill paid_amount
                    c.execute("UPDATE purchase_bills SET paid_amount = paid_amount + ? WHERE id = ?", (amount, bill_id))
                    conn.commit()
                    conn.close()
                    st.success("✅ पेमेंट दर्ज हो गया!")
                    st.rerun()

    with tab2:
        conn = get_conn()
        payments = pd.read_sql("""
            SELECT p.payment_date, pb.bill_no, s.name as supplier, p.amount, p.mode, p.reference, p.notes
            FROM payments p
            JOIN purchase_bills pb ON p.bill_id = pb.id
            JOIN suppliers s ON pb.supplier_id = s.id
            ORDER BY p.id DESC
        """, conn)
        conn.close()
        if not payments.empty:
            payments["amount"] = payments["amount"].apply(format_inr)
            st.dataframe(payments, use_container_width=True, hide_index=True)
        else:
            st.info("अभी कोई पेमेंट नहीं हुआ")

# ==================== SUPPLIERS ====================
elif menu == "🏪 Suppliers":
    st.title("🏪 Suppliers Management")

    tab1, tab2 = st.tabs(["नया सप्लायर ऐड करें", "सभी सप्लायर"])

    with tab1:
        with st.form("supplier_form", clear_on_submit=True):
            name = st.text_input("सप्लायर नाम *")
            phone = st.text_input("फोन नंबर")
            address = st.text_area("पता")
            gstin = st.text_input("GSTIN")

            submitted = st.form_submit_button("✅ सप्लायर सेव करें", use_container_width=True)

            if submitted:
                if not name.strip():
                    st.error("नाम जरूरी है")
                else:
                    conn = get_conn()
                    c = conn.cursor()
                    c.execute("""
                        INSERT INTO suppliers (name, phone, address, gstin, created_at)
                        VALUES (?, ?, ?, ?, ?)
                    """, (name.strip(), phone, address, gstin, datetime.now().isoformat()))
                    conn.commit()
                    conn.close()
                    st.success(f"✅ सप्लायर '{name}' ऐड हो गया!")

    with tab2:
        suppliers = get_suppliers()
        if not suppliers.empty:
            st.dataframe(suppliers[["name", "phone", "address", "gstin"]], use_container_width=True, hide_index=True)
        else:
            st.info("अभी कोई सप्लायर नहीं है")

# ==================== ITEMS MASTER ====================
elif menu == "➕ Items Master":
    st.title("➕ Items Master (आइटम लिस्ट)")

    tab1, tab2 = st.tabs(["नया आइटम ऐड करें", "सभी आइटम"])

    with tab1:
        with st.form("item_form", clear_on_submit=True):
            name = st.text_input("आइटम नाम *")
            unit = st.selectbox("यूनिट", ["pcs", "set", "bottle", "vial", "bag", "box", "can", "liter", "other"])
            min_stock = st.number_input("न्यूनतम स्टॉक (Alert के लिए)", min_value=0.0, value=10.0, step=1.0)

            submitted = st.form_submit_button("✅ आइटम सेव करें", use_container_width=True)

            if submitted:
                if not name.strip():
                    st.error("नाम जरूरी है")
                else:
                    conn = get_conn()
                    c = conn.cursor()
                    try:
                        c.execute("""
                            INSERT INTO items (name, unit, min_stock, current_stock, created_at)
                            VALUES (?, ?, ?, 0, ?)
                        """, (name.strip(), unit, min_stock, datetime.now().isoformat()))
                        conn.commit()
                        st.success(f"✅ आइटम '{name}' ऐड हो गया!")
                    except sqlite3.IntegrityError:
                        st.error("यह आइटम पहले से मौजूद है")
                    conn.close()

    with tab2:
        items = get_items()
        if not items.empty:
            st.dataframe(
                items[["name", "unit", "current_stock", "min_stock"]].rename(columns={
                    "name": "आइटम", "unit": "यूनिट",
                    "current_stock": "वर्तमान स्टॉक", "min_stock": "न्यूनतम"
                }),
                use_container_width=True, hide_index=True
            )

            st.markdown("---")
            st.subheader("न्यूनतम स्टॉक अपडेट करें")
            item_to_edit = st.selectbox("आइटम चुनें", items["name"].tolist(), key="edit_item")
            new_min = st.number_input("नया न्यूनतम स्टॉक", min_value=0.0, step=1.0, key="new_min")
            if st.button("अपडेट करें"):
                item_id = int(items[items["name"] == item_to_edit]["id"].iloc[0])
                conn = get_conn()
                c = conn.cursor()
                c.execute("UPDATE items SET min_stock = ? WHERE id = ?", (new_min, item_id))
                conn.commit()
                conn.close()
                st.success("अपडेट हो गया!")
                st.rerun()
        else:
            st.info("अभी कोई आइटम नहीं है")

# ==================== REPORTS ====================
elif menu == "📈 Reports":
    st.title("📈 Reports")

    col1, col2 = st.columns(2)
    from_date = col1.date_input("From Date", value=date.today().replace(day=1))
    to_date = col2.date_input("To Date", value=date.today())

    conn = get_conn()

    st.subheader("Stock In Summary")
    stock_in_report = pd.read_sql("""
        SELECT i.name, SUM(si.quantity) as total_in, i.unit, SUM(si.amount) as total_value
        FROM stock_in si
        JOIN items i ON si.item_id = i.id
        WHERE si.entry_date BETWEEN ? AND ?
        GROUP BY i.name, i.unit
        ORDER BY total_in DESC
    """, conn, params=(from_date.isoformat(), to_date.isoformat()))
    if not stock_in_report.empty:
        stock_in_report["total_value"] = stock_in_report["total_value"].apply(format_inr)
        st.dataframe(stock_in_report, use_container_width=True, hide_index=True)
    else:
        st.info("इस अवधि में कोई Stock In नहीं")

    st.subheader("Stock Out Summary")
    stock_out_report = pd.read_sql("""
        SELECT i.name, SUM(so.quantity) as total_out, i.unit, so.reason
        FROM stock_out so
        JOIN items i ON so.item_id = i.id
        WHERE so.entry_date BETWEEN ? AND ?
        GROUP BY i.name, i.unit, so.reason
        ORDER BY total_out DESC
    """, conn, params=(from_date.isoformat(), to_date.isoformat()))
    if not stock_out_report.empty:
        st.dataframe(stock_out_report, use_container_width=True, hide_index=True)
    else:
        st.info("इस अवधि में कोई Stock Out नहीं")

    st.subheader("Supplier Payment Summary")
    pay_report = pd.read_sql("""
        SELECT s.name as supplier,
               SUM(pb.total_amount) as total_billed,
               SUM(pb.paid_amount) as total_paid,
               SUM(pb.total_amount - pb.paid_amount) as balance
        FROM purchase_bills pb
        JOIN suppliers s ON pb.supplier_id = s.id
        GROUP BY s.name
    """, conn)
    conn.close()

    if not pay_report.empty:
        pay_report["total_billed"] = pay_report["total_billed"].apply(format_inr)
        pay_report["total_paid"] = pay_report["total_paid"].apply(format_inr)
        pay_report["balance"] = pay_report["balance"].apply(format_inr)
        st.dataframe(pay_report, use_container_width=True, hide_index=True)
    else:
        st.info("अभी कोई बिल/पेमेंट डेटा नहीं")
