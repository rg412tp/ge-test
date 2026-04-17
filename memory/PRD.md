# GCSE Question Bank Platform - PRD

## Original Problem Statement
Build a database for Genius Education (GE) tuition center to extract GCSE Maths questions from PDF files. Extract questions with their diagrams, crop images cleanly (no bleeding text), and store in a database format for reuse. Custom GE ID system for parent-child question tracking. Support marks, difficulty levels, topics, and marking schemes.

## User Personas
1. **Maths Tutor (GE)** - Uploads past papers, reviews extracted questions, builds question banks for students
2. **Admin/Reviewer** - Approves/rejects extracted questions, ensures quality, tags difficulty & topics

## Core Requirements (Static)
- Upload GCSE Maths question paper PDFs
- AI-powered extraction of questions and parts (Q1, Q1a, Q1b, etc.)
- Extract and crop diagrams/graphs/tables cleanly
- Custom GE ID system: GE-{year}-P{paper}-Q{number}, sub-parts append A/B/C
- Store structured data in MongoDB
- Review interface for approval workflow
- Support for AQA, Edexcel, OCR exam boards
- Mark scheme upload, extraction, and linking
- Difficulty tagging: Bronze, Silver, Gold
- Topic tagging: 30 GCSE topics across 4 categories
- LaTeX rendering for mathematical expressions

## Architecture
- **Frontend**: React 19 with Tailwind CSS, Phosphor Icons, KaTeX
- **Backend**: FastAPI with Motor (async MongoDB)
- **Database**: MongoDB
- **AI**: OpenAI GPT-5.2 with vision (via Emergent LLM key)
- **Storage**: Emergent Object Storage for PDFs and images

## GE ID System
- Paper: `GE-{year}-P{paper_number}` → e.g., GE-2017-P1
- Question: `GE-{year}-P{paper}-Q{number}` → e.g., GE-2017-P1-Q01
- Part: `GE-{year}-P{paper}-Q{number}{LETTER}` → e.g., GE-2017-P1-Q01A, GE-2017-P1-Q01B
- Parent-child: Question ge_id links to paper ge_code, part ge_id links to question ge_id

## What's Been Implemented

### Phase 1 (Jan 2026)
- Paper CRUD, PDF upload, AI extraction pipeline, question approval workflow, stats, Swiss brutalist UI

### Phase 2 (Apr 2026)
- **CRITICAL FIX**: Fixed `image_contents` → `file_contents` in GPT-5.2 vision calls (was causing all extractions to fail)
- GE ID system for papers, questions, and parts
- Mark scheme PDF upload + AI extraction + auto-linking to questions
- 30 GCSE topics across 4 categories (Number, Algebra, Geometry, Statistics)
- Difficulty tagging (Bronze/Silver/Gold)
- LaTeX rendering with KaTeX for mathematical expressions
- Dual upload zones (question paper + mark scheme)
- Enhanced filtering by status, topic, and difficulty
- Mark type breakdown (M/A/B marks) in mark scheme

## Prioritized Backlog

### P0 (Next)
- Test with real GCSE PDF papers to validate extraction quality
- Verify image cropping accuracy on actual papers

### P1 (Important)
- Bulk question approval
- Export questions to PDF/docx formats
- Question search by text/topic

### P2 (Nice to Have)
- User authentication
- Assignment generation from question bank
- Student-facing delivery
