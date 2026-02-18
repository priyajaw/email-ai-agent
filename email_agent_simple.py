import streamlit as st
from google import genai
from imapclient import IMAPClient
import email
from email import policy
import os
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()
client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

# Page config
st.set_page_config(
    page_title="Email Auto-Responder",
    page_icon="📧",
    layout="centered"
)

# Simple CSS
st.markdown("""
<style>
    .big-title {
        font-size: 2rem;
        font-weight: bold;
        text-align: center;
        margin-bottom: 2rem;
        color: #1f77b4;
    }
    .email-card {
        background-color: #f8f9fa;
        padding: 1.5rem;
        border-radius: 10px;
        margin-bottom: 1.5rem;
        border-left: 4px solid #1f77b4;
    }
    .urgent-card {
        border-left: 4px solid #f44336;
        background-color: #ffebee;
    }
    .spam-card {
        border-left: 4px solid #9e9e9e;
        background-color: #f5f5f5;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'emails' not in st.session_state:
    st.session_state.emails = []

# ============================================
# Functions
# ============================================

def fetch_and_process():
    """Fetch and process emails"""
    # Get credentials from .env
    email_address = os.environ.get("EMAIL_ADDRESS")
    password = os.environ.get("EMAIL_PASSWORD")
    server = os.environ.get("IMAP_SERVER", "imap.gmail.com")
    
    if not email_address or not password:
        st.error("⚠️ Missing credentials in .env file!")
        st.info("Add EMAIL_ADDRESS and EMAIL_PASSWORD to your .env file")
        return False
    
    try:
        # Connect
        with st.spinner(f"📬 Connecting to {email_address}..."):
            imap = IMAPClient(server, use_uid=True, ssl=True)
            imap.login(email_address, password)
            imap.select_folder('INBOX')
            
            # Fetch unread emails
            messages = imap.search(['UNSEEN'])
            
            if not messages:
                st.info("📭 No unread emails found!")
                return True
            
            # Limit to 10
            messages = messages[:10]
            st.success(f"✅ Found {len(messages)} unread email(s)")
            
            # Process each email
            raw_messages = imap.fetch(messages, ['RFC822'])
            st.session_state.emails = []
            
            progress = st.progress(0)
            for idx, (msg_id, data) in enumerate(raw_messages.items()):
                # Parse email
                msg = email.message_from_bytes(data[b'RFC822'], policy=policy.default)
                
                # Extract body
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
                
                email_data = {
                    'from': str(msg['From']),
                    'subject': str(msg['Subject']) or "(No Subject)",
                    'body': body[:1500]
                }
                
                # Classify
                classification = classify_email(email_data)
                
                # Draft response
                response = None
                if classification['category'] not in ['spam'] and classification['needs_reply'] == 'yes':
                    response = draft_response(email_data, classification)
                
                st.session_state.emails.append({
                    'from': email_data['from'],
                    'subject': email_data['subject'],
                    'body': email_data['body'],
                    'category': classification['category'],
                    'priority': classification['priority'],
                    'response': response
                })
                
                progress.progress((idx + 1) / len(messages))
            
            imap.logout()
            return True
            
    except Exception as e:
        st.error(f"❌ Error: {str(e)}")
        return False

def classify_email(email_data):
    """Quick classification"""
    prompt = f"""
Classify this email:

From: {email_data['from']}
Subject: {email_data['subject']}
Body: {email_data['body'][:600]}

Reply with ONLY:
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
    """Draft response"""
    prompt = f"""
Draft a professional email response.

From: {email_data['from']}
Subject: {email_data['subject']}
Body: {email_data['body'][:500]}

Category: {classification['category']}
Priority: {classification['priority']}

Write a 2-paragraph professional response. Be concise.
"""
    
    response = client.models.generate_content(
        model="models/gemini-2.5-flash",
        contents=prompt
    )
    
    return response.text

# ============================================
# UI
# ============================================

st.markdown('<div class="big-title">📧 Email Auto-Responder</div>', unsafe_allow_html=True)

# Simple metrics at top
if st.session_state.emails:
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("📬 Total", len(st.session_state.emails))
    with col2:
        urgent = sum(1 for e in st.session_state.emails if e['category'] == 'urgent')
        st.metric("🚨 Urgent", urgent)
    with col3:
        responded = sum(1 for e in st.session_state.emails if e['response'])
        st.metric("✍️ Responses", responded)
    
    st.markdown("---")

# Main button
if st.button("🚀 Fetch & Process Emails", type="primary", use_container_width=True):
    fetch_and_process()

st.markdown("---")

# Display emails
if st.session_state.emails:
    st.subheader("📨 Emails")
    
    for email in st.session_state.emails:
        # Determine card style
        card_class = "urgent-card" if email['category'] == 'urgent' else "spam-card" if email['category'] == 'spam' else "email-card"
        
        # Icon
        icon = "🚨" if email['category'] == 'urgent' else "🗑️" if email['category'] == 'spam' else "📧"
        
        with st.container():
            st.markdown(f'<div class="{card_class}">', unsafe_allow_html=True)
            
            # Header
            st.markdown(f"### {icon} {email['subject']}")
            st.caption(f"**From:** {email['from']}")
            
            # Category tags
            col1, col2 = st.columns([3, 1])
            with col1:
                st.markdown(f"📂 **{email['category'].upper()}** | ⚡ **{email['priority'].upper()}**")
            
            # Email preview
            with st.expander("📄 View Email"):
                st.text(email['body'][:500] + "..." if len(email['body']) > 500 else email['body'])
            
            # Response
            if email['response']:
                st.markdown("**✍️ Drafted Response:**")
                st.success(email['response'])
                
                # Download
                st.download_button(
                    "💾 Download",
                    email['response'],
                    file_name=f"response_{email['subject'][:20]}.txt",
                    key=f"dl_{email['subject']}"
                )
            else:
                st.info("⏭️ No response needed")
            
            st.markdown('</div>', unsafe_allow_html=True)
            st.markdown("")

else:
    # Welcome message
    st.info("👆 Click the button above to fetch and process your emails")
    
    st.markdown("### ✨ What This Does:")
    st.markdown("""
    1. 📬 Connects to your email (Gmail/Outlook)
    2. 🤖 AI classifies each email
    3. ✍️ Drafts professional responses
    4. 💾 Download ready-to-send replies
    """)
    
    st.markdown("### ⚙️ Setup Required:")
    st.code("""
# Add to .env file:
EMAIL_ADDRESS=your.email@gmail.com
EMAIL_PASSWORD=your-app-password
IMAP_SERVER=imap.gmail.com
    """)