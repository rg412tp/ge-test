from fastapi import FastAPI, APIRouter, UploadFile, File, HTTPException, Response
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timezone
import base64
import io
import fitz  # PyMuPDF
from PIL import Image
import asyncio
import json as json_lib
from google import genai
from google.genai import types

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')
# Also load production env if exists
prod_env = ROOT_DIR / '.env.production'
if prod_env.exists():
    load_dotenv(prod_env, override=True)

# MongoDB connection
mongo_url = os.environ.get('MONGO_URL')
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ.get('DB_NAME', 'ge_question_bank')]

# Gemini API Key (used ONLY for topic/difficulty classification)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_MODEL = "gemini-2.5-flash"

# Mathpix API (used for PDF text/LaTeX/image extraction)
MATHPIX_APP_ID = os.environ.get("MATHPIX_APP_ID", "")
MATHPIX_APP_KEY = os.environ.get("MATHPIX_APP_KEY", "")

# Local file storage
UPLOAD_DIR = ROOT_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
(UPLOAD_DIR / "pdfs").mkdir(exist_ok=True)
(UPLOAD_DIR / "images").mkdir(exist_ok=True)
(UPLOAD_DIR / "mark-schemes").mkdir(exist_ok=True)

# Object Storage (Emergent - only used in dev environment, optional)
STORAGE_URL = "https://integrations.emergentagent.com/objstore/api/v1/storage"
EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY")
APP_NAME = "gcse-question-bank"
storage_key = None
USE_LOCAL_STORAGE = not EMERGENT_KEY or EMERGENT_KEY.strip() == ""

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create the main app
app = FastAPI(title="GCSE Question Bank API")

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# ============ File Storage Functions ============
def init_storage():
    """Initialize object storage - only for Emergent dev environment"""
    global storage_key
    if USE_LOCAL_STORAGE:
        logger.info("Using local file storage")
        return None
    if storage_key:
        return storage_key
    try:
        import requests
        resp = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": EMERGENT_KEY}, timeout=30)
        resp.raise_for_status()
        storage_key = resp.json()["storage_key"]
        logger.info("Emergent object storage initialized")
        return storage_key
    except Exception as e:
        logger.warning(f"Emergent storage not available, using local: {e}")
        return None

def put_object(path: str, data: bytes, content_type: str) -> dict:
    """Upload file - local or cloud"""
    if USE_LOCAL_STORAGE:
        local_path = UPLOAD_DIR / path
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(data)
        return {"path": str(local_path)}
    import requests
    key = init_storage()
    if not key:
        # Fallback to local
        local_path = UPLOAD_DIR / path
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(data)
        return {"path": str(local_path)}
    resp = requests.put(
        f"{STORAGE_URL}/objects/{path}",
        headers={"X-Storage-Key": key, "Content-Type": content_type},
        data=data, timeout=120
    )
    resp.raise_for_status()
    return resp.json()

def get_object(path: str) -> tuple:
    """Download file - local or cloud"""
    # Try local first
    local_path = UPLOAD_DIR / path
    if local_path.exists():
        content_type = "image/png" if path.endswith(".png") else "application/pdf"
        return local_path.read_bytes(), content_type
    # Try cloud
    if not USE_LOCAL_STORAGE:
        import requests
        key = init_storage()
        if key:
            resp = requests.get(
                f"{STORAGE_URL}/objects/{path}",
                headers={"X-Storage-Key": key}, timeout=60
            )
            resp.raise_for_status()
            return resp.content, resp.headers.get("Content-Type", "application/octet-stream")
    raise FileNotFoundError(f"File not found: {path}")

# ============ Pydantic Models ============
class PaperCreate(BaseModel):
    board: str = "AQA"  # AQA, Edexcel, OCR
    qualification: str = "GCSE"
    subject: str = "Mathematics"
    paper_number: str = "1"
    tier: str = "Higher"  # Foundation, Higher
    session: str = "June"
    exam_year: int = 2024

class Paper(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    board: str
    qualification: str
    subject: str
    paper_number: str
    tier: str
    session: str
    exam_year: int
    status: str = "processing"  # processing, extracted, reviewed
    pdf_path: Optional[str] = None
    total_questions: int = 0
    ge_code: Optional[str] = None  # e.g., GE-2017-P1
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class QuestionPart(BaseModel):
    part_label: str  # a, b, c, etc.
    text: str
    latex: Optional[str] = None
    marks: Optional[int] = None
    images: List[str] = []  # List of image asset IDs
    confidence: float = 0.0
    mark_scheme: Optional[str] = None  # Mark scheme for this part
    mark_scheme_latex: Optional[str] = None
    ge_id: Optional[str] = None  # e.g., GE-2017-P1-Q01A

class Question(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    paper_id: str
    question_number: int
    text: str
    latex: Optional[str] = None
    parts: List[QuestionPart] = []
    marks: Optional[int] = None
    images: List[str] = []  # List of image asset IDs
    has_diagram: bool = False
    has_table: bool = False
    status: str = "draft"  # draft, needs_review, approved
    confidence: float = 0.0
    review_reason_codes: List[str] = []
    # New fields for difficulty and topics
    difficulty: Optional[str] = None  # bronze, silver, gold
    topics: List[str] = []  # e.g., ["algebra", "quadratics", "factorisation"]
    mark_scheme: Optional[str] = None  # Overall mark scheme text
    mark_scheme_latex: Optional[str] = None
    mark_scheme_id: Optional[str] = None  # Link to mark scheme document
    ge_id: Optional[str] = None  # e.g., GE-2017-P1-Q01 (parent)
    parent_ge_id: Optional[str] = None  # Parent GE ID for hierarchy
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

# Mark Scheme Models
class MarkSchemeCreate(BaseModel):
    paper_id: str

class MarkScheme(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    paper_id: str
    pdf_path: Optional[str] = None
    status: str = "pending"  # pending, processing, extracted, linked
    total_entries: int = 0
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class MarkSchemeEntry(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    mark_scheme_id: str
    paper_id: str
    question_number: int
    part_label: Optional[str] = None
    marks: int = 0
    method_marks: int = 0  # M marks
    accuracy_marks: int = 0  # A marks
    b_marks: int = 0  # B marks
    text: str = ""
    latex: Optional[str] = None
    acceptable_alternatives: List[str] = []
    follow_through_notes: Optional[str] = None
    reasoning_notes: Optional[str] = None
    linked_question_id: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

# Topic/Tag Model
class Topic(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    category: str  # e.g., "Number", "Algebra", "Geometry", "Statistics"
    description: Optional[str] = None

# Predefined topics for GCSE Maths
GCSE_TOPICS = [
    {"name": "number-operations", "category": "Number", "description": "Basic operations, BIDMAS"},
    {"name": "fractions", "category": "Number", "description": "Fractions, decimals, percentages"},
    {"name": "ratio-proportion", "category": "Number", "description": "Ratio and proportion"},
    {"name": "percentages", "category": "Number", "description": "Percentage calculations"},
    {"name": "indices", "category": "Number", "description": "Powers and roots"},
    {"name": "standard-form", "category": "Number", "description": "Standard form notation"},
    {"name": "surds", "category": "Number", "description": "Surd manipulation"},
    {"name": "algebraic-expressions", "category": "Algebra", "description": "Simplifying expressions"},
    {"name": "linear-equations", "category": "Algebra", "description": "Solving linear equations"},
    {"name": "quadratics", "category": "Algebra", "description": "Quadratic equations and graphs"},
    {"name": "factorisation", "category": "Algebra", "description": "Factorising expressions"},
    {"name": "simultaneous-equations", "category": "Algebra", "description": "Solving simultaneous equations"},
    {"name": "inequalities", "category": "Algebra", "description": "Linear and quadratic inequalities"},
    {"name": "sequences", "category": "Algebra", "description": "Arithmetic and geometric sequences"},
    {"name": "functions", "category": "Algebra", "description": "Function notation and graphs"},
    {"name": "angles", "category": "Geometry", "description": "Angle properties"},
    {"name": "triangles", "category": "Geometry", "description": "Triangle properties and congruence"},
    {"name": "circles", "category": "Geometry", "description": "Circle theorems"},
    {"name": "area-perimeter", "category": "Geometry", "description": "Area and perimeter calculations"},
    {"name": "volume-surface-area", "category": "Geometry", "description": "3D shapes"},
    {"name": "trigonometry", "category": "Geometry", "description": "Sin, cos, tan"},
    {"name": "pythagoras", "category": "Geometry", "description": "Pythagoras theorem"},
    {"name": "transformations", "category": "Geometry", "description": "Translations, rotations, reflections"},
    {"name": "vectors", "category": "Geometry", "description": "Vector operations"},
    {"name": "coordinates", "category": "Geometry", "description": "Coordinate geometry"},
    {"name": "probability", "category": "Statistics", "description": "Probability calculations"},
    {"name": "data-handling", "category": "Statistics", "description": "Collecting and representing data"},
    {"name": "averages", "category": "Statistics", "description": "Mean, median, mode, range"},
    {"name": "cumulative-frequency", "category": "Statistics", "description": "Cumulative frequency and box plots"},
    {"name": "histograms", "category": "Statistics", "description": "Histogram interpretation"},
]

class ImageAsset(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    paper_id: str
    question_id: Optional[str] = None
    storage_path: str
    original_filename: str
    content_type: str
    width: int
    height: int
    page_number: int
    crop_coords: Optional[Dict[str, int]] = None  # x, y, width, height
    description: Optional[str] = None
    is_deleted: bool = False
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class ExtractionJob(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    paper_id: str
    status: str = "pending"  # pending, processing, completed, failed
    total_pages: int = 0
    processed_pages: int = 0
    questions_found: int = 0
    images_extracted: int = 0
    error_message: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    api_calls: int = 0  # Track number of AI calls
    mathpix_output: Optional[str] = None  # Cache Mathpix markdown to avoid re-extracting on Gemini retry
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

# ============ Cost Tracking ============
async def log_api_call(paper_id: str, call_type: str, model: str = GEMINI_MODEL):
    """Log every AI API call for cost monitoring"""
    doc = {
        "id": str(uuid.uuid4()),
        "paper_id": paper_id,
        "call_type": call_type,  # "question_extraction", "diagram_detection", "crop_refinement", "mark_scheme"
        "model": model,
        "provider": "gemini",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    await db.api_call_logs.insert_one(doc)

# ============ AI Extraction Functions ============
def _init_gemini_client():
    """Initialize Google Gemini client"""
    return genai.Client(api_key=GEMINI_API_KEY)

def _parse_json_response(response_text: str) -> dict:
    """Parse JSON from AI response, handling LaTeX escapes robustly"""
    text = response_text.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    
    # Try direct parse
    try:
        return json_lib.loads(text)
    except json_lib.JSONDecodeError:
        pass
    
    # Fix: replace problematic LaTeX escapes inside JSON strings
    # Strategy: find all string values and fix backslashes inside them
    import re
    
    def fix_json_string(match):
        """Fix backslashes inside a JSON string value"""
        s = match.group(0)
        # Already valid JSON escapes: \", \\, \/, \b, \f, \n, \r, \t, \uXXXX
        # Everything else needs double-escaping
        inner = s[1:-1]  # Remove quotes
        fixed = ""
        i = 0
        while i < len(inner):
            if inner[i] == '\\' and i + 1 < len(inner):
                next_char = inner[i + 1]
                if next_char in '"\\bfnrtu/':
                    fixed += inner[i:i+2]
                    i += 2
                else:
                    fixed += '\\\\' + next_char
                    i += 2
            else:
                fixed += inner[i]
                i += 1
        return '"' + fixed + '"'
    
    # Match JSON string values (between quotes, handling escaped quotes)
    fixed = re.sub(r'"(?:[^"\\]|\\.)*"', fix_json_string, text)
    
    try:
        return json_lib.loads(fixed)
    except json_lib.JSONDecodeError as e:
        logger.error(f"JSON parse failed even after fixes: {e}")
        # Last resort: extract just the questions array
        match = re.search(r'"questions"\s*:\s*\[', fixed)
        if match:
            try:
                # Try wrapping in object
                return json_lib.loads('{"questions": []}')
            except:
                pass
        return {"questions": []}

async def _call_gemini_vision(system_prompt: str, user_prompt: str, image_base64: str) -> str:
    """Call Gemini with an image and return text response"""
    client = _init_gemini_client()
    image_bytes = base64.b64decode(image_base64)
    
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=[
            types.Content(
                role="user",
                parts=[
                    types.Part.from_text(text=system_prompt + "\n\n" + user_prompt),
                    types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
                ],
            )
        ],
    )
    return response.text

# ============ Mathpix Extraction (handles EVERYTHING) ============
import requests as http_requests
import re
import time

def mathpix_submit_pdf(pdf_content: bytes) -> str:
    """Submit PDF to Mathpix - extracts text, LaTeX, tables, AND images in one call"""
    headers = {"app_id": MATHPIX_APP_ID, "app_key": MATHPIX_APP_KEY}
    resp = http_requests.post(
        "https://api.mathpix.com/v3/pdf",
        headers=headers,
        files={"file": ("paper.pdf", pdf_content, "application/pdf")},
        data={
            "options_json": json_lib.dumps({
                "conversion_formats": {"md": True},
                "math_inline_delimiters": ["\\(", "\\)"],
                "math_display_delimiters": ["\\[", "\\]"],
                "enable_tables_fallback": True,
                "include_line_data": True,
                "include_diagram_text": True,
            })
        },
        timeout=60
    )
    resp.raise_for_status()
    return resp.json()["pdf_id"]

def mathpix_poll_status(pdf_id: str, max_wait: int = 300) -> bool:
    """Wait for Mathpix to finish processing"""
    headers = {"app_id": MATHPIX_APP_ID, "app_key": MATHPIX_APP_KEY}
    for _ in range(max_wait // 3):
        resp = http_requests.get(f"https://api.mathpix.com/v3/pdf/{pdf_id}", headers=headers, timeout=30)
        data = resp.json()
        status = data.get("status", "")
        if status == "completed":
            return True
        if status == "error":
            raise Exception(f"Mathpix error: {data}")
        time.sleep(3)
    raise Exception("Mathpix timeout")

def mathpix_get_mmd(pdf_id: str) -> str:
    """Get Mathpix Markdown (text + LaTeX + image URLs + tables)"""
    headers = {"app_id": MATHPIX_APP_ID, "app_key": MATHPIX_APP_KEY}
    resp = http_requests.get(f"https://api.mathpix.com/v3/pdf/{pdf_id}.mmd", headers=headers, timeout=60)
    resp.raise_for_status()
    return resp.text

def mathpix_get_lines(pdf_id: str) -> dict:
    """Get structured line data with diagram image URLs"""
    headers = {"app_id": MATHPIX_APP_ID, "app_key": MATHPIX_APP_KEY}
    resp = http_requests.get(f"https://api.mathpix.com/v3/pdf/{pdf_id}.lines.json", headers=headers, timeout=60)
    resp.raise_for_status()
    return resp.json()

def download_image(url: str) -> bytes:
    """Download image from Mathpix CDN"""
    resp = http_requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.content

def parse_mathpix_mmd(mmd_content: str) -> list:
    """Parse Mathpix Markdown into structured questions with images"""
    questions = []
    lines = mmd_content.split('\n')
    
    current_q = None
    current_part = None
    current_text = []
    current_images = []
    
    # Question: "1 ", "**1**", "1.", "1)" at line start
    q_pattern = re.compile(r'^(?:\*\*)?(\d{1,2})(?:\*\*)?\s*[.)\s]')
    # Part: "(a)", "**(a)**"
    part_pattern = re.compile(r'^(?:\*\*)?\(([a-z])\)(?:\*\*)?\s*')
    # Image: ![...](url)
    img_pattern = re.compile(r'!\[([^\]]*)\]\(([^)]+)\)')
    # Marks: [2 marks], (2 marks), [2], (Total for Question ... marks)
    marks_pattern = re.compile(r'\((\d+)\s*marks?\)', re.IGNORECASE)
    
    def save_current():
        nonlocal current_q, current_part, current_text, current_images
        text = '\n'.join(current_text).strip()
        if not text and not current_images:
            current_text = []
            current_images = []
            return
            
        if current_q is not None and current_q > 0:
            # Find or create question
            existing = next((q for q in questions if q["question_number"] == current_q), None)
            if not existing:
                existing = {
                    "question_number": current_q, "text": "", "latex": "",
                    "parts": [], "has_diagram": False, "has_table": False,
                    "marks": None, "image_urls": []
                }
                questions.append(existing)
            
            # Extract marks
            m = marks_pattern.search(text)
            marks = int(m.group(1)) if m else None
            
            if current_part:
                existing["parts"].append({
                    "part_label": current_part,
                    "text": clean_text(text),
                    "latex": text,
                    "marks": marks,
                    "image_urls": current_images.copy()
                })
            else:
                existing["text"] = clean_text(text)
                existing["latex"] = text
                if marks:
                    existing["marks"] = marks
            
            if current_images:
                existing["has_diagram"] = True
                existing["image_urls"].extend(current_images)
            
            if '|' in text and text.count('|') > 3:
                existing["has_table"] = True
        
        current_text = []
        current_images = []
    
    for line in lines:
        # Check for images first (and extract URLs without adding the markdown to text)
        img_match = img_pattern.search(line)
        if img_match:
            current_images.append(img_match.group(2))
            # Remove the image markdown from the line, keep any text before/after
            line_without_img = img_pattern.sub('', line).strip()
            if line_without_img and current_q is not None:
                current_text.append(line_without_img)
            continue

        # Check for question number
        stripped = line.strip()
        q_match = q_pattern.match(stripped)
        if q_match and not stripped.startswith('('):
            save_current()
            current_q = int(q_match.group(1))
            current_part = None
            rest = stripped[q_match.end():].strip()
            current_text = [rest] if rest else []
            continue

        # Check for part
        part_match = part_pattern.match(stripped)
        if part_match and current_q:
            save_current()
            current_part = part_match.group(1)
            rest = stripped[part_match.end():].strip()
            current_text = [rest] if rest else []
            continue

        # Regular line - add if we're in a question
        if current_q is not None and stripped:
            current_text.append(line)
    
    save_current()
    return questions

def clean_text(text: str) -> str:
    """Clean LaTeX for readable display - removes image URLs, font commands, tables, etc."""
    t = text

    # Remove image URLs (both markdown and plain CDN URLs)
    t = re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', '', t)  # Remove markdown images
    t = re.sub(r'https?://[^\s)]+\.(?:jpg|jpeg|png|gif|webp)', '', t)  # Remove image URLs

    # Remove LaTeX tables entirely (convert to simple text representation)
    # Handles \begin{tabular}...\end{tabular} blocks
    t = re.sub(r'\\begin\{tabular\}[^\}]*\}', '', t)  # Remove tabular begin
    t = re.sub(r'\\end\{tabular\}', '', t)  # Remove tabular end
    t = re.sub(r'\\hline', '', t)  # Remove horizontal lines
    t = re.sub(r'&', '|', t)  # Convert column separators to pipes for readability

    # Remove strikethrough formatting (~~text~~)
    t = re.sub(r'~~([^~]*)~~', r'\1', t)

    # Remove extra backslashes (multiple consecutive backslashes)
    t = re.sub(r'\\{2,}', ' ', t)  # Double/triple backslashes to single space

    # Remove LaTeX math delimiters
    t = re.sub(r'\\\(|\\\)', '', t)
    t = re.sub(r'\\\[|\\\]', '', t)

    # Handle special LaTeX commands with arguments
    t = re.sub(r'\\oldsymbol\{([^}]*)\}', r'\1', t)  # \oldsymbol{t} -> t
    t = re.sub(r'\\text\{([^}]*)\}', r'\1', t)
    t = re.sub(r'\\mathrm\{([^}]*)\}', r'\1', t)  # \mathrm{m} -> m
    t = re.sub(r'\\mathbf\{([^}]*)\}', r'\1', t)  # \mathbf{text} -> text
    t = re.sub(r'\\mathit\{([^}]*)\}', r'\1', t)  # \mathit{text} -> text
    t = re.sub(r'\\rm\s+([^\s\\}]+)', r'\1', t)  # \rm text -> text
    t = re.sub(r'\\bf\s+([^\s\\}]+)', r'\1', t)  # Bold: \bf text -> text
    t = re.sub(r'\\it\s+([^\s\\}]+)', r'\1', t)  # Italic: \it text -> text

    # Handle fractions and roots (including inline variations)
    t = re.sub(r'\\frac\s*\{\s*([^}]*)\s*\}\s*\{\s*([^}]*)\s*\}', r'\1/\2', t)
    t = re.sub(r'\\sqrt\s*\{\s*([^}]*)\s*\}', r'√(\1)', t)

    # Spacing and structural commands
    t = re.sub(r'\\(quad|qquad|,|;|!)\s*', ' ', t)
    t = re.sub(r'\\ldots', '...', t)  # Ellipsis
    t = re.sub(r'\\\\\s*', ' ', t)  # Line breaks in tables

    # Math relations and comparison operators
    t = re.sub(r'\\leq|\\leqslant', '≤', t)
    t = re.sub(r'\\geq|\\geqslant', '≥', t)
    t = re.sub(r'\\neq', '≠', t)
    t = re.sub(r'\\approx', '≈', t)
    t = re.sub(r'\\propto', '∝', t)

    # Math symbols and operators
    t = re.sub(r'\\times', '×', t)
    t = re.sub(r'\\div', '÷', t)
    t = re.sub(r'\\pm', '±', t)
    t = re.sub(r'\\mp', '∓', t)
    t = re.sub(r'\\pi', 'π', t)
    t = re.sub(r'\\alpha', 'α', t)
    t = re.sub(r'\\beta', 'β', t)
    t = re.sub(r'\\gamma', 'γ', t)
    t = re.sub(r'\\theta', 'θ', t)
    t = re.sub(r'\\lambda', 'λ', t)
    t = re.sub(r'\\mu', 'μ', t)
    t = re.sub(r'\\sigma', 'σ', t)
    t = re.sub(r'\\infty', '∞', t)
    t = re.sub(r'\\leftarrow', '←', t)
    t = re.sub(r'\\rightarrow', '→', t)
    t = re.sub(r'\\Rightarrow', '⇒', t)

    # Superscripts and subscripts - preserve the content
    t = re.sub(r'\^\s*\{\s*([^}]*)\s*\}', r'^\1', t)
    t = re.sub(r'_\s*\{\s*([^}]*)\s*\}', r'_\1', t)

    # Remove any remaining LaTeX commands (but keep the content if wrapped in braces)
    # This handles \cmd{text} -> text pattern
    t = re.sub(r'\\([a-zA-Z]+)\s*\{\s*([^}]*)\s*\}', r'\2', t)

    # Remove remaining bare LaTeX commands
    t = re.sub(r'\\[a-zA-Z]+\s*', '', t)

    # Remove any remaining braces and brackets that aren't part of content
    t = re.sub(r'[\{\}]', '', t)

    # Clean up whitespace
    t = re.sub(r'\n{3,}', '\n\n', t)  # Max 2 consecutive newlines
    t = re.sub(r'[ \t]{2,}', ' ', t)  # Single space between words
    t = re.sub(r'\s*\|\s*', ' | ', t)  # Clean up table column separators

    return t.strip()

async def classify_and_structure_with_gemini(mmd_content: str, paper_id: str) -> list:
    """ONE Gemini call: takes Mathpix markdown and returns structured questions with classification. Retries on 503."""
    client = _init_gemini_client()
    # Truncate if too long (Gemini context limit)
    content = mmd_content[:30000] if len(mmd_content) > 30000 else mmd_content

    prompt = f"""You are parsing a GCSE Maths exam paper. Below is the full content extracted by Mathpix OCR.

YOUR JOB: Identify each exam question and return structured JSON.

CRITICAL JSON RULES:
- In "text" fields: NO backslashes at all. Write plain readable text.
- In "latex" fields: Use double-escaped backslashes: \\\\\\\\ for LaTeX commands.
- If unsure, just put clean text in both fields - do NOT break JSON with bad escapes.

CONTENT RULES:
1. TABLES: If content has \\begin{{tabular}} or |...|, include the full table. In "text" render readable: "Equation | Letter\\ny=-x^3 | \\ny=x^3 |". Keep LaTeX table in "latex".
2. IMAGES: Any ![...](url) is a diagram. Put ALL URLs in "image_urls". Set "has_diagram":true. NEVER skip images. Filter out border/watermark/logo images.
3. GEOMETRIC LABELS: "ADC" stays "ADC" not "A D C". Keep letter combos: ABC, PQR, ABCD.
4. FULL TEXT: Include complete question context. "The diagram shows four triangles with angles 55, 45..." not just labels.
5. PARTS: Each (a),(b),(c) is separate with COMPLETE text.
6. MARKS: From "(2 marks)" or "(Total for question = 5 marks)".

GCSE papers have 20-25 questions. Data numbers are NOT question numbers.

Return ONLY JSON:
{{
  "questions": [
    {{
      "question_number": 1,
      "text": "Complete readable text with tables formatted",
      "latex": "With LaTeX double-escaped",
      "parts": [{{"part_label":"a","text":"Full part","latex":"LaTeX","marks":2}}],
      "marks": 5,
      "has_diagram": true,
      "has_table": false,
      "image_urls": ["https://..."],
      "difficulty": "bronze|silver|gold",
      "topics": ["topic1"]
    }}
  ]
}}

Topics: number-operations, fractions, ratio-proportion, percentages, indices, standard-form, surds, algebraic-expressions, linear-equations, quadratics, factorisation, simultaneous-equations, inequalities, sequences, functions, angles, triangles, circles, area-perimeter, volume-surface-area, trigonometry, pythagoras, transformations, vectors, coordinates, probability, data-handling, averages, cumulative-frequency, histograms

MATHPIX CONTENT:
{content}"""

    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=[types.Content(role="user", parts=[types.Part.from_text(text=prompt)])]
            )
            await log_api_call(paper_id, "gemini_structure_classify")
            result = _parse_json_response(response.text)
            return result.get("questions", [])
        except Exception as e:
            error_str = str(e)
            is_503 = "503" in error_str or "UNAVAILABLE" in error_str
            is_last_attempt = (attempt == max_retries - 1)

            if is_503 and not is_last_attempt:
                wait_time = 2 ** attempt
                logger.info(f"Gemini 503 error (attempt {attempt+1}/{max_retries}), retrying in {wait_time}s...")
                await asyncio.sleep(wait_time)
                continue
            else:
                logger.error(f"Gemini structuring error (attempt {attempt+1}/{max_retries}): {e}")
                return []


async def extract_mark_scheme_from_page(page_image_base64: str, page_number: int, mark_scheme_id: str) -> Dict[str, Any]:
    """Use Gemini Flash to extract mark scheme entries"""
    try:
        system_prompt = """Extract GCSE mark scheme entries. Return JSON:
{"entries": [{"question_number": 1, "part_label": "a", "marks": 2, "method_marks": 1, "accuracy_marks": 1, "b_marks": 0,
"text": "Factorisation of x^2 + 5x + 6", "latex": "\\( x^2 + 5x + 6 = (x+2)(x+3) \\)",
"acceptable_alternatives": ["(x+3)(x+2)"], "follow_through_notes": "FT from (a)", "reasoning_notes": "M1 for attempt"}],
"page_has_content": true, "confidence": 0.95}
If blank: {"entries": [], "page_has_content": false, "confidence": 1.0}"""
        response_text = await _call_gemini_vision(system_prompt, f"Extract mark scheme from page {page_number}. Return JSON only.", page_image_base64)
        await log_api_call(mark_scheme_id, "mark_scheme_extraction")
        return _parse_json_response(response_text)
    except Exception as e:
        logger.error(f"Error extracting mark scheme page {page_number}: {e}")
        return {"entries": [], "page_has_content": False, "confidence": 0.0}

async def extract_diagram_from_page(page_image_base64: str, page_number: int, paper_id: str, question_number: int) -> Dict[str, Any]:
    """Use Gemini to identify diagram boundaries for cropping"""
    try:
        system_prompt = """Identify diagram boundaries for cropping. Include the COMPLETE diagram with ALL labels and numbers visible.
Add 5% padding on all sides to avoid clipping edges.
Coordinates as percentages (0-100).

Return JSON:
{"diagrams": [{"question_number": 1, "type": "graph", "description": "...", 
  "bounding_box": {"x_percent": 10, "y_percent": 20, "width_percent": 70, "height_percent": 50}}],
 "has_diagrams": true}
If none: {"diagrams": [], "has_diagrams": false}"""

        user_prompt = f"Find ALL diagrams on this page for question {question_number}. Include full diagram with padding. Return JSON only."
        
        response_text = await _call_gemini_vision(system_prompt, user_prompt, page_image_base64)
        await log_api_call(paper_id, "diagram_detection")
        return _parse_json_response(response_text)
        
    except Exception as e:
        logger.error(f"Error extracting diagram from page {page_number}: {e}")
        return {"diagrams": [], "has_diagrams": False, "error": str(e)}

# ============ PDF Processing Functions ============
def convert_page_to_base64(pdf_document, page_number: int, dpi: int = 200) -> str:
    """Convert a PDF page to base64 encoded PNG image"""
    page = pdf_document[page_number]
    mat = fitz.Matrix(dpi/72, dpi/72)
    pix = page.get_pixmap(matrix=mat)
    img_data = pix.tobytes("png")
    return base64.b64encode(img_data).decode('utf-8')

def crop_image_from_page(pdf_document, page_number: int, bbox: Dict[str, float], dpi: int = 250) -> bytes:
    """Crop a specific region from a PDF page with generous padding"""
    page = pdf_document[page_number]
    mat = fitz.Matrix(dpi/72, dpi/72)
    pix = page.get_pixmap(matrix=mat)
    
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    
    # Calculate with 8% padding on all sides
    pad = 8
    x = int(max(0, bbox['x_percent'] - pad) / 100 * img.width)
    y = int(max(0, bbox['y_percent'] - pad) / 100 * img.height)
    x2 = int(min(100, bbox['x_percent'] + bbox['width_percent'] + pad) / 100 * img.width)
    y2 = int(min(100, bbox['y_percent'] + bbox['height_percent'] + pad) / 100 * img.height)
    
    cropped = img.crop((x, y, x2, y2))
    
    # Save to bytes
    img_byte_arr = io.BytesIO()
    cropped.save(img_byte_arr, format='PNG', optimize=True)
    return img_byte_arr.getvalue()

async def refine_crop_with_ai(cropped_base64: str, paper_id: str, question_number: int) -> Dict[str, Any]:
    """Send a cropped image back to AI to check if it needs tighter cropping"""
    try:
        system_prompt = """Check if this cropped diagram has unwanted question text.
If clean: {"needs_recrop": false}
If text bleeds in, return tighter bounds as % of this image:
{"needs_recrop": true, "tighter_box": {"x_percent": 5, "y_percent": 10, "width_percent": 90, "height_percent": 80}, "text_found": "description"}
Keep diagram labels (5m, axis numbers) - only remove question text paragraphs."""

        user_prompt = "Check this crop for text bleeding. Return JSON only."
        
        response_text = await _call_gemini_vision(system_prompt, user_prompt, cropped_base64)
        await log_api_call(paper_id, "crop_refinement")
        return _parse_json_response(response_text)
    except Exception as e:
        logger.error(f"Error in crop refinement: {e}")
        return {"needs_recrop": False}

# ============ GE ID Generation ============
BOARD_CODES = {"AQA": "AQ", "Edexcel": "EX", "OCR": "OC"}

def generate_ge_code(exam_year: int, board: str, paper_number: str) -> str:
    """Generate GE code for a paper: GE17EX1"""
    yr = str(exam_year)[-2:]  # Last 2 digits: 2017 → 17
    board_code = BOARD_CODES.get(board, board[:2].upper())
    return f"GE{yr}{board_code}{paper_number}"

def generate_ge_question_id(ge_code: str, question_number: int, import_year: int = None) -> str:
    """Generate GE ID for a question: GE17EX126001"""
    if import_year is None:
        import_year = datetime.now(timezone.utc).year
    yr_code = str(import_year)[-2:]  # 2026 → 26
    seq = str(question_number).zfill(3)  # 1 → 001
    return f"{ge_code}{yr_code}{seq}"

def generate_ge_part_id(ge_question_id: str, part_label: str) -> str:
    """Generate GE ID for a sub-part: GE17EX126001A"""
    return f"{ge_question_id}{part_label.upper()}"

# ============ API Endpoints ============
@api_router.get("/")
async def root():
    return {"message": "GCSE Question Bank API", "version": "1.0.0"}

@api_router.get("/health")
async def health():
    return {"status": "healthy", "storage_initialized": storage_key is not None}

# Paper endpoints
@api_router.post("/papers", response_model=Paper)
async def create_paper(paper_data: PaperCreate):
    paper = Paper(**paper_data.model_dump())
    paper.ge_code = generate_ge_code(paper.exam_year, paper.board, paper.paper_number)
    doc = paper.model_dump()
    await db.papers.insert_one(doc)
    return paper

@api_router.get("/papers", response_model=List[Paper])
async def list_papers():
    papers = await db.papers.find({}, {"_id": 0}).to_list(100)
    return papers

@api_router.get("/papers/{paper_id}", response_model=Paper)
async def get_paper(paper_id: str):
    paper = await db.papers.find_one({"id": paper_id}, {"_id": 0})
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    return paper

@api_router.delete("/papers/{paper_id}")
async def delete_paper(paper_id: str):
    """Delete a paper and all its questions, images, jobs"""
    paper = await db.papers.find_one({"id": paper_id}, {"_id": 0})
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    
    # Delete all related data
    del_q = await db.questions.delete_many({"paper_id": paper_id})
    del_img = await db.image_assets.delete_many({"paper_id": paper_id})
    del_jobs = await db.extraction_jobs.delete_many({"paper_id": paper_id})
    del_ms = await db.mark_schemes.delete_many({"paper_id": paper_id})
    del_mse = await db.mark_scheme_entries.delete_many({"paper_id": paper_id})
    del_logs = await db.api_call_logs.delete_many({"paper_id": paper_id})
    await db.papers.delete_one({"id": paper_id})
    
    return {
        "message": "Paper deleted",
        "deleted": {
            "questions": del_q.deleted_count,
            "images": del_img.deleted_count,
            "jobs": del_jobs.deleted_count,
            "mark_schemes": del_ms.deleted_count,
            "entries": del_mse.deleted_count,
            "logs": del_logs.deleted_count
        }
    }

# ============ Cost Monitoring Endpoint ============
@api_router.get("/api-usage")
async def get_api_usage(paper_id: Optional[str] = None):
    """Get API call usage stats for cost monitoring"""
    query = {}
    if paper_id:
        query["paper_id"] = paper_id
    
    total_calls = await db.api_call_logs.count_documents(query)
    
    # Breakdown by type
    pipeline = [
        {"$match": query},
        {"$group": {"_id": "$call_type", "count": {"$sum": 1}}}
    ]
    breakdown = {}
    async for doc in db.api_call_logs.aggregate(pipeline):
        breakdown[doc["_id"]] = doc["count"]
    
    # Gemini Flash pricing: ~$0.075/1M input tokens, ~$0.30/1M output tokens
    # Rough estimate: ~1500 tokens per vision call = ~$0.0002 per call
    est_cost_per_call = 0.0002
    estimated_cost = total_calls * est_cost_per_call
    
    # Per paper breakdown
    paper_pipeline = [
        {"$match": query},
        {"$group": {"_id": "$paper_id", "calls": {"$sum": 1}}}
    ]
    per_paper = {}
    async for doc in db.api_call_logs.aggregate(paper_pipeline):
        per_paper[doc["_id"]] = {"calls": doc["calls"], "est_cost": round(doc["calls"] * est_cost_per_call, 4)}
    
    return {
        "total_api_calls": total_calls,
        "breakdown_by_type": breakdown,
        "estimated_total_cost_usd": round(estimated_cost, 4),
        "model": GEMINI_MODEL,
        "provider": "gemini",
        "per_paper": per_paper
    }
@api_router.post("/papers/{paper_id}/upload")
async def upload_pdf(paper_id: str, file: UploadFile = File(...)):
    """Upload a PDF and start extraction"""
    # Verify paper exists
    paper = await db.papers.find_one({"id": paper_id}, {"_id": 0})
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")
    
    # Read PDF content
    pdf_content = await file.read()
    
    # Upload to object storage
    storage_path = f"{APP_NAME}/pdfs/{paper_id}/{uuid.uuid4()}.pdf"
    try:
        put_object(storage_path, pdf_content, "application/pdf")
    except Exception as e:
        logger.error(f"Failed to upload PDF to storage: {e}")
        raise HTTPException(status_code=500, detail="Failed to store PDF")
    
    # Update paper with PDF path
    await db.papers.update_one(
        {"id": paper_id},
        {"$set": {"pdf_path": storage_path, "status": "processing"}}
    )
    
    # Create extraction job
    job = ExtractionJob(paper_id=paper_id)
    await db.extraction_jobs.insert_one(job.model_dump())
    
    # Start extraction in background
    asyncio.create_task(process_pdf_extraction(paper_id, pdf_content, job.id))
    
    return {"message": "PDF uploaded successfully", "job_id": job.id, "paper_id": paper_id}

@api_router.post("/papers/{paper_id}/re-extract")
async def re_extract_paper(paper_id: str):
    """Re-extract a paper with improved settings (deletes old questions/images first)"""
    paper = await db.papers.find_one({"id": paper_id}, {"_id": 0})
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    
    if not paper.get("pdf_path"):
        raise HTTPException(status_code=400, detail="No PDF uploaded for this paper")
    
    # Download PDF from storage
    try:
        pdf_content, _ = get_object(paper["pdf_path"])
    except Exception as e:
        logger.error(f"Failed to download PDF: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve stored PDF")
    
    # Delete old questions and images for this paper
    await db.questions.delete_many({"paper_id": paper_id})
    await db.image_assets.update_many(
        {"paper_id": paper_id},
        {"$set": {"is_deleted": True}}
    )
    
    # Update paper status
    await db.papers.update_one(
        {"id": paper_id},
        {"$set": {"status": "processing", "total_questions": 0}}
    )
    
    # Create new extraction job
    job = ExtractionJob(paper_id=paper_id)
    await db.extraction_jobs.insert_one(job.model_dump())

    # Check if we have cached Mathpix output from a previous attempt
    last_job = await db.extraction_jobs.find_one(
        {"paper_id": paper_id, "id": {"$ne": job.id}},
        sort=[("created_at", -1)]
    )

    if last_job and last_job.get("mathpix_output"):
        # Mathpix already done - just retry Gemini
        logger.info(f"Reusing cached Mathpix output ({len(last_job['mathpix_output'])} chars)")
        asyncio.create_task(process_gemini_only(paper_id, last_job["mathpix_output"], job.id))
    else:
        # No cached output - do full extraction (Mathpix + Gemini)
        asyncio.create_task(process_pdf_extraction(paper_id, pdf_content, job.id))

    return {"message": "Re-extraction started", "job_id": job.id, "paper_id": paper_id}

async def process_pdf_extraction(paper_id: str, pdf_content: bytes, job_id: str):
    """Mathpix gets raw content once. Gemini structures it with retries. Caches Mathpix output to avoid re-extracting on Gemini retry."""
    try:
        await db.extraction_jobs.update_one(
            {"id": job_id},
            {"$set": {"status": "processing", "started_at": datetime.now(timezone.utc).isoformat()}}
        )

        paper = await db.papers.find_one({"id": paper_id}, {"_id": 0})
        ge_code = paper.get("ge_code") or generate_ge_code(
            paper.get('exam_year', 0), paper.get('board', 'AQA'), paper.get('paper_number', '1')
        )

        pdf_document = fitz.open(stream=pdf_content, filetype="pdf")
        total_pages = len(pdf_document)
        pdf_document.close()

        await db.extraction_jobs.update_one(
            {"id": job_id}, {"$set": {"total_pages": total_pages, "processed_pages": 1}}
        )

        # CALL 1: Mathpix - raw extraction (ONLY ONCE per extraction attempt)
        logger.info(f"Mathpix: submitting {total_pages} pages")
        await log_api_call(paper_id, "mathpix_pdf")
        mathpix_pdf_id = mathpix_submit_pdf(pdf_content)
        mathpix_poll_status(mathpix_pdf_id)
        mmd_content = mathpix_get_mmd(mathpix_pdf_id)
        logger.info(f"Mathpix done: {len(mmd_content)} chars")

        # Cache Mathpix output in extraction job for potential re-use on Gemini retry
        await db.extraction_jobs.update_one(
            {"id": job_id},
            {"$set": {"mathpix_output": mmd_content, "processed_pages": total_pages // 2}}
        )

        # CALL 2: Gemini - structure + classify in one call (with internal retry logic)
        logger.info("Gemini: structuring questions")
        structured_questions = await classify_and_structure_with_gemini(mmd_content, paper_id)
        logger.info(f"Gemini done: {len(structured_questions)} questions")
        
        await db.extraction_jobs.update_one(
            {"id": job_id}, {"$set": {"processed_pages": total_pages - 1}}
        )
        
        # Save to database
        all_questions = []
        images_extracted = 0
        
        for q_data in structured_questions:
            q_number = q_data.get("question_number", 0)
            if q_number <= 0:
                continue
            ge_question_id = generate_ge_question_id(ge_code, q_number)
            
            # Download Mathpix images
            image_ids = []
            for img_url in q_data.get("image_urls", []):
                try:
                    img_bytes = download_image(img_url)
                    img_id = str(uuid.uuid4())
                    img_path = f"{APP_NAME}/images/{paper_id}/{img_id}.png"
                    put_object(img_path, img_bytes, "image/png")
                    img_asset = ImageAsset(
                        id=img_id, paper_id=paper_id, storage_path=img_path,
                        original_filename=f"Q{q_number}.png", content_type="image/png",
                        width=0, height=0, page_number=0,
                        description=f"Diagram Q{q_number}"
                    )
                    await db.image_assets.insert_one(img_asset.model_dump())
                    image_ids.append(img_id)
                    images_extracted += 1
                except Exception as e:
                    logger.error(f"Image download error: {e}")
            
            # Build parts (skip parts without valid part_label)
            parts = []
            for p in q_data.get("parts", []):
                pl = p.get("part_label") or ""  # Handle None values
                if not pl or not pl.strip():  # Skip empty/None part labels
                    logger.debug(f"Skipping part without label in Q{q_number}")
                    continue

                part_text = p.get("text", "").strip()
                if not part_text:  # Skip parts with no text
                    logger.debug(f"Skipping part {pl} in Q{q_number} - no text")
                    continue

                ge_part_id = generate_ge_part_id(ge_question_id, pl)
                parts.append(QuestionPart(
                    part_label=pl.strip(), text=clean_text(part_text),
                    latex=p.get("latex"), marks=p.get("marks"),
                    confidence=0.95, ge_id=ge_part_id, images=image_ids
                ))
            
            question = Question(
                paper_id=paper_id, question_number=q_number,
                text=clean_text(q_data.get("text", "")), latex=q_data.get("latex"),
                parts=parts, marks=q_data.get("marks"), images=image_ids,
                has_diagram=q_data.get("has_diagram", len(image_ids) > 0),
                has_table=q_data.get("has_table", False), confidence=0.95,
                difficulty=q_data.get("difficulty"), topics=q_data.get("topics", []),
                ge_id=ge_question_id, parent_ge_id=ge_code, status="draft"
            )
            await db.questions.insert_one(question.model_dump())
            all_questions.append(question)
        
        await db.extraction_jobs.update_one(
            {"id": job_id},
            {"$set": {"status": "completed", "processed_pages": total_pages,
                      "questions_found": len(all_questions), "images_extracted": images_extracted,
                      "completed_at": datetime.now(timezone.utc).isoformat()}}
        )
        await db.papers.update_one(
            {"id": paper_id},
            {"$set": {"status": "extracted", "total_questions": len(all_questions)}}
        )
        logger.info(f"Done: {len(all_questions)} questions, {images_extracted} images (1 Mathpix + 1 Gemini)")
        
    except Exception as e:
        logger.error(f"Extraction failed: {e}")
        await db.extraction_jobs.update_one(
            {"id": job_id},
            {"$set": {"status": "failed", "error_message": str(e),
                      "completed_at": datetime.now(timezone.utc).isoformat()}}
        )
        await db.papers.update_one({"id": paper_id}, {"$set": {"status": "failed"}})


async def process_gemini_only(paper_id: str, mmd_content: str, job_id: str):
    """Retry Gemini structuring ONLY - reuses cached Mathpix output. Avoids wasting API tokens."""
    try:
        await db.extraction_jobs.update_one(
            {"id": job_id},
            {"$set": {"status": "processing", "started_at": datetime.now(timezone.utc).isoformat()}}
        )

        paper = await db.papers.find_one({"id": paper_id}, {"_id": 0})
        ge_code = paper.get("ge_code") or generate_ge_code(
            paper.get('exam_year', 0), paper.get('board', 'AQA'), paper.get('paper_number', '1')
        )

        # SKIP Mathpix entirely - use cached output
        logger.info(f"Gemini (retry): structuring questions from cached Mathpix output ({len(mmd_content)} chars)")
        structured_questions = await classify_and_structure_with_gemini(mmd_content, paper_id)
        logger.info(f"Gemini done: {len(structured_questions)} questions")

        # Save to database (same as full extraction)
        all_questions = []
        images_extracted = 0

        for q_data in structured_questions:
            q_number = q_data.get("question_number", 0)
            if q_number <= 0:
                continue
            ge_question_id = generate_ge_question_id(ge_code, q_number)

            # Download Mathpix images
            image_ids = []
            for img_url in q_data.get("image_urls", []):
                try:
                    img_bytes = download_image(img_url)
                    img_id = str(uuid.uuid4())
                    img_path = f"{APP_NAME}/images/{paper_id}/{img_id}.png"
                    put_object(img_path, img_bytes, "image/png")
                    img_asset = ImageAsset(
                        id=img_id, paper_id=paper_id, storage_path=img_path,
                        original_filename=f"Q{q_number}.png", content_type="image/png",
                        width=0, height=0, page_number=0,
                        description=f"Diagram Q{q_number}"
                    )
                    await db.image_assets.insert_one(img_asset.model_dump())
                    image_ids.append(img_id)
                    images_extracted += 1
                except Exception as e:
                    logger.error(f"Image download error: {e}")

            # Build parts (skip parts without valid part_label)
            parts = []
            for p in q_data.get("parts", []):
                pl = p.get("part_label") or ""
                if not pl or not pl.strip():
                    logger.debug(f"Skipping part without label in Q{q_number}")
                    continue

                part_text = p.get("text", "").strip()
                if not part_text:
                    logger.debug(f"Skipping part {pl} in Q{q_number} - no text")
                    continue

                ge_part_id = generate_ge_part_id(ge_question_id, pl)
                parts.append(QuestionPart(
                    part_label=pl.strip(), text=clean_text(part_text),
                    latex=p.get("latex"), marks=p.get("marks"),
                    confidence=0.95, ge_id=ge_part_id, images=image_ids
                ))

            question = Question(
                question_number=q_number, text=clean_text(q_data.get("text", "")),
                latex=q_data.get("latex"), parts=parts, marks=q_data.get("marks", 0),
                has_diagram=q_data.get("has_diagram", False),
                has_table=q_data.get("has_table", False),
                image_ids=image_ids, difficulty=q_data.get("difficulty"),
                topics=q_data.get("topics", []), paper_id=paper_id, ge_id=ge_question_id
            )
            await db.questions.insert_one(question.model_dump())
            all_questions.append(question)

        # Update paper and job
        await db.papers.update_one(
            {"id": paper_id},
            {"$set": {"status": "extracted", "total_questions": len(all_questions)}}
        )

        await db.extraction_jobs.update_one(
            {"id": job_id},
            {"$set": {
                "status": "completed", "questions_found": len(all_questions),
                "images_extracted": images_extracted, "api_calls": 1,
                "completed_at": datetime.now(timezone.utc).isoformat()
            }}
        )

        logger.info(f"Done: {len(all_questions)} questions, {images_extracted} images (cached Mathpix + Gemini retry)")

    except Exception as e:
        logger.error(f"Gemini retry failed: {e}")
        await db.extraction_jobs.update_one(
            {"id": job_id},
            {"$set": {"status": "failed", "error_message": str(e),
                      "completed_at": datetime.now(timezone.utc).isoformat()}}
        )
        await db.papers.update_one({"id": paper_id}, {"$set": {"status": "failed"}})

# Extraction job status
@api_router.get("/extraction-jobs/{job_id}")
async def get_extraction_job(job_id: str):
    job = await db.extraction_jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

@api_router.get("/papers/{paper_id}/extraction-status")
async def get_paper_extraction_status(paper_id: str):
    job = await db.extraction_jobs.find_one(
        {"paper_id": paper_id},
        {"_id": 0},
        sort=[("created_at", -1)]
    )
    if not job:
        raise HTTPException(status_code=404, detail="No extraction job found for this paper")
    return job

# Question endpoints
@api_router.get("/questions", response_model=List[Question])
async def list_questions(paper_id: Optional[str] = None, status: Optional[str] = None):
    query = {}
    if paper_id:
        query["paper_id"] = paper_id
    if status:
        query["status"] = status
    questions = await db.questions.find(query, {"_id": 0}).to_list(500)
    return questions

@api_router.get("/questions/{question_id}", response_model=Question)
async def get_question(question_id: str):
    question = await db.questions.find_one({"id": question_id}, {"_id": 0})
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    return question

@api_router.patch("/questions/{question_id}")
async def update_question(question_id: str, updates: Dict[str, Any]):
    """Update a question (for review/approval workflow)"""
    # Filter allowed update fields
    allowed_fields = ["text", "latex", "marks", "status", "parts", "review_reason_codes", "difficulty", "topics", "mark_scheme", "mark_scheme_latex"]
    filtered_updates = {k: v for k, v in updates.items() if k in allowed_fields}
    
    if not filtered_updates:
        raise HTTPException(status_code=400, detail="No valid update fields provided")
    
    result = await db.questions.update_one(
        {"id": question_id},
        {"$set": filtered_updates}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Question not found")
    
    return {"message": "Question updated", "updated_fields": list(filtered_updates.keys())}

@api_router.post("/questions/{question_id}/approve")
async def approve_question(question_id: str):
    """Approve a question"""
    result = await db.questions.update_one(
        {"id": question_id},
        {"$set": {"status": "approved"}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Question not found")
    return {"message": "Question approved"}

@api_router.post("/questions/{question_id}/reject")
async def reject_question(question_id: str, reason: Optional[str] = None):
    """Reject a question and mark for re-review"""
    updates = {"status": "needs_review"}
    if reason:
        updates["review_reason_codes"] = [reason]
    
    result = await db.questions.update_one(
        {"id": question_id},
        {"$set": updates}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Question not found")
    return {"message": "Question rejected"}

# ============ Image Replace Endpoint ============
@api_router.post("/questions/{question_id}/replace-image")
async def replace_question_image(question_id: str, file: UploadFile = File(...), old_image_id: Optional[str] = None):
    """Replace or add an image for a question"""
    question = await db.questions.find_one({"id": question_id}, {"_id": 0})
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    
    # Read image
    img_data = await file.read()
    
    # Upload to storage
    img_id = str(uuid.uuid4())
    ext = file.filename.split(".")[-1] if "." in file.filename else "png"
    img_path = f"{APP_NAME}/images/{question['paper_id']}/{img_id}.{ext}"
    put_object(img_path, img_data, file.content_type or "image/png")
    
    # Get image dimensions
    try:
        pil_img = Image.open(io.BytesIO(img_data))
        width, height = pil_img.size
    except Exception:
        width, height = 0, 0
    
    # Create image asset
    img_asset = ImageAsset(
        id=img_id,
        paper_id=question["paper_id"],
        question_id=question_id,
        storage_path=img_path,
        original_filename=file.filename,
        content_type=file.content_type or "image/png",
        width=width,
        height=height,
        page_number=0,
        description="Manually uploaded replacement"
    )
    await db.image_assets.insert_one(img_asset.model_dump())
    
    # Update question images list
    current_images = question.get("images", [])
    if old_image_id and old_image_id in current_images:
        # Replace old with new
        current_images = [img_id if x == old_image_id else x for x in current_images]
        # Soft-delete old image
        await db.image_assets.update_one({"id": old_image_id}, {"$set": {"is_deleted": True}})
    else:
        # Add new image
        current_images.append(img_id)
    
    await db.questions.update_one(
        {"id": question_id},
        {"$set": {"images": current_images, "has_diagram": True}}
    )
    
    # Also update parts to share the new image
    parts = question.get("parts", [])
    if parts:
        for part in parts:
            if old_image_id and old_image_id in part.get("images", []):
                part["images"] = [img_id if x == old_image_id else x for x in part["images"]]
            elif not part.get("images"):
                part["images"] = current_images
        await db.questions.update_one(
            {"id": question_id},
            {"$set": {"parts": parts}}
        )
    
    return {"message": "Image replaced", "new_image_id": img_id, "images": current_images}

@api_router.delete("/questions/{question_id}/images/{image_id}")
async def remove_question_image(question_id: str, image_id: str):
    """Remove an image from a question"""
    question = await db.questions.find_one({"id": question_id}, {"_id": 0})
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    
    # Remove from question images list
    current_images = [x for x in question.get("images", []) if x != image_id]
    await db.questions.update_one(
        {"id": question_id},
        {"$set": {"images": current_images, "has_diagram": len(current_images) > 0}}
    )
    
    # Soft-delete image
    await db.image_assets.update_one({"id": image_id}, {"$set": {"is_deleted": True}})
    
    return {"message": "Image removed"}

# Image endpoints
@api_router.get("/images/{image_id}")
async def get_image(image_id: str):
    """Get image metadata"""
    image = await db.image_assets.find_one({"id": image_id, "is_deleted": False}, {"_id": 0})
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
    return image

@api_router.get("/images/{image_id}/download")
async def download_image_endpoint(image_id: str):
    """Download the actual image file"""
    image = await db.image_assets.find_one({"id": image_id, "is_deleted": False}, {"_id": 0})
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
    
    try:
        data, content_type = get_object(image["storage_path"])
        return Response(content=data, media_type=content_type)
    except Exception as e:
        logger.error(f"Error downloading image: {e}")
        raise HTTPException(status_code=500, detail="Failed to download image")

@api_router.get("/papers/{paper_id}/images")
async def list_paper_images(paper_id: str):
    """List all images for a paper"""
    images = await db.image_assets.find(
        {"paper_id": paper_id, "is_deleted": False},
        {"_id": 0}
    ).to_list(100)
    return images

# Stats endpoint
@api_router.get("/stats")
async def get_stats():
    """Get overall statistics"""
    total_papers = await db.papers.count_documents({})
    total_questions = await db.questions.count_documents({})
    approved_questions = await db.questions.count_documents({"status": "approved"})
    pending_review = await db.questions.count_documents({"status": "needs_review"})
    total_images = await db.image_assets.count_documents({"is_deleted": False})
    total_mark_schemes = await db.mark_schemes.count_documents({})
    
    return {
        "total_papers": total_papers,
        "total_questions": total_questions,
        "approved_questions": approved_questions,
        "pending_review": pending_review,
        "total_images": total_images,
        "total_mark_schemes": total_mark_schemes
    }

# ============ Topic Endpoints ============
@api_router.get("/topics")
async def list_topics():
    """Get all available topics"""
    return GCSE_TOPICS

@api_router.get("/topics/categories")
async def list_topic_categories():
    """Get topic categories"""
    categories = {}
    for topic in GCSE_TOPICS:
        cat = topic["category"]
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(topic)
    return categories

# ============ Mark Scheme Endpoints ============
@api_router.post("/papers/{paper_id}/mark-scheme/upload")
async def upload_mark_scheme(paper_id: str, file: UploadFile = File(...)):
    """Upload a mark scheme PDF and start extraction"""
    # Verify paper exists
    paper = await db.papers.find_one({"id": paper_id}, {"_id": 0})
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")
    
    # Read PDF content
    pdf_content = await file.read()
    
    # Upload to object storage
    storage_path = f"{APP_NAME}/mark-schemes/{paper_id}/{uuid.uuid4()}.pdf"
    try:
        put_object(storage_path, pdf_content, "application/pdf")
    except Exception as e:
        logger.error(f"Failed to upload mark scheme to storage: {e}")
        raise HTTPException(status_code=500, detail="Failed to store mark scheme")
    
    # Create mark scheme record
    mark_scheme = MarkScheme(paper_id=paper_id, pdf_path=storage_path, status="processing")
    await db.mark_schemes.insert_one(mark_scheme.model_dump())
    
    # Start extraction in background
    asyncio.create_task(process_mark_scheme_extraction(paper_id, pdf_content, mark_scheme.id))
    
    return {"message": "Mark scheme uploaded successfully", "mark_scheme_id": mark_scheme.id, "paper_id": paper_id}

async def process_mark_scheme_extraction(paper_id: str, pdf_content: bytes, mark_scheme_id: str):
    """Background task to extract mark scheme entries from PDF"""
    try:
        # Open PDF
        pdf_document = fitz.open(stream=pdf_content, filetype="pdf")
        total_pages = len(pdf_document)
        
        all_entries = []
        
        # Process each page
        for page_num in range(total_pages):
            try:
                # Convert page to image
                page_base64 = convert_page_to_base64(pdf_document, page_num)
                
                # Extract mark scheme using AI
                extraction_result = await extract_mark_scheme_from_page(page_base64, page_num + 1, mark_scheme_id)
                
                if extraction_result.get("entries"):
                    for entry_data in extraction_result["entries"]:
                        entry = MarkSchemeEntry(
                            mark_scheme_id=mark_scheme_id,
                            paper_id=paper_id,
                            question_number=entry_data.get("question_number", 0),
                            part_label=entry_data.get("part_label"),
                            marks=entry_data.get("marks", 0),
                            method_marks=entry_data.get("method_marks", 0),
                            accuracy_marks=entry_data.get("accuracy_marks", 0),
                            b_marks=entry_data.get("b_marks", 0),
                            text=entry_data.get("text", ""),
                            latex=entry_data.get("latex"),
                            acceptable_alternatives=entry_data.get("acceptable_alternatives", []),
                            follow_through_notes=entry_data.get("follow_through_notes"),
                            reasoning_notes=entry_data.get("reasoning_notes")
                        )
                        await db.mark_scheme_entries.insert_one(entry.model_dump())
                        all_entries.append(entry)
                        
            except Exception as e:
                logger.error(f"Error processing mark scheme page {page_num}: {e}")
        
        pdf_document.close()
        
        # Update mark scheme status
        await db.mark_schemes.update_one(
            {"id": mark_scheme_id},
            {"$set": {"status": "extracted", "total_entries": len(all_entries)}}
        )
        
        # Auto-link entries to questions
        await link_mark_scheme_to_questions(paper_id, mark_scheme_id)
        
        logger.info(f"Mark scheme extraction completed: {len(all_entries)} entries")
        
    except Exception as e:
        logger.error(f"Mark scheme extraction failed: {e}")
        await db.mark_schemes.update_one(
            {"id": mark_scheme_id},
            {"$set": {"status": "failed"}}
        )

async def link_mark_scheme_to_questions(paper_id: str, mark_scheme_id: str):
    """Auto-link mark scheme entries to questions"""
    # Get all questions for this paper
    questions = await db.questions.find({"paper_id": paper_id}, {"_id": 0}).to_list(500)
    
    # Get all mark scheme entries
    entries = await db.mark_scheme_entries.find(
        {"mark_scheme_id": mark_scheme_id},
        {"_id": 0}
    ).to_list(500)
    
    linked_count = 0
    
    for entry in entries:
        # Find matching question
        for question in questions:
            if question["question_number"] == entry["question_number"]:
                # Update the entry with question link
                await db.mark_scheme_entries.update_one(
                    {"id": entry["id"]},
                    {"$set": {"linked_question_id": question["id"]}}
                )
                
                # If it's a part-level entry, update the part
                if entry.get("part_label"):
                    # Update the specific part's mark scheme
                    parts = question.get("parts", [])
                    for i, part in enumerate(parts):
                        if part.get("part_label") == entry["part_label"]:
                            parts[i]["mark_scheme"] = entry["text"]
                            parts[i]["mark_scheme_latex"] = entry.get("latex")
                            parts[i]["marks"] = entry["marks"]
                    await db.questions.update_one(
                        {"id": question["id"]},
                        {"$set": {"parts": parts}}
                    )
                else:
                    # Update question-level mark scheme
                    await db.questions.update_one(
                        {"id": question["id"]},
                        {"$set": {
                            "mark_scheme": entry["text"],
                            "mark_scheme_latex": entry.get("latex"),
                            "mark_scheme_id": mark_scheme_id,
                            "marks": entry["marks"]
                        }}
                    )
                
                linked_count += 1
                break
    
    # Update mark scheme status to linked
    await db.mark_schemes.update_one(
        {"id": mark_scheme_id},
        {"$set": {"status": "linked"}}
    )
    
    logger.info(f"Linked {linked_count} mark scheme entries to questions")

@api_router.get("/papers/{paper_id}/mark-scheme")
async def get_paper_mark_scheme(paper_id: str):
    """Get mark scheme for a paper"""
    mark_scheme = await db.mark_schemes.find_one(
        {"paper_id": paper_id},
        {"_id": 0},
        sort=[("created_at", -1)]
    )
    if not mark_scheme:
        raise HTTPException(status_code=404, detail="No mark scheme found for this paper")
    return mark_scheme

@api_router.get("/mark-scheme-entries")
async def list_mark_scheme_entries(
    paper_id: Optional[str] = None,
    mark_scheme_id: Optional[str] = None,
    question_number: Optional[int] = None
):
    """List mark scheme entries with optional filters"""
    query = {}
    if paper_id:
        query["paper_id"] = paper_id
    if mark_scheme_id:
        query["mark_scheme_id"] = mark_scheme_id
    if question_number:
        query["question_number"] = question_number
    
    entries = await db.mark_scheme_entries.find(query, {"_id": 0}).to_list(500)
    return entries

@api_router.get("/questions/{question_id}/mark-scheme")
async def get_question_mark_scheme(question_id: str):
    """Get mark scheme entries linked to a specific question"""
    entries = await db.mark_scheme_entries.find(
        {"linked_question_id": question_id},
        {"_id": 0}
    ).to_list(50)
    return entries

# ============ Question Update Endpoints for Tags/Difficulty ============
@api_router.patch("/questions/{question_id}/difficulty")
async def update_question_difficulty(question_id: str, difficulty: str):
    """Update question difficulty level"""
    if difficulty not in ["bronze", "silver", "gold"]:
        raise HTTPException(status_code=400, detail="Invalid difficulty. Use: bronze, silver, gold")
    
    result = await db.questions.update_one(
        {"id": question_id},
        {"$set": {"difficulty": difficulty}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Question not found")
    return {"message": "Difficulty updated", "difficulty": difficulty}

@api_router.patch("/questions/{question_id}/topics")
async def update_question_topics(question_id: str, topics: List[str]):
    """Update question topics"""
    # Validate topics against predefined list
    valid_topic_names = [t["name"] for t in GCSE_TOPICS]
    invalid_topics = [t for t in topics if t not in valid_topic_names]
    if invalid_topics:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid topics: {invalid_topics}. Use valid topic names from /api/topics"
        )
    
    result = await db.questions.update_one(
        {"id": question_id},
        {"$set": {"topics": topics}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Question not found")
    return {"message": "Topics updated", "topics": topics}

@api_router.get("/questions/by-topic/{topic}")
async def get_questions_by_topic(topic: str, status: Optional[str] = None):
    """Get all questions with a specific topic"""
    query = {"topics": topic}
    if status:
        query["status"] = status
    questions = await db.questions.find(query, {"_id": 0}).to_list(500)
    return questions

@api_router.get("/questions/by-difficulty/{difficulty}")
async def get_questions_by_difficulty(difficulty: str, status: Optional[str] = None):
    """Get all questions with a specific difficulty"""
    if difficulty not in ["bronze", "silver", "gold"]:
        raise HTTPException(status_code=400, detail="Invalid difficulty")
    query = {"difficulty": difficulty}
    if status:
        query["status"] = status
    questions = await db.questions.find(query, {"_id": 0}).to_list(500)
    return questions

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup():
    try:
        init_storage()
    except Exception as e:
        logger.error(f"Storage init failed: {e}")

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
