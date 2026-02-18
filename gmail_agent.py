from google import genai
from imapclient import IMAPClient
import email
from email import policy
import os
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()
client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

# ============================================
# Gmail IMAP Connection
# ============================================

class GmailAgent:
    def __init__(self, email_address, app_password):
        """Initialize Gmail IMAP connection"""
        print(f"🔌 Connecting to Gmail...")
        
        try:
            self.imap = IMAPClient('imap.gmail.com', use_uid=True, ssl=True)
            self.imap.login(email_address, app_password)
            print(f"✅ Logged in as: {email_address}")
            
            # Select inbox
            self.imap.select_folder('INBOX')
            print("✅ Connected to INBOX")
            
        except Exception as e:
            print(f"❌ Login failed: {e}")
            print("\nTroubleshooting:")
            print("1. Make sure IMAP is enabled in Gmail settings")
            print("2. Use an App Password (not your regular Gmail password)")
            print("3. Enable 2-Step Verification first")
            raise
    
    def get_unread_emails(self, limit=10):
        """Get unread emails from Gmail"""
        print(f"\n📬 Fetching unread emails (limit: {limit})...")
        
        try:
            # Search for unread emails
            messages = self.imap.search(['UNSEEN'])
            
            if not messages:
                print("✅ No unread emails found")
                return []
            
            # Limit results
            messages = messages[:limit]
            
            print(f"✅ Found {len(messages)} unread email(s)")
            
            # Fetch email data
            emails = []
            raw_messages = self.imap.fetch(messages, ['RFC822'])
            
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
                
                email_data = {
                    'id': msg_id,
                    'from': str(email_message['From']),
                    'subject': str(email_message['Subject']) or "(No Subject)",
                    'date': str(email_message['Date']),
                    'body': body[:2000]  # Limit length
                }
                
                emails.append(email_data)
            
            return emails
            
        except Exception as e:
            print(f"❌ Error fetching emails: {e}")
            return []
    
    def close(self):
        """Close connection"""
        try:
            self.imap.logout()
            print("\n👋 Logged out from Gmail")
        except:
            pass

# ============================================
# AI Classification
# ============================================

def classify_email(email_data):
    """Classify email"""
    print(f"\n🤖 Analyzing: {email_data['subject'][:50]}...")
    
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
    
    # Parse
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
            if 'urgent' in line.lower(): 
                classification['category'] = 'urgent'
            elif 'spam' in line.lower() or 'promotional' in line.lower(): 
                classification['category'] = 'spam'
            elif 'customer' in line.lower(): 
                classification['category'] = 'customer_support'
            elif 'internal' in line.lower(): 
                classification['category'] = 'internal'
        elif 'PRIORITY:' in line_upper:
            if 'high' in line.lower(): 
                classification['priority'] = 'high'
            elif 'low' in line.lower(): 
                classification['priority'] = 'low'
        elif 'SENTIMENT:' in line_upper:
            if 'positive' in line.lower(): 
                classification['sentiment'] = 'positive'
            elif 'negative' in line.lower(): 
                classification['sentiment'] = 'negative'
        elif 'NEEDS_REPLY:' in line_upper:
            classification['needs_reply'] = 'yes' if 'yes' in line.lower() else 'no'
        elif 'REASON:' in line_upper:
            classification['reason'] = line.split(':', 1)[1].strip() if ':' in line else ''
    
    return classification

def draft_response(email_data, classification):
    """Draft professional response"""
    if classification['category'] == 'spam' or classification['needs_reply'] == 'no':
        return None
    
    tone = "professional and helpful"
    if classification['priority'] == 'high':
        tone = "immediate and solution-focused"
    elif classification['sentiment'] == 'negative':
        tone = "empathetic and reassuring"
    
    draft_prompt = f"""
Draft a professional email response.

Original Email:
From: {email_data['from']}
Subject: {email_data['subject']}
Body: {email_data['body'][:600]}

Context:
- Category: {classification['category']}
- Priority: {classification['priority']}
- Sentiment: {classification['sentiment']}

Requirements:
- Tone: {tone}
- 2-3 concise paragraphs
- Include greeting and closing
- Professional and clear

Draft the response:
"""
    
    response = client.models.generate_content(
        model="models/gemini-2.5-flash",
        contents=draft_prompt
    )
    
    return response.text

# ============================================
# Main Processing
# ============================================

def process_gmail():
    """Main function to process Gmail"""
    print("="*80)
    print("🤖 GMAIL AUTO-RESPONDER AGENT")
    print("="*80)
    
    # Get credentials
    email_address = os.environ.get("EMAIL_ADDRESS")
    email_password = os.environ.get("EMAIL_PASSWORD")
    
    if not email_address or not email_password:
        print("\n❌ Missing credentials!")
        print("\nAdd to your .env file:")
        print("EMAIL_ADDRESS=your.email@gmail.com")
        print("EMAIL_PASSWORD=your-16-char-app-password")
        print("IMAP_SERVER=imap.gmail.com")
        return
    
    # Connect to Gmail
    agent = GmailAgent(email_address, email_password)
    
    try:
        # Get unread emails
        emails = agent.get_unread_emails(limit=5)
        
        if not emails:
            print("\n✅ No unread emails to process!")
            return
        
        # Create output folder
        os.makedirs('responses', exist_ok=True)
        
        results = []
        
        for idx, email_data in enumerate(emails, 1):
            print(f"\n{'='*80}")
            print(f"📧 EMAIL {idx}/{len(emails)}")
            print(f"{'='*80}")
            print(f"From: {email_data['from']}")
            print(f"Subject: {email_data['subject']}")
            print(f"Preview: {email_data['body'][:100]}...")
            
            # Classify
            classification = classify_email(email_data)
            
            print(f"\n📊 CLASSIFICATION:")
            print(f"   Category: {classification['category'].upper()}")
            print(f"   Priority: {classification['priority'].upper()}")
            print(f"   Sentiment: {classification['sentiment'].upper()}")
            print(f"   Needs Reply: {classification['needs_reply'].upper()}")
            if classification['reason']:
                print(f"   Reason: {classification['reason']}")
            
            # Draft response
            response_text = None
            if classification['needs_reply'] == 'yes' and classification['category'] != 'spam':
                print(f"\n✍️  DRAFTING RESPONSE...")
                response_text = draft_response(email_data, classification)
                
                print(f"\n{'─'*80}")
                print(response_text)
                print(f"{'─'*80}")
                
                needs_review = classification['priority'] == 'high' or classification['category'] == 'urgent'
                print(f"\n🚦 Needs Human Review: {'YES ⚠️' if needs_review else 'NO ✅'}")
            else:
                print(f"\n⏭️  No response needed")
            
            # Save result
            result = {
                'from': email_data['from'],
                'subject': email_data['subject'],
                'classification': classification,
                'response': response_text
            }
            results.append(result)
            
            # Save to file
            if response_text:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"responses/gmail_{timestamp}_{idx}.txt"
                
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(f"TO: {email_data['from']}\n")
                    f.write(f"RE: {email_data['subject']}\n")
                    f.write(f"CLASSIFICATION: {classification['category']}\n")
                    f.write(f"PRIORITY: {classification['priority']}\n")
                    f.write(f"SENTIMENT: {classification['sentiment']}\n")
                    f.write(f"{'='*80}\n\n")
                    f.write(response_text)
                
                print(f"\n💾 Saved to: {filename}")
        
        # Summary report
        print(f"\n{'='*80}")
        print("📊 PROCESSING SUMMARY")
        print(f"{'='*80}")
        print(f"Total Processed: {len(results)}")
        print(f"Responses Drafted: {sum(1 for r in results if r['response'])}")
        
        categories = {}
        priorities = {}
        sentiments = {}
        
        for r in results:
            cat = r['classification']['category']
            pri = r['classification']['priority']
            sent = r['classification']['sentiment']
            
            categories[cat] = categories.get(cat, 0) + 1
            priorities[pri] = priorities.get(pri, 0) + 1
            sentiments[sent] = sentiments.get(sent, 0) + 1
        
        print(f"\n📂 By Category:")
        for cat, count in sorted(categories.items()):
            print(f"   {cat:<20} {count}")
        
        print(f"\n⚡ By Priority:")
        for pri in ['high', 'medium', 'low']:
            if pri in priorities:
                print(f"   {pri:<20} {priorities[pri]}")
        
        print(f"\n😊 By Sentiment:")
        for sent in ['positive', 'neutral', 'negative']:
            if sent in sentiments:
                print(f"   {sent:<20} {sentiments[sent]}")
        
        print("\n✅ PROCESSING COMPLETE!")
        
    finally:
        agent.close()

if __name__ == "__main__":
    try:
        process_gmail()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()