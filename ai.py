import streamlit as st
import pandas as pd
import requests
import re
from io import BytesIO
from urllib.parse import urlparse
from datetime import datetime
import json

from langchain_groq import ChatGroq
from langchain_core.prompts import PromptTemplate

# ------------------ PAGE CONFIG ------------------
st.set_page_config(
    page_title="AI B2B Lead Generator Pro",
    page_icon="🚀",
    layout="wide"
)

# ------------------ CONSTANTS ------------------
EMAIL_REGEX = r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"
PHONE_REGEX = r"\+?\d[\d\s\-]{7,15}"

FREE_EMAIL_DOMAINS = [
    "gmail.com", "yahoo.com", "outlook.com",
    "hotmail.com", "aol.com", "icloud.com"
]

BLOCKED_DOMAINS = [
    "yelp", "clutch", "justdial",
    "indiamart", "yellowpages", "facebook.com",
    "instagram.com", "twitter.com"
]

# ------------------ SIDEBAR CONFIGURATION ------------------
with st.sidebar:
    st.title("⚙️ Configuration")
    
    st.subheader("🔑 API Keys")
    serpapi_key = st.text_input("SerpAPI Key", type="password")
    groq_api_key = st.text_input("Groq API Key", type="password")
    hunter_api_key = st.text_input("Hunter.io API Key (Optional)", type="password", help="For email verification")

    
    st.subheader("📊 Lead Settings")
    max_leads = st.slider("Max Leads to Generate", 5, 50, 20)
    min_score = st.slider("Minimum Lead Score", 1, 10, 5, help="Only export leads above this score")
    search_pages = st.slider("Search Depth (Pages)", 1, 5, 3)
    
    st.subheader("🚫 Domain Exclusions")
    exclude_domains = st.text_area(
        "Exclude Domains (one per line)",
        placeholder="example.com\ncompetitor.com",
        help="Enter domains to exclude from lead generation, one per line"
    )
    
    st.subheader("📅 Meeting Link")
    meeting_link = st.text_input(
        "Your Meeting Link",
        "https://calendly.com/your-name/meeting"
    )
    
    st.subheader("💾 Export Options")
    export_format = st.selectbox(
        "Export Formats",
        ["Excel", "CSV", "JSON"]
    )

# ------------------ MAIN UI ------------------
st.title("🚀 AI B2B Lead Generator Pro")
st.markdown("### AI-powered lead generation with advanced scoring & multi-channel outreach")

if not serpapi_key or not groq_api_key:
    st.warning("⚠️ Please enter required API keys in the sidebar")
    st.stop()

# ------------------ LLM SETUP ------------------
llm = ChatGroq(
    groq_api_key=groq_api_key,
    model_name="llama-3.3-70b-versatile",
    temperature=0.2
)

# ------------------ HELPER FUNCTIONS ------------------

def get_domain(url):
    try:
        return urlparse(url).netloc.replace("www.", "")
    except:
        return ""

def is_company_email(email, website):
    domain = get_domain(website)
    email_domain = email.split("@")[-1].lower()
    if email_domain in FREE_EMAIL_DOMAINS:
        return False
    return domain and domain in email_domain

def is_valid_phone(phone):
    digits = re.sub(r"\D", "", phone)
    return 10 <= len(digits) <= 15

def verify_email_hunter(email):
    if not hunter_api_key:
        return "Not Verified", 0
    try:
        url = f"https://api.hunter.io/v2/email-verifier"
        params = {"email": email, "api_key": hunter_api_key}
        res = requests.get(url, params=params, timeout=5)
        data = res.json()
        if data.get("data"):
            status = data["data"].get("status", "unknown")
            score = data["data"].get("score", 0)
            return status, score
    except:
        pass
    return "Not Verified", 0

def extract_company_size(text):
    size_indicators = {
        "enterprise": ["fortune 500", "global", "worldwide", "international"],
        "medium": ["team of", "employees", "staff members"],
        "small": ["family owned", "local", "boutique"]
    }
    text_lower = text.lower()
    employee_match = re.search(r"(\d+)\+?\s*employees", text_lower)
    if employee_match:
        count = int(employee_match.group(1))
        if count > 500:
            return "Enterprise (500+)"
        elif count > 50:
            return "Medium (50-500)"
        else:
            return "Small (1-50)"
    for size, keywords in size_indicators.items():
        if any(kw in text_lower for kw in keywords):
            return size.capitalize()
    return "Unknown"

def detect_technologies(text):
    tech_stack = []
    technologies = {
        "WordPress": ["wp-content", "wordpress"],
        "Shopify": ["shopify", "myshopify"],
        "React": ["react", "reactjs"],
        "Angular": ["angular", "angularjs"],
        "Salesforce": ["salesforce"],
        "HubSpot": ["hubspot"],
        "Google Analytics": ["google-analytics", "gtag"],
        "Mailchimp": ["mailchimp"],
        "Stripe": ["stripe"],
        "PayPal": ["paypal"]
    }
    text_lower = text.lower()
    for tech, keywords in technologies.items():
        if any(kw in text_lower for kw in keywords):
            tech_stack.append(tech)
    return ", ".join(tech_stack) if tech_stack else "None detected"

def check_buying_signals(company, location):
    signals = []
    try:
        url = "https://serpapi.com/search.json"
        params = {
            "engine": "google",
            "q": f'"{company}" hiring OR funding OR expansion',
            "api_key": serpapi_key,
            "num": 5
        }
        res = requests.get(url, params=params, timeout=8)
        data = res.json()
        for result in data.get("organic_results", []):
            snippet = result.get("snippet", "").lower()
            title = result.get("title", "").lower()
            if "hiring" in snippet or "hiring" in title:
                signals.append("Currently Hiring")
            if "funding" in snippet or "funding" in title:
                signals.append("Recently Funded")
            if "expansion" in snippet or "expansion" in title:
                signals.append("Expanding")
    except:
        pass
    return ", ".join(signals) if signals else "None"

def get_social_presence(company):
    social = {"LinkedIn": "", "Twitter": "", "Facebook": ""}
    try:
        url = "https://serpapi.com/search.json"
        params = {
            "engine": "google",
            "q": f'"{company}" site:linkedin.com OR site:twitter.com OR site:facebook.com',
            "api_key": serpapi_key,
            "num": 5
        }
        res = requests.get(url, params=params, timeout=8)
        data = res.json()
        for result in data.get("organic_results", []):
            link = result.get("link", "")
            if "linkedin.com/company" in link and not social["LinkedIn"]:
                social["LinkedIn"] = link
            elif "twitter.com" in link and not social["Twitter"]:
                social["Twitter"] = link
            elif "facebook.com" in link and not social["Facebook"]:
                social["Facebook"] = link
    except:
        pass
    return social

def search_businesses(industry, location, pages=3):
    url = "https://serpapi.com/search.json"
    all_results = []
    for page in range(pages):
        params = {
            "engine": "google",
            "q": f"{industry} in {location}",
            "api_key": serpapi_key,
            "num": 10,
            "start": page * 10
        }
        res = requests.get(url, params=params, timeout=10)
        data = res.json()
        all_results.extend(data.get("organic_results", []))
    return all_results

def scrape_website(url):
    try:
        res = requests.get(url, timeout=8, headers={'User-Agent': 'Mozilla/5.0'})
        soup = BeautifulSoup(res.text, "html.parser")
        text = soup.get_text(separator=" ")
        emails = list(set(re.findall(EMAIL_REGEX, text)))
        phones = list(set(re.findall(PHONE_REGEX, text)))
        company_size = extract_company_size(text)
        tech_stack = detect_technologies(text)
        return emails, phones, text, company_size, tech_stack
    except:
        return [], [], "", "Unknown", "None"

def get_linkedin_info(company, location):
    url = "https://serpapi.com/search.json"
    params = {
        "engine": "google",
        "q": f'"{company}" {location} LinkedIn',
        "api_key": serpapi_key,
        "num": 5
    }
    res = requests.get(url, params=params, timeout=10)
    data = res.json()
    linkedin = ""
    founder = ""
    for r in data.get("organic_results", []):
        link = r.get("link", "")
        title = r.get("title", "")
        if "linkedin.com/company" in link:
            linkedin = link
        if any(k in title.lower() for k in ["founder", "ceo", "co-founder", "owner"]):
            founder = title
    return linkedin, founder

def score_lead_enhanced(company_info, industry, buying_signals):
    prompt = PromptTemplate(
        input_variables=["company_info", "industry", "buying_signals"],
        template="""
Analyze this B2B lead and provide a detailed assessment.

Company Info:
{company_info}

Industry: {industry}
Buying Signals: {buying_signals}

Provide your analysis in this exact format:

Lead Quality: [Hot/Warm/Cold]
Lead Score: [1-10]
Pain Point: [One specific pain point]
Best Contact Time: [Suggested day and time]
Personalization Hook: [One unique fact about the company to use in outreach]
"""
    )
    return llm.invoke(
        prompt.format(
            company_info=company_info, 
            industry=industry,
            buying_signals=buying_signals
        )
    ).content

def generate_email_variations(company, pain_point, meeting_link):
    prompt = PromptTemplate(
        input_variables=["company", "pain_point", "meeting_link"],
        template="""
Write 2 different cold email variations for A/B testing.

Company: {company}
Pain Point: {pain_point}
CTA: {meeting_link}

Format:
EMAIL A:
[Subject line]
[Body under 120 words]

EMAIL B:
[Different subject line]
[Different body under 120 words]
"""
    )
    return llm.invoke(
        prompt.format(
            company=company,
            pain_point=pain_point,
            meeting_link=meeting_link
        )
    ).content

def generate_follow_up_sequence(company, pain_point):
    prompt = PromptTemplate(
        input_variables=["company", "pain_point"],
        template="""
Create a 3-email follow-up sequence.

Company: {company}
Pain Point: {pain_point}

Format:
FOLLOW-UP 1 (Day 3):
[Subject]
[Body - 80 words max]

FOLLOW-UP 2 (Day 7):
[Subject]
[Body - 80 words max]

FOLLOW-UP 3 (Day 14):
[Subject]
[Body - 80 words max]
"""
    )
    return llm.invoke(
        prompt.format(company=company, pain_point=pain_point)
    ).content

def generate_multichannel_outreach(company, pain_point, meeting_link):
    prompt = PromptTemplate(
        input_variables=["company", "pain_point", "meeting_link"],
        template="""
Create outreach messages for multiple channels.

Company: {company}
Pain Point: {pain_point}

Generate:
1. WhatsApp Message (50 words)
2. SMS Message (25 words)
3. LinkedIn Message (80 words)

Meeting Link: {meeting_link}
"""
    )
    return llm.invoke(
        prompt.format(
            company=company,
            pain_point=pain_point,
            meeting_link=meeting_link
        )
    ).content

# ------------------ SEARCH INPUTS ------------------
col1, col2 = st.columns(2)
with col1:
    industry = st.text_input("🏭 Industry", "Real Estate Agents")
with col2:
    location = st.text_input("📍 Location", "New York")

# ------------------ GENERATE LEADS (Enhanced) ------------------
if st.button("🔍 Generate Enhanced Leads", type="primary", use_container_width=True):
    leads = []
    seen_domains = set()
    
    excluded = set()
    if exclude_domains:
        excluded = set(line.strip().lower() for line in exclude_domains.split("\n") if line.strip())
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    with st.spinner("🔍 Searching for businesses..."):
        results = search_businesses(industry, location, pages=search_pages)
        total_results = len(results)
    
    for idx, r in enumerate(results):
        if len(leads) >= max_leads:
            break
        
        progress = (idx + 1) / total_results
        progress_bar.progress(progress)
        status_text.text(f"Processing {idx + 1}/{total_results} - Found {len(leads)} qualified leads")
        
        company = r.get("title", "")
        website = r.get("link", "")
        domain = get_domain(website)
        
        if not domain or domain in seen_domains:
            continue
        if any(b in website.lower() for b in BLOCKED_DOMAINS):
            continue
        if domain in excluded:
            continue
        
        seen_domains.add(domain)
        
        emails, phones, page_text, company_size, tech_stack = scrape_website(website)
        valid_email = next((e for e in emails if is_company_email(e, website)), "")
        valid_phone = next((p for p in phones if is_valid_phone(p)), "")
        if not valid_email and not valid_phone:
            continue
        
        email_status = "Not Verified"
        email_score = 0
        if valid_email and hunter_api_key:
            email_status, email_score = verify_email_hunter(valid_email)
        
        linkedin, founder = get_linkedin_info(company, location)
        buying_signals = check_buying_signals(company, location)
        social = get_social_presence(company)
        
        company_info = f"""
Company: {company}
Website: {website}
Email: {valid_email} (Status: {email_status})
Phone: {valid_phone}
Size: {company_size}
Tech Stack: {tech_stack}
LinkedIn: {linkedin}
Key Contact: {founder}
Buying Signals: {buying_signals}
"""
        analysis = score_lead_enhanced(company_info, industry, buying_signals)
        score_match = re.search(r"Lead Score:\s*(\d+)", analysis)
        ai_score = int(score_match.group(1)) if score_match else 5
        
        hybrid_score = 0
        if valid_email: hybrid_score += 2
        if valid_phone: hybrid_score += 2
        if buying_signals != "None": hybrid_score += 2
        if linkedin: hybrid_score += 1
        hybrid_score += min(ai_score, 3)
        lead_score = min(hybrid_score, 10)
        
        if lead_score < min_score:
            continue
        
        email_variations = generate_email_variations(company, analysis, meeting_link)
        follow_ups = generate_follow_up_sequence(company, analysis)
        multichannel = generate_multichannel_outreach(company, analysis, meeting_link)
        
        leads.append({
            "Company": company,
            "Website": website,
            "Email": valid_email,
            "Email Status": email_status,
            "Email Score": email_score,
            "Phone": valid_phone,
            "Company Size": company_size,
            "Technology Stack": tech_stack,
            "LinkedIn": linkedin or social["LinkedIn"],
            "Twitter": social["Twitter"],
            "Facebook": social["Facebook"],
            "Key Contact": founder,
            "Buying Signals": buying_signals,
            "Lead Score": lead_score,
            "Lead Analysis": analysis,
            "Email Variations (A/B)": email_variations,
            "Follow-up Sequence": follow_ups,
            "Multi-channel Outreach": multichannel,
            "Meeting Link": meeting_link,
            "Generated Date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
    
    progress_bar.progress(1.0)
    status_text.text(f"✅ Complete! Generated {len(leads)} qualified leads")
    
    if not leads:
        st.warning("⚠️ No qualified leads found. Try adjusting your filters or search criteria.")
        st.stop()
    
    df = pd.DataFrame(leads)
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Leads", len(leads))
    with col2:
        avg_score = df["Lead Score"].mean()
        st.metric("Avg Lead Score", f"{avg_score:.1f}/10")
    with col3:
        verified_count = df[df["Email Status"] == "valid"].shape[0]
        st.metric("Verified Emails", verified_count)
    with col4:
        with_signals = df[df["Buying Signals"] != "None"].shape[0]
        st.metric("With Buying Signals", with_signals)
    
    st.success("✅ Lead Generation Complete!")
    st.dataframe(df, use_container_width=True, height=400)

    # ------------------ EXPORT ------------------
    st.subheader("📥 Download Leads")
    col1, col2, col3 = st.columns(3)
    
    if "Excel" in export_format:
        with col1:
            buffer = BytesIO()
            with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
                df.to_excel(writer, index=False, sheet_name="Leads")
            st.download_button(
                "📊 Download Excel",
                buffer.getvalue(),
                f"b2b_leads_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
    
    if "CSV" in export_format:
        with col2:
            csv = df.to_csv(index=False)
            st.download_button(
                "📄 Download CSV",
                csv,
                f"b2b_leads_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                "text/csv",
                use_container_width=True
            )
    
    if "JSON" in export_format:
        with col3:
            json_data = df.to_json(orient="records", indent=2)
            st.download_button(
                "🗂️ Download JSON",
                json_data,
                f"b2b_leads_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                "application/json",
                use_container_width=True
            )

# ------------------ FOOTER ------------------
st.markdown("---")
st.markdown("💡 **Tips**: Use specific industry keywords, enable Hunter.io for email verification, adjust minimum score to filter leads")
