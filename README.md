# 🦌 Trailcam Wildlife Research Platform

A collaborative Django-based platform for **uploading, analyzing, staging, and publishing trail camera images** for wildlife research.

This project is designed to support **teams of researchers** working together to process large volumes of trailcam images by extracting metadata (via OCR), reviewing results, editing metadata, and publishing only high-quality, validated images to a public gallery.

---

## ✨ Key Features

### 🔐 Role-Based Access

* **Public users**

  * View published wildlife images in the gallery
* **Researchers**

  * Upload trailcam images
  * Analyze images using OCR + SpeciesNet detections
  * Edit metadata inline
  * Publish / unpublish images
  * Collaborate in a shared staging area
  * Manage cameras and locations
  * Collaborate in a shared staging area

---

### 🧪 Staging → Publishing Workflow

* All uploaded photos enter a **shared staging area** (`/upload`)
* Any researcher can:

  * Analyze metadata
  * Correct OCR results
  * Delete unnecessary images
* Only **validated images** are published to the public gallery
* Published images can later be **unpublished** and returned to staging

This workflow ensures **data quality, collaboration, and accountability**.

---

### 🧠 OCR + AI (SpeciesNet) Analysis

When images are uploaded (or a researcher clicks **Analyze**), the system:

1. Crops the bottom overlay of the trailcam image
2. Applies OCR (Tesseract)
3. Extracts:
   * Camera ID (e.g. `TRAILCAM05`)
   * Date
   * Time
   * Temperature (°C)
   * Pressure (inHg)
4. Normalizes common OCR errors:
   * 0, Q, D -> 0 in a camera number
5. Automatically attaches/creates Camera (defaults to St. Edward's Univ. coords on create)
6. Runs **SpeciesNet** on the image to detect animals/people/vehicles and stores detections with normalized bounding boxes (0..1)
7. Saves parsed metadata and detections to the database

Privacy: when a photo is published, any detection classified as a person is permanently blacked out in the saved image.

Researchers can then **review and edit** extracted values before publishing.

---

### 📷 Camera Management (CRUD)

Researchers can manage cameras via the Cameras page.

**Camera Model**

Each camera includes:
    * name (unique, e.g. TRAILCAM05)
    * base_latitude
    * base_longitude
    * description (optional)
    * is_active

**Camera Actions**
  * Create cameras via a page-based form
  * Edit camera metadata via a page-based form
    * Activate / deactivate cameras
    * Search cameras by name or description

**OCR Integration**
    * OCR-extracted camera IDs are normalized (e.g. TRAILCAMQ5 → TRAILCAM05)
    * If a matching active camera exists, it is automatically linked
    * If not, a camera is created automatically using normalized name and default coordinates
    * This ensures consistent camera IDs and location metadata across the dataset.

---

### 📝 Page-based Metadata Editing

* Clicking Edit opens a **page-based editor**
* Metadata fields use appropriate controls:

  * Camera → text input with suggestions
  * Date → date picker
  * Time → time picker
  * Temperature / Pressure → numeric inputs with validation
* A **Save** button persists edits and reloads the editor
* A **Publish** button saves the current edits and publishes in one step (also applies person blackout)

---

### 🖼️ Gallery Experience

* Clean, card-based UI
* Optional toggle to hide/show metadata
* Bounding boxes are rendered on images; people are blacked out
* Filter bar with Camera, Date range, Temperature range, Pressure range, and Species (checkboxes)
* Public gallery shows **only published images**

---

## 🧱 Tech Stack

| Layer            | Technology                     |
| ---------------- | ------------------------------ |
| Backend          | Django                         |
| Frontend         | Django Templates + Vanilla JS  |
| OCR              | Tesseract (via `pytesseract`)  |
| AI Detection     | SpeciesNet (local JSON model)  |
| Image Processing | Pillow                         |
| Database         | SQLite (dev), easily swappable |
| Auth             | Django Auth                    |
| Styling          | CSS (externalized, modular)    |

---

## 📂 Project Structure (Relevant Parts)

```text
django-trailcam-animal-tracker/
│
├── wildlife/
│   ├── models.py          # Photo, Camera, Species, etc.
│   ├── views.py           # Upload, analyze, publish, unpublish
│   ├── urls.py
│   ├── templates/
│   │   └── wildlife/
│   │       ├── base.html
│   │       ├── upload.html
│   │       └── gallery.html
│   ├── static/
│   │   └── wildlife/
│   │       └── styles.css
│   └── utils/
│       ├── ocr.py         # OCR + regex parsing logic
│       └── utils.py       # Shared helpers
│   └── services/
│       └── speciesnet.py  # SpeciesNet detection pipeline + persistence
│
├── media/                 # Uploaded images
└── manage.py
```

---

## 🔁 Core Workflows

### 1️⃣ Upload & Staging

1. Researcher uploads images (single files or entire folders)
2. Client shows a **progress bar** updating as each image is processed server-side
3. Server runs OCR + SpeciesNet during upload
4. Images appear in `/upload` (staging) and are **not public**

---

### 2️⃣ Analysis

1. Researcher can click **Analyze** to re-run OCR + SpeciesNet on a single staging photo
2. OCR extracts metadata; SpeciesNet produces detections and bounding boxes
3. Results are stored and displayed
4. Researchers can edit metadata in the page-based editor

---

### 3️⃣ Publishing

1. Image must have valid metadata
2. Researcher clicks **Publish** (saves current edits automatically)
3. Any person detections are permanently blacked out in the image file
4. Image becomes visible in `/gallery`

---

### 4️⃣ Unpublishing

1. Researcher clicks **Unpublish** in gallery
2. Image returns to staging
3. Can be edited or deleted

---

## 🛡️ Data Integrity & Validation

* Metadata inputs enforce:

  * Valid dates/times
  * Reasonable temperature/pressure ranges
* Server-side validation ensures correctness
* OCR errors are expected and handled gracefully

---

## 🚀 Getting Started

### Install dependencies

Use a virtual environment and install from `requirements.txt`:

```bash
python -m venv .venv
source .venv/bin/activate  # macOS/Linux
# .venv\Scripts\activate  # Windows PowerShell

pip install -r requirements.txt
```

### Install Tesseract (macOS)

```bash
brew install tesseract
```

### Run server

```bash
python manage.py migrate
python manage.py runserver
```

Optional: ensure `speciesnet.json` exists at the project root (or configured path) if required by `services/speciesnet.py`.

---

## 📜 License

This project is intended for **academic and research use**.
License can be added as needed.

---



## 🔁 User Flow Diagrams

```mermaid
flowchart TD

%% ========= ROLES / SWIMLANES =========
subgraph Researcher
  R1([Log in])
  R2[Upload trailcam images]
  R3[View shared staging area]
  R4[Open photo modal]
  R5[Click Analyze]
  R6[Review and edit metadata in modal]
  R7{Publish or Delete?}
  R8[Publish image]
  R9[Delete image]
  R10[View public gallery]
  R11[Unpublish image]

  RC1[Open Cameras page]
  RC2[Create new camera]
  RC3[Edit camera]
  RC4[Save camera]
  RC5[Activate or deactivate camera]
end

subgraph System
  S1[Receive uploads]
  S2[Store image in staging]
  S3[Run OCR on image]
  S3A[Normalize OCR camera id]
  S4{Camera exists?}
  S5[Attach camera to photo]
  S6[Return metadata to modal]
  S7[Save edited metadata]
  S8[Publish image]
  S9[Delete image permanently]
  S10[Return image to staging]

  SC1[Validate camera fields]
  SC2[Create camera record]
  SC3[Update camera record]
end

subgraph Public_User
  P1[Browse gallery]
  P2[View image and metadata]
end

%% ========= PHOTO FLOW =========
R1 --> R2 --> S1 --> S2 --> R3 --> R4 --> R5 --> S3 --> S3A --> S4
S4 -->|Yes| S5 --> S6 --> R6 --> S7 --> R7
S4 -->|No| S6 --> R6

R7 -->|Publish| R8 --> S8 --> P1 --> P2
R7 -->|Delete| R9 --> S9 --> R3

R10 --> R11 --> S10 --> R3

%% ========= CAMERA FLOW =========
R1 --> RC1
RC1 --> RC2 --> SC1 --> SC2 --> RC4
RC1 --> RC3 --> SC1 --> SC3 --> RC4
RC1 --> RC5 --> SC3
```

## 🧱 System Architecture Diagram

``` mermaid
flowchart LR

%% =======================
%% Django Wildlife Platform — System Architecture
%% =======================

%% --- FRONTEND ---
subgraph FE[Frontend]
  T[Django Templates HTML]
  JS[Vanilla JavaScript]
  CSS[CSS]
end

%% --- BACKEND ---
subgraph BE[Backend]
  V[Django Views]
  AUTH[Auth & Permissions\nResearcher vs Public]
  ORM[Django ORM]
end

%% --- UTILITIES / PIPELINE ---
subgraph U[Utilities / Analysis Pipeline]
  PIL[Pillow\nimage preprocessing]
  OCR[Tesseract OCR\ntext extraction]
  RX[Regex Metadata Extractor\nparse timestamp / camera id / etc.]
end

%% --- STORAGE ---
subgraph ST[Storage]
  MEDIA[(Media Files\nuploaded images)]
  DB[(Database\nPhotos • Cameras • Metadata)]
end

%% --- USERS ---
R[Researcher browser]
P[Public User browser]

%% =======================
%% General request flow
%% =======================
R -->|HTTP GET/POST| V
P -->|HTTP GET| V

V --> AUTH
AUTH -->|allowed| V

V -->|render HTML| T
T --> JS
T --> CSS

%% =======================
%% Upload -> Staging
%% =======================
R -->|Upload images| V
V -->|save file| MEDIA
V -->|create/update Photo row staging| ORM
ORM --> DB

%% =======================
%% Analyze pipeline data flow
%% =======================
R -->|Click Analyze AJAX/fetch| JS
JS -->|POST /analyze photo_id| V

V -->|load image bytes| MEDIA
V -->|run preprocessing| PIL
PIL --> OCR
OCR --> RX

RX -->|metadata fields + confidence| V
V -->|persist extracted metadata| ORM
ORM --> DB

V -->|JSON response| JS
JS -->|open modal for review/edit| T

%% =======================
%% Publish / Unpublish / Delete
%% =======================
R -->|Publish modal submit| JS
JS -->|POST /publish photo_id| V
V -->|set status=published| ORM --> DB

P -->|Browse gallery| V
V -->|query published photos| ORM --> DB
V -->|serve images| MEDIA

R -->|Unpublish| JS -->|POST /unpublish photo_id| V
V -->|set status=staging| ORM --> DB

R -->|Delete| JS -->|POST /delete photo_id| V
V -->|delete DB rows| ORM --> DB
V -->|delete media file| MEDIA

```

## 🗃️ Data Model Diagram 

```mermaid
erDiagram
  USER ||--o{ PHOTO : uploads
  CAMERA ||--o{ PHOTO : captures

  USER {
    int id PK
    string username
    boolean is_researcher
  }

  CAMERA {
    int id PK
    string name
    decimal base_latitude
    decimal base_longitude
    string description
    boolean is_active
  }

  PHOTO {
    int id PK
    string image
    boolean is_published
    date date_taken
    time time_taken
    float temperature
    float pressure
    int camera_id FK
    int uploaded_by_id FK
  }
```

---

## 🧭 Roadmap (High-Level)

    ✅ Shared staging workflow
    ✅ Modal-based metadata editing
    ✅ Camera CRUD + OCR integration
    ✅ Animal detection & classification
    ✅ Map-based sightings view
    📊 Excel information Extraction
    🚀 Deployment & background processing


## 🏙️ Images

<img width="1878" height="831" alt="Screenshot 2025-12-29 at 8 30 27 PM" src="https://github.com/user-attachments/assets/c076ccf5-f7c1-41c8-afea-3ecfb2bb497f" />
Public gallery view, where you can filter images, and view locaiton of images on map.

<img width="1202" height="571" alt="Screenshot 2025-12-29 at 8 30 40 PM" src="https://github.com/user-attachments/assets/b4f88ae4-7c09-47cc-93be-505df5e07778" />
Detailed researcher view of images.
