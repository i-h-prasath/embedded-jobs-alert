import os, requests, re, smtplib, json
from datetime import datetime, timezone
from email.mime.text import MIMEText

ADZUNA_ID = os.getenv("ADZUNA_APP_ID")
ADZUNA_KEY = os.getenv("ADZUNA_APP_KEY")
EMAIL_FROM = (os.getenv("EMAIL_FROM") or "").strip()
EMAIL_PASS = (os.getenv("EMAIL_PASS") or "").replace(" ", "").strip()
EMAIL_TO = (os.getenv("EMAIL_TO") or "").strip()

MAX_SEND = 100  # you said ok even if 100
PAGES_PER_QUERY = 3  # 3 x 50 = 150 per query
QUERIES = ["firmware developer", "embedded software engineer", "bsp developer", "linux device driver developer", "microcontroller developer", "embedded C developer"]

INCLUDE_TITLE = ["firmware", "embedded", "bsp", "device driver", "device-driver",
                 "microcontroller", "stm32", "esp32", "rtos", "yocto", "u-boot",
                 "linux kernel", "linux device", "iot firmware", "bare metal", "baremetal"]
EMBEDDED_IN_DESC = ["firmware","embedded","bsp","microcontroller","stm32","esp32",
                    "rtos","yocto","u-boot","device driver","linux kernel"]
EXCLUDE = ["senior", "lead", "manager", "architect", "staff", "principal", "team lead", "8+ years", "10 years"]

def is_relevant(title, desc):
    t = title.lower()
    d = desc.lower()
    full = t + " " + d
    # 1. title must be embedded
    is_emb = False
    if any(k in t for k in INCLUDE_TITLE):
        is_emb = True
    elif "software developer" in t or "software engineer" in t:
        if any(k in d for k in EMBEDDED_IN_DESC):
            is_emb = True
    if not is_emb:
        return False, "not embedded"
    # 2. 0-3 years
    if any(k in full for k in EXCLUDE):
        return False, "senior/excluded"
    m = re.findall(r"(\d+)\s*(?:[-–to ]+\s*(\d+))?\s*\+?\s*years?", full)
    if m:
        mins = [int(a) for a,b in m if a.isdigit()]
        if mins and min(mins) > 3:
            return False, f"min {min(mins)}y >3"
    return True, "ok"

def stable_key(j):
    # Use Adzuna stable ID first
    if j.get("id"):
        return f"adzuna-{j.get('id')}"
    # fallback: normalized title+company
    t = (j.get("title","") or "").lower().strip()
    c = str(j.get("company",{}).get("display_name","")).lower().strip()
    return f"{t}|{c}"[:200]

# Load seen
try:
    with open("seen.json","r") as f:
        seen = set(json.load(f))
except:
    seen = set()
print(f"Loaded seen count: {len(seen)}")

utc_h = datetime.now(timezone.utc).hour
slot = "Morning 10AM" if utc_h==4 else "Afternoon 3PM" if utc_h==9 else "Night 8PM"

fresh = []
for query in QUERIES:
    for page in [1,2,3]:  # pagination to get 100+
        url = f"https://api.adzuna.com/v1/api/jobs/in/search/{page}"
        params = {"app_id": ADZUNA_ID, "app_key": ADZUNA_KEY,
                  "results_per_page": 50, "what": query,
                  "where": "India", "max_days_old": 1, "sort_by": "date"}
        try:
            data = requests.get(url, params=params, timeout=20).json()
            results = data.get("results", [])
            print(f"Query '{query}' page {page}: got {len(results)}")
            if not results:
                break
            for j in results:
                key = stable_key(j)
                if key in seen:
                    continue
                title = j.get("title","")
                desc = j.get("description","")
                ok, reason = is_relevant(title, desc)
                if ok:
                    fresh.append((title, j.get("company",{}).get("display_name",""),
                                  j.get("location",{}).get("display_name",""), j.get("redirect_url"), key))
                    if len(fresh) >= MAX_SEND:
                        break
                # DON'T add rejected to seen, so if we tune filter later they can come back
                # But add sent immediately to avoid dup across queries in same run
                # We will add to seen after loop
            if len(fresh) >= MAX_SEND:
                break
        except Exception as e:
            print("Adzuna error", e)
    if len(fresh) >= MAX_SEND:
        break

print(f"Fresh NEW found: {len(fresh)}")

# Save only SENT keys -> never send again second time
for _,_,_,_,key in fresh:
    seen.add(key)

with open("seen.json","w") as f:
    json.dump(list(seen)[-3000:], f)

if not fresh:
    print("No NEW jobs, skipping mail")
else:
    html = f"<h2>Embedded 0-3yr - {slot} - {datetime.now().date()} - {len(fresh)} NEW</h2>"
    for t,c,l,link,_key in fresh:
        html += f"<p><b>{t}</b> - {c} ({l})<br><a href='{link}'>Apply Link</a></p>"
    msg = MIMEText(html, "html")
    msg["Subject"] = f"[{slot}] Embedded 0-3yr: {len(fresh)} new"
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(EMAIL_FROM, EMAIL_PASS)
        s.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())
    print(f"Sent {len(fresh)}")
