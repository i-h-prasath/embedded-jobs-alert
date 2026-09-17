import os, requests, re, smtplib, json
from datetime import datetime, timezone
from email.mime.text import MIMEText

ADZUNA_ID = os.getenv("ADZUNA_APP_ID")
ADZUNA_KEY = os.getenv("ADZUNA_APP_KEY")
EMAIL_FROM = (os.getenv("EMAIL_FROM") or "").strip()
EMAIL_PASS = (os.getenv("EMAIL_PASS") or "").replace(" ", "").strip()
EMAIL_TO = (os.getenv("EMAIL_TO") or "").strip()

# --- 1. TITLE FILTER - must be embedded related ---
INCLUDE_TITLE = ["firmware", "embedded", "bsp", "device driver", "device-driver",
                 "microcontroller", "stm32", "esp32", "rtos", "yocto", "u-boot",
                 "linux kernel", "linux device", "iot firmware", "bare metal", "baremetal"]

# allow software developer ONLY if description has embedded words
EMBEDDED_IN_DESC = ["firmware","embedded","bsp","microcontroller","stm32","esp32",
                    "rtos","yocto","u-boot","device driver","linux kernel","can protocol",
                    "spi", "i2c", "uart", "arm cortex"]

EXCLUDE = ["senior", "lead", "manager", "architect", "staff", "principal",
           "team lead", "tech lead", "8+ years", "8 years", "10 years", "10+"]

def is_embedded_title(title, desc):
    t = title.lower()
    d = desc.lower()
    # direct embedded title
    if any(k in t for k in INCLUDE_TITLE):
        return True
    # software developer + embedded in description = allow
    if "software developer" in t or "software engineer" in t:
        if any(k in d for k in EMBEDDED_IN_DESC):
            return True
    return False

def is_0_to_3_years(title, desc):
    full = (title + " " + desc).lower()

    # instant reject senior roles
    if any(k in full for k in EXCLUDE):
        return False, "senior/excluded"

    # find all like 0-3 years, 1-4 years, 0 to 3 years, 2+ years, 3 years
    # we take the SMALLEST min found
    patterns = re.findall(r"(\d+)\s*(?:[-–to ]+\s*(\d+))?\s*\+?\s*years?", full)
    if patterns:
        mins = []
        for a,b in patterns:
            try:
                mins.append(int(a))
            except: pass
        if mins:
            min_exp = min(mins)
            if min_exp > 3:
                return False, f"min {min_exp}y >3"
            else:
                return True, f"min {min_exp}y ok"

    # no years mentioned -> allow if fresher/junior/0-3 words, else allow for manual check
    # but still reject if 5-8 clearly present
    if "fresher" in full or "junior" in full or "0-3" in full or "0 to 3" in full:
        return True, "fresher/junior"
    return True, "no exp mentioned - allow"

def is_relevant(title, desc):
    if not is_embedded_title(title, desc):
        return False, "not embedded title"
    ok, reason = is_0_to_3_years(title, desc)
    if not ok:
        return False, reason
    return True, reason

# --- 2. SEEN MEMORY - don't resend ---
try:
    with open("seen.json","r") as f:
        seen = set(json.load(f))
except:
    seen = set()

utc_h = datetime.now(timezone.utc).hour
if utc_h == 4:
    slot = "Morning 10AM"
elif utc_h == 9:
    slot = "Afternoon 3PM"
else:
    slot = "Night 8PM"

fresh = []

# Adzuna India - only last 1 day, newest first
for query in ["firmware developer", "embedded software engineer",
              "bsp developer", "linux device driver developer", "microcontroller developer"]:
    url = f"https://api.adzuna.com/v1/api/jobs/in/search/1"
    params = {"app_id": ADZUNA_ID, "app_key": ADZUNA_KEY,
              "results_per_page": 50, "what": query,
              "where": "India", "max_days_old": 1, "sort_by": "date"}
    try:
        data = requests.get(url, params=params, timeout=20).json()
        for j in data.get("results", []):
            # use stable ID, not redirect_url with tracking token
            job_id = str(j.get("id") or j.get("redirect_url"))
            if job_id in seen:
                continue
            title = j.get("title","")
            desc = j.get("description","")
            ok, reason = is_relevant(title, desc)
            print(f"CHECK: {title[:60]} -> {ok} ({reason})")
            if ok:
                fresh.append((title, j.get("company",{}).get("display_name",""),
                              j.get("location",{}).get("display_name",""), j.get("redirect_url")))
                seen.add(job_id)
            else:
                # remember rejected too, so we don't re-check same ID next run
                seen.add(job_id)
    except Exception as e:
        print("Adzuna error", e)

# keep last 2000 to avoid big file
with open("seen.json","w") as f:
    json.dump(list(seen)[-2000:], f)

# --- 3. SEND MAIL ONLY IF NEW ---
if not fresh:
    print("No NEW jobs, skipping mail")
else:
    html = f"<h2>Embedded 0-3yr - {slot} - {datetime.now().date()} - {len(fresh)} NEW</h2>"
    for t,c,l,link in fresh:
        html += f"<p><b>{t}</b> - {c} ({l})<br><a href='{link}'>Apply Link</a></p>"

    msg = MIMEText(html, "html")
    msg["Subject"] = f"[{slot}] Embedded 0-3yr: {len(fresh)} new"
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(EMAIL_FROM, EMAIL_PASS)
        s.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())
    print(f"Sent {len(fresh)} for {slot}")
