# chat_companion.py
"""
GPT‑powered Franchise Chat Companion

Conversation flow:
1. Greets the user and asks for primary interests
2. Collects liquid capital, time commitment, and size preference (large vs small system)
3. Filters 'data/ifpg_dataset.xlsx' and uses ChatGPT to explain matches

Author: 2025
"""

# ---------- IMPORTS ----------
import streamlit as st
import pandas as pd
import openai, os, re
from pathlib import Path

# ---------- STREAMLIT PAGE CONFIG (must be before any other st.* call) ----------
st.set_page_config(page_title="Franchise Chat Companion")

# ---------- OPENAI SETUP ----------
openai.api_key = (
    os.getenv("OPENAI_API_KEY") or
    st.secrets.get("OPENAI_API_KEY", "")
)
if not openai.api_key:
    st.error("OPENAI_API_KEY is missing in Streamlit secrets.")
    st.stop()

MODEL  = "gpt-3.5-turbo"   # or "gpt-4o" if available
TOP_K  = 6                 # rows to include in GPT context


# ---------- LOAD DATA ----------
DATA_FILE = "data/ifpg_dataset.xlsx"

@st.cache_data
def load_df(path: str) -> pd.DataFrame:
    if not Path(path).exists():
        st.error(f"Dataset not found: {path}")
        st.stop()
    df_ = pd.read_excel(path)
    df_.columns = df_.columns.str.strip().str.lower()
    return df_

df = load_df(DATA_FILE)


# ---------- HELPER FUNCTIONS ----------
def money(val):
    if val is None or pd.isna(val):
        return "N/A"
    num = re.sub(r"[^\d.]", "", str(val))
    if not num or float(num) == 0:
        return "N/A"
    return f"${float(num):,.0f}"

def size_bucket(units):
    try:
        return "large" if int(units) >= 100 else "small"
    except Exception:
        return "unknown"

def format_row(row):
    m = lambda c: row[c] if c in row and pd.notna(row[c]) else "N/A"
    return (
        f"**{m('franchise name')}** ({m('industry')})\n"
        f"- Startup Cost: {money(m('cash required'))}\n"
        f"- Franchise Fee: {money(m('franchise fee')) if 'franchise fee' in row else 'N/A'}\n"
        f"- Units Open: {m('number of units open')}\n"
        f"- URL: {m('url')}"
    )

def gpt(system_msg, user_msg, temp=0.6):
    """Simple wrapper around OpenAI chat completion."""
    res = openai.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
        temperature=temp,
        max_tokens=700,
    )
    return res.choices[0].message.content.strip()


# ---------- STATE SETUP ----------
if "history" not in st.session_state:
    st.session_state.history = []
    st.session_state.profile = {
        "interests": [],
        "capital": None,
        "hours":   None,      # owner | semi | passive
        "size":    None,      # small | large | either
    }
    greeting = (
        "Hey there! How are you doing today? I’m excited that you’re interested in a franchise business. "
        "**What are your primary interests?** _(e.g., fitness, coffee, home services, golf...)_"
    )
    st.session_state.history.append(("assistant", greeting))

# ---------- RENDER CHAT HISTORY ----------
for role, msg in st.session_state.history:
    st.chat_message(role).markdown(msg)

# ---------- USER INPUT ----------
user_msg = st.chat_input("Type your reply…")

if user_msg:
    # Store user turn
    st.session_state.history.append(("user", user_msg))
    st.chat_message("user").markdown(user_msg)

    prof   = st.session_state.profile
    last_ai = [m for r, m in st.session_state.history if r == "assistant"][-1].lower()

    # ---- BASIC FIELD EXTRACTION ----
    if "primary interests" in last_ai:
        prof["interests"] = re.findall(r"[a-zA-Z]{3,}", user_msg.lower())

    elif "liquid capital" in last_ai:
        if m := re.search(r"\$?([\d,]+)", user_msg):
            prof["capital"] = int(m.group(1).replace(",", ""))

    elif "hours per week" in last_ai:
        txt = user_msg.lower()
        prof["hours"] = (
            "semi" if "semi" in txt else
            "passive" if "passive" in txt or "<5" in txt else
            "owner"
        )

    elif "prefer a" in last_ai and ("large" in last_ai or "small" in last_ai):
        txt = user_msg.lower()
        prof["size"] = (
            "small" if "small" in txt else
            "large" if "large" in txt or "big" in txt else
            "either"
        )

    # ---- DETERMINE NEXT STEP ----
    missing = [k for k, v in prof.items() if not v]

    if missing:
        nxt = missing[0]

        # Baseline follow-up question text
        if nxt == "capital":
            q = ("To narrow things down, roughly **how much liquid capital** could you invest "
                 "in the initial franchise startup?")
        elif nxt == "hours":
            q = ("How many **hours per week** do you want to spend on the business once it’s running? "
                 "_Full‑time owner‑operator, semi‑absentee (10‑20 hrs), or mostly passive (< 5 hrs)?_")
        elif nxt == "size":
            q = (
                "Would you prefer a **large, established franchise system** or a "
                "**smaller, more entrepreneurial one**?  \n\n"
                "**Smaller systems** can be more cost‑effective and flexible but sometimes have lighter support.  \n"
                "**Larger systems** often cost more up front but provide robust training, marketing, and brand recognition.  \n"
                "Feel free to say **small, large, or either**."
            )
        else:  # interests missing
            q = "Tell me about industries or activities you’re passionate about."

        # Let GPT rephrase to sound friendly
        follow_up = gpt(
            "You are a friendly franchise advisor. Rewrite the prompt below as one engaging question.",
            q,
            temp=0.7,
        )
        st.session_state.history.append(("assistant", follow_up))
        st.chat_message("assistant").markdown(follow_up)

    else:
        # ---- BUILD RECOMMENDATIONS ----
        rec = df.copy()

        # interests
        if prof["interests"]:
            kw = prof["interests"]
            pattern = "|".join(kw)
            rec = rec[
                rec["industry"].str.contains(pattern, case=False, na=False) |
                rec["business summary"].str.contains(pattern, case=False, na=False)
            ]

        # capital
        if prof["capital"]:
            rec["low"] = (
                rec["cash required"].str.extract(r"(\d[\d,]*)")
                                    .replace({",": ""}, regex=True)
                                    .astype(float)
            )
            rec = rec[rec["low"] <= prof["capital"]]

        # hours
        hrs = prof["hours"]
        if hrs == "semi":
            rec = rec[rec["semi-absentee ownership"] == "Yes"]
        elif hrs == "passive":
            rec = rec[rec["passive franchise"] == "Yes"]

        # size
        if prof["size"] != "either":
            rec = rec[rec["number of units open"].apply(size_bucket) == prof["size"]]

        top = rec.head(TOP_K)

        if top.empty:
            reply = (
                "I couldn’t find franchises that meet all those criteria. "
                "Would you like to adjust your capital range or industry interests?"
            )
        else:
            ctx = "\n\n".join(format_row(r) for _, r in top.iterrows())
            reply = gpt(
                "You are an expert franchise broker. Use ONLY the context below.",
                f"CONTEXT:\n{ctx}\n\n"
                "In 2‑3 sentences per brand, explain why each fits the user's profile. "
                "Finish by inviting further questions.",
                temp=0.65,
            )

        st.session_state.history.append(("assistant", reply))
        st.chat_message("assistant").markdown(reply)
