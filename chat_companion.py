# chat_companion.py   – v4 “Warm Pipeline + Clarifier”  (May 2025)
# ---------------------------------------------------------------
import streamlit as st
import pandas as pd
import openai, os, re
from pathlib import Path

# ---------- Page config must come first ----------
st.set_page_config(page_title="Franchise Chat Companion")
# -------------------------------------------------

# ---------- OpenAI setup ----------
openai.api_key = (
    os.getenv("OPENAI_API_KEY") or
    st.secrets.get("OPENAI_API_KEY", "")
)
if not openai.api_key:
    st.error("OPENAI_API_KEY missing in Streamlit secrets.")
    st.stop()

MODEL, TOP_K = "gpt-3.5-turbo", 6

# ---------- Data ----------
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

# ---------- Helpers ----------
def money(val):
    if val is None or pd.isna(val): return "N/A"
    num = re.sub(r"[^\d.]", "", str(val))
    return "N/A" if not num or float(num) == 0 else f"${float(num):,.0f}"

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
        max_tokens=650,
    ).choices[0].message.content.strip()

def capture_size(txt):
    txt = txt.lower()
    if re.search(r"\bsmall\b", txt):  return "small"
    if re.search(r"\b(large|big)\b", txt): return "large"
    if re.search(r"\b(either|any|no preference)\b", txt): return "either"
    return None

# ---------- Session state ----------
if "history" not in st.session_state:
    st.session_state.history = []
    st.session_state.profile = {
        "name": None,
        "interests": [],
        "capital": None,
        "hours": None,   # owner | semi | passive
        "size":  None,   # small | large | either
    }
    st.session_state.stage = "rapport"

# ---------- Render chat ----------
for role, msg in st.session_state.history:
    st.chat_message(role).markdown(msg)

# ---------- First greeting ----------
if not st.session_state.history:
    greet = (
        "Hey there! 👋 How are you doing today? I’m excited you’re exploring franchise ownership. "
        "**What are your primary interests?** _(e.g., fitness, coffee, home services, golf…)_"
    )
    st.session_state.history.append(("assistant", greet))
    st.chat_message("assistant").markdown(greet)

# ---------- User input ----------
user_msg = st.chat_input("Type your message…")

if user_msg:
    st.session_state.history.append(("user", user_msg))
    st.chat_message("user").markdown(user_msg)

    prof, stage = st.session_state.profile, st.session_state.stage
    lower = user_msg.lower()

    # --- light name capture ---
    if not prof["name"]:
        m = re.search(r"\b(?:i[' ]?m|my name is)\s+([a-zA-Z]+)", user_msg, re.I)
        if m: prof["name"] = m.group(1).title()

    # --- empathy if fear words ---
    if any(w in lower for w in ["scared", "nervous", "worried", "fear"]):
        reassure = (
            "Totally understandable—taking the first step can feel daunting. "
            "I’m here to make the process clear and comfortable. Let’s go at your pace. 😊"
        )
        st.session_state.history.append(("assistant", reassure))
        st.chat_message("assistant").markdown(reassure)

    # ---------- Clarifier: benefits small vs large -----------
    if stage == "size" and re.search(r"(benefit|advantage|difference).*small.*large", lower):
        explain = (
            "**Small systems**\n"
            "• Lower entry cost on average\n"
            "• Flexibility to influence local strategy & culture\n"
            "• Faster decision cycles but lighter national marketing/support\n\n"
            "**Large systems**\n"
            "• Robust training, peer network, national ad fund\n"
            "• Strong brand recognition and lender familiarity\n"
            "• Higher startup costs, stricter standards"
        )
        follow = "Given that overview, which feels like a better fit for you—**small**, **large**, or **either**?"
        st.session_state.history.extend([("assistant", explain), ("assistant", follow)])
        st.chat_message("assistant").markdown(explain)
        st.chat_message("assistant").markdown(follow)
        # stay in 'size' stage until captured
        continue

    # ---------- Pipeline extraction ----------
    if stage == "rapport":
        prof["interests"] = re.findall(r"[a-zA-Z]{3,}", lower)
        st.session_state.stage = "capital"
        ask = "To match brands to your budget, roughly **how much liquid capital** could you invest upfront?"
        st.session_state.history.append(("assistant", ask))
        st.chat_message("assistant").markdown(ask)

    elif stage == "capital":
        if m := re.search(r"\$?([\d,]+)", lower):
            prof["capital"] = int(m.group(1).replace(",", ""))
            st.session_state.stage = "hours"
            ask = (
                "Great. How involved would you like to be once it’s running?\n"
                "*• Full‑time owner‑operator*\n*• Semi‑absentee (≈10‑20 hrs/week)*\n"
                "*• Mostly passive (< 5 hrs/week)*"
            )
            st.session_state.history.append(("assistant", ask))
            st.chat_message("assistant").markdown(ask)
        else:
            retry = "No worries—an approximate number or range is fine whenever you’re ready."
            st.session_state.history.append(("assistant", retry))
            st.chat_message("assistant").markdown(retry)

    elif stage == "hours":
        if re.search(r"(semi|10-?20|part[- ]?time)", lower):
            prof["hours"] = "semi"
        elif re.search(r"(passive|<\s*5|five\s*hours)", lower):
            prof["hours"] = "passive"
        else:
            prof["hours"] = "owner"
        st.session_state.stage = "size"
        ask = (
            "Do you lean toward a **large, established franchise system** with extensive support, "
            "or a **smaller, more entrepreneurial system** that’s often lower cost and flexible? "
            "Feel free to answer: **small**, **large**, or **either**."
        )
        st.session_state.history.append(("assistant", ask))
        st.chat_message("assistant").markdown(ask)

    elif stage == "size":
        size_choice = capture_size(lower)
        if size_choice:
            prof["size"] = size_choice
            st.session_state.stage = "recommend"
        else:
            reprompt = "Just let me know if you prefer **small**, **large**, or **either**."
            st.session_state.history.append(("assistant", reprompt))
            st.chat_message("assistant").markdown(reprompt)

    # ---------- Recommendation -----------
    if st.session_state.stage == "recommend":
        rec = df.copy()
        # interests
        if prof["interests"]:
            pat = "|".join(prof["interests"])
            rec = rec[
                rec["industry"].str.contains(pat, case=False, na=False) |
                rec["business summary"].str.contains(pat, case=False, na=False)
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
        h = prof["hours"]
        if h == "semi":
            rec = rec[rec["semi-absentee ownership"] == "Yes"]
        elif h == "passive":
            rec = rec[rec["passive franchise"] == "Yes"]
        # size
        if prof["size"] != "either":
            rec = rec[rec["number of units open"].apply(size_bucket) == prof["size"]]

        top = rec.head(TOP_K)

        if top.empty:
            respond = (
                "It seems no brands tick every box. Would you like to broaden your budget, "
                "adjust hours, or explore a different industry niche?"
            )
        else:
            ctx = "\n\n".join(format_row(r) for _, r in top.iterrows())
            system = (
                "You are a warm, consultative franchise advisor. "
                "For each brand in CONTEXT, write 2 friendly sentences on why it fits the user's profile. "
                "Close with an invitation to schedule a deeper call or ask more questions."
            )
            respond = gpt(system, f"User profile: {prof}\n\nCONTEXT:\n{ctx}")

        st.session_state.history.append(("assistant", respond))
        st.chat_message("assistant").markdown(respond)
        st.session_state.stage = "done"
        # capture size choice globally—even after recommend, user can change
    else:
        # Fallback size capture even if not in size stage
        if prof["size"] is None:
            if size_val := capture_size(lower):
                prof["size"] = size_val
