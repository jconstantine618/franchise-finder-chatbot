# chat_companion.py
"""
Conversational Franchise Advisor (GPT-powered)

Starts with:  “Hey there! How are you doing today? I’m excited that you’re
interested in a franchise business. What are your primary interests?”

Collects:
  • interests  • capital  • hours involvement  • size preference
Then filters ifpg dataset.xlsx and lets ChatGPT craft the answer.

Author: 2025
"""

import streamlit as st
import pandas as pd
import openai, os, re, math
from pathlib import Path
from difflib import get_close_matches

# ------------- CONFIG --------------
DATA_FILE = "data/ifpg_dataset.xlsx"          # exact file name in repo
MODEL     = "gpt-3.5-turbo"              # or "gpt-4o"
TOP_K     = 6                            # rows to pass as context
openai.api_key = (
    os.getenv("OPENAI_API_KEY") or
    st.secrets.get("OPENAI_API_KEY", "")
)
if not openai.api_key:
    st.error("OPENAI_API_KEY is missing in Streamlit secrets.")
    st.stop()

# ------------- Load data -----------
@st.cache_data
def load_df():
    if not Path(DATA_FILE).exists():
        st.error(f"Dataset not found: {DATA_FILE}")
        st.stop()
    df = pd.read_excel(DATA_FILE)
    df.columns = df.columns.str.strip().str.lower()
    return df

df = load_df()

# ------------- Helpers -------------
def money(x):
    if x is None or pd.isna(x): return "N/A"
    num = re.sub(r"[^\d.]", "", str(x))
    if num == "" or float(num) == 0: return "N/A"
    return f"${float(num):,.0f}"

def size_bucket(units):
    try: return "large" if int(units) >= 100 else "small"
    except: return "unknown"

def format_row(row):
    m = lambda c: row[c] if c in row and pd.notna(row[c]) else "N/A"
    return (
        f"**{m('franchise name')}** ({m('industry')})\n"
        f"- Startup Cost: {money(m('cash required'))}\n"
        f"- Franchise Fee: {money(m('franchise fee')) if 'franchise fee' in row else 'N/A'}\n"
        f"- Units Open: {m('number of units open')}\n"
        f"- URL: {m('url')}"
    )

def gpt(system_msg, user_msg, temp=0.5):
    resp = openai.chat.completions.create(
        model=MODEL,
        messages=[
            {"role":"system", "content":system_msg},
            {"role":"user", "content":user_msg}
        ],
        temperature=temp,
        max_tokens=700,
    )
    return resp.choices[0].message.content.strip()

# ------------- Streamlit set‑up -------------
st.set_page_config(page_title="Franchise Chat Companion")
st.title("🤖 Franchise Chat Companion")

if "history" not in st.session_state:
    st.session_state.history = []
    st.session_state.profile = {
        "interests": [],
        "capital": None,
        "hours":   None,   # owner | semi | passive
        "size":    None,   # small | large | either
    }
    greeting = (
        "Hey there! How are you doing today? I’m excited that you’re interested "
        "in a franchise business. **What are your primary interests?** "
        "_(For example: fitness, pets, coffee, golf, tech...)_"
    )
    st.session_state.history.append(("assistant", greeting))

# render chat history
for role, msg in st.session_state.history:
    st.chat_message(role).markdown(msg)

user_msg = st.chat_input("Type your reply…")

if user_msg:
    st.session_state.history.append(("user", user_msg))
    st.chat_message("user").markdown(user_msg)

    prof      = st.session_state.profile
    last_ai   = [m for r,m in st.session_state.history if r=="assistant"][-1].lower()

    # ---- Quick field extraction ----
    if "primary interests" in last_ai:
        prof["interests"] = re.findall(r"[a-zA-Z]{3,}", user_msg.lower())
    elif "liquid capital" in last_ai:
        m = re.search(r"\$?([\d,]+)", user_msg)
        if m: prof["capital"] = int(m.group(1).replace(",", ""))
    elif "hours per week" in last_ai:
        txt = user_msg.lower()
        prof["hours"] = ("semi" if "semi" in txt else
                         "passive" if "passive" in txt or "<5" in txt else
                         "owner")
    elif "prefer a" in last_ai and ("large" in last_ai or "small" in last_ai):
        txt = user_msg.lower()
        prof["size"] = ("small" if "small" in txt else
                        "large" if "large" in txt or "big" in txt else
                        "either")

    # ---- Ask next question or produce results ----
    missing = [k for k,v in prof.items() if not v]

    if missing:
        nxt = missing[0]
        # baseline prompt
        if nxt == "capital":
            baseline = ("To match you with brands that fit your budget, "
                        "roughly **how much liquid capital** could you invest?")
        elif nxt == "hours":
            baseline = ("How many **hours per week** do you want to spend on the business "
                        "after it’s running? _full‑time, semi‑absentee, or passive?_")
        elif nxt == "size":
            baseline = (
                "Would you prefer a **large, established franchise system** "
                "or a **smaller, more entrepreneurial one**?  "
                "Smaller systems can cost less and be flexible but may offer less support; "
                "larger systems often cost more but provide robust training and marketing. "
                "Feel free to answer **small, large, or either.**"
            )
        else:
            baseline = "Tell me about industries or activities you’re passionate about."

        # Let GPT rephrase question for natural tone
        ask = gpt(
            "You are a friendly franchise advisor. Rewrite the prompt below as one engaging question.",
            baseline,
            temp=0.7
        )
        st.session_state.history.append(("assistant", ask))
        st.chat_message("assistant").markdown(ask)

    else:
        # ---- Build recommendation DataFrame ----
        rec = df.copy()

        if prof["interests"]:
            kw = prof["interests"]
            rec = rec[rec["industry"].str.contains("|".join(kw), case=False, na=False) |
                      rec["business summary"].str.contains("|".join(kw), case=False, na=False)]

        if prof["capital"]:
            rec["low"] = (
                rec["cash required"].str.extract(r"(\d[\d,]*)")
                                    .replace({",": ""}, regex=True)
                                    .astype(float)
            )
            rec = rec[rec["low"] <= prof["capital"]]

        hrs = prof["hours"]
        if hrs == "semi":
            rec = rec[rec["semi-absentee ownership"] == "Yes"]
        elif hrs == "passive":
            rec = rec[rec["passive franchise"] == "Yes"]

        if prof["size"] != "either":
            rec = rec[rec["number of units open"].apply(size_bucket) == prof["size"]]

        top = rec.head(TOP_K)

        if top.empty:
            assistant_reply = (
                "I couldn’t find franchises that match all those criteria. "
                "Would you like to adjust your capital range or interest keywords?"
            )
        else:
            ctx = "\n\n".join(format_row(r) for _, r in top.iterrows())
            assistant_reply = gpt(
                "You are an expert franchise broker. "
                "Use ONLY the context rows to craft the answer.",
                f"CONTEXT:\n{ctx}\n\n"
                "In 2‑3 sentences per brand, explain why each fits the user's profile. "
                "Finish by inviting follow‑up questions.",
                temp=0.65
            )

        st.session_state.history.append(("assistant", assistant_reply))
        st.chat_message("assistant").markdown(assistant_reply)
