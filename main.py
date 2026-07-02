from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
import pdfplumber as pdf
import pandas as pd
import os
import re
import time
import requests
import fitz



#----- CONFIG -----#

DOWNLOAD_DIR = r"C:\linkedin_pdfs" 

PROFILE_PATH = r"C:\selenium\linkedin_profile" 

load_dotenv()

SERPAPI_KEY = os.getenv("SERPAPI_KEY")

if not SERPAPI_KEY:
    raise ValueError(
        "SERPAPI_KEY environment variable not found."
    )

EMAIL_REGEX = r'\b[A-Za-z0-9._%+-]+@(?!example|test|domain)[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b'

PHONE_REGEX = r'(?:\+?91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}'

blacklist = {
    "computer science",
    "b.tech",
    "bachelor",
    "master",
    "engineering",
    "degree",
    "cgpa",
    "grade"
}

company_blacklist = {
    "india",
    "district",
    "computer science",
    "page",
    "present"
}

role_keywords = {
    "developer",
    "engineer",
    "intern",
    "employee",
    "manager",
    "specialist",
    "analyst",
    "consultant",
    "designer",
    "lead",
    "architect",
    "associate"
}



#----- DRIVER SETUP -----#

def init_driver():

    options = Options()

    prefs = {
        "download.default_directory": DOWNLOAD_DIR,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "plugins.always_open_pdf_externally": True
    }

    options.add_experimental_option("prefs", prefs)
    options.add_argument(f"user-data-dir={PROFILE_PATH}") 
    return webdriver.Chrome(options=options)


#==================== LINKEDIN SCRAPING PIPELINE =====================#


#----- LOGIN + USER-QUERY -----#


#---Login_&_Session_Reuse---#

def login(driver):

    if "login" in driver.current_url: 

        print("first run detected -> logging in")

        email = next(
        e for e in driver.find_elements(By.CSS_SELECTOR, 'input[type="email"]')
        if e.is_displayed()
        )

        password = next(
            p for p in driver.find_elements(By.CSS_SELECTOR, 'input[type="password"]')
            if p.is_displayed()
        )

        EmaiL = input("Enter your email: ")
        PassworD = input("Enter the password: ")
        email.send_keys(EmaiL)
        password.send_keys(PassworD)

        buttons = driver.find_elements(By.TAG_NAME, "button")

        for b in buttons:
            if b.text == "Sign in" and b.is_displayed():
                b.click()
                break

        print("logging in..")
        print("if any verification occurs, complete it manually, then press enter")

    else:
        print("Already logged in -> skipping login")


#---Search_Keywords_&_Get_Profiles---#

def search_people(driver, keywords):
    print("\n=== Candidate Search Started ===")
    time.sleep(5)
    search_box = driver.find_element( 
        By.CSS_SELECTOR,
        'input[placeholder="Search"]'
    )

    search_box.clear()
    search_box.send_keys(keywords)
    search_box.send_keys(Keys.ENTER)

    print("\nSearching LinkedIn profiles...")

    time.sleep(5)

    people = driver.find_element(By.XPATH, "//a[normalize-space()='People']")
    people.click()

    time.sleep(5)

    profiles = driver.find_elements(By.CSS_SELECTOR, 'a[href*="/in/"]')

    profile_urls = []
    seen = set()

    for p in profiles:
        try:
            href = p.get_attribute("href")
            if href:
                href = href.split("?")[0].rstrip("/")
                if href not in seen:
                    seen.add(href)
                    profile_urls.append(href)
                    print(f"\nCandidate found: {href}")
        except:
            continue
    return profile_urls


#----- NAVIGATION + SCRAPING -----#


#---Open_Profile---#

def open_profile(driver, profile_url):
    return driver.get(profile_url)


#---Get_Profile_Name---#

def extract_name(driver):
    try:
        time.sleep(5)
        h2s = driver.find_elements(By.TAG_NAME, "h2")
        Name = h2s[1].text.strip() if len(h2s)>1 else "Unknown"
        print("Candidate Name: ", Name)
        return Name
    except:
        return "Unknown"


#---Extract_Profile_Skills---#

def extract_skills(driver, profile_url):

    time.sleep(5)

    skills_url = profile_url.rstrip("/") + "/details/skills/"

    driver.get(skills_url)

    time.sleep(5)

    #click Tools & Technologies button
    tools_tabs = driver.find_elements(
        By.XPATH,
        "//*[contains(text(),'Tools & Technologies')]"
    )

    if tools_tabs:
        driver.execute_script(
            "arguments[0].click();",
            tools_tabs[0]
        )
    else:
        print("No Tools & Technologies section")

    time.sleep(3)

    #Count skill elements
    clean = []

    seen_skills = set()

    container = driver.find_element(By.TAG_NAME, "main")

    def get_skill_count(driver):
        return len(driver.find_elements(
            By.XPATH,
            "//div[starts-with(@componentkey,'com.linkedin.sdui.profile.skill')]"
        ))
        
    #Scroll page to load content
    prev_count = 0

    while True:
        driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight;", container)
        time.sleep(1.5)
        curr_count = get_skill_count(driver)
        if curr_count == prev_count:
            break
        prev_count = curr_count

    time.sleep(5)

    #Extract skills from 'Skills' section
    skills = driver.find_elements(
        By.XPATH,
        "//div[starts-with(@componentkey,'com.linkedin.sdui.profile.skill')]//span"
    )

    for s in skills:
        txt = s.get_attribute("innerText")
        if txt:
            txt = txt.strip()
            if 2 < len(txt) < 40 and txt not in seen_skills:
                seen_skills.add(txt)
                clean.append(txt)

    print("Candidate Skills: ", clean)
    return clean


#---Download_Profile_CV---#

def download_cv(driver):
        
        print("Downloading CV...")

        time.sleep(5)

        more_btn = driver.find_elements(By.CSS_SELECTOR, 'button[aria-label="More"]')[1]
        more_btn.click()

        time.sleep(2)

        driver.find_element(
            By.XPATH,
            "//*[@role='menuitem'][contains(., 'Save to PDF')]"
        ).click()

        print("\nDownloaded CV")


#---Parse_Downloaded_CV---#

def parse_pdf(pdf):
    print("Parsing CV...")
    pdfs = [
        os.path.join(DOWNLOAD_DIR, f)
        for f in os.listdir(DOWNLOAD_DIR)
        if f.endswith(".pdf")
    ]

    if not pdfs:
        print("No PDF found, skipping...")
        return None

    latest_pdf = max(pdfs, key=os.path.getctime)
        
    text = ""

    with pdf.open(latest_pdf) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"

    return text, latest_pdf


#---Extract_Email_&_Phone_From_Parsed_CV---#

def extract_cv_contacts(text, name):

    email_match = re.search(
        r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
        text
    )

    phone_match = re.search(
        r"(?:\+?91[\s-]?)?[6-9]\d{9}",
        text
    )

    cv_email = email_match.group(0) if email_match else None
    cv_phone = phone_match.group(0) if phone_match else None

    print(f"Name: {name}")
    print(f"Email: {cv_email if cv_email else 'Not found'}")
    print(f"Phone: {cv_phone if cv_phone else 'Not found'}")
    return cv_email, cv_phone


#---Extract_College_From_Parsed_CV---#

def extract_college(text, blacklist):

    match = re.search(
        r'Education(.*?)(Skills|Certifications|Projects|Experience|Licenses|$)',
        text,
        re.DOTALL | re.IGNORECASE
    )

    if not match:
        return None

    education_text = match.group(1)

    lines = [
        line.strip()
        for line in education_text.split("\n")
        if line.strip()
    ]

    for line in lines:
        lower = line.lower()
        if any(word in lower for word in blacklist):
            continue
        if len(line) > 3:
            return line
    return None


#---Extract_Companies_From_Parsed_CV---#

def extract_companies(text, company_blacklist, role_keywords):

    companies = []

    match = re.search(
        r'Experience(.*?)(Education|Skills|Certifications|Projects|Licenses|$)',
        text,
        re.DOTALL | re.IGNORECASE
    )

    experience_text = match.group(1) if match else ""

    lines = [
        line.strip()
        for line in experience_text.split("\n")
        if line.strip()
    ]

    date_pattern = re.compile(
        r'((Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|'
        r'January|February|March|April|May|June|July|August|'
        r'September|October|November|December)\s+\d{4})',
        re.I
    )

    #Pattern:Company->Role->Date
    for i, line in enumerate(lines):
        if not (date_pattern.search(line) and i >= 2):
            continue
        company = lines[i - 2].strip().title()
        if any(word in company.lower() for word in company_blacklist):
            continue
        if any(word in company.lower() for word in role_keywords):
            continue
        companies.append(company)

    #Pattern:Company->Role->
    for i in range(len(lines) - 1):
        current = lines[i]
        nxt = lines[i + 1].lower()
        if any(word in nxt for word in role_keywords):
            if not any(word in current.lower() for word in company_blacklist):
                companies.append(current)


    seen_companies = set()

    final_companies = []

    for company in companies:
        key = company.lower().strip()
        if key not in seen_companies:
            seen_companies.add(key)
            final_companies.append(company)
       
    return final_companies

#---Select_Anchor(College/Companies)_For_Advanced_Search_Queries---#
def build_anchor(Name, final_companies=None, college=None):

    if final_companies:
        primary_anchor = final_companies[0]
        source = "company"
    elif college:
        primary_anchor = college
        source = "college"
    else:
        primary_anchor = Name
        source = "name"

    return primary_anchor


#==================== ADVANCED SEARCH PIPELINE =====================#


#----- ADVANCED SEARCH HELPERS -----#

#---Search_API_Starter---#
def google_search(query):
    params = {
        "engine": "google",
        "q": query,
        "api_key": SERPAPI_KEY,
        "num": 10,
        "gl": "in",
        "hl": "en",
    }
    try:
        r = requests.get(
                "https://serpapi.com/search",
                params=params,
                timeout=10
            )
        return r.json()  

    except:
        return {"organic_results": []}

#---Get_Search_Result_Page_Text---#
def fetch_page_text(url):
    try:
        r = requests.get(
            url,
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        return r.text[:5000]
    except:
        return ""

#---Normalize_Result_Page_Text---#
def normalize_text(text):
    text = text.replace("\n", " ")
    text = text.replace("\t", " ")
    return re.sub(r'\s+', ' ', text)      

#---Clean_Normalized_Page_Text---#
def clean_scraped_text(text):
    text = re.sub(r'\b\d{13,}\b', ' ', text)   # remove long IDs
    text = re.sub(r'\b\d{9,12}\b', ' ', text)  # remove DOM numbers
    return re.sub(r'\s+', ' ', text)

#---Search_Queries---#
def queries(Name, search_anchor, final_companies, college):

    queries = [
        f'"{Name}" "{search_anchor}" email',
        f'"{Name}" "{search_anchor}" contact',
        f'"{search_anchor}" "@gmail.com" OR "@outlook.com"',
        f'"{search_anchor}" "+91" phone OR mobile',
        f'site:linkedin.com/in "{Name}"'
    ]

    if final_companies:
        for c in final_companies[:2]:
            queries.append(f'"{Name}" "{c}" email')
            queries.append(f'"{c}" contact email')
        queries.append(f'"{search_anchor}" "{final_companies[0]}" email')

    if search_anchor:
        queries.append(f'"{Name}" "{search_anchor}" email')

    if college:
        queries.append(f'"{Name}" "{college}" email')

    return queries


#----- PERFORM ADVANCED SEARCH -----#

def run_serp(pdf_text, q):

    use_serp = True
    print("Contact details incomplete. Searching web...")
    #---GetResponses---#
    responses = []

    #---ParallelExecution---#
    with ThreadPoolExecutor(max_workers=2) as ex:
        responses = list(ex.map(google_search, q))
    if not responses:
        print("NO SERP RESPONSES → skipping profile")
        return {
            "emails": [],
            "phones": [],
            "combined_text": ""
        }

    #---ExtractRawText---#    
    serp_text = "" 
    
    for data in responses:
        for r in data.get("organic_results", []):
            serp_text += " " + r.get("title", "")
            serp_text += " " + r.get("snippet", "")

            link = r.get("link")
            if link:
                if "linkedin.com" not in link:
                    serp_text += fetch_page_text(link)

    #---Merge+Clean---#
    combined_text = normalize_text(clean_scraped_text(serp_text + " " + pdf_text))

    #---ExtractEmail---#
    emails_found = {
        e.lower().strip()
        for e in re.findall(EMAIL_REGEX, combined_text)
        if is_valid_email(e)
    }

    if emails_found:
        print(f"Email(s) found: {', '.join(emails_found)}")

    #---ExtractPhone---#
    raw_phones = re.findall(PHONE_REGEX, combined_text)

    phones_found = set()

    for p in raw_phones:
        digits = re.sub(r'\D', '', p)

        if len(digits) == 12 and digits.startswith("91"):
            digits = digits[2:]

        if len(digits) == 10:
            phones_found.add(digits)
            print(f"Phone found: {p}")

    print("found ", len(emails_found), " emails and ", len(phones_found), " phone numbers")

    #---ReturnContactInfo---#
    return {
        "emails": list(emails_found),
        "phones": list(phones_found),
        "combined_text": combined_text
    }    



#----- SEARCH RESULTS SCORING -----#

def search_score(emails_raw, phones_raw, name, combined_text):

    best_email = pick_best_email(
        emails_raw,
        name
    )

    best_phone = pick_best_phone(
        phones_raw,
        name,
        combined_text
    )

    print("Selected Email: ", best_email)
    print("Selected Contact Number: ", best_phone)

    return best_email, best_phone

#---Accept_Valid_Emails_From_Found_Emails---#
def is_valid_email(email):
        email = email.lower().strip()

        bad_patterns = [
            "example", "test", "domain", "xxxx", "xxx", "sample"
        ]

        if any(b in email for b in bad_patterns):
            return False

        domain = email.split("@")[-1]

        if len(domain) < 5:
            return False

        return True

#---Get_Best_Email_From_Valid_Emails---#
def pick_best_email(emails, name=None):

    cleaned = []
    seen = set()

    for e in emails:
        e = e.strip().lower()

        # Filter bad emails here
        if e not in seen and is_valid_email(e):
            seen.add(e)
            cleaned.append(e)
    
    if not cleaned:
        return None

    def normalize(s):
        return re.sub(r'[^a-z]', '', s.lower())

    name_norm = normalize(name or "")

    def score(email):
        s = 0
        email = email.lower()

        local_part = email.split("@")[0]
        local_norm = normalize(local_part)

        # name similarity boost
        if name_norm and local_norm:
            if name_norm in local_norm or local_norm in name_norm:
                s += 6

        s += len(set(name_norm) & set(local_norm)) * 0.5

        if "gmail" not in email:
            s += 3

        if email.startswith(("info@", "contact@", "hr@", "support@", "hello@")):
            s -= 2

        if re.search(r"(team|careers|jobs|admin)", local_part):
            s -= 2

        if "xxx" in email or "example" in email:
            s -= 10

        return s

    sorted_emails = sorted(cleaned, key=score, reverse=True)

    return sorted_emails[0] if sorted_emails else None

#---Get_Best_Phone_No._From_Found_No.s---#
def pick_best_phone(phones, name=None, text=""):
    if not phones:
        return None

    def score(phone):
        s = 0

        digits = re.sub(r"\D", "", phone)

        if len(digits) == 10:
            s += 5

        if len(digits) > 12 or len(digits) < 10:
            s -= 5

        if digits.startswith("91") or phone.strip().startswith("+91"):
            s += 4

        if digits and digits[0] in "789":
            s += 3

        if len(set(digits)) <= 3:
            s -= 4

        lower_text = text.lower()
        if "contact" in lower_text:
            s += 1
        if name and name.lower() in lower_text:
            s += 1

        if "+" in phone or "-" in phone:
            s += 1

        return s

    seen_phones = set()
    unique_phones = []
    for p in phones:
        digits = re.sub(r"\D", "", p)
        if digits not in seen_phones:
            seen_phones.add(digits)
            unique_phones.append(p)

    sorted_phones = sorted(unique_phones, key=score, reverse=True)

    return sorted_phones[0] if sorted_phones else None 


#==================== GENERATE NEW CV ====================#


SIDEBAR_COLOR = (
    0.1607999950647354,
    0.24310000240802765,
    0.28630000352859497
)

def generate_pdf(name, pdf_path, email, phone):

    print("Generating updated CV...")

    doc = fitz.open(pdf_path)
    page = doc[0]

    sidebar_spans = []

    existing_emails = set()
    existing_phones = set()

    linkedin_y = None
    linkedin_size = None

    for block in page.get_text("dict")["blocks"]:

        if "lines" not in block:
            continue

        for line in block["lines"]:

            for span in line["spans"]:

                text = span["text"].strip()

                if not text:
                    continue

                x0, y0, x1, y1 = span["bbox"]

                if x0 > 202:
                    continue

                existing_emails.update(
                    e.lower().strip()
                    for e in re.findall(EMAIL_REGEX, text)
                )

                existing_phones.update(
                    re.sub(r"\D", "", p)
                    for p in re.findall(PHONE_REGEX, text)
                )

                sidebar_spans.append({
                    "text": text,
                    "x": x0,
                    "y": y0,
                    "size": span["size"],
                    "color": span["color"]
                })

                if (
                    linkedin_y is None
                    and "linkedin.com" in text.lower()
                ):
                    linkedin_y = y0
                    linkedin_size = span["size"]

    if linkedin_y is None:
        print("LinkedIn URL not found")
        doc.close()
        return None

    email_to_insert = None
    phone_to_insert = None

    if email:

        normalized_email = email.lower().strip()

        if normalized_email not in existing_emails:
            email_to_insert = email
            print(f"Email added: {email}")

    if phone:

        normalized_phone = re.sub(r"\D", "", phone)

        if normalized_phone not in existing_phones:
            phone_to_insert = phone
            print(f"Phone added: {phone}")

    line_height = linkedin_size * 1.35

    extra_lines = 0

    if email_to_insert:
        extra_lines += 1

    if phone_to_insert:
        extra_lines += 1

    extra_space = line_height * extra_lines

    sidebar_rect = fitz.Rect(
        0,
        0,
        202,
        page.rect.height
    )

    page.add_redact_annot(
        sidebar_rect,
        fill=SIDEBAR_COLOR
    )

    page.apply_redactions()

    linkedin_replaced = False

    for span in sidebar_spans:

        text = span["text"]

        x = span["x"]
        y = span["y"]

        if y > linkedin_y:
            y += extra_space

        size = span["size"]

        color_int = span["color"]

        r = ((color_int >> 16) & 255) / 255
        g = ((color_int >> 8) & 255) / 255
        b = (color_int & 255) / 255

        color = (r, g, b)

        if (
            not linkedin_replaced
            and "linkedin.com" in text.lower()
        ):

            current_y = y

            if email_to_insert:

                page.insert_text(
                    (x, current_y),
                    email_to_insert,
                    fontsize=size,
                    color=color
                )

                current_y += line_height

            if phone_to_insert:

                page.insert_text(
                    (x, current_y),
                    phone_to_insert,
                    fontsize=size,
                    color=color
                )

                current_y += line_height

            page.insert_text(
                (x, current_y),
                text,
                fontsize=size,
                color=color
            )

            linkedin_replaced = True
            continue

        page.insert_text(
            (x, y),
            text,
            fontsize=size,
            color=color
        )

    safe_name = re.sub(
        r"[^A-Za-z0-9]",
        "_",
        name
    )

    output_pdf = f"{safe_name}_updated_cv.pdf"

    if os.path.exists(output_pdf):
        os.remove(output_pdf)

    doc.save(output_pdf)
    doc.close()

    print(f"Updated CV saved: {output_pdf}")

    return os.path.abspath(output_pdf)

#==================== PROFILE PROCESSING =====================#


def process_profile(driver, profile_url):

    open_profile(driver=driver, profile_url=profile_url)

    Name = extract_name(driver=driver)

    download_cv(driver=driver)
    
    clean = extract_skills(driver=driver, profile_url=profile_url)    
    
    text, latest_pdf = parse_pdf(pdf=pdf)
    if not text:
        text = ""

    cv_email, cv_phone = extract_cv_contacts(text=text, name=Name)
    
    college = extract_college(text=text, blacklist=blacklist)
     
    final_companies = extract_companies(text=text, company_blacklist=company_blacklist, role_keywords=role_keywords)
    
    search_anchor = build_anchor(Name=Name, final_companies=final_companies, college=college)

    use_serp = (cv_email is None or cv_phone is None)
                
    result = None

    if use_serp:
        q = queries(Name=Name, search_anchor=search_anchor, final_companies=final_companies, college=college)
        search_results = run_serp(pdf_text=text, q=q)
        emails_raw = search_results["emails"]
        phones_raw = search_results["phones"]
        CombinedText = search_results["combined_text"]  
        best_email, best_phone = search_score(emails_raw = emails_raw, phones_raw = phones_raw, name = Name, combined_text = CombinedText)
    else:
        best_email, best_phone = None, None

    profile_data, final_email, final_phone = candidate_data(Name, clean, cv_email, best_email, cv_phone, best_phone, profile_url)

    generate_pdf(name=Name, pdf_path=latest_pdf, email=final_email, phone=final_phone)
    
    return profile_data



def candidate_data(Name, clean, cv_email, best_email, cv_phone, best_phone, profile_url):
    final_email = cv_email or best_email
    final_phone = cv_phone or best_phone

    profile_data = {
        "Name": Name,
        "Skills": ", ".join(clean),
        "Email": final_email,
        "Phone Number": final_phone,
        "LinkedIn ID": profile_url
    }

    return profile_data, final_email, final_phone
    


driver = init_driver()

driver.get("https://www.linkedin.com/feed/")

login(driver)

keywords = input("Enter Skillset: ")

profile_urls = search_people(driver, keywords)

seen_profiles = set()

profiles_data = []

for url in profile_urls:
    if url in seen_profiles:
        continue
    seen_profiles.add(url)
    result = process_profile(
        driver,
        url
    )

    if result:
        profiles_data.append(result)

    df = pd.DataFrame(profiles_data)

    print(df)

    df.to_excel(
        "linkedin_profiles.xlsx",
        index=False
    )

    print("Profile added to Excel")

    total = 5 * 60

    for remaining in range(total, 0, -1):
        mins, secs = divmod(remaining, 60)
        print(
            f"\r Moving to next profile in: {mins:02d}:{secs:02d}",
            end=""
        )
        time.sleep(1)

    print("\nMoving to next profile...")


