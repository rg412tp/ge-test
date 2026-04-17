# GCSE Question Bank Platform - PRD

## Original Problem Statement
Build a database to extract GCSE Maths questions from PDF files. Extract questions with their diagrams, crop images cleanly (no bleeding text), and store in a database format for reuse. Later stages will add marks, difficulty levels, subjects, and marking schemes.

## User Personas
1. **Maths Tutor** - Uploads past papers, reviews extracted questions, builds question banks for students
2. **Admin/Reviewer** - Approves/rejects extracted questions, ensures quality

## Core Requirements (Static)
- Upload GCSE Maths question paper PDFs
- AI-powered extraction of questions and parts (Q1, Q1a, Q1b, etc.)
- Extract and crop diagrams/graphs/tables cleanly
- Store structured data in MongoDB
- Review interface for approval workflow
- Support for AQA, Edexcel, OCR exam boards

## Architecture
- **Frontend**: React 19 with Tailwind CSS, Phosphor Icons
- **Backend**: FastAPI with Motor (async MongoDB)
- **Database**: MongoDB
- **AI**: OpenAI GPT-5.2 with vision (via Emergent LLM key)
- **Storage**: Emergent Object Storage for PDFs and images

## What's Been Implemented (Phase 1 MVP)
**Date: January 2026**

### Backend
- Paper CRUD endpoints (create, list, get)
- PDF upload with object storage
- AI extraction pipeline using GPT-5.2 vision
- Question extraction with parts detection
- Diagram boundary detection and cropping
- Image asset storage and retrieval
- Question approval/reject workflow
- Stats endpoint

### Frontend
- Swiss/brutalist dual-pane dashboard
- Paper creation form (board, year, paper, tier, session)
- PDF drag-and-drop upload zone
- Extraction progress tracking
- Question list with filtering
- Question detail view with diagrams
- Approve/Reject buttons
- Stats display

## Prioritized Backlog

### P0 (Critical - Next)
- Test with real GCSE PDF papers
- Improve diagram cropping accuracy
- Add LaTeX rendering for mathematical expressions

### P1 (Important)
- Mark scheme PDF upload and linking
- Add marks field editing
- Difficulty level tagging (Bronze/Silver/Gold)
- Topic/subject tagging

### P2 (Nice to Have)
- Bulk question approval
- Export questions to various formats
- Question search by text/topic
- User authentication

## Next Tasks
1. Upload actual GCSE past paper PDFs to test extraction
2. Fine-tune AI prompts for better question boundary detection
3. Improve image cropping with padding adjustments
4. Add mark scheme extraction workflow
5. Implement LaTeX rendering for math expressions
