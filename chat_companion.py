# chat_companion.py  – v4.1  (stop instead of continue)
import streamlit as st
import pandas as pd
import openai, os, re
from pathlib import Path

# ---------- must be first ----------
st.set_page_config(page_title="Franchise Chat Companion")

# ---------- OpenAI ----------
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
def money(v): 
    if v is None or pd.isna(v): return "N/A"
    n = re.sub(r"[^\d.]", "", str(v))
    return "N/A" if not n or float(n) == 0 else f"${float(n):,.0f}"

def size_bucket(u):
    try: return "large" if int(u) >= 100 else "small"
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

def gpt(sys,u,temp=0.6):
    return openai.chat.completions.create(
        model=MODEL,
        messages=[{"role":"system","content":sys},{"role":"user","content":u}],
        temperature=temp,max_tokens=650,
    ).choices[0].message.content.strip()

def capture_size(t):
    t=t.lower()
    if re.search(r"\bsmall\b",t): return "small"
    if re.search(r"\b(large|big)\b",t): return "large"
    if re.search(r"\b(either|any|no preference)\b",t): return "either"
    return None

# ---------- State ----------
if "history" not in st.session_state:
    st.session_state.history=[]
    st.session_state.profile={"name":None,"interests":[],"capital":None,"hours":None,"size":None}
    st.session_state.stage="rapport"

for role,msg in st.session_state.history:
    st.chat_message(role).markdown(msg)

if not st.session_state.history:
    greet=("Hey there! 👋 How are you doing today? I’m excited you’re exploring franchise ownership. "
           "**What are your primary interests?** _(e.g., fitness, coffee, home services, golf…)_")
    st.session_state.history.append(("assistant",greet))
    st.chat_message("assistant").markdown(greet)

user=st.chat_input("Type your message…")
if not user: st.stop()

st.session_state.history.append(("user",user))
st.chat_message("user").markdown(user)

prof,stage=st.session_state.profile,st.session_state.stage
lower=user.lower()

# name grab
if not prof["name"]:
    m=re.search(r"\b(?:i[' ]?m|my name is)\s+([a-zA-Z]+)",user,re.I)
    if m: prof["name"]=m.group(1).title()

# empathy
if any(w in lower for w in["scared","nervous","worried","fear"]):
    st.chat_message("assistant").markdown(
        "Totally understandable—taking the first step can feel daunting. "
        "I’ll guide you at your pace. 😊")
    st.session_state.history.append(("assistant",
        "Totally understandable—taking the first step can feel daunting. "
        "I’ll guide you at your pace. 😊"))

# ----- Clarifier block -----
if stage=="size" and re.search(r"(benefit|advantage|difference).*small.*large",lower):
    explain=(
      "**Small systems**\n• Lower average entry cost\n• Flexibility to influence local strategy\n"
      "• Faster decisions, lighter national support\n\n"
      "**Large systems**\n• Robust training & ad fund\n• Strong brand recognition\n"
      "• Higher startup cost, stricter standards")
    follow="Which feels like a better fit—**small**, **large**, or **either**?"
    for m in (explain,follow):
        st.session_state.history.append(("assistant",m))
        st.chat_message("assistant").markdown(m)
    st.stop()          # <–– replaces the invalid 'continue'

# ----- Pipeline -----
# ----- RAPPORT / INTERESTS -------------------------------
if stage == "rapport":
    # pull words with 3+ letters as a first pass
    kws = re.findall(r"[a-zA-Z]{3,}", lower)
    # discard very generic words
    stop = {"just", "really", "little", "starting", "journey", "into", "franchising"}
    kws = [w for w in kws if w not in stop]

    if kws:
        prof["interests"] = kws
        st.session_state.stage = "capital"
        ask = ("Thanks! To match brands to your budget, roughly **how much liquid capital** "
               "could you invest upfront?")
        st.session_state.history.append(("assistant", ask))
        st.chat_message("assistant").markdown(ask)
    else:
        # user didn't give concrete interests – re‑prompt with examples
        prompt = (
            "No problem—I’d love to learn what sparks your excitement. "
            "For instance, do you enjoy **fitness**, **pets**, **home improvement**, "
            "**coffee**, **education**, or something else entirely? "
            "Any keywords will help me narrow the universe of franchises."
        )
        st.session_state.history.append(("assistant", prompt))
        st.chat_message("assistant").markdown(prompt)
    st.stop()

if stage=="capital":
    if m:=re.search(r"\$?([\d,]+)",lower):
        prof["capital"]=int(m.group(1).replace(",",""))
        st.session_state.stage="hours"
        ask=("Great. How involved would you like to be once it’s running?\n"
             "*• Full‑time owner‑operator*\n*• Semi‑absentee (≈10‑20 hrs/week)*\n"
             "*• Mostly passive (< 5 hrs/week)*")
        st.session_state.history.append(("assistant",ask)); st.chat_message("assistant").markdown(ask); st.stop()
    else:
        st.chat_message("assistant").markdown(
            "No worries—whenever you have an approximate amount, let me know!")
        st.session_state.history.append(("assistant",
            "No worries—whenever you have an approximate amount, let me know!"))
        st.stop()

if stage=="hours":
    if re.search(r"(semi|10-?20|part[- ]?time)",lower):
        prof["hours"]="semi"
    elif re.search(r"(passive|<\s*5|five\s*hours)",lower):
        prof["hours"]="passive"
    else:
        prof["hours"]="owner"
    st.session_state.stage="size"
    ask=("Do you lean toward a **large, established system** with extensive support, "
         "or a **smaller, entrepreneurial system** that’s often lower cost and flexible? "
         "Feel free to answer: **small**, **large**, or **either**.")
    st.session_state.history.append(("assistant",ask)); st.chat_message("assistant").markdown(ask); st.stop()

if stage=="size":
    if choice:=capture_size(lower):
        prof["size"]=choice
        st.session_state.stage="recommend"
    else:
        rep="Just let me know if you prefer **small**, **large**, or **either**."
        st.session_state.history.append(("assistant",rep)); st.chat_message("assistant").markdown(rep); st.stop()

# ---------- Recommendation ----------
rec=df.copy()
if prof["interests"]:
    pat="|".join(prof["interests"])
    rec=rec[rec["industry"].str.contains(pat,case=False,na=False)|
            rec["business summary"].str.contains(pat,case=False,na=False)]
if prof["capital"]:
    rec["low"]=rec["cash required"].str.extract(r"(\d[\d,]*)").replace({",":""},regex=True).astype(float)
    rec=rec[rec["low"]<=prof["capital"]]
if prof["hours"]=="semi":
    rec=rec[rec["semi-absentee ownership"]=="Yes"]
elif prof["hours"]=="passive":
    rec=rec[rec["passive franchise"]=="Yes"]
if prof["size"]!="either":
    rec=rec[rec["number of units open"].apply(size_bucket)==prof["size"]]

top=rec.head(TOP_K)
if top.empty:
    respond=("It looks like no brands match every filter. "
             "Would you like to adjust budget, hours, or explore another industry?")
else:
    ctx="\n\n".join(format_row(r) for _,r in top.iterrows())
    system=("You are a warm, consultative franchise advisor. "
            "For each brand in CONTEXT, write 2 friendly sentences on why it fits the user profile. "
            "End by inviting them to schedule a discovery call.")
    respond=gpt(system,f"User profile: {prof}\n\nCONTEXT:\n{ctx}")

st.session_state.history.append(("assistant",respond))
st.chat_message("assistant").markdown(respond)
st.session_state.stage="done"
