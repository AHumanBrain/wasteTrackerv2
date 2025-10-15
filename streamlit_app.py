# streamlit_app.py
#
# Streamlit chemical waste tracker with:
# - add entries (date, business, stream, quantity kg)
# - delete entry with confirmation
# - CSV export / download
# - preserved audit log of every add/delete/reset
# - reset inventory (clears current waste but keeps audit)
# - monthly & annual tallies
# - 80% capacity warning and slick color-changing progress bar
# - bar chart (streams) and pie chart (businesses)
#
# No pandas required. Uses sqlite3 and built-in libraries.
#
# Run:
#   pip install streamlit altair
#   streamlit run streamlit_app.py
#

import streamlit as st
import sqlite3
from datetime import datetime, date
import csv
import io
import altair as alt
from typing import List, Dict, Any

# -----------------------
# Configuration
# -----------------------
DB_PATH = "waste_streamlit.db"   # change if you want a specific path
MAX_MASS_ON_SITE = 1000.0        # kg monthly capacity
BUSINESSES = ["DAB", "CTI"]
STREAMS = ["ACN", "DCM"]

# -----------------------
# Database helpers
# -----------------------
def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    conn = get_conn()
    c = conn.cursor()
    # current inventory table
    c.execute("""
    CREATE TABLE IF NOT EXISTS waste (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        business TEXT NOT NULL,
        stream TEXT NOT NULL,
        quantity REAL NOT NULL
    )
    """)
    # audit log table
    c.execute("""
    CREATE TABLE IF NOT EXISTS audit (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event TEXT NOT NULL,            -- 'insert'|'delete'|'reset'
        entry_date TEXT,                -- the date field from the entry (YYYY-MM-DD) or NULL for reset
        business TEXT,
        stream TEXT,
        quantity REAL,
        ts TEXT NOT NULL                -- timestamp of event
    )
    """)
    conn.commit()
    conn.close()

def insert_entry(entry_date: str, business: str, stream: str, quantity: float):
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT INTO waste (date, business, stream, quantity) VALUES (?, ?, ?, ?)",
              (entry_date, business, stream, quantity))
    conn.commit()
    # add to audit
    c.execute("INSERT INTO audit (event, entry_date, business, stream, quantity, ts) VALUES (?, ?, ?, ?, ?, ?)",
              ("insert", entry_date, business, stream, quantity, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

def delete_entry(entry_id: int):
    conn = get_conn()
    c = conn.cursor()
    # fetch the row to log it
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
    # dump existing rows to audit as reset events (so user can see what was reset)
    c.execute("SELECT date, business, stream, quantity FROM waste")
    rows = c.fetchall()
    ts = datetime.utcnow().isoformat()
    for r in rows:
        c.execute("INSERT INTO audit (event, entry_date, business, stream, quantity, ts) VALUES (?, ?, ?, ?, ?, ?)",
                  ("reset", r[0], r[1], r[2], r[3], ts))
    # clear the waste table
    c.execute("DELETE FROM waste")
    conn.commit()
    conn.close()

def get_monthly_entries(year_month: str) -> List[tuple]:
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, date, business, stream, quantity FROM waste WHERE date LIKE ? ORDER BY date ASC", (f"{year_month}%",))
    rows = c.fetchall()
    conn.close()
    return rows

def get_all_audit(limit: int = 1000) -> List[tuple]:
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, event, entry_date, business, stream, quantity, ts FROM audit ORDER BY id DESC LIMIT ?", (limit,))
    rows = c.fetchall()
    conn.close()
    return rows

def get_annual_total(year: int) -> float:
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

# Sidebar controls
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
    if st.button("Download full audit log (CSV)"):
        # generate CSV of audit
        audit = get_all_audit(limit=1000000)
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["id","event","entry_date","business","stream","quantity","ts"])
        writer.writerows(audit)
        st.download_button("Download audit.csv", data=buffer.getvalue(), file_name="audit.csv", mime="text/csv")
    st.markdown("Hosting & Teams")
    st.markdown("To embed this app into Microsoft Teams, host it at a public HTTPS URL (e.g. Streamlit Cloud, Render, Railway) and add it as a Teams tab (Website). See the 'Embed into Teams' section below for steps.")
    st.markdown("---")
    st.markdown("Developer notes")
    st.write(f"DB path: `{DB_PATH}`")
    st.write(f"Capacity: {MAX_MASS_ON_SITE} kg")

# --- Main layout: left column form + right column charts/totals
col_form, col_viz = st.columns([1, 2])

# FORM: add entry
with col_form:
    st.subheader("Add waste entry")
    today = datetime.today().strftime("%Y-%m-%d")
    entry_date = st.date_input("Date", value=date.today())
    business = st.selectbox("Business", BUSINESSES)
    stream = st.selectbox("Stream", STREAMS)
    quantity = st.number_input("Quantity (kg)", min_value=0.0, step=0.01, format="%.2f")
    if st.button("Add entry"):
        insert_entry(entry_date.isoformat(), business, stream, float(quantity))
        st.success("Entry added.")
        st.experimental_rerun()  # refresh to show new entry / updated charts

# Ensure we display the *current month* rows
current_month = datetime.today().strftime("%Y-%m")
entries = get_monthly_entries(current_month)  # list of (id, date, business, stream, quantity)

# Compute totals for display
monthly_total = sum(row[4] for row in entries) if entries else 0.0
usage_percent = min(monthly_total / MAX_MASS_ON_SITE * 100 if MAX_MASS_ON_SITE > 0 else 0, 100)
annual_total = get_annual_total(datetime.today().year)

# Right column: charts & progress
with col_viz:
    st.subheader("Overview")
    # Warning if >=80%
    if usage_percent >= 80:
        st.warning(f"⚠️ On-site capacity at {usage_percent:.1f}% ({monthly_total:.2f} kg / {MAX_MASS_ON_SITE} kg).")

    # Slick progress bar (HTML + CSS) with animation
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
    // compute dynamic color by mapping pct 0->100 to hsl(210 -> 0)
    function pctToHue(p) {{
        const start = 210, end = 0;
        return Math.round(start + (end - start) * (p/100));
    }}
    const hue = pctToHue(Math.min(100, pct));
    const color = `hsl(${hue}, 75%, 55%)`;
    // set gradient with color at the current percentage
    // We'll make left portion the computed color, right portion darker.
    setTimeout(()=>{{
        bar.style.width = Math.min(100, pct) + '%';
        bar.style.background = color;
        bar.textContent = Math.round(pct) + '%';
    }}, 50);
    </script>
    """
    st.components.v1.html(progress_html, height=100)

    # Charts: bar for streams and pie for businesses
    st.markdown("### Charts")
    # prepare data for altair (list of dicts)
    stream_totals = {}
    business_totals = {}
    for _, d, b, s, q in [(row[0], row[1], row[2], row[3], row[4]) for row in entries]:
        pass  # this loop is awkward; we will construct from 'entries' below

    # Build aggregates from entries
    for row in entries:
        _id, d, b, s, q = row
        stream_totals.setdefault(s, 0.0)
        stream_totals[s] += q
        business_totals.setdefault(b, 0.0)
        business_totals[b] += q

    # Ensure the charts include all pre-defined labels (so missing ones show as 0)
    stream_data = [{"stream": s, "quantity": float(stream_totals.get(s, 0.0))} for s in STREAMS]
    business_data = [{"business": b, "quantity": float(business_totals.get(b, 0.0))} for b in BUSINESSES]

    # Altair bar chart (streams)
    stream_chart = alt.Chart(alt.Data(values=stream_data)).mark_bar().encode(
        x=alt.X('stream:N', title='Stream'),
        y=alt.Y('quantity:Q', title='Quantity (kg)'),
        color=alt.Color('quantity:Q', scale=alt.Scale(scheme='purpleorange'), legend=None),
        tooltip=['stream', alt.Tooltip('quantity:Q', format='.2f')]
    ).properties(height=300, width='container')
    st.altair_chart(stream_chart, use_container_width=True)

    # Altair pie chart for business breakdown
    if any(d["quantity"] > 0 for d in business_data):
        pie = alt.Chart(alt.Data(values=business_data)).mark_arc().encode(
            theta=alt.Theta(field="quantity", type="quantitative"),
            color=alt.Color(field="business", type="nominal", legend=alt.Legend(title="Business")),
            tooltip=[alt.Tooltip('business:N'), alt.Tooltip('quantity:Q', format='.2f')]
        ).properties(height=300)
        st.altair_chart(pie, use_container_width=True)
    else:
        st.info("No business data yet to display pie chart.")

    # Annual tally
    st.markdown(f"**Running annual tally (year {datetime.today().year}):** {annual_total:.2f} kg")

# -----------------------
# Lower area: table of entries with delete buttons
# -----------------------
st.subheader("This month's entries (editable)")

if entries:
    # present a table and per-row delete
    for row in entries:
        entry_id, d, b, s, q = row
        cols = st.columns([2,2,2,1,1])
        cols[0].write(d)
        cols[1].write(b)
        cols[2].write(s)
        cols[3].write(f"{q:.2f} kg")
        delete_key = f"delete_{entry_id}"
        if cols[4].button("Delete", key=delete_key):
            # set a session state to remember pending delete
            st.session_state["pending_delete"] = {"id": entry_id, "date": d, "business": b, "stream": s, "quantity": q}
            st.experimental_rerun()
    # If a delete is pending, show confirmation box
    if st.session_state.get("pending_delete"):
        pd = st.session_state["pending_delete"]
        st.warning(f"Confirm deletion of entry: {pd['date']} — {pd['business']} / {pd['stream']} — {pd['quantity']} kg")
        confirm_col, cancel_col = st.columns(2)
        if confirm_col.button("Confirm delete"):
            delete_entry(pd["id"])
            st.success("Entry deleted and logged.")
            del st.session_state["pending_delete"]
            st.experimental_rerun()
        if cancel_col.button("Cancel"):
            del st.session_state["pending_delete"]
            st.info("Deletion cancelled.")
            st.experimental_rerun()
else:
    st.info("No entries for this month yet.")

st.markdown("---")
st.subheader("Audit log (most recent events)")
audit = get_all_audit(limit=200)
if audit:
    # simple table
    rows_for_display = []
    for a in audit:
        aid, event, entry_date, business, stream, quantity, ts = a
        rows_for_display.append({
            "id": aid,
            "event": event,
            "entry_date": entry_date,
            "business": business,
            "stream": stream,
            "quantity": f"{quantity:.2f}" if quantity is not None else "",
            "timestamp": ts
        })
    st.table(rows_for_display)
else:
    st.info("No audit records yet.")

# -----------------------
# Embed into Teams (instructions)
# -----------------------
st.markdown("---")
st.header("Embed this app into Microsoft Teams")
st.markdown("""
You can add the hosted Streamlit app as a **Website** tab in Microsoft Teams or package it as a Teams tab app. Two common options:

1. **Quick (Website tab)**  
   - Host this Streamlit app at a public HTTPS URL (Streamlit Community Cloud, Render, Railway, etc.).  
   - In Teams, go to the channel where you want the tab → click **+** → choose **Website** → paste the app URL → click **Save**.  
   - Make sure the hosting provider allows embedding in an iframe; Streamlit Cloud pages generally work as website tabs.

2. **App manifest (packs to a tab)**  
   - Create a Teams app manifest where the tab `contentUrl` points to your app URL.  
   - Upload the manifest to your Teams tenant (requires admin sidebar OR developer mode).  
   - See Microsoft docs for packaging Teams tab apps.

**Notes & gotchas**
- The app must be served over HTTPS for Teams.  
- If you host behind an auth layer, Teams needs to be able to authenticate users (SSO options exist but are separate).  
- If you want a more integrated experience (deep linking, SSO), we can add Teams SSO support — tell me and I'll outline the steps.
""")

# Final small footer
st.markdown("**Done.** If you want changes (more charts, filtering by date range, per-business views, or SSO for Teams), tell me what to add and I'll update the app.")
