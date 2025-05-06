# chat_companion.py
"""
Streamlit Chatbot that answers questions about franchises
listed in ifpg_dataset.xlsx and about the user's recommended
brands (passed in via query params or an import).
"""

import streamlit as st
import pandas as pd
import re
from pathlib import Path

# ---------- CONFIG ----------
DATA_FILE = "ifpg_dataset.xlsx"   # same file used by Franchise Fit Finder
# --------------------------------

@st.cache_data
def load_df(path: str) -> pd.DataFrame:
    if not Path(path).exists():
        st.error(f"Dataset not found → {path}")
        st.stop()
    df = pd.read_excel(path)
    df.columns = df.columns.str.strip().str.lower()
    return df

df = load_df(DATA_FILE)

# --------------------------------
# Utility helpers
# --------------------------------
def normalize_name(name: str) -> str:
    """Simple canonical form used for matching."""
    return re.sub(r"[^a-z0-9]", "", name.lower())

name_index = {normalize_name(n): n for n in df["franchise name"]}

def find_brand_in_text(text: str):
    """Return the first recognized franchise name in user text, else None."""
    txt = normalize_name(text)
    for key, full in name_index.items():
        if key in txt:
            return full
    return None

def get_brand_details(name: str) -> str:
    """Build a nicely formatted bullet list for a franchise row."""
    row = df[df["franchise name"] == name].iloc[0]
    m = lambda c: row[c] if c in row and pd.notna(row[c]) else "N/A"
    return (
        f"**{name}**  \n"
        f"*Industry:* {m('industry')}  \n"
        f"*Startup Cost:* {m('cash required')}  \n"
        f"*Franchise Fee:* {m('franchise fee') if 'franchise fee' in row else 'N/A'}  \n"
        f"*Veteran Discount:* {m('veteran discount')}  \n"
        f"*Units Open:* {m('number of units open')}  \n"
        f"*Support:* {m('support')}  \n"
        f"*URL:* {m('url')}"
    )

# Optional: inject recommended list via URL param ?rec=Brand1|Brand2
rec_param = st.query_params.get("rec")
recommended = []
if rec_param:
    recommended = [b.strip() for b in rec_param.split("|") if b.strip() in name_index.values()]

# --------------------------------
# Chat UI
# --------------------------------
st.set_page_config(page_title="Franchise Chat Companion")
st.title("🤖 Franchise Chat Companion")

if recommended:
    st.info(
        "**Brands you matched with:**  \n" +
        ", ".join(f"**{b}**" for b in recommended)
    )

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

# Render chat history
for role, msg in st.session_state.chat_history:
    st.chat_message(role).markdown(msg)

# User input
prompt = st.chat_input("Ask me about any franchise, costs, industries…")
if prompt:
    st.session_state.chat_history.append(("user", prompt))
    st.chat_message("user").markdown(prompt)

    # ------- Simple intent handling -------
    resp = ""
    brand_in_text = find_brand_in_text(prompt)

    # 1) Direct brand lookup
    if brand_in_text:
        resp = get_brand_details(brand_in_text)

    # 2) Ask to list recommended brands
    elif "my matches" in prompt.lower() or "my recommendations" in prompt.lower():
        if recommended:
            resp = "\n\n".join(get_brand_details(b) for b in recommended)
        else:
            resp = "I don't have your match list right now—try the quiz first!"

    # 3) Cost filter intent
    elif m := re.search(r"under\s*\$?(\d[\d,]*)", prompt.lower()):
        limit = int(m.group(1).replace(",", ""))
        cheap = df[df["cash required"].str.contains(r"\d") &
                   (df["cash required"].str.extract(r"(\d[\d,]*)")
                    .replace({",": ""}, regex=True).astype(float) < limit)]
        if cheap.empty:
            resp = f"No franchises list a startup cost under ${limit:,}."
        else:
            resp = "**Franchises under $" + f"{limit:,}:**\n\n" + \
                   "\n\n".join(f"- {n}" for n in cheap["franchise name"].head(20))

    # 4) Industry list intent
    elif "list industries" in prompt.lower():
        inds = sorted({i.strip() for cell in df["industry"].dropna()
                       for i in str(cell).split(",")})
        resp = "**Industries represented:**  \n" + ", ".join(inds)

    # 5) Fallback
    else:
        resp = (
            "I’m not sure how to help with that. "
            "Try asking about a specific franchise name, "
            "an industry, or say something like "
            "“show me brands under $75k.”"
        )

    st.session_state.chat_history.append(("assistant", resp))
    st.chat_message("assistant").markdown(resp)
