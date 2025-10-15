import streamlit as st
import pandas as pd
import datetime
import os
import json
import altair as alt

# =========================================================
# CONFIG
# =========================================================
DATA_FILE = "waste_data.csv"
LOG_FILE = "waste_log.json"
MAX_CAPACITY = 1000  # kg limit
st.set_page_config(page_title="Waste Tracker", layout="wide")

# =========================================================
# INITIAL SETUP
# =========================================================
def load_data():
    if os.path.exists(DATA_FILE):
        return pd.read_csv(DATA_FILE)
    return pd.DataFrame(columns=["Date", "Business", "Stream", "Quantity (kg)"])

def save_data(df):
    df.to_csv(DATA_FILE, index=False)

def log_action(action, record=None):
    log_entry = {
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "action": action,
        "record": record
    }
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r") as f:
            logs = json.load(f)
    else:
        logs = []
    logs.append(log_entry)
    with open(LOG_FILE, "w") as f:
        json.dump(logs, f, indent=2)

# =========================================================
# APP TITLE
# =========================================================
st.title("♻️ Waste Inventory Tracker")
st.markdown("Track, visualize, and manage your site waste capacity in real time.")

# =========================================================
# LOAD & DISPLAY DATA
# =========================================================
df = load_data()

# =========================================================
# INPUT FORM
# =========================================================
st.subheader("Add New Waste Entry")
col1, col2, col3, col4 = st.columns(4)

with col1:
    date = st.date_input("Date", datetime.date.today())

with col2:
    business = st.selectbox("Business", ["DAB", "CTI"])

with col3:
    stream = st.selectbox("Waste Stream", ["ACN", "DCM"])

with col4:
    quantity = st.number_input("Quantity (kg)", min_value=0.0, step=0.1)

if st.button("➕ Add Entry"):
    new_entry = {
        "Date": date.strftime("%Y-%m-%d"),
        "Business": business,
        "Stream": stream,
        "Quantity (kg)": quantity,
    }
    df = pd.concat([df, pd.DataFrame([new_entry])], ignore_index=True)
    save_data(df)
    log_action("ADD_ENTRY", new_entry)
    st.success("✅ Entry added successfully!")

# =========================================================
# DELETE ENTRIES
# =========================================================
st.subheader("Manage Entries")
if not df.empty:
    selected_row = st.selectbox("Select an entry to delete", df.index, format_func=lambda x: f"{df.loc[x, 'Date']} - {df.loc[x, 'Business']} - {df.loc[x, 'Stream']} ({df.loc[x, 'Quantity (kg)']} kg)")
    if st.button("🗑️ Delete Selected Entry"):
        confirm = st.checkbox("Are you sure you want to delete this entry?")
        if confirm:
            deleted = df.loc[selected_row].to_dict()
            df = df.drop(selected_row).reset_index(drop=True)
            save_data(df)
            log_action("DELETE_ENTRY", deleted)
            st.success("✅ Entry deleted.")
        else:
            st.warning("⚠️ Please confirm deletion before proceeding.")
else:
    st.info("No entries yet. Add some to get started.")

# =========================================================
# RESET INVENTORY
# =========================================================
st.subheader("Reset Inventory")
if st.button("♻️ Reset All Data"):
    if st.checkbox("Are you absolutely sure? This cannot be undone."):
        df = pd.DataFrame(columns=["Date", "Business", "Stream", "Quantity (kg)"])
        save_data(df)
        log_action("RESET_DATA")
        st.success("✅ All data reset successfully!")

# =========================================================
# ANNUAL TALLY
# =========================================================
st.subheader("📅 Annual Tally")
if not df.empty:
    df["Year"] = pd.to_datetime(df["Date"]).dt.year
    yearly_sum = df.groupby("Year")["Quantity (kg)"].sum().reset_index()
    st.dataframe(yearly_sum, use_container_width=True)
else:
    st.info("No data available for annual summary yet.")

# =========================================================
# CAPACITY TRACKER (PROGRESS BAR)
# =========================================================
total_kg = df["Quantity (kg)"].sum() if not df.empty else 0
percent_full = min(total_kg / MAX_CAPACITY, 1.0)
hue = int(200 - (percent_full * 200))  # blue → red
progress_color = f"hsl({hue}, 75%, 55%)"

st.markdown(f"### 🏭 Total Waste Stored: **{total_kg:.1f} / {MAX_CAPACITY} kg**")
st.markdown(
    f"""
    <div style='background-color:#ddd; border-radius:20px; height:25px; width:100%;'>
        <div style='background-color:{progress_color}; width:{percent_full*100}%; height:100%; border-radius:20px;'></div>
    </div>
    """,
    unsafe_allow_html=True
)

if percent_full >= 0.8:
    st.error("⚠️ WARNING: You are at or above 80% waste capacity!")

# =========================================================
# VISUALIZATION (Altair)
# =========================================================
if not df.empty:
    stream_chart = (
        alt.Chart(df)
        .mark_bar()
        .encode(
            x=alt.X("Date:T", title="Date"),
            y=alt.Y("sum(Quantity (kg)):Q", title="Quantity (kg)"),
            color="Stream:N",
            tooltip=["Date", "Business", "Stream", "Quantity (kg)"]
        )
        .properties(width=800, height=300, title="Waste Accumulation Over Time")
    )
    st.altair_chart(stream_chart, use_container_width=True)
else:
    st.info("No data available yet to visualize.")

# =========================================================
# LOG VIEWER
# =========================================================
st.subheader("📜 Action Log")
if os.path.exists(LOG_FILE):
    with open(LOG_FILE, "r") as f:
        logs = json.load(f)
    st.json(logs)
else:
    st.info("No actions logged yet.")

# =========================================================
# END
# =========================================================
st.caption("Embed this Streamlit app in Microsoft Teams using a Teams website tab (add URL of deployment).")
