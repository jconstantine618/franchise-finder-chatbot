# chat_companion.py  –  v3 “Warm Pipeline”  (May 2025)
# ----------------------------------------------------
import streamlit as st
import pandas as pd
import openai, os, re
from pathlib import Path

# ---------- STREAMLIT MUST COME FIRST ----------
st.set_page_config(page_title="Franchise Chat Companion")
# ----------------------------------------------

# ---------- OPENAI ----------
openai.api_key = (
    os.getenv("OPENAI_API_KEY") or
    st.secrets.get("OPENAI_API_KEY", "")
)
if not openai.api_key:
    st.error("Please add OPENAI_API_KEY in Streamlit secrets.")
    st.stop()

MODEL  = "gpt-3.5-turbo"
TOP_K  = 6

# ---------- DATA ----------
DATA_FILE = "data/ifpg_dataset.xlsx"

@st.cache_data
def load_df():
    if not Path(DATA_FILE).exists():
        st.error(f"Dataset not found: {DATA_FILE}")
        st.stop()
    df_ = pd.read_excel(DATA_FILE)
    df_.columns = df_.columns.str.strip().str.lower()
    return df_

df = load_df()

# ---------- UTILITIES ----------
def money(v):
    if v is None or pd.isna(v): return "N/A"
    x = re.sub(r"[^\d.]", "", str(v))
    return "N/A" if not x or float(x) == 0 else f"${float(x):,.0f}"

def size_bucket(units):
    try: return "large" if int(units) >= 100 else "small"
    except: return "unknown"

def format_row(r):
    m = lambda c: r[c] if c in r and pd.notna(r[c]) else "N/A"
    return (
        f"**{m('franchise name')}** ({m('industry')})\n"
        f"- Startup Cost: {money(m('cash required'))}\n"
        f"- Franchise Fee: {money(m('franchise fee')) if 'franchise fee' in r else 'N/A'}\n"
        f"- Units Open: {m('number of units open')}\n"
        f"- URL: {m('url')}"
    )

def gpt(system, user, temp=0.6):
    return openai.chat.completions.create(
        model=MODEL,
        messages=[{"role":"system","content":system},
                  {"role":"user","content":user}],
        temperature=temp,
        max_tokens=600,
    ).choices[0].message.content.strip()

def capture_size(txt):
    txt = txt.lower()
    if re.search(r"\bsmall\b", txt):   return "small"
    if re.search(r"\b(large|big)\b", txt): return "large"
    if re.search(r"\b(either|any|no preference)\b", txt): return "either"
    return None

# ---------- SESSION STATE ----------
if "history" not in st.session_state:
    st.session_state.history = []
    st.session_state.profile = {
        "name": None,
        "interests": [],
        "capital": None,
        "hours": None,
        "size": None,
    }
    st.session_state.stage = "rapport"   # pipeline pointer

# ---------- DISPLAY HISTORY ----------
for role, msg in st.session_state.history:
    st.chat_message(role).markdown(msg)

# ---------- FIRST GREETING ----------
if not st.session_state.history:
    greet = (
        "Hey there! 👋  How are you doing today? I’m excited you’re exploring franchise ownership. "
        "**What are your primary interests?** (For example: fitness, coffee, home‑services, golf …)"
    )
    st.session_state.history.append(("assistant", greet))
    st.chat_message("assistant").markdown(greet)

# ---------- USER INPUT ----------
user_msg = st.chat_input("Type your message…")

if user_msg:
    st.session_state.history.append(("user", user_msg))
    st.chat_message("user").markdown(user_msg)

    prof   = st.session_state.profile
    stage  = st.session_state.stage
    lower  = user_msg.lower()

    # 1) LIGHT NAME GRAB (if user says “I’m John” etc.)
    if not prof["name"]:
        m = re.search(r"\b(?:i[' ]?m|my name is)\s+([a-zA-Z]+)", user_msg, re.I)
        if m: prof["name"] = m.group(1).title()

    # 2) EMOTION ACKNOWLEDGEMENT
    if any(w in lower for w in ["scared", "nervous", "worried", "fear"]):
        empathy = (
            "I completely understand—that feeling is perfectly normal when considering a big step like a franchise. "
            "My role is to guide you at your pace and make the process clear and comfortable. "
            "Let’s tackle each piece together. 😊"
        )
        st.session_state.history.append(("assistant", empathy))
        st.chat_message("assistant").markdown(empathy)

    # 3) PIPELINE LOGIC ---------------------------------------------------
    if stage == "rapport":
        # capture interests keywords
        prof["interests"] = re.findall(r"[a-zA-Z]{3,}", lower)
        st.session_state.stage = "capital"
        q = "To match brands to your budget, may I ask **about how much liquid capital** you could invest upfront?"
        st.session_state.history.append(("assistant", q))
        st.chat_message("assistant").markdown(q)

    elif stage == "capital":
        if m := re.search(r"\$?([\d,]+)", lower):
            prof["capital"] = int(m.group(1).replace(",", ""))
            st.session_state.stage = "hours"
            q = ("Got it—thank you! ✨  Next, how involved would you like to be once it’s running?\n"
                 "*• Full‑time owner‑operator*\n"
                 "*• Semi‑absentee (≈10‑20 hrs/week)*\n"
                 "*• Mostly passive (< 5 hrs/week)*")
            st.session_state.history.append(("assistant", q))
            st.chat_message("assistant").markdown(q)
        else:
            retry = "No worries—when you have an approximate amount, let me know (even a rough range is fine!)."
            st.session_state.history.append(("assistant", retry))
            st.chat_message("assistant").markdown(retry)

    elif stage == "hours":
        if "semi" in lower or "10" in lower or "20" in lower:
            prof["hours"] = "semi"
        elif "passive" in lower or "<5" in lower:
            prof["hours"] = "passive"
        else:
            prof["hours"] = "owner"
        st.session_state.stage = "size"
        q = (
            "Fantastic. One last preference question: **Do you lean toward a large, established franchise system "
            "with extensive support, or a smaller, more entrepreneurial system that’s often lower cost and flexible?** "
            "_Feel free to say **small, large, or either**._"
        )
        st.session_state.history.append(("assistant", q))
        st.chat_message("assistant").markdown(q)

    elif stage == "size":
        grabbed = capture_size(lower)
        if grabbed:
            prof["size"] = grabbed
            st.session_state.stage = "recommend"
        else:
            retry = "Just let me know if you prefer **small**, **large**, or **either**—no rush."
            st.session_state.history.append(("assistant", retry))
            st.chat_message("assistant").markdown(retry)

    # 4) RECOMMENDATION & CLOSE ------------------------------------------
    if st.session_state.stage == "recommend":
        # filter dataset
        rec = df.copy()
        # interests
        if prof["interests"]:
            pattern = "|".join(prof["interests"])
            rec = rec[
                rec["industry"].str.contains(pattern, case=False, na=False) |
                rec["business summary"].str.contains(pattern, case=False, na=False)
            ]
        # capital
        rec["low"] = (
            rec["cash required"].str.extract(r"(\d[\d,]*)")
                               .replace({",": ""}, regex=True).astype(float)
        )
        rec = rec[rec["low"] <= (prof["capital"] or 1e9)]
        # hours
        if prof["hours"] == "semi":
            rec = rec[rec["semi-absentee ownership"] == "Yes"]
        elif prof["hours"] == "passive":
            rec = rec[rec["passive franchise"] == "Yes"]
        # size
        if prof["size"] != "either":
            rec = rec[rec["number of units open"].apply(size_bucket) == prof["size"]]

        top = rec.head(TOP_K)
        if top.empty:
            reply = (
                "It looks like none match every filter. Would you like to broaden budget or hours, "
                "or should we explore a different industry niche?"
            )
        else:
            ctx = "\n\n".join(format_row(r) for _, r in top.iterrows())
            system = (
                "You are a warm, consultative franchise advisor who follows Dale Carnegie courtesy, "
                "Sandler clarity, and Challenger insight. Respond in 2‑3 friendly sentences per brand, "
                "explaining why each fits the user's stated interests, capital, hours, and size preference. "
                "Finish by offering an easy next step (e.g., schedule a detailed call)."
            )
            reply = gpt(system, f"User profile: {prof}\n\nBRANDS:\n{ctx}")

        st.session_state.history.append(("assistant", reply))
        st.chat_message("assistant").markdown(reply)
        st.session_state.stage = "done"   # stop further questions
