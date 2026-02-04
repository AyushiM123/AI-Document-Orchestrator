import streamlit as st
import pdfplumber
import json
import requests
from google import genai

# --- Page config ---
st.set_page_config(page_title="AI Document Orchestrator")
st.title("AI-Powered Document Orchestrator")

# --- Load API key for Gemini ---
api_key = st.secrets["GEMINI_API_KEY"]
client = genai.Client(api_key=api_key)

# --- File uploader & question input ---
uploaded_file = st.file_uploader("Upload a PDF or TXT document", type=["pdf", "txt"])
user_question = st.text_input("Ask a question about the document")

# --- Function to extract text ---
def extract_text(file):
    if file.type == "application/pdf":
        text = ""
        with pdfplumber.open(file) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        return text
    else:
        return file.read().decode("utf-8")

# --- Function to call Gemini API ---
def call_gemini(document_text, question):
    prompt = f"""
You are an intelligent document analysis agent.

Document:
{document_text}

User Question:
{question}

Task:
Extract 5–8 key-value pairs relevant to the question.
Return ONLY valid JSON.
No explanation. No markdown.
"""
    response = client.models.generate_content(
        model="models/gemini-2.0-flash",
        contents=prompt
    )

    # Clean raw text
    raw_text = response.text.strip()
    if raw_text.startswith("```"):
        raw_text = raw_text.strip("`")
        if raw_text.startswith("json"):
            raw_text = raw_text[4:].strip()

    try:
        return json.loads(raw_text)
    except Exception:
        return {
            "error": "Invalid JSON returned",
            "raw_response": raw_text
        }

# --- Step 1: Extract text & call Gemini ---
extracted_data = None
show_email_section = False  # flag to control email input

if uploaded_file and user_question:
    text = extract_text(uploaded_file)
    extracted_data = call_gemini(text, user_question)

    st.subheader("Structured Data Extracted")
    st.json(extracted_data)

    if isinstance(extracted_data, dict) and "error" not in extracted_data:
        show_email_section = True
    else:
        st.error("Cannot send email: extracted data is invalid or contains errors.")

# --- Step 2: Email input & send button ---
if show_email_section:
    recipient_email = st.text_input("Recipient Email ID")
    send_email = st.button("Send Alert Mail")

    if send_email:
        recipient_email_str = str(recipient_email).strip()
        question_str = str(user_question).strip()
        # --- Flatten extracted_data to a readable string for n8n ---
        extracted_info_str = ""
        if isinstance(extracted_data, dict):
            for key, value in extracted_data.items():
                extracted_info_str += f"{key}: {value}\n"
        else:
            extracted_info_str = str(extracted_data)

        # --- Prepare payload ---
        payload = {
            "document_text": text,
            "extracted_info": extracted_info_str,  # flattened string
            "question": question_str,
            "recipient_email": recipient_email_str
        }

        # --- Debug: show payload before sending ---
        st.write("DEBUG: Payload sent to n8n:", payload)

        if st.secrets.get("N8N_WEBHOOK_URL"):
            try:
                response = requests.post(st.secrets["N8N_WEBHOOK_URL"], json=payload)
                st.write("DEBUG: Raw n8n response:", response.text)

                # Try parsing JSON, fallback if fails
                try:
                    result = response.json()
                except Exception:
                    result = {
                        "final_answer": "Email sent (could not parse JSON)",
                        "email_body": payload["extracted_info"],
                        "status": "SENT"
                    }

            except Exception as e:
                result = {
                    "final_answer": "Failed to call n8n webhook",
                    "email_body": "",
                    "status": f"FAILED ({str(e)})"
                }

            # --- Display results ---
            st.subheader("Final Analytical Answer")
            st.write(result.get("final_answer", "No answer returned"))
            st.subheader("Generated Email Body")
            st.write(result.get("email_body", "No email generated"))
            st.subheader("Email Automation Status")
            st.success(result.get("status", "Webhook called"))

        else:
            st.warning("n8n Webhook URL not configured yet!")
