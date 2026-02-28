import os
import uuid
import json
import pickle
import base64
import threading
import time
import schedule
import psycopg2
import requests
import gradio as gr

from dotenv import load_dotenv
from email.mime.text import MIMEText
from datetime import datetime

from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build


# ================= ENV =================

load_dotenv()

DB_URL = os.getenv("DB_URL")
GMAIL_USER = os.getenv("GMAIL_USER")
HF_URL = os.getenv("HF_URL")
XSRF_TOKEN = os.getenv("XSRF_TOKEN")
BIP_SESSION = os.getenv("BIP_SESSION")
BIP_API = "https://bip.bitsathy.ac.in/nova-api/student-activity-masters"

TOKEN_FILE = "token.pkl"

STATE_FILE = "state.json"
NEW_EVENTS_FILE = "new_events.json"
PAGE1_LOG_FILE = "page1_logs.json"

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

MAX_PAGES = 50
REQUEST_TIMEOUT = 20


# ================= DB =================

def get_db():
    try:
        return psycopg2.connect(DB_URL, sslmode="require")
    except Exception as e:
        print(f"❌ DB Connection error: {e}")
        raise


# ================= COOKIES =================

def load_cookies():
    """Load cookies from environment variables only"""
    if not XSRF_TOKEN or not BIP_SESSION:
        raise Exception("XSRF_TOKEN and BIP_SESSION must be set in environment variables")
    
    return {
        "XSRF-TOKEN": XSRF_TOKEN,
        "bip_session": BIP_SESSION
    }


# ================= GMAIL =================

def create_token():
    if not os.path.exists("credentials.json"):
        raise Exception("credentials.json missing")

    flow = InstalledAppFlow.from_client_secrets_file(
        "credentials.json",
        SCOPES
    )

    creds = flow.run_local_server(port=0)

    with open(TOKEN_FILE, "wb") as f:
        pickle.dump(creds, f)

    return creds


def get_gmail():
    creds = None

    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "rb") as f:
            creds = pickle.load(f)

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())

        with open(TOKEN_FILE, "wb") as f:
            pickle.dump(creds, f)

    if not creds:
        creds = create_token()

    return build("gmail", "v1", credentials=creds)


def send_email(to, subject, html):
    try:
        service = get_gmail()

        msg = MIMEText(html, "html")
        msg["To"] = to
        msg["From"] = GMAIL_USER
        msg["Subject"] = subject

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()

        service.users().messages().send(
            userId="me",
            body={"raw": raw}
        ).execute()

        print("✅ Sent:", to)
        return True

    except Exception as e:
        print("❌ Mail error:", e)
        return False


# ================= EMAIL =================

def create_event_email(event, unsub):
    return f"""
    <h2>📢 New BIP Event</h2>
    <b>{event['event_name']}</b>
    <ul>
      <li>Code: {event['event_code']}</li>
      <li>Organizer: {event['organizer']}</li>
      <li>Date: {event['start_date']}</li>
      <li>Location: {event['location']}</li>
    </ul>
    <a href="{event['web_url']}">View</a>
    <hr>
    <a href="{unsub}">Unsubscribe</a>
    """


# ================= BIP API =================

HEADERS = {
    "accept": "application/json",
    "x-requested-with": "XMLHttpRequest",
}

BASE_PARAMS = {
    "perPage": 10
}


def fetch_page(page):
    """Fetch a specific page from BIP API"""
    cookies = load_cookies()
    
    params = BASE_PARAMS.copy()
    params["page"] = page

    r = requests.get(
        BIP_API,
        params=params,
        headers=HEADERS,
        cookies=cookies,
        timeout=REQUEST_TIMEOUT
    )

    # Expired session
    if "text/html" in r.headers.get("Content-Type", ""):
        raise Exception("Session expired. Login again.")

    r.raise_for_status()

    return r.json()


def fetch_latest():
    """Legacy function - now uses fetch_page"""
    return fetch_page(1)["resources"]


def parse_event(resource):
    """Parse event resource into clean data structure"""
    data = {}

    for f in resource.get("fields", []):
        key = f.get("attribute")
        val = f.get("value")
        
        if key:
            data[key] = val

    data["id"] = resource["id"]["value"]
    data["title"] = resource.get("title")

    return data


def fetch_new_events(old_id):
    """Fetch all new events since the last known ID"""
    page = 1
    new_events = []

    while page <= MAX_PAGES:
        print(f"📄 Fetching page {page}...")

        try:
            data = fetch_page(page)
            resources = data.get("resources", [])
        except Exception as e:
            print(f"❌ Error fetching page {page}: {e}")
            break

        if not resources:
            break

        for res in resources:
            ev = parse_event(res)

            if ev["id"] == old_id:
                return new_events

            new_events.append(ev)

        page += 1

    return new_events


# ================= STATE MANAGEMENT =================

def load_state():
    """Load the last processed event state"""
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except:
        return None


def save_state(latest_id):
    """Save the latest processed event ID"""
    state = {
        "latest_id": latest_id,
        "last_updated": datetime.now().isoformat()
    }
    
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def save_new_events(events):
    """Save new events to file"""
    data = {
        "timestamp": datetime.now().isoformat(),
        "count": len(events),
        "events": events
    }
    
    with open(NEW_EVENTS_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ================= PAGE 1 LOGGER =================

def load_page1_logs():
    """Load page 1 historical logs"""
    try:
        with open(PAGE1_LOG_FILE, "r") as f:
            return json.load(f)
    except:
        return []


def save_page1_logs(logs):
    """Save page 1 logs to file"""
    with open(PAGE1_LOG_FILE, "w") as f:
        json.dump(logs, f, indent=2, ensure_ascii=False)


def log_page1_to_file():
    """Save page 1 snapshot to file"""
    try:
        data = fetch_page(1)
        resources = data.get("resources", [])
        
        events = []
        for res in resources:
            events.append(parse_event(res))

        logs = load_page1_logs()
        
        entry = {
            "timestamp": datetime.now().isoformat(),
            "count": len(events),
            "events": events
        }

        logs.append(entry)
        
        # Keep only last 100 entries to prevent file from growing too large
        if len(logs) > 100:
            logs = logs[-100:]
        
        save_page1_logs(logs)
        
        print(f"📝 Page-1 snapshot saved ({len(events)} events)")
        return True
        
    except Exception as e:
        print(f"❌ Failed to log page 1: {e}")
        return False


# ================= SUBSCRIBE =================

def subscribe(email):

    if not email or not email.endswith("@bitsathy.ac.in"):
        return "❌ Use college email only"

    try:
        db = get_db()
        cur = db.cursor()

        # Check existing user
        cur.execute("""
            SELECT email_verified, unsubscribed
            FROM users
            WHERE email=%s
        """, (email,))

        row = cur.fetchone()

        # -----------------------------
        # EXISTING USER
        # -----------------------------
        if row:
            verified, unsub = row

            # Already active
            if verified and not unsub:
                cur.close()
                db.close()
                return "✅ You're already subscribed"

            # Re-subscribe user
            if verified and unsub:
                new_unsub_token = uuid.uuid4().hex

                cur.execute("""
                    UPDATE users
                    SET unsubscribed=false,
                        unsubscribe_token=%s
                    WHERE email=%s
                """, (new_unsub_token, email))
                db.commit()
                cur.close()
                db.close()
                return "✅ Successfully re-subscribed"

            # Not verified yet → resend verification
            if not verified:
                verification_token = uuid.uuid4().hex

                cur.execute("""
                    UPDATE users
                    SET verification_token=%s
                    WHERE email=%s
                """, (verification_token, email))

                db.commit()

                verify_link = f"{HF_URL}?verify={verification_token}"

                send_email(
                    email,
                    "Verify BIP Alerts",
                    f"Click <a href='{verify_link}'>here</a> to verify"
                )

                cur.close()
                db.close()
                return "📩 Verification email re-sent"

        # -----------------------------
        # NEW USER
        # -----------------------------
        verification_token = uuid.uuid4().hex
        unsubscribe_token = uuid.uuid4().hex

        cur.execute("""
            INSERT INTO users(
                email,
                email_verified,
                verification_token,
                unsubscribe_token,
                unsubscribed
            )
            VALUES(%s, false, %s, %s, false)
        """, (email, verification_token, unsubscribe_token))

        db.commit()

        verify_link = f"{HF_URL}?verify={verification_token}"

        send_email(
            email,
            "Verify BIP Alerts",
            f"Click <a href='{verify_link}'>here</a> to verify"
        )

        cur.close()
        db.close()

        return "📩 Verification sent"

    except Exception as e:
        print("❌ Subscribe error:", e)
        return f"❌ Error: {str(e)}"
    
# ================= VERIFY =================

def verify_user(token):
    if not token:
        return ""

    try:
        db = get_db()
        cur = db.cursor()

        cur.execute("""
            UPDATE users
            SET email_verified = true,
                verification_token = NULL,
                unsubscribed = false
            WHERE verification_token = %s
            AND email_verified = false
        """, (token,))

        if cur.rowcount == 0:
            result = "❌ Invalid or expired verification link"
        else:
            result = "✅ Email verified successfully!"

        db.commit()
        cur.close()
        db.close()

        return result

    except Exception as e:
        print("❌ Verify error:", e)
        return f"❌ Verification failed: {str(e)}"

# ================= UNSUBSCRIBE =================
def unsubscribe_user(token):
    if not token:
        return ""

    try:
        db = get_db()
        cur = db.cursor()

        cur.execute("""
            UPDATE users
            SET unsubscribed = true
            WHERE unsubscribe_token = %s
            AND email_verified = true
        """, (token,))

        if cur.rowcount == 0:
            result = "❌ Invalid or expired unsubscribe link"
        else:
            result = "✅ Successfully unsubscribed from BIP alerts"

        db.commit()
        cur.close()
        db.close()

        return result

    except Exception as e:
        print("❌ Unsubscribe error:", e)
        return f"❌ Unsubscribe failed: {str(e)}"

# ================= EMAIL STATUS =================

def check_email_status(email):
    if not email or not email.endswith("@bitsathy.ac.in"):
        return "❌ Please enter a valid college email"

    try:
        db = get_db()
        cur = db.cursor()

        cur.execute("""
            SELECT email_verified, unsubscribed, verification_token
            FROM users 
            WHERE email=%s
        """, (email,))

        result = cur.fetchone()
        cur.close()
        db.close()

        if not result:
            return "📧 Email not found. Click Subscribe to register."
        
        verified, unsubscribed, token = result
        
        if unsubscribed:
            return "🚫 Email is unsubscribed from alerts"
        elif verified:
            return "✅ Email is verified and subscribed to alerts"
        else:
            return "⏳ Email registered but not verified. Check your inbox."
            
    except Exception as e:
        print(f"❌ Status check error: {e}")
        return f"❌ Database error: {str(e)}"


# ================= ENHANCED NOTIFIER =================

def check_events():
    """Enhanced event checker with state tracking"""
    print("\n🔍 Checking for new events...")

    try:
        # Save page 1 snapshot
        log_page1_to_file()

        state = load_state()

        # First run
        if not state:
            print("🆕 First run detected")

            data = fetch_page(1)
            resources = data.get("resources", [])

            if not resources:
                print("⚠️ No events found")
                return "⚠️ No events found on first run"

            first_event = parse_event(resources[0])
            save_state(first_event["id"])

            print("📌 Saved initial ID:", first_event["id"])
            return f"📌 Initialized with event ID: {first_event['id']}"

        old_id = state["latest_id"]
        print("📍 Last known ID:", old_id)

        new_events = fetch_new_events(old_id)

        if not new_events:
            print("⏳ No new events added")
            return "⏳ No new events found"

        latest = new_events[0]
        print(f"\n🔥 {len(new_events)} NEW EVENT(S) ADDED!")
        print("📢 Latest Event:", latest.get("event_name", "Unknown"))

        # Save new events to file
        save_new_events(new_events)

        # Update state
        save_state(latest["id"])

        # Send notifications to users
        return send_notifications_for_events(new_events)

    except Exception as e:
        error_msg = f"❌ Event check error: {e}"
        print(error_msg)
        return error_msg

def send_notifications_for_events(new_events):
    """Send one combined email for all new events"""

    if not new_events:
        return "📭 No events to notify"

    try:
        db = get_db()
        cur = db.cursor()

        cur.execute("""
            SELECT id,email,unsubscribe_token
            FROM users
            WHERE email_verified=true
            AND unsubscribed=false
        """)

        users = cur.fetchall()

        if not users:
            cur.close()
            db.close()
            return "📭 No verified users"

        # Build combined HTML
        events_html = ""

        for i, event in enumerate(new_events, 1):
            events_html += f"""
            <hr>
            <h3>{i}. {event['event_name']}</h3>
            <ul>
              <li><b>Code:</b> {event['event_code']}</li>
              <li><b>Event Name:</b> {event['event_name']}</li>
              <li><b>Organizer:</b> {event['organizer']}</li>
              <li><b>Date:</b> {event['start_date']}</li>
              <li><b>Category:</b> {event['event_category']}</li>
              <li><b>BIP URL:</b> <a href="https://bip.bitsathy.ac.in/nova/resources/student-achievement-loggers">Logger Link</a></li>
              <li><b>Location:</b> {event['location']}</li>
              <li><b>View:</b> <a href="{event['web_url']}">Link</a></li>
            </ul>
            """

        subject = f"📢 {len(new_events)} New BIP Events Added"

        total_sent = 0

        for uid, mail, unsubscribe_token in users:

            html = f"""
            <h2>📢 New BIP Events Alert</h2>
            <p>{len(new_events)} new events have been added:</p>
            {events_html}
            <hr>
            <a href="{HF_URL}?unsubscribe={unsubscribe_token}">Unsubscribe</a>
            """

            if send_email(mail, subject, html):
                total_sent += 1

        cur.close()
        db.close()

        return f"✅ Sent {total_sent} combined notifications"

    except Exception as e:
        print("❌ Notification error:", e)
        return f"❌ Error: {e}"

def run_notifier():
    """Legacy function - now uses enhanced check_events"""
    return check_events()



# ================= SCHEDULER =================

def scheduler_worker():
    print("⏰ Scheduler started")

    # Initial run
    try:
        result = check_events()
        print(f"Initial check: {result}")
    except Exception as e:
        print(f"❌ Initial check failed: {e}")

    # Schedule every 3 minutes
    schedule.every(3).minutes.do(check_events)

    while True:
        try:
            schedule.run_pending()
        except Exception as e:
            print(f"❌ Scheduler error: {e}")
        time.sleep(30)


# ================= ROUTER =================

def route_handler(req: gr.Request):
    try:
        params = req.query_params

        if "verify" in params:
            return verify_user(params["verify"])
        
        if "unsubscribe" in params:
            return unsubscribe_user(params["unsubscribe"])

        return ""
    
    except Exception as e:
        print(f"❌ Router error: {e}")
        return f"❌ Error: {str(e)}"


# ================= UI =================

with gr.Blocks(title="BIP Notifier", theme=gr.themes.Soft()) as app:

    gr.Markdown("# 📢 BIP Event Email Alerts")
    gr.Markdown("*Auto-checking every 3 minutes for new events*")

    # ---------- Main Section ----------
    with gr.Row():
        with gr.Column():
            email = gr.Textbox(
                label="College Email (@bitsathy.ac.in)",
                placeholder="your.name@bitsathy.ac.in"
            )
            
            with gr.Row():
                sub_btn = gr.Button("Subscribe", variant="primary")
                status_btn = gr.Button("Check Status", variant="secondary")
            
            out = gr.Textbox(label="Status", interactive=False, lines=3)

    sub_btn.click(subscribe, email, out)
    status_btn.click(check_email_status, email, out)

    # ---------- System Status ----------
    with gr.Accordion("📊 System Status", open=False):
        def get_system_status():
            try:
                state = load_state()
                page1_logs = load_page1_logs()
                
                status = "### Current State:\n"
                
                if state:
                    status += f"- **Last Event ID**: {state.get('latest_id', 'N/A')}\n"
                    status += f"- **Last Updated**: {state.get('last_updated', 'N/A')}\n"
                else:
                    status += "- **Status**: Not initialized\n"
                
                status += f"- **Page 1 Logs**: {len(page1_logs)} entries\n"
                
                if os.path.exists(NEW_EVENTS_FILE):
                    with open(NEW_EVENTS_FILE, 'r') as f:
                        new_events = json.load(f)
                    status += f"- **Last New Events**: {new_events.get('count', 0)} events\n"
                else:
                    status += "- **Last New Events**: None\n"
                
                return status
                
            except Exception as e:
                return f"❌ Error loading status: {e}"
        
        status_btn = gr.Button("Get System Status")
        status_out = gr.Textbox(label="System Status", lines=5, interactive=False)
        status_btn.click(get_system_status, None, status_out)

    # ---------- Instructions ----------
    with gr.Accordion("📝 Instructions", open=False):
        gr.Markdown("""
        ### How to use:
        1. Enter your college email (@bitsathy.ac.in)
        2. Click **Subscribe**
        3. Check your email and click the verification link
        4. You'll receive alerts for new BIP events automatically
        
        ### Admin Setup:
        1. Login to BIP portal in browser
        2. Open Developer Tools (F12) → Network tab
        3. Make any request and copy XSRF-TOKEN and bip_session cookies
        4. Paste them in Admin Controls above
        
        ### Files Created:
        - `state.json`: Tracks last processed event
        - `page1_logs.json`: Historical snapshots of page 1
        - `new_events.json`: Latest batch of new events found
        """)

    # ---------- URL Handler ----------
    app.load(route_handler, None, out)


# ================= MAIN =================

if __name__ == "__main__":
    print("🚀 BIP Event Notifier (Enhanced with File Tracking)")
    print("=" * 50)
    
    # Start scheduler in background
    scheduler_thread = threading.Thread(
        target=scheduler_worker,
        daemon=True
    )
    scheduler_thread.start()

    # Start Gradio app
    app.launch(
        share=False  # Set to True for public sharing
    )