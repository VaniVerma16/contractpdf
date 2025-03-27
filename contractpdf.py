from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, validator
from typing import Literal, Optional
import openai
import os
from fpdf import FPDF
import re
from dotenv import load_dotenv
load_dotenv()
from openai import OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ====== FastAPI Setup ======
app = FastAPI()

class ContractRequest(BaseModel):
    contract_type: Literal[
        "nda", "contractor", "sla", "partnership",
        "sales", "employment", "lease", "mou", "noncompete"
    ]
    party_a: str
    party_b: str
    duration: str
    clause_query: str
    property_address: Optional[str] = None  # for lease
    position: Optional[str] = None          # for employment
    goods_description: Optional[str] = None # for sales
    scope: Optional[str] = None             # for noncompete
    jurisdiction: str = "New Delhi"

    @validator('party_a', 'party_b')
    def validate_party_names(cls, v):
        if not v or len(v) < 2:
            raise ValueError("Party names must be valid and at least 2 characters long")
        return v

    @validator('duration')
    def validate_duration(cls, v):
        if not re.match(r'^\d+\s+(year|years|month|months|day|days)$', v):
            raise ValueError("Duration must be in format '# year/years/month/months/day/days'")
        return v

# ====== Clause Retrieval and Refinement ======
def retrieve_clause(query: str, contract_type: str) -> str:
    specialized_clause_banks = {
        "nda": [
            "All confidential information shall remain the exclusive property of the disclosing party and shall not be used for any purpose other than the intended business collaboration.",
            "Breach of confidentiality shall result in liquidated damages of INR 10,00,000 and potential legal action under Information Technology Act, 2000.",
            "Confidentiality obligations persist for five years post-termination of agreement."
        ],
        "employment": [
            "The employee agrees to abide by the company's code of conduct and intellectual property guidelines as per Indian labor laws.",
            "Termination may occur with notice as specified in Industrial Disputes Act, 1947.",
            "Dispute resolution through mandatory arbitration under Arbitration and Conciliation Act, 1996."
        ],
        "noncompete": [
            "The restricted period shall not exceed two years and shall be limited to the metropolitan areas where the employer conducts primary business.",
            "Compensation shall be provided to the employee during the non-compete period as per legal standards.",
            "The non-compete clause is subject to judicial review of reasonableness."
        ]
    }
    default_clauses = [
        "This Agreement shall be governed by the laws of India and subject to the jurisdiction of courts in New Delhi.",
        "All disputes shall be resolved through arbitration under the Arbitration and Conciliation Act, 1996.",
        "Each party shall bear its own legal costs unless otherwise specified by law."
    ]
    clauses = specialized_clause_banks.get(contract_type, default_clauses)
    return clauses[0]

def refine_clause_with_legal_expertise(clause: str, contract_type: str) -> str:
    LEGAL_PROMPTS = {
        "nda": {
            "context": "Indian Contract Act 1872 + IT Act 2000 amendments",
            "requirements": [
                "Define 'Confidential Information' per Indian judicial precedents",
                "Include mandatory arbitration clause per Arbitration Act 1996",
                "Specify territorial jurisdiction (e.g., Delhi High Court)",
                "Explicitly exclude publicly available information",
                "Include return/destruction obligations post-termination"
            ],
            "examples": [
                "As per XYZ vs. ABC (2022), confidential information shall include...",
                "Breach penalties not exceeding ₹5,00,000 as per Section 73"
            ]
        },
        "contractor": {
            "context": "Indian Contract Act + Service Tax/GST provisions",
            "requirements": [
                "Clear distinction from employment relationship",
                "IP ownership transfer clauses per Copyright Act 1957",
                "Termination for convenience with notice period",
                "Liability caps as per Indian standards",
                "GST invoicing and TDS compliance"
            ],
            "examples": [
                "Contractor shall be responsible for their own GST compliance as per Section 22 of CGST Act",
                "IP developed shall vest with client per Section 17 of Copyright Act"
            ]
        },
        "sla": {
            "context": "Consumer Protection Act 2019 + IT Act",
            "requirements": [
                "Quantifiable service metrics (e.g., 99.5% uptime)",
                "Penalties for non-performance as liquidated damages",
                "Force majeure clause covering Indian scenarios",
                "Dispute resolution through Delhi arbitration",
                "Exclusions for third-party failures"
            ],
            "examples": [
                "Service credits of 0.1% of monthly fee per 1% downtime below SLA",
                "As per Amazon Web Services India vs. ACIT (2021)"
            ]
        },
        "partnership": {
            "context": "Indian Partnership Act 1932 + GST provisions",
            "requirements": [
                "Profit-sharing ratio with tax implications",
                "Admission/retirement of partners procedure",
                "Dissolution conditions as per Section 39",
                "Bank account operation authority",
                "Non-compete during partnership"
            ],
            "examples": [
                "Profits shall be shared 60:40 after accounting for interest on capital per Section 13(b)",
                "Retiring partner liable for acts until public notice under Section 32"
            ]
        },
        "sales": {
            "context": "Sale of Goods Act 1930 + GST laws",
            "requirements": [
                "Clear passing of property/title clauses",
                "Incoterms adapted for Indian logistics",
                "GST invoicing and HSN code details",
                "Inspection period (minimum 7 days)",
                "Remedies for defective goods"
            ],
            "examples": [
                "Risk passes to buyer upon delivery at registered GST location",
                "Defects must be reported within 15 days as per Section 55"
            ]
        },
        "employment": {
            "context": "New Labor Codes 2023 + Industrial Disputes Act",
            "requirements": [
                "Comply with 48-hour work week limits",
                "Include PF/ESI/gratuity obligations",
                "Termination notice period as per state laws",
                "Non-solicitation restrictions",
                "IP assignment clause"
            ],
            "examples": [
                "Notice period of 90 days as per Maharashtra Shops Act",
                "Gratuity payable after 5 years continuous service under Payment of Gratuity Act"
            ]
        },
        "lease": {
            "context": "Transfer of Property Act 1882 + RERA",
            "requirements": [
                "RERA registration number if applicable",
                "Maintenance charges breakdown",
                "Lock-in period and renewal terms",
                "Municipal tax liability",
                "Eviction procedure per state laws"
            ],
            "examples": [
                "Lessee shall pay property tax within 15 days of receipt of bill",
                "Security deposit not exceeding 3 months rent as per Delhi Rent Act"
            ]
        },
        "mou": {
            "context": "Indian Contract Act + Specific Relief Act",
            "requirements": [
                "Clear 'binding/non-binding' designation",
                "Confidentiality obligations",
                "Governing law clause",
                "Termination notice period",
                "No third-party rights"
            ],
            "examples": [
                "This MoU is not legally enforceable except for clauses 3-5",
                "Subject to exclusive jurisdiction of Bangalore courts"
            ]
        },
        "noncompete": {
            "context": "Indian Contract Act Section 27 + recent judgments",
            "requirements": [
                "Geographic restriction (max: district level)",
                "Time limit (max: 24 months)",
                "Consideration for restriction",
                "Industry-specific limitations",
                "Garden leave clause if applicable"
            ],
            "examples": [
                "Non-compete limited to Pune Municipal Corporation area",
                "Valid for 12 months with 50% salary continuation"
            ]
        }
    }
    
    prompt = f"""As a Supreme Court of India registered contract lawyer, refine this {contract_type} clause:

**Original Clause**: {clause}

**Legal Framework**: {LEGAL_PROMPTS[contract_type]['context']}

**Must Include**:
{"".join(f"✓ {req}" for req in LEGAL_PROMPTS[contract_type]['requirements'])}

**Good Examples**:
{"".join(f"• {ex}" for ex in LEGAL_PROMPTS[contract_type]['examples'])}

**Refinement Rules**:
1. Use active voice with "Shall" for obligations
2. Reference specific Indian statutes
3. Include enforcement mechanism
4. Maximum 3 sentences
5. Use Rs. for penalties

Refined Clause:"""
    
    response = client.chat.completions.create(
        model="gpt-3.5-turbo-16k",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        max_tokens=300
    )
    return response.choices[0].message.content.strip()

# ====== Template Generator ======
def get_legal_template(data: ContractRequest, clause: str) -> str:
    A, B, D = data.party_a, data.party_b, data.duration
    J = data.jurisdiction
    T = data.contract_type

    legal_templates = {
        "nda": f"""NON-DISCLOSURE AGREEMENT\n\nThis Non-Disclosure Agreement is made between {A} and {B}.\n\n1. Term: {D}\n2. Confidentiality: All information exchanged shall be kept confidential.\n3. Legal Clause: {clause}\n4. Jurisdiction: Governed by the laws of India, jurisdiction in {J}.\n\nSigned: {A}, {B}""",

        "contractor": f"""INDEPENDENT CONTRACTOR AGREEMENT\n\nThis agreement is made between {A} and {B}.\n\n1. Duration: {D}\n2. Role: Independent Contractor\n3. Legal Clause: {clause}\n4. Jurisdiction: {J}\n\nSigned: {A}, {B}""",

        "sla": f"""SERVICE LEVEL AGREEMENT\n\nThis agreement is between {A} and {B}.\n\n1. Term: {D}\n2. Services: As per annexure\n3. Legal Clause: {clause}\n4. Jurisdiction: {J}\n\nSigned: {A}, {B}""",

        "partnership": f"""PARTNERSHIP AGREEMENT\n\nThis partnership is entered between {A} and {B}.\n\n1. Term: {D}\n2. Terms: Equal stake and responsibility\n3. Legal Clause: {clause}\n4. Jurisdiction: {J}\n\nSigned: {A}, {B}""",

        "sales": f"""SALES AGREEMENT\n\nThis agreement is made between {A} (Seller) and {B} (Buyer).\n\n1. Duration: {D}\n2. Goods/Services: {data.goods_description}\n3. Legal Clause: {clause}\n4. Jurisdiction: {J}\n\nSigned: {A}, {B}""",

        "employment": f"""EMPLOYMENT AGREEMENT\n\nThis employment agreement is made between {A} and {B}.\n\n1. Position: {data.position}\n2. Duration: {D}\n3. Legal Clause: {clause}\n4. Jurisdiction: {J}\n\nSigned: {A}, {B}""",

        "lease": f"""LEASE AGREEMENT\n\nThis agreement is made between {A} (Lessor) and {B} (Lessee).\n\n1. Property: {data.property_address}\n2. Duration: {D}\n3. Legal Clause: {clause}\n4. Jurisdiction: {J}\n\nSigned: {A}, {B}""",

        "mou": f"""MEMORANDUM OF UNDERSTANDING\n\nThis MoU is entered into by {A} and {B}.\n\n1. Term: {D}\n2. Understanding: As per mutual discussion\n3. Legal Clause: {clause}\n4. Jurisdiction: {J}\n\nSigned: {A}, {B}""",

        "noncompete": f"""NON-COMPETE AGREEMENT\n\nThis agreement is between {A} and {B}.\n\n1. Duration: {D}\n2. Scope: {data.scope}\n3. Legal Clause: {clause}\n4. Jurisdiction: {J}\n\nSigned: {A}, {B}"""
    }

    return legal_templates.get(T, "Invalid contract type.")

# ====== PDF Export ======
def save_as_pdf(content: str, filename: str = "generated_contract.pdf"):
    content = (content.replace("’", "'")
                  .replace("“", '"')
                  .replace("”", '"')
                  .replace("₹", "Rs."))
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Arial", size=11)
    pdf.set_text_color(0, 0, 0)
    pdf.set_fill_color(240, 240, 240)
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, "LEGAL CONTRACT DOCUMENT", 0, 1, 'C')
    pdf.ln(10)
    pdf.set_font("Arial", size=11)
    for line in content.split("\n"):
        pdf.multi_cell(0, 8, line)
    pdf.output(filename)


# ====== API Endpoint ======
import uuid
import requests
import os

@app.post("/generate")
def generate_contract(data: ContractRequest):
    try:
        raw_clause = retrieve_clause(data.clause_query, data.contract_type)
        refined_clause = refine_clause_with_legal_expertise(raw_clause, data.contract_type)
        contract_text = get_legal_template(data, refined_clause)

        # Generate and save PDF with a unique filename
        filename = f"{uuid.uuid4().hex}.pdf"
        save_as_pdf(contract_text, filename)

        # Upload to GoFile
        with open(filename, "rb") as f:
            upload_res = requests.post("https://store1.gofile.io/uploadFile", files={"file": f})

        if upload_res.status_code != 200:
            raise Exception(f"Upload failed: {upload_res.status_code}")

        res_json = upload_res.json()
        if res_json.get("status") != "ok":
            raise Exception(f"Gofile error: {res_json}")

        # Extract the public download page link
        file_url = res_json["data"]["downloadPage"]

        return {
            "message": "Contract generated and uploaded.",
            "contract": contract_text,
            "pdf_url": file_url
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Contract generation failed: {str(e)}")
