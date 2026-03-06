# CVForge — Product Requirements Document (v1.0)

## 1. Overview

**CVForge** is a local-first, hybrid (CLI + Web UI) tool that helps developers tailor their CV per job application, score it against ATS systems, and export clean PDFs — all without touching LibreOffice or any cloud service.

**Target User:** The developer themselves (single-user tool).

**Core Philosophy:**
- Offline-first, no external dependencies for core functionality
- Master CV is the single source of truth — never edit outputs directly
- Spec-driven development (OpenSpec)
- LLM integration is future-scoped but architecturally planned (modular adapter)

---

## 2. Problem Statement

Applying for jobs as a multi-disciplinary developer (full-stack + data science) requires frequent CV and cover letter tailoring. Current workflow pain points:

1. No MS Word on Ubuntu; LibreOffice is clunky for frequent edits and PDF exports
2. Cover letters must be rewritten per JD (future scope)
3. CVs fail ATS screening despite appearing well-formatted — root cause unclear

---

## 3. MVP Scope

### 3.1 In Scope (v1)

| Feature | Description |
|---------|-------------|
| Master CV (YAML) | Single YAML file containing all experiences, skills, projects, education — tagged by category |
| JD Parser | Extract keywords, required skills, and role metadata from pasted/uploaded job descriptions |
| CV Tailoring Engine | Match JD keywords against master CV → auto-select and reorder relevant sections |
| ATS Scorer | Keyword match %, format health checks, actionable suggestions |
| PDF Export | ATS-safe, single-column PDF from HTML/CSS templates via WeasyPrint |
| CV Templates | 2–3 selectable HTML/CSS templates (minimal, modern, academic) |
| CLI Interface | `cvforge tailor`, `cvforge score`, `cvforge export` |
| Web UI | Paste JD → preview tailored CV → tweak selections → download PDF |

### 3.2 Out of Scope (Future)

- LLM-assisted cover letter generation (adapter interface defined, not implemented)
- Job application tracker
- Multiple master CV profiles
- Cloud sync or multi-device support
- User authentication (single-user, local tool)

---

## 4. Architecture

### 4.1 System Design

```
┌─────────────┐     ┌─────────────┐
│   CLI        │     │   Web UI    │
│  (Typer)     │     │  (React +   │
│              │     │   FastAPI)  │
└──────┬───────┘     └──────┬──────┘
       │                    │
       └────────┬───────────┘
                │
        ┌───────▼────────┐
        │   Core Engine   │
        │   (Python)      │
        ├─────────────────┤
        │ • jd_parser     │
        │ • matcher       │
        │ • scorer        │
        │ • renderer      │
        │ • yaml_loader   │
        └───────┬─────────┘
                │
    ┌───────────┼───────────┐
    │           │           │
┌───▼───┐ ┌────▼────┐ ┌────▼────┐
│Master │ │Templates│ │Synonyms │
│CV.yaml│ │(HTML/CSS│ │  .yaml  │
│       │ │+Jinja2) │ │         │
└───────┘ └─────────┘ └─────────┘
```

**Key Principle:** CLI and Web UI are thin wrappers around the shared core engine. All logic lives in `core/`.

### 4.2 Project Structure

```
cvforge/
├── core/                   # Shared Python engine
│   ├── __init__.py
│   ├── yaml_loader.py      # Parse & validate master_cv.yaml
│   ├── jd_parser.py        # JD keyword/skill extraction
│   ├── matcher.py          # Match JD ↔ master CV sections
│   ├── scorer.py           # ATS scoring + format health checks
│   ├── renderer.py         # Jinja2 → HTML → PDF pipeline
│   └── llm/                # Future: LLM adapter layer
│       ├── __init__.py
│       └── base.py         # Abstract base class (interface only)
│
├── cli/                    # CLI interface
│   ├── __init__.py
│   └── main.py             # Typer commands
│
├── web/                    # Web interface
│   ├── api/                # FastAPI backend
│   │   ├── __init__.py
│   │   └── routes.py
│   └── client/             # Minimal React frontend
│       ├── src/
│       └── package.json
│
├── templates/              # CV HTML/CSS templates
│   ├── minimal/
│   │   ├── template.html
│   │   └── style.css
│   ├── modern/
│   │   ├── template.html
│   │   └── style.css
│   └── academic/
│       ├── template.html
│       └── style.css
│
├── data/
│   ├── master_cv.yaml      # User's master CV (source of truth)
│   └── synonyms.yaml       # Skill synonym mappings
│
├── output/                 # Generated PDFs
│
├── specs/                  # OpenSpec files
│
├── tests/
│
├── pyproject.toml
└── README.md
```

---

## 5. Tech Stack

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| Core engine | Python 3.11+ | Rich NLP/PDF ecosystem, developer's strength |
| Master CV format | YAML | Human-readable, git-friendly, hand-editable |
| JD keyword extraction | spaCy + RAKE (via `multi_rake` or `yake`) | Offline, fast, no API dependency |
| Skill matching | RapidFuzz + custom synonym map | Handles abbreviations, aliases, fuzzy variants |
| CV templates | Jinja2 + HTML/CSS | Full design control, easy to add new templates |
| PDF generation | WeasyPrint | HTML/CSS → PDF, no LibreOffice dependency, ATS-safe output |
| CLI framework | Typer | Clean DX, auto-generated help, type hints |
| Web backend | FastAPI | Lightweight, async, pairs well with Typer |
| Web frontend | React (minimal) | Component-based, developer knows it |
| Storage | File system (YAML + PDFs) | No DB overhead, everything local and portable |

---

## 6. Data Models

### 6.1 Master CV Schema (`master_cv.yaml`)

```yaml
personal:
  name: "Fahim Forhad"
  email: "fahimforhad.brisbane@gmail.com"
  phone: "0416792302"
  location: "Red Hill, Queensland"
  visa: "485 Graduate Temporary (Full Working Rights)"
  linkedin: "https://linkedin.com/in/fahimforhad"   # Full URLs for ATS
  github: "https://github.com/fahimforhad"

# --- Role Variants ---
# Each role_variant defines a title + summary + skill ordering + experience framing
# The tailoring engine selects the closest variant based on JD match, then fine-tunes
role_variants:
  software_engineer:
    title: "Software Engineer"
    summary: >
      Full-stack Software Engineer with 4+ years building scalable web applications
      and leading engineering teams. Combines strong React/Node.js expertise with
      recent Master's in Data Science to deliver high-performance, data-informed
      products. Reduced platform load times by 50% for 100K+ users through
      optimization and collaborative problem-solving. Thrives in team-oriented
      environments that value technical craftsmanship and continuous learning.
    skill_priority: ["frontend", "backend", "devops", "data-science"]

  ml_engineer:
    title: "Machine Learning Engineer"
    summary: >
      Data and Machine Learning Engineer with 4+ years of industry experience
      building data-driven systems, applied machine learning pipelines, and
      production analytics platforms. Strong background in Python, machine learning,
      data engineering, and cloud-based deployments, complemented by hands-on
      experience delivering secure federated learning systems and predictive
      analytics solutions. Proven ability to translate business and research
      requirements into scalable, production-ready ML and data solutions.
    skill_priority: ["ml", "data-engineering", "analytics", "devops", "frontend"]

  data_engineer:
    title: "Data Engineer"
    summary_base: "ml_engineer"  # Reuse ML engineer summary with minor tweaks
    skill_priority: ["data-engineering", "ml", "devops", "backend"]

# --- Skills ---
# Grouped by category for rendering; each skill tagged for matching
skill_groups:
  - group: "Programming & Query Languages"
    skills:
      - name: "Python"
        aliases: ["python3"]
        tags: ["backend", "data-science", "ml", "data-engineering"]
      - name: "SQL"
        aliases: []
        tags: ["backend", "data-engineering", "analytics"]
      - name: "Bash"
        aliases: ["shell", "shell scripting"]
        tags: ["devops", "backend"]
      - name: "JavaScript"
        aliases: ["JS", "ES6", "ES6+", "ECMAScript"]
        tags: ["frontend", "fullstack"]
      - name: "TypeScript"
        aliases: ["TS"]
        tags: ["frontend", "fullstack"]
      - name: "C#"
        aliases: ["csharp", "c-sharp"]
        tags: ["backend"]

  - group: "Frontend Development"
    tags: ["frontend"]
    skills:
      - name: "React.js"
        aliases: ["React", "ReactJS"]
        tags: ["frontend"]
      - name: "HTML5"
        aliases: ["HTML"]
        tags: ["frontend"]
      - name: "CSS3"
        aliases: ["CSS"]
        tags: ["frontend"]
      - name: "SCSS"
        aliases: ["Sass"]
        tags: ["frontend"]
      - name: "Tailwind"
        aliases: ["Tailwind CSS", "TailwindCSS"]
        tags: ["frontend"]
      - name: "Responsive Design"
        tags: ["frontend"]
      - name: "Performance Optimization"
        tags: ["frontend"]
      - name: "Unit Testing"
        aliases: ["Jest", "React Testing Library"]
        tags: ["frontend", "testing"]

  - group: "Backend & Databases"
    skills:
      - name: "Express"
        aliases: ["Express.js"]
        tags: ["backend"]
      - name: "REST APIs"
        aliases: ["RESTful APIs", "REST"]
        tags: ["backend", "fullstack"]
      - name: "GraphQL"
        tags: ["backend", "frontend"]
      - name: "Authentication & RBAC"
        aliases: ["Auth", "RBAC", "OAuth"]
        tags: ["backend", "security"]
      - name: "PostgreSQL"
        aliases: ["Postgres", "psql"]
        tags: ["backend", "data-engineering"]
      - name: "MongoDB"
        aliases: ["Mongo"]
        tags: ["backend"]
      - name: "Redis"
        tags: ["backend"]

  - group: "Data Engineering"
    skills:
      - name: "Data Pipelines"
        aliases: ["ETL", "ELT", "ETL/ELT"]
        tags: ["data-engineering"]
      - name: "Feature Engineering"
        tags: ["data-engineering", "ml"]
      - name: "Data Cleaning"
        aliases: ["Data Wrangling"]
        tags: ["data-engineering", "analytics"]
      - name: "Synthetic Data Generation"
        tags: ["data-engineering", "ml"]
      - name: "Data Validation"
        tags: ["data-engineering"]

  - group: "Machine Learning"
    skills:
      - name: "Scikit-learn"
        aliases: ["sklearn"]
        tags: ["ml", "data-science"]
      - name: "PyTorch"
        tags: ["ml", "deep-learning"]
      - name: "Predictive Modelling"
        aliases: ["Predictive Modeling"]
        tags: ["ml", "data-science"]
      - name: "Model Training & Evaluation"
        tags: ["ml"]
      - name: "Model Deployment"
        tags: ["ml", "devops"]
      - name: "Federated Learning"
        tags: ["ml", "security", "distributed-systems"]

  - group: "Analytics & Visualisation"
    skills:
      - name: "Pandas"
        tags: ["analytics", "data-science"]
      - name: "NumPy"
        tags: ["analytics", "data-science"]
      - name: "Matplotlib"
        tags: ["analytics", "data-viz"]
      - name: "Power BI"
        tags: ["analytics", "data-viz"]
      - name: "Tableau"
        tags: ["analytics", "data-viz"]
      - name: "Exploratory Data Analysis"
        aliases: ["EDA"]
        tags: ["analytics", "data-science"]

  - group: "DevOps & Engineering Practices"
    skills:
      - name: "Docker"
        aliases: ["Docker Compose"]
        tags: ["devops"]
      - name: "Git"
        aliases: ["GitHub", "Git/GitHub"]
        tags: ["devops"]
      - name: "CI/CD"
        aliases: ["GitHub Actions", "CI", "CICD"]
        tags: ["devops"]
      - name: "Linux"
        aliases: ["Ubuntu", "Debian"]
        tags: ["devops"]
      - name: "Azure Machine Learning"
        aliases: ["Azure ML"]
        tags: ["devops", "ml", "cloud"]
      - name: "Agile/Scrum"
        aliases: ["Agile", "Scrum"]
        tags: ["process"]
      - name: "Code Reviews"
        tags: ["process"]

# --- Experience ---
# Each role has role_variants to control title/framing per CV type
# Highlights individually tagged for granular selection
experience:
  - company: "Queensland Cyber Infrastructure Federation (QCIF)"
    location: "Brisbane, AU"
    start: "2025-09"
    end: "2025-12"
    role_variants:
      software_engineer: "Software Engineer (ML Security Engineer)"
      ml_engineer: "Machine Learning Engineer (Security & Distributed Systems)"
      data_engineer: "Data Engineer (Distributed Systems)"
    tags: ["ml", "security", "devops", "distributed-systems"]
    highlights:
      - text: "Designed and deployed a secure, containerised federated learning environment using Docker and Docker Compose, validating up to 4 concurrent federated nodes on a local testbed with a computer vision dataset"
        tags: ["ml", "devops", "docker", "federated-learning"]
      - text: "Architected the system for horizontal scaling beyond local hardware constraints, separating server and client components to support multi-organisation deployments"
        tags: ["architecture", "distributed-systems", "scalability"]
      - text: "Automated end-to-end provisioning with shell scripts, reducing environment setup time from several hours to under 30 minutes"
        tags: ["devops", "automation", "bash"]
        variant_only: ["software_engineer"]  # Only show for SWE variant
      - text: "Implemented privacy-preserving service communication using mTLS, OpenVPN, and Keycloak (OIDC), enabling ML training without direct data transfer"
        tags: ["security", "ml", "devops"]
      - text: "Conducted system testing to identify bottlenecks and security risks, producing actionable recommendations for production readiness"
        tags: ["testing", "security", "performance"]
      - text: "Authored comprehensive deployment and security documentation"
        tags: ["documentation"]

  - company: "Sarina Russo Group"
    location: "Brisbane, AU"
    start: "2025-05"
    end: "2025-08"
    role_variants:
      software_engineer: "Software Engineer (Data and Analytics)"
      ml_engineer: "Data Engineer"
      data_engineer: "Data Engineer"
    tags: ["data-engineering", "ml", "analytics"]
    highlights:
      - text: "Built a complete predictive analytics pipeline (research, feature engineering, training, deployment) to identify at-risk students and support early intervention"
        tags: ["ml", "data-engineering", "pipeline"]
      - text: "Designed and delivered an interactive Power BI dashboard used by academic and support staff, replacing spreadsheet-based reporting"
        tags: ["analytics", "data-viz", "power-bi"]
      - text: "Generated synthetic datasets to validate model behaviour under data privacy constraints"
        tags: ["data-engineering", "ml", "privacy"]
      - text: "Produced user documentation and led a client handover, allowing continued use without ongoing engineering support"
        tags: ["documentation", "stakeholder-management"]

  - company: "Gain Solutions"
    location: "Dhaka, Bangladesh"
    start: "2021-09"
    end: "2023-11"
    role_variants:
      software_engineer: "Frontend Team Lead"
      ml_engineer: "Frontend Team Lead"
      data_engineer: "Frontend Team Lead"
    tags: ["frontend", "leadership", "performance"]
    highlights:
      - text: "Led frontend development for Uniteliving.no, a property platform serving 650+ partner organisations and 100,000+ users"
        tags: ["frontend", "leadership", "large-scale"]
      - text: "Implemented key platform features including Google Maps–based property search, real-time chat, and comprehensive settings module"
        tags: ["frontend", "react", "fullstack"]
        variant_only: ["software_engineer"]
      - text: "Reduced modal and table rendering time from ~7s to ~1.3s using React optimisation techniques (React.memo, useMemo, useCallback)"
        tags: ["frontend", "performance", "react"]
      - text: "Cut partner dashboard load time by ~50%, directly improving usability and partner engagement"
        tags: ["frontend", "performance"]
      - text: "Led and mentored a team of 4 frontend developers, enforcing coding standards in an Agile environment"
        tags: ["leadership", "mentoring", "agile"]
        variant_only: ["software_engineer"]
      - text: "Collaborated with product and engineering teams to support data-informed decisions on a large-scale property platform"
        tags: ["analytics", "product", "collaboration"]
        variant_only: ["ml_engineer", "data_engineer"]

  - company: "Ideaxen"
    location: "Dhaka, Bangladesh"
    start: "2020-08"
    end: "2021-07"
    role_variants:
      software_engineer: "Junior Software Developer"
      ml_engineer: "Junior Software Developer"
    tags: ["backend", "erp"]
    highlights:
      - text: "Engineered core modules for a comprehensive ERP solution, focusing on complex inventory management systems"
        tags: ["backend", "erp"]
      - text: "Implemented Code First approach using C# .NET MVC to design database schemas and business logic layers"
        tags: ["backend", "csharp", "database"]
      - text: "Developed automated tracking for stock movements, ensuring data accuracy across multi-warehouse environments"
        tags: ["backend", "data-integrity", "automation"]

  - company: "Bluebeak.ai"
    location: "Remote"
    start: "2018-07"
    end: "2019-08"
    role_variants:
      ml_engineer: "Data Analyst"
      data_engineer: "Data Analyst"
    tags: ["analytics", "data-science"]
    show_for: ["ml_engineer", "data_engineer"]  # Hide from SWE variant
    highlights:
      - text: "Leveraged R, sparklyr, and dplyr to manipulate and clean massive datasets for AI-driven predictive modeling"
        tags: ["data-engineering", "analytics", "r"]
      - text: "Conducted exploratory data analysis to identify patterns in user behavior, contributing to AI algorithm optimization"
        tags: ["analytics", "eda", "data-science"]
      - text: "Streamlined data workflows to reduce processing time for high-volume datasets"
        tags: ["data-engineering", "performance"]

# --- Education ---
education:
  - degree: "Master of Data Science (Professional)"
    institution: "James Cook University Brisbane"
    location: "Brisbane, AU"
    start: "2024-03"
    end: "2025-12"
    tags: ["data-science", "ml"]
    highlights:
      - text: "Completed two industry placements: Federated Learning (QCIF) and Predictive Analytics (Sarina Russo Group)"
        tags: ["ml", "data-engineering"]
      - text: "Relevant Coursework: Data Mining and Machine Learning, Statistical Modeling, Database Modelling"
        tags: ["ml", "data-science", "database"]
      - text: "CGPA: 6.14/7.00"

  - degree: "Computer Science and Engineering"
    institution: "American International University Bangladesh (AIUB)"
    location: "Dhaka, Bangladesh"
    end: "2020-03"
    tags: ["cs", "fullstack", "backend"]

# --- Certifications ---
certifications:
  - name: "Node.js Microservice Certificate"
    issuer: "Tecognize Training"
    tags: ["backend", "nodejs"]
```

**Design Decisions:**
- **`role_variants` on experiences:** Same job, different title/framing per CV type (e.g., QCIF is "Software Engineer" or "ML Engineer" depending on target role) — this is the core innovation solving the two-CV problem
- **`variant_only` on highlights:** Some bullet points only appear for certain variants (e.g., mentoring details for SWE, data collaboration framing for ML)
- **`show_for` on experiences:** Entire roles can be hidden per variant (e.g., Bluebeak.ai only shows on ML/Data CVs)
- **`skill_groups`** instead of flat list: Groups map directly to CV section rendering, with tags for matching
- **`skill_priority`** in role variants: Controls which skill groups appear first
- Every item has `tags` for matching against JD keywords
- `aliases` on skills handle synonym matching natively
- `summary` per variant allows quick swaps without LLM
- `highlights` are individually tagged so granular selection is possible

### 6.2 Synonyms Map (`synonyms.yaml`)

```yaml
# Maps variations → canonical form (bidirectional lookup at runtime)
javascript: ["js", "es6", "es6+", "ecmascript", "vanilla js"]
typescript: ["ts"]
python: ["python3", "py"]
machine_learning: ["ml", "machine-learning", "ml/ai"]
artificial_intelligence: ["ai", "ai/ml"]
react: ["reactjs", "react.js", "react js"]
node: ["nodejs", "node.js"]
express: ["expressjs", "express.js"]
postgresql: ["postgres", "psql", "pg"]
mongodb: ["mongo"]
amazon_web_services: ["aws"]
google_cloud_platform: ["gcp"]
microsoft_azure: ["azure"]
continuous_integration: ["ci", "ci/cd", "cicd", "github actions"]
docker: ["containerisation", "containerization", "containers"]
kubernetes: ["k8s"]
rest_api: ["rest", "restful", "rest apis", "restful apis"]
graphql: ["gql"]
scikit_learn: ["sklearn", "scikit learn"]
exploratory_data_analysis: ["eda"]
extract_transform_load: ["etl", "elt", "etl/elt"]
power_bi: ["powerbi"]
cascading_style_sheets: ["css", "css3"]
hypertext_markup_language: ["html", "html5"]
sass: ["scss"]
tailwind_css: ["tailwind", "tailwindcss"]
federated_learning: ["fl", "distributed ml"]
role_based_access_control: ["rbac"]
agile: ["scrum", "agile/scrum"]
dotnet: [".net", "c#.net", "csharp", "c#"]
```

### 6.3 JD Parse Output (Internal)

```yaml
# Output of jd_parser — not stored, used in-memory
role: "Senior Frontend Developer"
company: "Acme Inc"
keywords:
  required: ["React", "TypeScript", "REST APIs", "CI/CD"]
  preferred: ["GraphQL", "AWS", "testing"]
  soft_skills: ["team player", "mentoring"]
experience_years: 5
```

---

## 7. Core Modules — Functional Specs

### 7.1 `yaml_loader.py`

**Responsibility:** Load, validate, and expose master CV data.

**Behavior:**
- Load `master_cv.yaml` and validate against expected schema
- Return structured Python objects (dataclasses or Pydantic models)
- Raise clear errors on missing required fields or malformed YAML
- Support hot-reload in web mode (watch file for changes)

### 7.2 `jd_parser.py`

**Responsibility:** Extract structured data from raw job description text.

**Behavior:**
- Input: raw JD text (string)
- Extract technical skills, tools, frameworks using spaCy NER + keyword extraction (RAKE/YAKE)
- Normalize extracted terms using `synonyms.yaml`
- Classify keywords as required vs preferred (heuristic: proximity to words like "must", "required" vs "nice to have", "bonus")
- Output: structured dict with `required`, `preferred`, `soft_skills` keyword lists

### 7.3 `matcher.py`

**Responsibility:** Score and select master CV sections relevant to a JD.

**Behavior:**
- Input: parsed JD keywords + loaded master CV
- **Step 1 — Variant Selection:** Compute tag overlap between JD keywords and each `role_variant`'s `skill_priority` categories. Select the best-matching variant as the base framing.
- **Step 2 — Skill Matching:** Match JD keywords against CV skills using:
  - Exact match (after normalization)
  - Alias match (via skill aliases)
  - Fuzzy match (RapidFuzz, threshold configurable, default 85)
  - Synonym map match
- **Step 3 — Experience Filtering:** For each experience entry:
  - Use the selected variant's `role_variants` title
  - Include/exclude highlights based on `variant_only` and `show_for` rules
  - Score remaining highlights by JD keyword overlap with their tags
  - Rank highlights within each role by relevance score
- **Step 4 — Section Assembly:** Assemble tailored CV with:
  - Selected variant's title and summary
  - Skills reordered by variant's `skill_priority`
  - Experience with variant-appropriate titles and filtered/ranked highlights
- Return ranked/filtered CV sections with match scores
- Allow manual override: user can pin/unpin items before export

### 7.4 `scorer.py`

**Responsibility:** Score a tailored CV against a JD for ATS compatibility.

**Behavior:**
- **Keyword Score (0–100):** % of JD required keywords found in tailored CV
- **Format Score (0–100):** Check for ATS-safe formatting:
  - Single-column layout ✓
  - Standard section headings (Experience, Education, Skills, Projects) ✓
  - No images/graphics ✓
  - No tables (or simple tables only) ✓
  - Standard fonts ✓
  - Parseable PDF text layer ✓
- **Overall Score:** Weighted combination (keyword 60%, format 40%)
- **Suggestions:** Actionable list, e.g.:
  - "Add 'TypeScript' to skills section (required in JD, missing from CV)"
  - "Rename 'Things I Built' → 'Projects' for ATS compatibility"
  - "Move 'React' from project descriptions to dedicated Skills section"

### 7.5 `renderer.py`

**Responsibility:** Convert tailored CV data into HTML and then PDF.

**Behavior:**
- Input: selected CV sections + chosen template name
- Load Jinja2 template (HTML + CSS) from `templates/{name}/`
- Render HTML with CV data
- Convert HTML → PDF using WeasyPrint
- Save PDF to `output/` with naming convention: `{name}_{company}_{date}.pdf`
- Return file path

---

## 8. Interface Specs

### 8.1 CLI Commands

```bash
# Tailor CV to a job description
cvforge tailor --jd <path_or_text> [--template minimal|modern|academic] [--output filename.pdf]

# Score your CV against a JD
cvforge score --jd <path_or_text> [--cv output/latest.pdf]

# Export master CV as-is (no tailoring)
cvforge export [--template minimal] [--output filename.pdf]

# Preview in browser (opens rendered HTML)
cvforge preview --jd <path_or_text> [--template minimal]

# Validate master CV YAML
cvforge validate

# List available templates
cvforge templates
```

**UX Notes:**
- `--jd` accepts both a file path and inline text (detect by checking if path exists)
- Without `--template`, use user's configured default
- Interactive mode: if `--jd` is omitted, prompt to paste JD text

### 8.2 Web UI

**Pages/Views:**

1. **Dashboard (Home)**
   - Paste/upload JD text area
   - "Tailor CV" button → goes to Preview

2. **Preview**
   - Side-by-side: JD keywords (left) ↔ Tailored CV preview (right)
   - Checkboxes to pin/unpin CV sections
   - Template selector dropdown
   - ATS score badge (prominently displayed)
   - "Download PDF" button

3. **ATS Report**
   - Keyword match breakdown (matched / missing / partial)
   - Format health checklist
   - Suggestions list with severity (critical / warning / info)

4. **Settings** (minimal)
   - Default template selection
   - Master CV file path
   - Synonym map path

**API Endpoints (FastAPI):**

```
POST   /api/tailor          # Body: { jd_text, template? } → tailored CV data + score
GET    /api/export/{id}     # Download PDF for a tailored result
POST   /api/score           # Body: { jd_text } → ATS score + suggestions
GET    /api/templates       # List available templates
GET    /api/master-cv       # Return current master CV data
POST   /api/validate        # Validate master CV
```

---

## 9. ATS Scoring Rules

### Keyword Matching Rules
- Exact match after lowercasing and stripping punctuation
- Alias resolution (JS → JavaScript) via skills aliases + synonyms map
- Fuzzy matching with RapidFuzz (threshold: 85) for typos and variations
- Compound skill matching: "CI/CD" should match "CI" or "CD" or "CI/CD"

### Format Health Checks
| Check | Severity | Rule |
|-------|----------|------|
| Single column layout | Critical | Template enforced |
| Standard section headers | Critical | Must use: Summary, Experience, Education, Skills, Projects, Certifications |
| No images/graphics | Critical | Template enforced (no `<img>` tags) |
| Parseable text layer | Critical | WeasyPrint generates selectable text by default |
| No tables for layout | Warning | Content tables OK, layout tables flagged |
| Standard fonts | Warning | Stick to Arial, Calibri, Times New Roman, Helvetica |
| 1–2 pages max | Info | Flag if >2 pages |
| Contact info present | Info | Check personal section completeness |

---

## 10. Templates

### Template Requirements
- Single-column layout (ATS requirement)
- Standard section ordering: Contact → Summary → Skills → Experience → Education → Projects → Certifications
- Clean, readable typography (11–12pt body, 14–16pt headings)
- No graphics, icons, or images
- Sufficient white space
- Print-friendly (PDF must look identical to screen)

### Template Variants
1. **Minimal** — Maximum whitespace, simple lines as dividers, most ATS-safe
2. **Modern** — Subtle color accents on headings, slightly more visual hierarchy
3. **Academic** — Prioritizes education and publications sections, formal tone

---

## 11. Configuration

Single config file: `cvforge.yaml` (project root)

```yaml
master_cv: "./data/master_cv.yaml"
synonyms: "./data/synonyms.yaml"
output_dir: "./output"
default_template: "minimal"
fuzzy_threshold: 85
scorer_weights:
  keyword: 0.6
  format: 0.4
web:
  port: 8000
  host: "127.0.0.1"
```

---

## 12. Development Plan

### Phase 1: Foundation
- [ ] Project scaffolding + OpenSpec setup
- [ ] Master CV YAML schema definition + validation (`yaml_loader.py`)
- [ ] Sample `master_cv.yaml` with realistic data
- [ ] Synonyms map (`synonyms.yaml`)

### Phase 2: Core Engine
- [ ] JD parser (`jd_parser.py`) — keyword extraction + classification
- [ ] Matcher (`matcher.py`) — JD ↔ CV matching + scoring
- [ ] ATS scorer (`scorer.py`) — keyword + format scoring
- [ ] Renderer (`renderer.py`) — Jinja2 + WeasyPrint pipeline

### Phase 3: Templates
- [ ] Minimal template (HTML/CSS)
- [ ] Modern template
- [ ] Academic template
- [ ] Template rendering tests

### Phase 4: CLI
- [ ] Typer CLI with all commands
- [ ] Interactive JD input mode
- [ ] End-to-end CLI workflow test

### Phase 5: Web UI
- [ ] FastAPI backend + API routes
- [ ] React frontend — Dashboard, Preview, ATS Report
- [ ] Side-by-side preview with pin/unpin
- [ ] PDF download flow

### Phase 6: Polish
- [ ] Error handling + edge cases
- [ ] Documentation (README, usage guide)
- [ ] Test suite
- [ ] Package for local install (`pip install -e .`)

---

## 13. Success Metrics

- **Time to tailor:** < 2 minutes from pasting JD to downloading PDF (vs 15–20 min manual)
- **ATS score:** Consistently > 80% keyword match on relevant roles
- **Zero external dependency:** Core workflow works fully offline
- **Template quality:** PDF output passes manual review as professional and clean

---

## 14. Future Roadmap (Post-MVP)

1. **LLM Adapter Layer** — Pluggable interface supporting Claude API, OpenAI, Ollama
2. **Cover Letter Generator** — Template-based (offline) + LLM-enhanced (optional)
3. **Job Application Tracker** — Log applications, statuses, versions
4. **ATS Simulator** — Parse own PDF like an ATS would, show extracted text
5. **Multiple Profiles** — Separate master CVs for different career tracks
6. **Browser Extension** — Auto-extract JD from job posting pages

---

## Appendix A: ATS Diagnosis of Current CVs

Analysis of `Fahim-Forhad-Resume.pdf` (SWE) and `Fahim-Forhad-Resume-ds.pdf` (ML/DS) to inform scoring rules and template design.

### Likely ATS Failure Points

| Issue | Severity | Detail |
|-------|----------|--------|
| Contact info layout | Critical | Email, phone, location, LinkedIn, GitHub all on one line — many ATS parsers fail to delimit these and jumble them into one string |
| LinkedIn/GitHub as text, not URLs | Warning | "LinkedIn GitHub" without full URLs — ATS can't parse or verify these |
| Visa status in header | Warning | "485 Graduate Temporary (Full Working Rights)" may confuse ATS header parsing; better as a separate line or in a notes field |
| Skill grouping as inline commas | Moderate | "Python, SQL, Bash, JavaScript (ES6+), TypeScript" — some ATS prefer one skill per line or clear delimiters; parenthetical aliases like "(ES6+)" can break tokenization |
| Role title variation | Moderate | QCIF listed as "Software Engineer (ML Security Engineer)" vs "Machine Learning Engineer (Security & Distributed Systems)" — compound titles with parentheticals can confuse ATS role parsing |
| Bullet density | Info | 6 bullets per role is good, but some older ATS truncate after 4-5 per section |
| No dedicated "Projects" section | Info | All work is under Experience — adding a Projects section would give more keyword surface area for ATS matching |
| PDF text layer | Unknown | Need to verify via `pdfminer` extraction — if these were generated from a template with complex formatting, the underlying text may not match what's visually displayed |

### Recommendations Built Into CVForge

1. **Contact section:** Render each field on its own line or with clear delimiters (pipe, bullet). Full URLs for LinkedIn/GitHub.
2. **Skills section:** Render as tagged, clearly delimited items — not long comma-separated paragraphs.
3. **Role titles:** Single clean title, no parentheticals. Move the context into bullet points.
4. **Visa status:** Render as a separate, clearly labeled line below contact info.
5. **ATS preview feature:** Parse the generated PDF with `pdfminer` and show the extracted text side-by-side with the visual — this reveals exactly what ATS sees.
6. **Keyword injection:** After matching, suggest adding missing JD keywords to the Skills section or weaving them into existing bullet points.

### Template Section Order (ATS-Optimized)

Based on analysis of common ATS parsers (Workday, Greenhouse, Lever, ICIMS):

```
1. Name + Contact (structured, one field per line)
2. Professional Summary (2-3 sentences)
3. Skills (grouped, clearly delimited)
4. Professional Experience (reverse chronological)
5. Education
6. Certifications
7. Projects (optional)
```

Skills BEFORE experience is intentional — ATS often does a first-pass keyword scan on the top third of the document. Putting skills early maximizes keyword hits in that initial scan.