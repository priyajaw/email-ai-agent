from google import genai
from google.genai import types
import os
from dotenv import load_dotenv
from datetime import datetime
import shutil

load_dotenv()
client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

# ============================================
# Read Email from File
# ============================================

def read_email(filepath: str) -> dict:
    """Read an email file and extract details"""
    print(f"   📧 Reading email: {filepath}")
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Simple parsing
    lines = content.split('\n')
    email_data = {
        'from': '',
        'subject': '',
        'date': '',
        'body': ''
    }
    
    body_started = False
    body_lines = []
    
    for line in lines:
        if line.startswith('From:'):
            email_data['from'] = line.replace('From:', '').strip()
        elif line.startswith('Subject:'):
            email_data['subject'] = line.replace('Subject:', '').strip()
        elif line.startswith('Date:'):
            email_data['date'] = line.replace('Date:', '').strip()
        elif line.strip() == '' and not body_started:
            body_started = True
        elif body_started:
            body_lines.append(line)
    
    email_data['body'] = '\n'.join(body_lines).strip()
    email_data['full_content'] = content
    
    return email_data

# ============================================
# Save Response
# ============================================

def save_response(filename: str, classification: str, response: str, needs_review: bool):
    """Save the drafted response to a file"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"responses/{timestamp}_{filename}"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(f"CLASSIFICATION: {classification}\n")
        f.write(f"NEEDS HUMAN REVIEW: {'YES' if needs_review else 'NO'}\n")
        f.write(f"{'='*60}\n\n")
        f.write(response)
    
    print(f"   💾 Response saved to: {output_file}")
    return output_file

# ============================================
# Main Agent Logic
# ============================================

def process_email(email_file: str):
    """Process a single email file"""
    print(f"\n{'='*70}")
    print(f"📨 PROCESSING: {email_file}")
    print(f"{'='*70}")
    
    # Read the email
    email_data = read_email(email_file)
    
    print(f"\n📧 Email Details:")
    print(f"   From: {email_data['from']}")
    print(f"   Subject: {email_data['subject']}")
    print(f"   Preview: {email_data['body'][:100]}...")
    
    # STEP 1: Classify the email
    print(f"\n🤖 STEP 1: Classifying email...")
    
    classification_prompt = f"""
Analyze this email and classify it into ONE category. Respond with ONLY the category name.

Email:
From: {email_data['from']}
Subject: {email_data['subject']}
Body: {email_data['body']}

Categories:
- urgent: Payment issues, system down, angry customers, needs immediate action
- spam: Promotional emails, scams, suspicious content
- customer_support: Customer questions, feature requests, help needed
- general_inquiry: General questions, information requests
- internal: Emails from colleagues or internal team

Respond with ONLY ONE WORD from the categories above.
"""
    
    response = client.models.generate_content(
        model="models/gemini-2.5-flash",
        contents=classification_prompt
    )
    
    # Get classification
    classification_text = response.text.strip().lower()
    
    # Parse classification
    if "urgent" in classification_text:
        classification = "urgent"
    elif "spam" in classification_text:
        classification = "spam"
    elif "customer" in classification_text or "support" in classification_text:
        classification = "customer_support"
    elif "internal" in classification_text:
        classification = "internal"
    else:
        classification = "general_inquiry"
    
    print(f"\n📊 Classification: {classification.upper()}")
    
    # STEP 2: Draft response
    print(f"\n🤖 STEP 2: Drafting response...")
    
    if classification == "spam":
        print(f"   🗑️  SPAM detected - No response needed")
        response_text = "[NO RESPONSE - MARKED AS SPAM]"
        needs_review = False
    else:
        # Create response guidelines based on classification
        if classification == "urgent":
            guidelines = """
- Acknowledge the urgency immediately
- Apologize for the inconvenience
- Provide immediate next steps
- Give a specific timeline (e.g., "within 1 hour")
- Escalate if needed
"""
        elif classification == "customer_support":
            guidelines = """
- Be empathetic and understanding
- Acknowledge their issue
- Provide clear solution or next steps
- Offer additional help if needed
"""
        else:
            guidelines = """
- Be friendly and professional
- Provide helpful information
- Offer to answer additional questions
"""
        
        draft_prompt = f"""
Draft a professional email response for this email.

Original Email:
From: {email_data['from']}
Subject: {email_data['subject']}
Body: {email_data['body']}

Type: {classification}

Guidelines:{guidelines}

Requirements:
- Professional and helpful tone
- 2-3 short paragraphs maximum
- Direct and clear
- Just the email body (no subject line, no "Dear X" greeting if not natural)

Draft the response:
"""
        
        response = client.models.generate_content(
            model="models/gemini-2.5-flash",
            contents=draft_prompt
        )
        
        response_text = response.text
        
        # Determine if needs human review
        needs_review = classification in ["urgent", "customer_support"]
        
        print(f"\n✉️  Drafted Response:")
        print(f"{'='*70}")
        print(response_text)
        print(f"{'='*70}")
        print(f"\n   🚦 Needs Human Review: {'YES ⚠️' if needs_review else 'NO ✅'}")
    
    # STEP 3: Save the response
    print(f"\n🤖 STEP 3: Saving response...")
    filename = os.path.basename(email_file)
    save_response(filename, classification, response_text, needs_review)
    
    # STEP 4: Move processed email
    processed_path = os.path.join("emails/processed", filename)
    shutil.move(email_file, processed_path)
    print(f"   📦 Moved to: {processed_path}")
    
    return {
        'classification': classification,
        'needs_review': needs_review,
        'response': response_text
    }

# ============================================
# Batch Processor
# ============================================

def process_all_emails():
    """Process all emails in the incoming folder"""
    print("🤖 EMAIL AUTO-RESPONDER AGENT")
    print("="*70)
    
    incoming_dir = "emails/incoming"
    email_files = [f for f in os.listdir(incoming_dir) if f.endswith('.txt')]
    
    if not email_files:
        print("\n📭 No emails to process!")
        return
    
    print(f"\n📬 Found {len(email_files)} email(s) to process\n")
    
    results = []
    for email_file in email_files:
        filepath = os.path.join(incoming_dir, email_file)
        result = process_email(filepath)
        results.append(result)
    
    # Summary
    print(f"\n{'='*70}")
    print(f"📊 PROCESSING SUMMARY")
    print(f"{'='*70}")
    print(f"Total Processed: {len(results)}")
    print(f"Urgent: {sum(1 for r in results if r['classification'] == 'urgent')}")
    print(f"Spam: {sum(1 for r in results if r['classification'] == 'spam')}")
    print(f"Customer Support: {sum(1 for r in results if r['classification'] == 'customer_support')}")
    print(f"Needs Human Review: {sum(1 for r in results if r['needs_review'])}")
    print(f"\n✅ All responses saved to 'responses/' folder")
    print(f"✅ Processed emails moved to 'emails/processed/' folder")

# ============================================
# RUN THE AGENT
# ============================================

if __name__ == "__main__":
    process_all_emails()