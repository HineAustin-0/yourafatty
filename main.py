import streamlit as st
import anthropic
import json
import os
import re
from datetime import datetime, timedelta

st.set_page_config(page_title="You're a Fatass. You Want Food?", layout="centered")

st.markdown("""
<style>
    .block-container { padding-top: 2rem; max-width: 720px; }
    h1 { font-size: 2.4rem; line-height: 1; margin-bottom: 0; }
    .tag { color: #888; font-size: 0.95rem; margin: 4px 0 18px; }
    .deal-card { border: 1px solid #e3e3e0; border-radius: 12px; padding: 14px 16px; margin-bottom: 8px; background: #fff; }
    .pct-high { background:#e8f5e9; color:#1b7a2e; }
    .pct-mid  { background:#fff4e0; color:#a35b00; }
    .pct-low  { background:#f0f0f0; color:#555; }
    .badge { padding: 3px 9px; border-radius: 5px; font-size: 0.75rem; font-weight: 600; }
    .chip { background:#f3f3f1; color:#666; padding:2px 8px; border-radius:5px; font-size:0.72rem; margin-right:4px; display:inline-block; }
    .restaurant { font-weight:600; font-size:1.05rem; }
    .deal-desc { font-size:0.92rem; margin:7px 0; }
    .howto { font-size:0.8rem; color:#777; border-top:1px solid #eee; padding-top:8px; margin-top:8px; }
</style>
""", unsafe_allow_html=True)

# --- API key: from Replit Secret, else manual input ---
api_key = os.environ.get("ANTHROPIC_API_KEY", "")
if not api_key:
    api_key = st.text_input("Anthropic API Key", type="password",
                            help="Get one at console.anthropic.com")

# --- Session + saved-deal persistence ---
if "deals" not in st.session_state:
    st.session_state.deals = []
if "meta" not in st.session_state:
    st.session_state.meta = None
if "saved" not in st.session_state:
    try:
        with open("saved_deals.json") as f:
            st.session_state.saved = json.load(f)
    except Exception:
        st.session_state.saved = []

def persist_saved():
    try:
        with open("saved_deals.json", "w") as f:
            json.dump(st.session_state.saved, f)
    except Exception:
        pass

# --- Header ---
st.markdown("# You're a Fatass.")
st.markdown("### You Want Food?")
st.markdown('<p class="tag">Type your city and state. Hit scan. Get every deal worth eating for, today and tomorrow.</p>', unsafe_allow_html=True)

c1, c2 = st.columns([3, 1])
with c1:
    city = st.text_input("City", placeholder="Lexington")
with c2:
    state = st.text_input("State", placeholder="MA", max_chars=2)

ready = bool(city.strip()) and len(state.strip()) == 2 and bool(api_key)
scan = st.button("SCAN FOR DEALS", type="primary", use_container_width=True, disabled=not ready)

# --- The scan ---
def run_scan(city, state, api_key):
    loc = f"{city.strip()}, {state.strip().upper()}"
    today = datetime.now().strftime("%A, %B %d, %Y")
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%A, %B %d, %Y")
    client = anthropic.Anthropic(api_key=api_key)

    system = f"""You are an expert food deal hunter. Search the web thoroughly and find ALL current food deals, promos, coupons, BOGO offers, free items, and discounts available today ({today}) and tomorrow ({tomorrow}) near {loc}.

Search specifically for:
1. National food holidays today and tomorrow with associated chain deals
2. Fast food app deals: McDonald's, Burger King, Wendy's, Taco Bell, Chick-fil-A, Subway, Chipotle, Panera, Five Guys, Shake Shack, Arby's, Sonic, Popeyes, KFC, Wingstop, Dairy Queen, Little Caesars, Jersey Mike's
3. Pizza: Domino's, Pizza Hut, Papa John's
4. Coffee: Starbucks, Dunkin', Dutch Bros
5. DoorDash, Uber Eats, Grubhub promo codes and first-order deals
6. Reddit r/frugal r/deals r/fastfood current deal threads
7. BOGO, free item with purchase, loyalty rewards, happy hours

For each deal, estimate the % discount. Free item with a required purchase: item_value / (purchase_value + item_value) * 100.

After searching, respond with ONLY a raw JSON object, no markdown, no backticks, no preamble:
{{"deals":[{{"id":"unique_id","restaurant":"Name","deal":"description","category":"fast_food|coffee|pizza|sitdown|delivery","source":"where found","discount_pct":75,"expires":"Today|Tomorrow|This week|Ongoing","how_to_get":"exact steps to claim","distance":"chain|local","order_types":["delivery","pickup","sitdown"],"link":"url or null"}}],"scan_date":"{today}","location":"{loc}"}}

Find 15-25 deals, sorted by discount_pct descending."""

    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8000,
        tools=[{
            "type": "web_search_20250305",
            "name": "web_search",
            "max_uses": 10,
            "user_location": {
                "type": "approximate",
                "city": city.strip(),
                "region": state.strip().upper(),
                "country": "US",
            },
        }],
        system=system,
        messages=[{"role": "user", "content":
            f"Find all food deals near {loc} for today ({today}) and tomorrow ({tomorrow}). "
            f"Search Reddit, every major fast food app, delivery platforms, and food holiday calendars. Be thorough."}],
    )

    text = "\n".join(b.text for b in resp.content if b.type == "text")
    try:
        parsed = json.loads(text.strip())
    except Exception:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            raise ValueError("Could not parse deals from the response.")
        parsed = json.loads(m.group(0))

    deals = sorted(parsed.get("deals", []), key=lambda d: d.get("discount_pct", 0), reverse=True)
    return deals, {"date": parsed.get("scan_date", today), "location": parsed.get("location", loc)}

if scan:
    with st.spinner("Scanning the internet for deals... (10-25 seconds)"):
        try:
            st.session_state.deals, st.session_state.meta = run_scan(city, state, api_key)
        except Exception as e:
            st.error(f"Scan failed: {e}")

# --- Rendering ---
def pct_class(p):
    return "pct-high" if p >= 70 else "pct-mid" if p >= 40 else "pct-low"

def render_deal(deal, key_prefix, idx):
    pct = deal.get("discount_pct", 0)
    chips = "".join(f'<span class="chip">{t}</span>' for t in deal.get("order_types", []))
    link = f'<a href="{deal["link"]}" target="_blank">Get deal &rarr;</a>' if deal.get("link") else ""
    howto = f'<div class="howto"><b>How to get it:</b> {deal.get("how_to_get","")}</div>' if deal.get("how_to_get") else ""
    st.markdown(f"""
    <div class="deal-card">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;">
            <span class="restaurant">{deal.get("restaurant","")}</span>
            <span class="badge {pct_class(pct)}">{pct}% off</span>
        </div>
        <div class="deal-desc">{deal.get("deal","")}</div>
        <div>
            <span class="chip">Expires: {deal.get("expires","")}</span>
            <span class="chip">{deal.get("source","")}</span>
            {chips}
        </div>
        {howto}
        <div style="margin-top:6px;">{link}</div>
    </div>""", unsafe_allow_html=True)

    did = deal.get("id", str(idx))
    saved = any(d.get("id") == did for d in st.session_state.saved)
    if st.button("\u2665 Saved" if saved else "\u2661 Save", key=f"{key_prefix}_{idx}_{did}"):
        if saved:
            st.session_state.saved = [d for d in st.session_state.saved if d.get("id") != did]
        else:
            st.session_state.saved.append(deal)
        persist_saved()
        st.rerun()

# --- Output ---
if st.session_state.deals or st.session_state.saved:
    t1, t2 = st.tabs([f"Deals ({len(st.session_state.deals)})", f"Saved ({len(st.session_state.saved)})"])
    with t1:
        if st.session_state.meta:
            m = st.session_state.meta
            st.caption(f"{m['location']} · {m['date']} · {len(st.session_state.deals)} deals · sorted by % off")
        dist = st.radio("Distance", ["All", "< 2 mi", "< 5 mi", "< 15 mi"],
                        horizontal=True, label_visibility="collapsed")
        dmap = {"< 2 mi": ["close","chain"],
                "< 5 mi": ["close","medium","chain"],
                "< 15 mi": ["close","medium","far","chain","local"]}
        deals = st.session_state.deals
        if dist != "All":
            deals = [d for d in deals if d.get("distance","chain") in dmap[dist]]
        if not deals:
            st.info("No deals in this range. Try a wider filter.")
        for i, d in enumerate(deals):
            render_deal(d, "r", i)
    with t2:
        if not st.session_state.saved:
            st.info("No saved deals yet. Tap Save on any deal.")
        for i, d in enumerate(st.session_state.saved):
            render_deal(d, "s", i)
