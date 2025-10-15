# streamlit_app.py (fixed JS template literal bug)

import streamlit as st
import sqlite3
from datetime import datetime, date
import csv
import io
import altair as alt

DB_PATH = "waste_streamlit.db"
MAX_MASS_ON_SITE = 1000.0
BUSINESSES = ["DAB", "CTI"]
STREAMS = ["ACN", "DCM"]

def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS waste (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        business TEXT NOT NULL,
        stream TEXT NOT NULL,
        quantity REAL NOT NULL
    )
    """)
    c.execute("""
    CREATE TABLE IF NOT EXISTS audit (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event TEXT NOT NULL,
        entry_date TEXT,
        business TEXT,
        stream TEXT,
        quantity REAL,
        ts TEXT NOT NULL
    )
    """)
    conn.commit()
    conn.close()

def insert_entry(entry_date, business, stream, quantity):
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT INTO waste (date, business, stream, quantity) VALUES (?, ?, ?, ?)",
              (entry_date, business, stream, quantity))
    c.execute("INSERT INTO audit (event, entry_date, business, stream, quantity, ts) VALUES (?, ?, ?, ?, ?, ?)",
              ("insert", entry_date, business, stream, quantity, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

def delete_entry(entry_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT date, business, stream, quantity FROM waste WHERE id = ?", (entry_id,))
    row = c.fetchone()
    if row:
        entry_date, business, stream, quantity = row
        c.execute("DELETE FROM waste WHERE id = ?", (entry_id,))
        c.execute("INSERT INTO audit (event, entry_date, business, stream, quantity, ts) VALUES (?, ?, ?, ?, ?, ?)",
                  ("delete", entry_date, business, stream, quantity, datetime.utcnow().isoformat()))
        conn.commit()
    conn.close()

def reset_inventory():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT date, business, stream, quantity FROM waste")
    rows = c.fetchall()
    ts = datetime.utcnow().isoformat()
    for r in rows:
        c.execute("INSERT INTO audit (event, entry_date, business, stream, quantity, ts) VALUES (?, ?, ?, ?, ?, ?)",
                  ("reset", r[0], r[1], r[2], r[3], ts))
    c.execute("DELETE FROM waste")
    conn.commit()
    conn.close()

def get_monthly_entries(year_month):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, date, business, stream, quantity FROM waste WHERE date LIKE ? ORDER BY date ASC", (f"{year_month}%",))
    rows = c.fetchall()
    conn.close()
    return rows

def get_all_audit(limit=1000):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, event, entry_date, business, stream, quantity, ts FROM audit ORDER BY id DESC LIMIT ?", (limit,))
    rows = c.fetchall()
    conn.close()
    return rows

def get_annual_total(year):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT SUM(quantity) FROM waste WHERE substr(date,1,4) = ?", (str(year),))
    s = c.fetchone()[0]
    conn.close()
    return float(s) if s else 0.0

# -----------------------
# Streamlit UI
# -----------------------
st.set_page_config(page_title="Chemical Waste Tracker", layout="wide", initial_sidebar_state="expanded")
init_db()

st.title("Chemical Waste Tracker (Streamlit)")

# Sidebar
with st.sidebar:
    st.header("Quick actions")
    if st.button("Reset inventory (clear current entries)"):
        if st.button("CONFIRM reset inventory (double-click)"):
            reset_inventory()
            st.success("Inventory reset — current waste cleared and saved to audit log.")
        else:
            st.info("Click CONFIRM reset inventory (double-click) to proceed.")
    st.markdown("---")
    st.markdown("**Export / Logs**")
    audit = get_all_audit(limit=1000000)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["id","event","entry_date","business","stream","quantity","ts"])
    writer.writerows(audit)
    st.download_button("Download audit log", data=buffer.getvalue(), file_name="audit.csv", mime="text/csv")

# Main UI
col_form, col_viz = st.columns([1, 2])

with col_form:
    st.subheader("Add waste entry")
    entry_date = st.date_input("Date", value=date.today())
    business = st.selectbox("Business", BUSINESSES)
    stream = st.selectbox("Stream", STREAMS)
    quantity = st.number_input("Quantity (kg)", min_value=0.0, step=0.01, format="%.2f")
    if st.button("Add entry"):
        insert_entry(entry_date.isoformat(), business, stream, float(quantity))
        st.success("Entry added.")
        st.experimental_rerun()

current_month = datetime.today().strftime("%Y-%m")
entries = get_monthly_entries(current_month)
monthly_total = sum(row[4] for row in entries) if entries else 0.0
usage_percent = min(monthly_total / MAX_MASS_ON_SITE * 100 if MAX_MASS_ON_SITE > 0 else 0, 100)
annual_total = get_annual_total(datetime.today().year)

with col_viz:
    st.subheader("Overview")
    if usage_percent >= 80:
        st.warning(f"⚠️ On-site capacity at {usage_percent:.1f}% ({monthly_total:.2f} kg / {MAX_MASS_ON_SITE} kg).")

    # ✅ FIXED — escape ${} inside f-string so Python doesn’t interpret it
    progress_html = f"""
    <div style="background:#2b2b2b;border-radius:10px;padding:8px;">
      <div style="color:#ddd;margin-bottom:6px">Monthly usage: {monthly_total:.2f} kg of {MAX_MASS_ON_SITE} kg ({usage_percent:.1f}%)</div>
      <div style="background:#333;border-radius:12px;overflow:hidden;height:30px">
        <div id="bar" style="
            width:0%;
            height:30px;
            border-radius:12px;
            text-align:center;
            color:white;
            line-height:30px;
            transition: width 1.2s ease, background-color 1.2s ease;
            background: linear-gradient(90deg, #4a90e2 0%, #4a90e2 50%, #ff5555 100%);
            ">
          0%
        </div>
      </div>
    </div>
    <script>
    const pct = {usage_percent:.2f};
    const bar = document.getElementById('bar');
    function pctToHue(p) {{
        const start = 210, end = 0;
        return Math.round(start + (end - start) * (p/100));
    }}
    const hue = pctToHue(Math.min(100, pct));
    const color = "hsl(" + hue + ", 75%, 55%)";  // ✅ no template literal, string concat instead
    setTimeout(() => {{
        bar.style.width = Math.min(100, pct) + '%';
        bar.style.background = color;
        bar.textContent = Math.round(pct) + '%';
    }}, 50);
    </script>
    """
    st.components.v1.html(progress_html, height=100)

    # Charts
    stream_totals = {}
    business_totals = {}
    for row in entries:
        _, d, b, s, q = row
        stream_totals[s] = stream_totals.get(s, 0) + q
        business_totals[b] = business_totals.get(b, 0) + q

    stream_data = [{"stream": s, "quantity": stream_totals.get(s, 0.0)} for s in STREAMS]
    business_data = [{"business": b, "quantity": business_totals.get(b, 0.0)} for b in BUSINESSES]

    st.markdown("### Charts")
    stream_chart = alt.Chart(alt.Data(values=stream_data)).mark_bar().encode(
        x="stream:N", y="quantity:Q", color="quantity:Q",
        tooltip=["stream", alt.Tooltip("quantity:Q", format=".2f")]
    )
    st.altair_chart(stream_chart, use_container_width=True)

    if any(d["quantity"] > 0 for d in business_data):
        pie = alt.Chart(alt.Data(values=business_data)).mark_arc().encode(
            theta="quantity:Q",
            color="business:N",
            tooltip=["business", alt.Tooltip("quantity:Q", format=".2f")]
        )
        st.altair_chart(pie, use_container_width=True)

    st.markdown(f"**Running annual tally (year {datetime.today().year}):** {annual_total:.2f} kg")

st.subheader("This month's entries")
if entries:
    for row in entries:
        entry_id, d, b, s, q = row
        cols = st.columns([2, 2, 2, 1, 1])
        cols[0].write(d)
        cols[1].write(b)
        cols[2].write(s)
        cols[3].write(f"{q:.2f} kg")
        if cols[4].button("Delete", key=f"del_{entry_id}"):
            st.session_state["pending_delete"] = {"id": entry_id, "d": d, "b": b, "s": s, "q": q}
            st.experimental_rerun()

    if st.session_state.get("pending_delete"):
        pd = st.session_state["pending_delete"]
        st.warning(f"Confirm deletion of entry: {pd['d']} — {pd['b']} / {pd['s']} — {pd['q']} kg")
        confirm, cancel = st.columns(2)
        if confirm.button("Confirm delete"):
            delete_entry(pd["id"])
            st.success("Entry deleted.")
            del st.session_state["pending_delete"]
            st.experimental_rerun()
        if cancel.button("Cancel"):
            del st.session_state["pending_delete"]
            st.experimental_rerun()
else:
    st.info("No entries this month yet.")

st.markdown("---")
st.subheader("Recent audit log")
audit = get_all_audit(200)
if audit:
    st.table(audit)
else:
    st.info("No audit records yet.")
