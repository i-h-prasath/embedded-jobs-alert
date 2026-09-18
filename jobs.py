import os, requests, re, smtplib, json
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText

ADZUNA_ID = os.getenv("ADZUNA_APP_ID")
ADZUNA_KEY = os.getenv("ADZUNA_APP_KEY")
EMAIL_FROM = (os.getenv("EMAIL_FROM") or "").strip()
EMAIL_PASS = (os.getenv("EMAIL_PASS") or "").replace(" ", "").strip()
EMAIL_TO = (os.getenv("EMAIL_TO") or "").strip()

MAX_SEND = 100
PAGES_PER_QUERY = 4  # 4 x 50 = 200 per query
MAX_DAYS_OLD = 7  # IMPORTANT: 7 for first catch-up, then daily NEW only. Change to 1 after 1st big mail if you want only daily fresh.
QUERIES = ["firmware developer", "embedded software engineer", "bsp developer", "linux device driver developer", "microcontroller developer", "embedded C developer", "iot firmware engineer", "rtos developer"]

INCLUDE_TITLE = ["firmware", "embedded", "bsp", "device driver", "device-driver",
                 "microcontroller", "stm32", "esp32", "rtos", "yocto", "u-boot",
                 "linux kernel", "linux device", "iot firmware", "bare metal", "baremetal"]
EMBEDDED_IN_DESC = ["firmware","embedded","bsp","microcontroller","stm32","esp32",
                    "rtos","yocto","u-boot","device driver","linux kernel","arm cortex","spi","i2c"]
EXCLUDE = ["senior", "lead", "manager", "architect", "staff", "principal", "team lead", "8+ years", "10 years"]

def check_embedded(title, desc):
    t = title.lower()
    d = desc.lower()
    if any(k in t for k in INCLUDE_TITLE):
        return True
    if "software developer" in t or "software engineer" in t:
        if any(k in d for k in EMBEDDED_IN_DESC):
            return True
    return False

def check_exp(title, desc):
    full = (title+" "+desc).lower()
    if any(k in full for k in EXCLUDE):
        return False, "senior/excluded"
    m = re.findall(r"(\d+)\s*(?:[-–to ]+\s*(\d+))?\s*\+?\s*years?", full)
    if m:
        mins = [int(a) for a,b in m if a.isdigit()]
        if mins and min(mins) > 3:
            return False, f"min {min(mins)}y >3"
    return True, "ok"

def stable_key(j):
    if j.get("id"):
        return f"adzuna-{j.get('id')}"
    t = (j.get("title","") or "").lower().strip()
    c = str(j.get("company",{}).get("display_name","")).lower().strip()
    return f"{t}|{c}"[:200]

def format_posted(created_str):
    # created like "2026-05-07T12:42:42Z" -> IST
    if not created_str:
        return "date not given"
    try:
        dt_utc = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
        dt_ist = dt_utc + timedelta(hours=5, minutes=30)
        return dt_ist.strftime("%d %b %Y, %I:%M %p IST")
    except:
        return created_str[:10]


try:
    with open("seen.json","r") as f:
        seen = set(json.load(f))
except:
    seen = set()
print(f"Loaded seen count: {len(seen)}")

utc_h = datetime.now(timezone.utc).hour
slot = "Morning 10AM" if utc_h==4 else "Afternoon 3PM" if utc_h==9 else "Night 8PM"

perfect = []
maybe = []
total_fetched = 0

for query in QUERIES:
    for page in [1,2,3,4]:
        url = f"https://api.adzuna.com/v1/api/jobs/in/search/{page}"
        params = {"app_id": ADZUNA_ID, "app_key": ADZUNA_KEY,
                  "results_per_page": 50, "what": query,
                  "where": "India", "max_days_old": MAX_DAYS_OLD, "sort_by": "date"}
        try:
            data = requests.get(url, params=params, timeout=20).json()
            results = data.get("results", [])
            print(f"Query '{query}' page {page}: got {len(results)}")
            total_fetched += len(results)
            if not results:
                break
            for j in results:
                key = stable_key(j)
                if key in seen:
                    continue
                seen.add(key) # mark seen immediately to avoid dup across queries in same run
                title = j.get("title","")
                desc = j.get("description","")
                is_emb = check_embedded(title, desc)
                if not is_emb:
                    continue
                ok_exp, _ = check_exp(title, desc)
                item = (title, j.get("company",{}).get("display_name",""),
                        j.get("location",{}).get("display_name",""), j.get("redirect_url"))
                if ok_exp:
                    if len(perfect) < MAX_SEND:
                        perfect.append(item)
                else:
                    # keep exp-mismatch in second list so you don't miss good company due to strict filter
                    if len(maybe) < 30:
                        maybe.append(item)
            if len(perfect) >= MAX_SEND:
                break
        except Exception as e:
            print("Adzuna error", e)
    if len(perfect) >= MAX_SEND:
        break

print(f"Total fetched: {total_fetched}, Perfect: {len(perfect)}, Maybe: {len(maybe)}")

with open("seen.json","w") as f:
    json.dump(list(seen)[-5000:], f)

fresh_count = len(perfect) + len(maybe)
if fresh_count == 0:
    print("No NEW jobs, skipping mail")
else:
    html = f"<h2>Embedded 0-3yr - {slot} - {datetime.now().date()} - {len(perfect)} PERFECT + {len(maybe)} MAYBE (fetched {total_fetched})</h2>"
    html += "<h3>✅ PERFECT MATCH 0-3yr (apply first)</h3>"
    for t,c,l,link in perfect:
        html += f"<p><b>{t}</b> - {c} ({l})<br><a href='{link}'>Apply Link</a></p>"
    if maybe:
        html += "<h3>⚠️ MAYBE CHECK - Embedded but exp not clear / >3yr mentioned (don't miss company)</h3>"
        for t,c,l,link in maybe:
            html += f"<p><b>{t}</b> - {c} ({l})<br><a href='{link}'>Apply Link</a></p>"
    msg = MIMEText(html, "html")
    msg["Subject"] = f"[{slot}] Embedded: {len(perfect)} perfect + {len(maybe)} maybe"
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(EMAIL_FROM, EMAIL_PASS)
        s.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())
    print(f"Sent {fresh_count}")
