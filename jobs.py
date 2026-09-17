import os, requests, re, smtplib
from datetime import datetime, timedelta
from email.mime.text import MIMEText

ADZUNA_ID = os.getenv("ADZUNA_APP_ID")
ADZUNA_KEY = os.getenv("ADZUNA_APP_KEY")
EMAIL_FROM = (os.getenv("EMAIL_FROM") or "").strip()
EMAIL_PASS = (os.getenv("EMAIL_PASS") or "").replace(" ", "").strip()
EMAIL_TO = (os.getenv("EMAIL_TO") or "").strip()

print(f"EMAIL_FROM set? {bool(EMAIL_FROM)}")
print(f"EMAIL_PASS len: {len(EMAIL_PASS) if EMAIL_PASS else 0} should be 16")
if not EMAIL_FROM or not EMAIL_PASS:
    raise SystemExit("Missing secrets - check Settings > Secrets and variables > Actions")


INCLUDE = ["firmware","embedded","bsp","device driver","microcontroller","stm32","esp32","rtos","yocto","u-boot","linux kernel","iot"]
EXCLUDE = ["senior","lead","manager","architect","staff","principal"]

def is_relevant(title, desc):
    t = title.lower()
    full = (title+" "+desc).lower()
    if not any(k in t for k in INCLUDE):
        return False
    if any(k in full for k in EXCLUDE):
        return False
    m = re.search(r"(\d+)\s*[-–to ]+\s*(\d+)?\s*years?", full)
    if m and int(m.group(1)) > 3:
        return False
    if "8+ years" in full or "10 years" in full:
        return False
    return True

fresh = []

# 1. Adzuna India - only last 1 day
for query in ["firmware developer", "embedded software engineer", "bsp developer"]:
    url = f"https://api.adzuna.com/v1/api/jobs/in/search/1"
    params = {
        "app_id": ADZUNA_ID, "app_key": ADZUNA_KEY,
        "results_per_page": 50, "what": query,
        "where": "India", "max_days_old": 1, "sort_by": "date"
    }
    try:
        data = requests.get(url, params=params, timeout=20).json()
        for j in data.get("results", []):
            title = j.get("title","")
            if is_relevant(title, j.get("description","")):
                fresh.append((title, j.get("company",{}).get("display_name",""), j.get("location",{}).get("display_name",""), j.get("redirect_url")))
    except Exception as e:
        print("Adzuna error", e)

# 2. Arbeitnow - free backup, no key needed
# Free public API — no API key required
# GET https://www.arbeitnow.com/api/job-board-api, no key
try:
    r = requests.get("https://www.arbeitnow.com/api/job-board-api", timeout=20).json()
    cutoff = datetime.now() - timedelta(days=1)
    for j in r.get("data", []):
        try:
            dt = datetime.fromisoformat(j.get("created_at","").replace("Z","+00:00").split(".")[0]+"+00:00")
        except: continue
        if dt.replace(tzinfo=None) < cutoff.replace(tzinfo=None):
            continue
        if is_relevant(j.get("title",""), j.get("description","")):
            fresh.append((j.get("title"), j.get("company_name"), j.get("location"), j.get("url")))
except Exception as e:
    print("Arbeitnow error", e)

# dedup
seen=set(); uniq=[]
for t,c,l,link in fresh:
    if link and link not in seen:
        seen.add(link); uniq.append((t,c,l,link))

# 3. Send Email
html = f"<h2>Embedded Jobs 0-3yr - {datetime.now().date()} - {len(uniq)} fresh</h2>"
for t,c,l,link in uniq:
    html += f"<p><b>{t}</b> - {c} ({l})<br><a href='{link}'>Apply Link</a></p>"
if not uniq:
    html += "<p>No fresh 0-3yr jobs today.</p>"

msg = MIMEText(html, "html")
msg["Subject"] = f"Embedded Jobs: {len(uniq)} fresh - {datetime.now().date()}"
msg["From"] = EMAIL_FROM
msg["To"] = EMAIL_TO

with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
    s.login(EMAIL_FROM, EMAIL_PASS)
    s.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())

print(f"Sent {len(uniq)} jobs")
