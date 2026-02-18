import streamlit as st
from google import genai
from imapclient import IMAPClient
import email
from email import policy
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import smtplib
import os
from dotenv import load_dotenv
from datetime import datetime
import json

load_dotenv()
client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

# Page config
st.set_page_config(
    page_title="AI Email Auto-Responder Pro",
    page_icon="📧",
    layout="wide"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        text-align: center;
        background: linear-gradient(90deg, #1f77b4, #ff7f0e);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 2rem;
    }
    .status-pending {
        background-color: #fff3cd;
        padding: 0.5rem;
        border-radius: 5px;
        border-left: 4px solid #ffc107;
    }
    .status-approved {
        background-color: #d4edda;
        padding: 0.5rem;
        border-radius: 5px;
        border-left: 4px solid #28a745;
    }
    .status-sent {
        background-color: #d1ecf1;
        padding: 0.5rem;
        border-radius: 5px;
        border-left: 4px solid #17a2b8;
    }
    .status-rejected {
        background-color: #f8d7da;
        padding: 0.5rem;
        border-radius: 5px;
        border-left: 4px solid #dc3545;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'emails' not in st.session_state:
    st.session_state.emails = []
if 'sent_log' not in st.session_state:
    st.session_state.sent_log = []

# ============================================
# Email Functions
# ============================================

def fetch_emails():
    """Fetch unread emails via IMAP"""
    email_address = os.environ.get("EMAIL_ADDRESS")
    password = os.environ.get("EMAIL_PASSWORD")
    server = os.environ.get("IMAP_SERVER", "imap.gmail.com")
    
    if not email_address or not password:
        st.error("⚠️ Missing credentials in .env file!")
        return None
    
    try:
        imap = IMAPClient(server, use_uid=True, ssl=True)
        imap.login(email_address, password)
        imap.select_folder('INBOX')
        
        messages = imap.search(['UNSEEN'])
        
        if not messages:
            return []
        
        messages = messages[:10]
        raw_messages = imap.fetch(messages, ['RFC822'])
        
        emails = []
        for msg_id, data in raw_messages.items():
            msg = email.message_from_bytes(data[b'RFC822'], policy=policy.default)
            
            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        try:
                            body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                            break
                        except:
                            pass
            else:
                try:
                    body = msg.get_payload(decode=True).decode('utf-8', errors='ignore')
                except:
                    body = str(msg.get_payload())
            
            emails.append({
                'id': str(msg_id),
                'from': str(msg['From']),
                'from_email': email.utils.parseaddr(str(msg['From']))[1],
                'subject': str(msg['Subject']) or "(No Subject)",
                'body': body[:1500],
                'status': 'pending',
                'response': None,
                'edited_response': None
            })
        
        imap.logout()
        return emails
        
    except Exception as e:
        st.error(f"❌ Error: {str(e)}")
        return None

def classify_email(email_data):
    """AI classification"""
    prompt = f"""
Classify this email:

From: {email_data['from']}
Subject: {email_data['subject']}
Body: {email_data['body'][:600]}

Reply ONLY:
CATEGORY: [urgent/spam/customer_support/general_inquiry]
PRIORITY: [high/medium/low]
NEEDS_REPLY: [yes/no]
"""
    
    response = client.models.generate_content(
        model="models/gemini-2.5-flash",
        contents=prompt
    )
    
    text = response.text.lower()
    
    return {
        'category': 'urgent' if 'urgent' in text else 'spam' if 'spam' in text else 'customer_support' if 'customer' in text else 'general_inquiry',
        'priority': 'high' if 'high' in text else 'low' if 'low' in text else 'medium',
        'needs_reply': 'yes' if 'yes' in text else 'no'
    }

def draft_response(email_data, classification):
    """AI draft response"""
    if classification['category'] == 'spam' or classification['needs_reply'] == 'no':
        return None
    
    prompt = f"""
Draft a professional email response.

From: {email_data['from']}
Subject: {email_data['subject']}
Body: {email_data['body'][:500]}

Category: {classification['category']}
Priority: {classification['priority']}

Write a professional 2-paragraph response. Be concise and helpful.
"""
    
    response = client.models.generate_content(
        model="models/gemini-2.5-flash",
        contents=prompt
    )
    
    return response.text

def send_email(to_email, subject, body):
    """Send email via SMTP"""
    email_address = os.environ.get("EMAIL_ADDRESS")
    password = os.environ.get("EMAIL_PASSWORD")
    
    # SMTP servers
    smtp_servers = {
        'gmail.com': ('smtp.gmail.com', 587),
        'outlook.com': ('smtp.office365.com', 587),
        'office365.com': ('smtp.office365.com', 587)
    }
    
    # Detect SMTP server
    domain = email_address.split('@')[1].lower()
    smtp_server, smtp_port = smtp_servers.get(domain, ('smtp.gmail.com', 587))
    
    try:
        # Create message
        msg = MIMEMultipart()
        msg['From'] = email_address
        msg['To'] = to_email
        msg['Subject'] = f"Re: {subject}"
        
        msg.attach(MIMEText(body, 'plain'))
        
        # Send
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(email_address, password)
        server.send_message(msg)
        server.quit()
        
        return True, None
        
    except Exception as e:
        return False, str(e)

# ============================================
# UI Header
# ============================================

st.markdown('<div class="main-header">📧 AI Email Auto-Responder Pro</div>', unsafe_allow_html=True)

# ============================================
# Sidebar Stats
# ============================================

with st.sidebar:
    st.header("📊 Statistics")
    
    if st.session_state.emails:
        total = len(st.session_state.emails)
        pending = sum(1 for e in st.session_state.emails if e['status'] == 'pending')
        sent = sum(1 for e in st.session_state.emails if e['status'] == 'sent')
        rejected = sum(1 for e in st.session_state.emails if e['status'] == 'rejected')
        
        st.metric("📬 Total", total)
        st.metric("⏳ Pending", pending, delta=f"{pending} awaiting review")
        st.metric("✅ Sent", sent, delta=f"{sent} sent successfully")
        st.metric("❌ Rejected", rejected)
    else:
        st.info("No emails processed yet")
    
    st.markdown("---")
    
    # Sent log
    if st.session_state.sent_log:
        st.subheader("📤 Recent Sends")
        for log in st.session_state.sent_log[-5:]:
            st.caption(f"✉️ {log['to']}")
            st.caption(f"   {log['timestamp']}")

# ============================================
# Main Actions
# ============================================

st.header("🚀 Actions")

col1, col2 = st.columns(2)

with col1:
    if st.button("📬 Fetch & Process New Emails", type="primary", use_container_width=True):
        with st.spinner("Fetching emails..."):
            emails = fetch_emails()
            
            if emails is None:
                st.error("Failed to fetch emails")
            elif len(emails) == 0:
                st.info("📭 No unread emails found!")
            else:
                st.success(f"✅ Found {len(emails)} unread email(s)")
                
                # Process each
                progress = st.progress(0)
                for idx, email_data in enumerate(emails):
                    classification = classify_email(email_data)
                    response = draft_response(email_data, classification)
                    
                    email_data['classification'] = classification
                    email_data['response'] = response
                    email_data['edited_response'] = response  # Initialize editable version
                    
                    progress.progress((idx + 1) / len(emails))
                
                st.session_state.emails = emails
                st.rerun()

with col2:
    if st.button("🔄 Clear All", use_container_width=True):
        st.session_state.emails = []
        st.rerun()

st.markdown("---")

# ============================================
# Display Emails
# ============================================

if st.session_state.emails:
    # Tabs
    tab1, tab2, tab3 = st.tabs(["⏳ Pending Review", "✅ Sent", "❌ Rejected"])
    
    with tab1:
        pending_emails = [e for e in st.session_state.emails if e['status'] == 'pending']
        
        if not pending_emails:
            st.info("✨ All emails reviewed!")
        else:
            st.write(f"**{len(pending_emails)} email(s) awaiting your review:**")
            
            for idx, email in enumerate(pending_emails):
                with st.container():
                    # Status indicator
                    status_class = f"status-{email['status']}"
                    
                    st.markdown(f'<div class="{status_class}">', unsafe_allow_html=True)
                    
                    # Email header
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        st.markdown(f"### 📧 {email['subject']}")
                        st.caption(f"**From:** {email['from']}")
                    with col2:
                        if 'classification' in email:
                            cat = email['classification']['category']
                            pri = email['classification']['priority']
                            
                            if cat == 'urgent':
                                st.error(f"🚨 {cat.upper()}")
                            elif cat == 'spam':
                                st.warning(f"🗑️ {cat.upper()}")
                            else:
                                st.info(f"📂 {cat.upper()}")
                            
                            st.caption(f"⚡ Priority: {pri.upper()}")
                    
                    # Original email body
                    with st.expander("📄 View Original Email"):
                        st.text(email['body'][:600] + "..." if len(email['body']) > 600 else email['body'])
                    
                    # Drafted response
                    if email['response']:
                        st.markdown("**✍️ AI Drafted Response:**")
                        
                        # Editable text area
                        edited_response = st.text_area(
                            "Edit response if needed:",
                            value=email['edited_response'],
                            height=150,
                            key=f"edit_{email['id']}"
                        )
                        
                        # Update edited response
                        email['edited_response'] = edited_response
                        
                        # Action buttons
                        col1, col2, col3, col4 = st.columns(4)
                        
                        with col1:
                            if st.button("✅ Approve & Send", key=f"approve_{email['id']}", type="primary"):
                                with st.spinner("Sending email..."):
                                    success, error = send_email(
                                        email['from_email'],
                                        email['subject'],
                                        edited_response
                                    )
                                    
                                    if success:
                                        email['status'] = 'sent'
                                        st.session_state.sent_log.append({
                                            'to': email['from_email'],
                                            'subject': email['subject'],
                                            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                                        })
                                        st.success("✅ Email sent successfully!")
                                        st.balloons()
                                        st.rerun()
                                    else:
                                        st.error(f"❌ Failed to send: {error}")
                        
                        with col2:
                            if st.button("❌ Reject", key=f"reject_{email['id']}"): 
                                email['status'] = 'rejected'
                                st.warning("Email rejected")
                                st.rerun()
                        
                        with col3:
                            # Download draft
                            st.download_button(
                                "💾 Download",
                                edited_response,
                                file_name=f"draft_{email['subject'][:20]}.txt",
                                key=f"dl_{email['id']}"
                            )
                        
                        with col4:
                            # Copy to clipboard
                            st.code(edited_response, language=None)
                    
                    else:
                        st.info("⏭️ No response needed (spam/no-reply)")
                        if st.button("❌ Mark as Reviewed", key=f"mark_{email['id']}"):
                            email['status'] = 'rejected'
                            st.rerun()
                    
                    st.markdown('</div>', unsafe_allow_html=True)
                    st.markdown("---")
    
    with tab2:
        sent_emails = [e for e in st.session_state.emails if e['status'] == 'sent']
        
        if not sent_emails:
            st.info("No emails sent yet")
        else:
            st.success(f"✅ {len(sent_emails)} email(s) sent successfully!")
            
            for email in sent_emails:
                with st.expander(f"✉️ {email['subject']}"):
                    st.markdown(f"**To:** {email['from']}")
                    st.markdown(f"**Sent:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                    st.markdown("**Response Sent:**")
                    st.success(email['edited_response'])
    
    with tab3:
        rejected_emails = [e for e in st.session_state.emails if e['status'] == 'rejected']
        
        if not rejected_emails:
            st.info("No rejected emails")
        else:
            st.write(f"❌ {len(rejected_emails)} email(s) rejected")
            
            for email in rejected_emails:
                with st.expander(f"📧 {email['subject']}"):
                    st.markdown(f"**From:** {email['from']}")
                    st.text(email['body'][:300])

else:
    # Welcome screen
    st.info("👆 Click 'Fetch & Process New Emails' to get started")
    
    st.markdown("### ✨ Complete Workflow:")
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        st.markdown("**1️⃣ Fetch**")
        st.caption("Get unread emails")
    with col2:
        st.markdown("**2️⃣ AI Draft**")
        st.caption("Generate responses")
    with col3:
        st.markdown("**3️⃣ Review**")
        st.caption("You edit & approve")
    with col4:
        st.markdown("**4️⃣ Send**")
        st.caption("Actually sends email")
    with col5:
        st.markdown("**5️⃣ Track**")
        st.caption("Monitor sent status")