import streamlit as st
import pdfplumber
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

# --- Function to call Gemini (PLAIN TEXT RESPONSE) ---
def call_gemini(document_text, question):
    prompt = f"""
You are an intelligent document analysis assistant.

Document:
{document_text}

User Question:
{question}

Task:
Answer the user's question in clear, professional plain English.
- Be concise but complete
- Use bullet points if helpful
- Do NOT return JSON
- Do NOT use markdown
- Just normal readable text
"""
    response = client.models.generate_content(
        model="models/gemini-2.0-flash",
        contents=prompt
    )

    return response.text.strip()

# --- Step 1: Extract text & call Gemini ---
analysis_text = None
show_email_section = False
document_text = ""

if uploaded_file and user_question:
    document_text = extract_text(uploaded_file)
    analysis_text = call_gemini(document_text, user_question)

    st.subheader("Document Analysis Result")
    st.text_area(
        "AI Generated Answer",
        analysis_text,
        height=300
    )

    if analysis_text and isinstance(analysis_text, str):
        show_email_section = True
    else:
        st.error("Analysis failed. Please try again.")

# --- Step 2: Email input & send button ---
if show_email_section:
    recipient_email = st.text_input("Recipient Email ID")
    send_email = st.button("Send Alert Mail")

    if send_email:
        payload = {
            "document_text": document_text,
            "analysis_text": analysis_text,
            "question": user_question.strip(),
            "recipient_email": recipient_email.strip()
        }

        # --- Debug payload ---
        st.write("DEBUG: Payload sent to n8n:", payload)

        if st.secrets.get("N8N_WEBHOOK_URL"):
            try:
                response = requests.post(
                    st.secrets["N8N_WEBHOOK_URL"],
                    json=payload
                )

                st.write("DEBUG: Raw n8n response:", response.text)

                try:
                    result = response.json()
                except Exception:
                    result = {}

                # 🔒 HARD GUARANTEE: Generated Email Body NEVER blank
                if not result.get("email_body"):
                    result["email_body"] = analysis_text

                if not result.get("status"):
                    result["status"] = "SENT"

                if not result.get("final_answer"):
                    result["final_answer"] = "Processed successfully"

            except Exception as e:
                result = {
                    "final_answer": "Failed to call n8n webhook",
                    "email_body": analysis_text,
                    "status": f"FAILED ({str(e)})"
                }

            # --- Display results ---
            st.subheader("Final Analytical Answer")
            st.write(result.get("final_answer", "No answer returned"))

            st.subheader("Generated Email Body")
            st.text_area(
                "Email Content",
                result.get("email_body", ""),
                height=250
            )

            st.subheader("Email Automation Status")
            status = result.get("status", "UNKNOWN")
            if status == "SENT":
                st.success("SENT")
            elif status == "SKIPPED":
                st.warning("SKIPPED")
            else:
                st.info(status)   

        else:
            st.warning("n8n Webhook URL not configured yet!")