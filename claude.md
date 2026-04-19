# GE Question Bank - Codebase Analysis

## Project Overview
A GCSE Maths question bank platform for Genius Education that extracts questions from PDF past papers, crops diagrams, and manages structured question data with mark schemes.

---

## BACKEND ANALYSIS (server.py - 1,548 lines)

### Architecture
- **Framework**: FastAPI + Motor (async MongoDB)
- **File Storage**: Local filesystem (with optional Emergent cloud storage fallback)
- **External APIs**: Mathpix (PDF extraction) + Gemini (classification)
- **Port**: 8001
- **Prefix**: `/api`

### Key Configuration
```python
# Environment Variables Required:
MONGO_URL = mongodb connection
DB_NAME = ge_question_bank
CORS_ORIGINS = https://apps.geniuseducation.co.uk,http://localhost
GEMINI_API_KEY = for topic/difficulty classification
MATHPIX_APP_ID = PDF text/LaTeX/image extraction (MISSING - CRITICAL)
MATHPIX_APP_KEY = PDF text/LaTeX/image extraction (MISSING - CRITICAL)
EMERGENT_LLM_KEY = optional cloud storage
```

### Database Models
- **Paper** - Exam paper metadata (board, year, session, tier, status)
- **Question** - Individual questions (text, LaTeX, parts, images, topics, difficulty, ge_id)
- **QuestionPart** - Sub-questions (a, b, c... with separate marks/images)
- **MarkScheme** - Mark allocation per question/part
- **ExtractionJob** - Job tracking for async PDF processing
- **ApiUsage** - Cost tracking for Gemini/Mathpix calls

### Extraction Pipeline Flow
1. **Upload PDF** → POST `/papers/{paper_id}/upload`
2. **Mathpix Processing** (if API keys exist):
   - Submit PDF to Mathpix API
   - Poll for completion (5min timeout)
   - Get Markdown (.mmd) with text + LaTeX + image URLs
   - Get structured line data (.lines.json)
3. **Image Extraction**:
   - Download images from Mathpix CDN
   - Detect diagram boundaries with Gemini Vision
   - Crop images with 8% padding
   - Refine crops with AI
   - Store locally or in cloud
4. **Structure & Classify**:
   - Parse Mathpix Markdown into questions
   - Use Gemini to classify topics (bronze/silver/gold)
   - Generate GE IDs (hierarchical: paper → question → part)
5. **Store Results** → MongoDB

### API Endpoints (45 endpoints)

#### Paper Management
- `GET /papers` - List all papers
- `POST /papers` - Create new paper
- `GET /papers/{paper_id}` - Get paper details
- `DELETE /papers/{paper_id}` - Delete paper
- `POST /papers/{paper_id}/upload` - Upload PDF
- `POST /papers/{paper_id}/re-extract` - Reprocess extraction

#### Question Management
- `GET /questions` - List all questions (optional filter by paper_id/status)
- `GET /questions/{question_id}` - Get question details
- `PATCH /questions/{question_id}` - Update question (text, marks, parts, difficulty, topics)
- `POST /questions/{question_id}/approve` - Mark as approved
- `POST /questions/{question_id}/reject` - Reject with reason

#### Images
- `GET /images/{image_id}` - Download image
- `POST /questions/{question_id}/replace-image` - Replace/add/remove images
- `POST /questions/{question_id}/crop-images` - Trigger re-cropping

#### Mark Schemes
- `POST /mark-schemes` - Upload mark scheme PDF
- `GET /mark-schemes/{mark_scheme_id}` - Get extracted mark scheme
- `POST /mark-schemes/{mark_scheme_id}/link` - Link mark scheme to questions

#### Metadata
- `GET /topics` - List all 30 GCSE topics
- `GET /extraction-jobs/{job_id}` - Get job status
- `GET /papers/{paper_id}/extraction-status` - Get paper extraction progress
- `GET /api-usage` - Get Gemini/Mathpix cost tracking

### Key Functions (Helper & Processing)

**Mathpix Integration** (MISSING - Need API Keys)
- `mathpix_submit_pdf()` - Send PDF to Mathpix
- `mathpix_poll_status()` - Wait for completion (polls every 3s)
- `mathpix_get_mmd()` - Fetch Markdown
- `mathpix_get_lines()` - Fetch structured line data
- `download_image()` - Download image from Mathpix CDN

**Text Processing**
- `parse_mathpix_mmd()` - Parse Markdown into questions/parts using regex
- `clean_text()` - Remove LaTeX commands for readable display

**Image Processing**
- `convert_page_to_base64()` - PDF page → PNG base64
- `crop_image_from_page()` - Crop bbox from PDF with 8% padding (250 DPI)
- `refine_crop_with_ai()` - Use Gemini Vision to improve crop

**Classification** (AI-Powered)
- `classify_and_structure_with_gemini()` - One Gemini call: structure + classify
  - Input: Mathpix Markdown (truncated to 30k chars)
  - Output: Structured JSON with topics (28 categories) + difficulty (bronze/silver/gold)
  - Handles tables, images, geometric labels
- `extract_mark_scheme_from_page()` - Gemini Vision: extract mark entries from page image
- `extract_diagram_from_page()` - Gemini Vision: detect diagram bounding boxes

**GE ID Generation** (Hierarchical)
- `generate_ge_code()` - Paper level: GE{year}{board}{paper} → GE17EX1
- `generate_ge_question_id()` - Question level: GE17EX126001
- `generate_ge_part_id()` - Part level: GE17EX126001A

**Storage**
- `init_storage()` - Connect to Emergent cloud or use local
- `put_object()` - Save file (local or cloud)
- `get_object()` - Retrieve file (tries local first, then cloud)

### Data Flow
```
PDF Upload → Mathpix → Markdown + Images → Parse & Structure → Classify → Store → MongoDB
     ↓          ↓              ↓                      ↓            ↓         ↓
  Local FS   Mathpix API   Crop Images        Gemini Vision    GE IDs    Questions
                                                                         + Topics
                                                                         + Difficulty
```

### Status Tracking
- Paper: processing → extracted → reviewed
- Question: draft → needs_review → approved
- ExtractionJob: pending → processing → completed/failed

---

## FRONTEND ANALYSIS (App.js - 1,405 lines)

### Architecture
- **Framework**: React 19 + Tailwind CSS
- **Math Rendering**: KaTeX (InlineMath/BlockMath for LaTeX)
- **Icons**: Phosphor Icons (sharp, duotone)
- **HTTP**: Axios
- **Routing**: React Router (BrowserRouter)
- **Notifications**: Sonner (toast)
- **Design**: Brutalist (hard borders, no shadows/rounded corners)

### Key Configuration
```javascript
BACKEND_URL = process.env.REACT_APP_BACKEND_URL
API = `${BACKEND_URL}/api`
```

### Main Components (13 Components)

#### Helper Functions
- `renderLatex(text, latex)` - Smart LaTeX rendering:
  - Handles tables (\begin{tabular})
  - Handles delimiters (\( \) and \[ \])
  - Detects LaTeX commands
  - Fallback to plain text for long English words

#### UI Components
1. **StatusTag** - Display question status (draft/processing/approved/etc)
   - CSS classes: status-draft, status-processing, status-needs-review, status-approved
2. **DifficultyBadge** - Bronze/Silver/Gold with colors
   - Colors: amber/slate/yellow
3. **TopicTags** - Editable topic selector with dropdown
   - Shows 28-30 GCSE topics organized by category
4. **ProgressBar** - Horizontal progress visualization
5. **PDFUploadZone** - Drag-drop file upload
   - Dropzone: 2px dashed black border
   - Hover: changes to solid, bg-slate-100
6. **PaperForm** - Create new paper (board, year, paper#, tier)

#### Main Features
7. **ExtractionStatus** - Progress tracking
   - Shows: status, page progress, questions found, images extracted
   - Polls `/extraction-jobs/{job_id}` every 2 seconds
8. **QuestionList** - Left pane: question rows
   - Filters: status, topic, difficulty
   - Shows: Q#, GE ID, icons (diagram/table/mark-scheme), difficulty, status, marks
9. **MarkSchemePanel** - Right bottom: mark scheme details
   - Shows entries with M (method) / A (accuracy) / B marks
   - Alternative answers and follow-through notes
10. **QuestionDetail** - Main editing panel
    - Edit: text, marks, parts, images, difficulty, topics
    - Replace/add/remove images
    - Approve/reject buttons
    - Status: draft/needs_review/approved

#### Main App Flow
11. **App Component** (Main)
    - Dual-pane layout: left (40%) = questions, right (60%) = details
    - Top: Paper form + extraction zone
    - States: selectedQuestion, questions, papers, selectedPaper
    - Handles: create paper → upload PDF → extract → review → approve

---

## Current Features Status

### ✅ Implemented & Working
- React UI with Tailwind CSS + Phosphor Icons
- Paper creation form (board, year, tier, session)
- PDF upload with progress tracking
- LaTeX rendering with KaTeX
- Question list with filters (status, topic, difficulty)
- Question editing (text, marks, parts)
- Difficulty tagging (bronze/silver/gold)
- Topic assignment (28 GCSE categories)
- Mark scheme panel
- GE ID hierarchy (paper → question → part)
- Image display
- Approve/reject workflow
- Cost tracking UI for API calls
- Responsive layout (left pane scrollable, right pane detail)

### ❌ Not Working / Blocked
- **PDF Extraction** - Mathpix API credentials MISSING
  - `mathpix_submit_pdf()` will fail silently
  - No markdown generation
  - No image URLs from Mathpix
  - Extraction pipeline stalls at Step 2
- **Image Extraction** - Cannot download images without Mathpix
- **Classification** - No structured questions to classify
- **Mark Scheme Upload** - No backend endpoint implemented yet

### ⚠️ Partial/Needs Testing
- Re-extraction endpoint (POST `/papers/{paper_id}/re-extract`)
- Image replacement workflow
- Mark scheme linking
- Database queries for filtering
- Async job tracking

---

## Critical Issues & Next Steps

### 🔴 CRITICAL BLOCKER: Test Backend Environment Variables NOT Loaded
**Location**: VPS at `/opt/ge-test/` - docker-compose issue

**The Problem**:
- Production backend (ge-backend) has env vars loaded ✅
- Test backend (ge-test-backend) has NO env vars loaded ❌
- Result: Test backend can't connect to MongoDB, APIs, or do any extraction

**Evidence**:
```
docker inspect ge-test-backend | grep -A 20 "Env"
Shows only: PATH, LANG, PYTHON_VERSION (no MONGO_URL, no GEMINI_KEY, nothing)

vs Production (ge-backend):
Shows: MONGO_URL, DB_NAME, GEMINI_API_KEY, MATHPIX_APP_ID/KEY, CORS_ORIGINS
```

**Why It's Happening**:
1. `/opt/ge-test/docker-compose.yml` is missing `env_file: - ./backend/.env.production`
2. OR the path is incorrect relative to where docker-compose runs
3. OR the backend/.env.production file is empty/corrupted

**Fix Priority**: 🔥 CRITICAL #1 - Check docker-compose.yml on VPS

**Steps to Fix**:
1. SSH to VPS: `cat /opt/ge-test/docker-compose.yml` (verify env_file exists)
2. Check file: `cat /opt/ge-test/backend/.env.production` (verify not empty)
3. Rebuild: `cd /opt/ge-test && docker-compose down && docker-compose build && docker-compose up -d`
4. Verify: `docker inspect ge-test-backend | grep MONGO_URL` (should show value)

---

### 🔴 BLOCKING ISSUE #2: Missing Mathpix Credentials in Test
**Location**: `/opt/ge-test/backend/.env.production`

**Missing**:
```
MATHPIX_APP_ID=geniuseducation_1bf00a_260351     ← Copy from production
MATHPIX_APP_KEY=53e84190eb.....5edc4c95685e5d9fb ← Copy from production
```

**Also Missing** in `/opt/ge-test/.env`:
```
REACT_APP_BACKEND_URL=http://187.124.54.5:9001
MONGO_ROOT_PASSWORD=ISbZh4mWYYh6.........DT0qLg
```

**Fix Priority**: 🔥 CRITICAL #2 - After fixing docker-compose loading

### Expected Files After Fix
```
backend/.env.production
├── MONGO_URL=mongodb://admin:PASSWORD@mongo:27017
├── DB_NAME=ge_question_bank
├── CORS_ORIGINS=https://apps.geniuseducation.co.uk
├── GEMINI_API_KEY=YOUR_GEMINI_KEY
├── MATHPIX_APP_ID=YOUR_APP_ID ← MISSING
└── MATHPIX_APP_KEY=YOUR_APP_KEY ← MISSING
```

---

## Technical Debt & Observations

1. **Error Handling**: Limited fallback for Mathpix failures
2. **Timeout**: 5 min max for Mathpix processing (may be tight for large PDFs)
3. **Image Padding**: Fixed 8% padding - may clip on unusual layouts
4. **LaTeX Parsing**: Regex-based - fragile for edge cases
5. **Topics**: Hardcoded 28 topics - should be configurable
6. **Test Coverage**: No unit/integration tests found

---

## Environment Setup Checklist

- [ ] Mathpix credentials acquired
- [ ] `backend/.env.production` created
- [ ] `backend/.env` created (dev)
- [ ] `.env` created (root, for docker-compose)
- [ ] MongoDB running
- [ ] Backend API accessible at http://localhost:8001/api
- [ ] Frontend running at http://localhost
- [ ] First PDF upload tested

---

---

## Environment Setup - FIXED ✅

### Files Updated for Better Documentation
1. **.env.example** - Enhanced with detailed comments about each variable
2. **backend/.env.example** - Comprehensive guide with API links and instructions
3. **docker-compose.test.yml** - NEW file for test environment (separate from production)

### For VPS Test Environment Setup

**Step 1: Create backend/.env.production**
```bash
cd /opt/ge-test
cp backend/.env.example backend/.env.production

# Edit with your credentials:
nano backend/.env.production
```

Fill in:
```
MONGO_URL=mongodb://admin:ISbZh4mWYYh6.........@mongo-test:27017
DB_NAME=ge_question_bank_test
CORS_ORIGINS=*
GEMINI_API_KEY=AIzaSyD5TA...........
EMERGENT_LLM_KEY=sk-emergent-84515Bb57D...
MATHPIX_APP_ID=geniuseducation_1bf00a_260351
MATHPIX_APP_KEY=53e84190eb.....5edc4c95685e5d9fb
```

**Step 2: Create .env**
```bash
nano /opt/ge-test/.env
```

Fill in:
```
REACT_APP_BACKEND_URL=http://187.124.54.5:9001
MONGO_ROOT_USERNAME=admin
MONGO_ROOT_PASSWORD=ISbZh4mWYYh6.........
```

**Step 3: Use test docker-compose**
```bash
cd /opt/ge-test
docker-compose -f docker-compose.test.yml down
docker-compose -f docker-compose.test.yml build --no-cache
docker-compose -f docker-compose.test.yml up -d
```

**Step 4: Verify env vars loaded**
```bash
docker inspect ge-test-backend | grep -A 30 "Env" | grep MATHPIX
```

Should show:
```
"MATHPIX_APP_ID=geniuseducation_1bf00a_260351",
"MATHPIX_APP_KEY=53e84190eb.....5edc4c95685e5d9fb",
```

**Step 5: Test the API**
```bash
curl http://187.124.54.5:9001/api/health
```

---

---

## Secret Storage Architecture - Production vs Test

### How Secrets Flow Into Docker Containers

```
┌─────────────────────────────────────────────────────────────┐
│ PRODUCTION (/opt/ge) - ✅ WORKING                           │
├─────────────────────────────────────────────────────────────┤
│ 1. DISK                                                     │
│    /opt/ge/backend/.env.production                          │
│    ├─ MONGO_URL=mongodb://admin:PASSWORD@mongo:27017       │
│    ├─ GEMINI_API_KEY=AIzaSyD5TAgHP.....                    │
│    └─ MATHPIX_APP_ID=geniuseducation_1bf00a_260351         │
│                                                              │
│ 2. docker-compose.yml (Line 6-7)                           │
│    env_file:                                                │
│      - ./backend/.env.production   ← LOADS SECRETS          │
│                                                              │
│ 3. Docker Container (docker inspect ge-backend)             │
│    "Env": [                                                  │
│      "MONGO_URL=mongodb://admin:IS...@mongo:27017",        │
│      "GEMINI_API_KEY=.......",                              │
│      "MATHPIX_APP_ID=geniuseducation_1bf00a_260351",      │
│      ...                                                     │
│    ]                                                        │
│                                                              │
│ 4. Application (backend/server.py:30)                       │
│    mongo_url = os.environ.get('MONGO_URL')  ← HAS VALUE     │
│    client = AsyncIOMotorClient(mongo_url)   ← CONNECTS ✅   │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ TEST (/opt/ge-test) - ❌ BROKEN                             │
├─────────────────────────────────────────────────────────────┤
│ 1. DISK                                                     │
│    /opt/ge-test/backend/.env.production                     │
│    ├─ MONGO_URL=mongodb://admin:PASSWORD@mongo-test:27017  │
│    ├─ GEMINI_API_KEY=AIzaSyD5TA...........                  │
│    └─ ❌ MISSING MATHPIX_APP_ID                            │
│                                                              │
│ 2. docker-compose.yml                                       │
│    ❌ NOT LOADING env_file!                                 │
│    (either missing directive or wrong path)                │
│                                                              │
│ 3. Docker Container (docker inspect ge-test-backend)        │
│    "Env": [                                                  │
│      "PATH=/usr/local/bin:/...",    ← Only defaults!        │
│      "LANG=C.UTF-8",                                        │
│      "PYTHON_VERSION=3.11.15",                              │
│      ... NO MONGO_URL, NO CREDENTIALS                       │
│    ]                                                        │
│                                                              │
│ 4. Application (backend/server.py:30)                       │
│    mongo_url = os.environ.get('MONGO_URL')  ← RETURNS None! │
│    client = AsyncIOMotorClient(None)        ← CRASHES ❌    │
└─────────────────────────────────────────────────────────────┘
```

### Key Insight
**Secrets are stored the SAME way in both environments (disk files).**
**The difference is HOW docker-compose.yml loads them into containers.**

---

## Last Updated
2026-04-19 - Full codebase analysis completed
2026-04-19 - Fixed environment configuration and added docker-compose.test.yml
2026-04-19 - Analyzed secret storage flow: Production (working) vs Test (broken)
