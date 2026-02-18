import streamlit as st
from google import genai
from imapclient import IMAPClient
import email
from email import policy
import os
from dotenv import load_dotenv
from datetime import datetime
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

load_dotenv()
client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

# Page config
st.set_page_config(
    page_title="AI Email Auto-Responder",
    page_icon="📧",
    layout="wide"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        background: linear-gradient(90deg, #1f77b4, #ff7f0e);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        margin-bottom: 2rem;
    }
    .urgent {
        background-color: #ffebee;
        padding: 1rem;
        border-left: 5px solid #f44336;
        border-radius: 5px;
        margin-bottom: 1rem;
    }
    .spam {
        background-color: #fafafa;
        padding: 1rem;
        border-left: 5px solid #9e9e9e;
        border-radius: 5px;
        margin-bottom: 1rem;
    }
    .customer {
        background-color: #e3f2fd;
        padding: 1rem;
        border-left: 5px solid #2196f3;
        border-radius: 5px;
        margin-bottom: 1rem;
    }
    .general {
        background-color: #f1f8e9;
        padding: 1rem;
        border-left: 5px solid #8bc34a;
        border-radius: 5px;
        margin-bottom: 1rem;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'processed_emails' not in st.session_state:
    st.session_state.processed_emails = []
if 'connected' not in st.session_state:
    st.session_state.connected = False

# ============================================
# IMAP Connection
# ============================================

def connect_imap(email_address, password, server):
    """Connect to IMAP server"""
    try:
        imap = IMAPClient(server, use_uid=True, ssl=True)
        imap.login(email_address, password)
        imap.select_folder('INBOX')
        return imap, None
    except Exception as e:
        return None, str(e)

def fetch_emails(imap, limit=10):
    """Fetch unread emails"""
    try:
        messages = imap.search(['UNSEEN'])
        
        if not messages:
            return [], None
        
        messages = messages[:limit]
        raw_messages = imap.fetch(messages, ['RFC822'])
        
        emails = []
        for msg_id, data in raw_messages.items():
            email_message = email.message_from_bytes(
                data[b'RFC822'],
                policy=policy.default
            )
            
            # Extract body
            body = ""
            if email_message.is_multipart():
                for part in email_message.walk():
                    if part.get_content_type() == "text/plain":
                        try:
                            body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                            break
                        except:
                            pass
            else:
                try:
                    body = email_message.get_payload(decode=True).decode('utf-8', errors='ignore')
                except:
                    body = str(email_message.get_payload())
            
            emails.append({
                'id': msg_id,
                'from': str(email_message['From']),
                'subject': str(email_message['Subject']) or "(No Subject)",
                'date': str(email_message['Date']),
                'body': body[:2000]
            })
        
        return emails, None
    except Exception as e:
        return [], str(e)

# ============================================
# AI Functions
# ============================================

def classify_email(email_data):
    """Classify email using AI"""
    classification_prompt = f"""
Analyze and classify this email.

From: {email_data['from']}
Subject: {email_data['subject']}
Body: {email_data['body'][:800]}

Provide:
CATEGORY: [urgent/spam/customer_support/general_inquiry/internal/promotional]
PRIORITY: [high/medium/low]
SENTIMENT: [positive/neutral/negative]
NEEDS_REPLY: [yes/no]
REASON: [brief explanation]
"""
    
    response = client.models.generate_content(
        model="models/gemini-2.5-flash",
        contents=classification_prompt
    )
    
    result_text = response.text
    
    classification = {
        'category': 'general_inquiry',
        'priority': 'medium',
        'sentiment': 'neutral',
        'needs_reply': 'yes',
        'reason': ''
    }
    
    for line in result_text.split('\n'):
        line_upper = line.upper()
        if 'CATEGORY:' in line_upper:
            if 'urgent' in line.lower(): classification['category'] = 'urgent'
            elif 'spam' in line.lower() or 'promotional' in line.lower(): classification['category'] = 'spam'
            elif 'customer' in line.lower(): classification['category'] = 'customer_support'
            elif 'internal' in line.lower(): classification['category'] = 'internal'
        elif 'PRIORITY:' in line_upper:
            if 'high' in line.lower(): classification['priority'] = 'high'
            elif 'low' in line.lower(): classification['priority'] = 'low'
        elif 'SENTIMENT:' in line_upper:
            if 'positive' in line.lower(): classification['sentiment'] = 'positive'
            elif 'negative' in line.lower(): classification['sentiment'] = 'negative'
        elif 'NEEDS_REPLY:' in line_upper:
            classification['needs_reply'] = 'yes' if 'yes' in line.lower() else 'no'
        elif 'REASON:' in line_upper:
            classification['reason'] = line.split(':', 1)[1].strip() if ':' in line else ''
    
    return classification

def draft_response(email_data, classification):
    """Draft AI response"""
    if classification['category'] == 'spam' or classification['needs_reply'] == 'no':
        return None
    
    tone = "professional and helpful"
    if classification['priority'] == 'high':
        tone = "immediate and solution-focused"
    elif classification['sentiment'] == 'negative':
        tone = "empathetic and reassuring"
    
    draft_prompt = f"""
Draft a professional email response.

Original:
From: {email_data['from']}
Subject: {email_data['subject']}
Body: {email_data['body'][:600]}

Context: {classification['category']} | {classification['priority']} priority

Requirements:
- Tone: {tone}
- 2-3 paragraphs
- Include greeting and closing
- Professional and clear

Draft:
"""
    
    response = client.models.generate_content(
        model="models/gemini-2.5-flash",
        contents=draft_prompt
    )
    
    return response.text

# ============================================
# UI Header
# ============================================

st.markdown('<div class="main-header">📧 AI Email Auto-Responder Agent</div>', unsafe_allow_html=True)

# ============================================
# Sidebar - IMAP Settings
# ============================================

with st.sidebar:
    st.header("⚙️ IMAP Settings")
    
    # Provider selection
    provider = st.selectbox(
        "Email Provider:",
        ["Gmail", "Outlook/Office 365", "Custom"]
    )
    
    # Auto-fill server
    if provider == "Gmail":
        imap_server = "imap.gmail.com"
    elif provider == "Outlook/Office 365":
        imap_server = "outlook.office365.com"
    else:
        imap_server = st.text_input("IMAP Server:", "imap.gmail.com")
    
    st.text_input("IMAP Server:", value=imap_server, disabled=True)
    
    email_address = st.text_input("📧 Email Address:", placeholder="your.email@gmail.com")
    email_password = st.text_input("🔑 Password:", type="password", placeholder="App password")
    
    email_limit = st.slider("📬 Emails to Fetch:", min_value=1, max_value=50, value=10)
    
    st.markdown("---")
    
    # Info boxes
    if provider == "Gmail":
        with st.expander("ℹ️ Gmail Setup"):
            st.markdown("""
**Steps:**
1. Enable IMAP in Gmail settings
2. Enable 2-Step Verification
3. Create App Password at:
   https://myaccount.google.com/apppasswords
4. Use the 16-char app password above
            """)
    elif provider == "Outlook/Office 365":
        with st.expander("ℹ️ Outlook Setup"):
            st.markdown("""
**Steps:**
1. Enable IMAP in Outlook settings
2. Create App Password at:
   https://mysignins.microsoft.com/security-info
3. Use the app password above
            """)
    
    st.markdown("---")
    
    # Connect button
    connect_button = st.button("🔌 Connect & Fetch Emails", type="primary", use_container_width=True)
    
    # Stats
    if st.session_state.processed_emails:
        st.markdown("### 📊 Statistics")
        total = len(st.session_state.processed_emails)
        st.metric("Total Processed", total)
        
        with_response = sum(1 for e in st.session_state.processed_emails if e['response'])
        st.metric("Responses Drafted", with_response)

# ============================================
# Main Content
# ============================================

if connect_button:
    if not email_address or not email_password:
        st.error("⚠️ Please enter email and password!")
    else:
        with st.spinner("🔌 Connecting to email server..."):
            imap, error = connect_imap(email_address, email_password, imap_server)
            
            if error:
                st.error(f"❌ Connection failed: {error}")
                st.info("""
**Troubleshooting:**
- Make sure IMAP is enabled
- Use an App Password (not regular password)
- Check the server address
                """)
            else:
                st.success(f"✅ Connected to {email_address}")
                
                # Fetch emails
                with st.spinner(f"📬 Fetching {email_limit} unread emails..."):
                    emails, error = fetch_emails(imap, email_limit)
                    
                    if error:
                        st.error(f"❌ Error fetching emails: {error}")
                    elif not emails:
                        st.info("📭 No unread emails found!")
                    else:
                        st.success(f"📧 Found {len(emails)} unread email(s)")
                        
                        # Process emails
                        st.session_state.processed_emails = []
                        progress_bar = st.progress(0)
                        status_text = st.empty()
                        
                        for idx, email_data in enumerate(emails):
                            status_text.text(f"Processing {idx+1}/{len(emails)}: {email_data['subject'][:50]}...")
                            
                            # AI Processing
                            classification = classify_email(email_data)
                            response_text = draft_response(email_data, classification)
                            
                            # Store result
                            st.session_state.processed_emails.append({
                                'from': email_data['from'],
                                'subject': email_data['subject'],
                                'body': email_data['body'],
                                'classification': classification,
                                'response': response_text,
                                'timestamp': datetime.now()
                            })
                            
                            progress_bar.progress((idx + 1) / len(emails))
                        
                        status_text.text("✅ Processing complete!")
                        imap.logout()
                        st.balloons()

# ============================================
# Display Results
# ============================================

if st.session_state.processed_emails:
    st.markdown("---")
    st.header("📊 Dashboard")
    
    # Metrics Row
    col1, col2, col3, col4 = st.columns(4)
    
    total_emails = len(st.session_state.processed_emails)
    urgent_count = sum(1 for e in st.session_state.processed_emails if e['classification']['category'] == 'urgent')
    high_priority = sum(1 for e in st.session_state.processed_emails if e['classification']['priority'] == 'high')
    needs_review = sum(1 for e in st.session_state.processed_emails if e['classification']['category'] in ['urgent', 'customer_support'])
    
    with col1:
        st.metric("📬 Total Emails", total_emails)
    with col2:
        st.metric("🚨 Urgent", urgent_count)
    with col3:
        st.metric("⚡ High Priority", high_priority)
    with col4:
        st.metric("👁️ Needs Review", needs_review)
    
    # Charts
    col1, col2 = st.columns(2)
    
    with col1:
        # Category pie chart
        category_counts = {}
        for email in st.session_state.processed_emails:
            cat = email['classification']['category']
            category_counts[cat] = category_counts.get(cat, 0) + 1
        
        fig = px.pie(
            values=list(category_counts.values()),
            names=list(category_counts.keys()),
            title="📂 Email Categories",
            color_discrete_sequence=px.colors.qualitative.Set3
        )
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        # Priority bar chart
        priority_counts = {'high': 0, 'medium': 0, 'low': 0}
        for email in st.session_state.processed_emails:
            pri = email['classification']['priority']
            priority_counts[pri] = priority_counts.get(pri, 0) + 1
        
        fig = go.Figure(data=[
            go.Bar(
                x=['High', 'Medium', 'Low'],
                y=[priority_counts['high'], priority_counts['medium'], priority_counts['low']],
                marker_color=['#f44336', '#ff9800', '#4caf50']
            )
        ])
        fig.update_layout(title="⚡ Priority Distribution", showlegend=False)
        st.plotly_chart(fig, use_container_width=True)
    
    # Email List
    st.markdown("---")
    st.header("📨 Processed Emails")
    
    # Filter
    filter_option = st.selectbox(
        "Filter by:",
        ["All Emails", "Urgent Only", "High Priority", "Needs Reply", "Spam"]
    )
    
    filtered_emails = st.session_state.processed_emails
    if filter_option == "Urgent Only":
        filtered_emails = [e for e in filtered_emails if e['classification']['category'] == 'urgent']
    elif filter_option == "High Priority":
        filtered_emails = [e for e in filtered_emails if e['classification']['priority'] == 'high']
    elif filter_option == "Needs Reply":
        filtered_emails = [e for e in filtered_emails if e['response'] is not None]
    elif filter_option == "Spam":
        filtered_emails = [e for e in filtered_emails if e['classification']['category'] == 'spam']
    
    st.write(f"Showing {len(filtered_emails)} email(s)")
    
    for idx, email in enumerate(filtered_emails):
        cat = email['classification']['category']
        
        # Icon selection
        if cat == 'urgent':
            icon = '🚨'
        elif cat == 'spam':
            icon = '🗑️'
        elif cat == 'customer_support':
            icon = '🎫'
        else:
            icon = '📧'
        
        with st.expander(f"{icon} {email['subject']}", expanded=(idx == 0)):
            col1, col2 = st.columns([2, 1])
            
            with col1:
                st.markdown(f"**From:** {email['from']}")
                st.markdown(f"**Subject:** {email['subject']}")
                st.markdown("**Body:**")
                st.text(email['body'][:400] + "..." if len(email['body']) > 400 else email['body'])
            
            with col2:
                st.markdown("**Classification:**")
                
                # Category badge
                cat_color = {
                    'urgent': '🔴',
                    'spam': '⚫',
                    'customer_support': '🔵',
                    'general_inquiry': '🟢',
                    'internal': '🟡'
                }
                st.info(f"{cat_color.get(cat, '⚪')} **{cat.upper().replace('_', ' ')}**")
                st.info(f"⚡ **Priority:** {email['classification']['priority'].upper()}")
                st.info(f"😊 **Sentiment:** {email['classification']['sentiment'].upper()}")
                
                if email['classification']['reason']:
                    st.caption(f"💡 {email['classification']['reason']}")
            
            if email['response']:
                st.markdown("---")
                st.markdown("**✍️ Drafted Response:**")
                st.success(email['response'])
                
                # Download button
                st.download_button(
                    label="💾 Download Response",
                    data=email['response'],
                    file_name=f"response_{email['subject'][:30].replace(' ', '_')}.txt",
                    mime="text/plain",
                    key=f"download_{idx}"
                )
            else:
                st.warning("⏭️ No response needed")
    
    # Export Report
    st.markdown("---")
    if st.button("📥 Export Full Report (CSV)", use_container_width=True):
        df_data = []
        for email in st.session_state.processed_emails:
            df_data.append({
                'From': email['from'],
                'Subject': email['subject'],
                'Category': email['classification']['category'],
                'Priority': email['classification']['priority'],
                'Sentiment': email['classification']['sentiment'],
                'Needs Reply': email['classification']['needs_reply'],
                'Has Response': 'Yes' if email['response'] else 'No',
                'Timestamp': email['timestamp'].strftime('%Y-%m-%d %H:%M:%S')
            })
        
        df = pd.DataFrame(df_data)
        csv = df.to_csv(index=False)
        
        st.download_button(
            label="📥 Download CSV",
            data=csv,
            file_name=f"email_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )

else:
    # Welcome screen
    st.info("👈 Enter your email credentials in the sidebar and click 'Connect & Fetch Emails'")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("### 🎯 Features")
        st.markdown("""
        - Auto-classify emails
        - Draft smart responses
        - Priority detection
        - Sentiment analysis
        """)
    
    with col2:
        st.markdown("### 📊 Analytics")
        st.markdown("""
        - Real-time dashboards
        - Category distribution
        - Priority charts
        - Export reports
        """)
    
    with col3:
        st.markdown("### ⚡ Supported")
        st.markdown("""
        - Gmail
        - Outlook/Office 365
        - Custom IMAP servers
        - Secure connections
        """)