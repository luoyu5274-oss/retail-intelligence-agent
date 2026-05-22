# Retail Intelligence Agent

AI-powered competitive analysis platform for sportswear brands. Parses Nike, Adidas, and Lululemon annual/quarterly report PDFs with LLM extraction, vector search, and calendar-aligned cross-brand comparison.

![Tech Stack](https://img.shields.io/badge/backend-Python%2FFastAPI-blue) ![Frontend](https://img.shields.io/badge/frontend-React%2FRecharts-orange) ![LLM](https://img.shields.io/badge/LLM-DeepSeek%20V4%20Flash-green) ![Status](https://img.shields.io/badge/status-complete-brightgreen)

## Preview

- Dashboard with KPI cards, revenue/margin charts, radar, and regional breakdown
- AI Q&A with vector search across 12 annual report PDFs (~5,000 pages)
- Inline chart toggle — click "Chart" on any table to render a bar/combo chart
- Calendar-aligned quarterly comparison across 3 brands with different fiscal year ends

## Architecture

```
├── backend/                  # FastAPI (port 8000)
│   ├── main.py              # API endpoints + chat system
│   ├── config.py            # Brand config, 12 PDFs across 3 brands
│   ├── pdf_parser.py        # PDF parsing + chunking (pdfplumber)
│   ├── vector_store.py      # TF-IDF vector index (sklearn, 2,450 chunks)
│   ├── llm_client.py        # DeepSeek API client
│   ├── financial_extractor.py  # LLM extraction pipeline + chart builder
│   └── quarterly_extractor.py  # Quarterly report extraction + calendar mapping
├── frontend/                 # React 19 + Vite 8
│   └── src/
│       ├── App.jsx          # Sidebar nav, split ready state
│       ├── App.css          # Warm minimal theme
│       └── components/
│           ├── Dashboard.jsx  # KPI cards, charts, quarterly comparison
│           ├── Chat.jsx       # Q&A with markdown + inline chart toggle
│           └── Updates.jsx    # Data source management
└── data/                     # Static data files
    ├── dashboard_data.json   # Verified financial data (12 reports)
    ├── quarterly_data.json   # Calendar-aligned quarterly data (9 reports)
    └── vector_store.npz      # TF-IDF index
```

## Quick Start

### Prerequisites

- Python 3.10+
- Node.js 18+
- DeepSeek API key (for chat/vector extraction)

### Setup

```bash
# Clone
git clone <repo-url>
cd retail-intel

# Backend
cd backend
pip install -r requirements.txt
# Create backend/.env with: DEEPSEEK_API_KEY=sk-xxx
python -m uvicorn main:app --host 0.0.0.0 --port 8000

# Frontend (new terminal)
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173` — dashboard loads instantly with static data. Click "Initialize" to build the vector index for Q&A.

## Features

### Smart Q&A with Vector Search
Ask questions about any brand's annual report data. TF-IDF vector search retrieves relevant text chunks from 12 PDFs, fed to DeepSeek V4 Flash for context-aware answers with source citations.

### Inline Chart Toggle
LLM responses with markdown tables get a "Chart" button. Click to render inline bar/combo charts — auto-detects percentage columns and renders them as lines on a dual-axis chart.

### Calendar-Aligned Quarterly Comparison
Solved the fiscal year misalignment problem: Nike (May), Adidas (Dec), Lululemon (late Jan). Quarterly reports are mapped to actual calendar months, enabling true apples-to-apples comparison.

### Static Dashboard Architecture
Dashboard KPIs and charts load from curated static JSON — instant load, zero API cost, no LLM dependency. Chat/vector search runs independently with its own ready state.

## Data Coverage

| Brand | Annual Reports | Quarterly Reports | Currency |
|-------|---------------|-------------------|----------|
| Nike | FY2022–2025 | Q1–Q3 FY2025 | USD |
| Adidas | FY2022–2025 | Q3 FY2024, Q1–Q3 FY2025 | EUR |
| Lululemon | FY2022–2025 | Q3 FY2024, Q1–Q3 FY2025 | USD |

## Key Design Decisions

| Decision | Approach | Rationale |
|----------|----------|-----------|
| Vector store | TF-IDF over SentenceTransformer | Index time: 2s vs 16min on CPU |
| Dashboard data | Static JSON over LLM extraction | Eliminates quality variance + 15min init |
| Financial pipeline | 5-step: extract → normalize → validate → retry → back-calculate | Auto-fix LLM errors (units, missing fields) |
| Chart toggle | Frontend table parsing over LLM format | No extra prompt engineering needed |
| Quarterly mapping | Calendar months over fiscal labels | Enables true cross-brand comparison |

## Tech Stack

- **Backend:** Python, FastAPI, pdfplumber, scikit-learn, NumPy, OpenAI SDK
- **Frontend:** React 19, Recharts 2, Vite 8, CSS Variables
- **LLM:** DeepSeek V4 Flash (via `deepseek-chat`)
- **Design:** Playfair Display + Inter + JetBrains Mono, warm minimal palette
