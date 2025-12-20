# django-trailcam-animal-tracker


---

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
  * Analyze images using OCR
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

### 🧠 OCR-Based Metadata Extraction

When a researcher clicks **Analyze**, the system:

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
5. Automatically Attaches Camera if it exists
5. Saves parsed metadata to the database

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
    * Create cameras via modal
    * Edit camera metadata via modal
    * Activate / deactivate cameras
    * Search cameras by name or description

**OCR Integration**
    * OCR-extracted camera IDs are normalized (e.g. TRAILCAMQ5 → TRAILCAM05)
    * If a matching active camera exists, it is automatically linked
    * If not, researchers are prompted to create the camera first
    * This ensures consistent camera IDs and location metadata across the dataset.

---

### 📝 Inline Metadata Editing (Modal Editor)

* Clicking a photo card opens a **modal editor**
* Metadata fields use appropriate controls:

  * Camera → text input with suggestions
  * Date → date picker
  * Time → time picker
  * Temperature / Pressure → numeric inputs with validation
* A **Save** button appears only when changes are made
* Successful saves close the modal automatically

---

### 🖼️ Gallery Experience

* Clean, card-based UI
* Optional toggle to hide/show metadata
* Hover and modal interactions for better image inspection
* Public gallery shows **only published images**

---

## 🧱 Tech Stack

| Layer            | Technology                     |
| ---------------- | ------------------------------ |
| Backend          | Django                         |
| Frontend         | Django Templates + Vanilla JS  |
| OCR              | Tesseract (via `pytesseract`)  |
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
│
├── media/                 # Uploaded images
└── manage.py
```

---

## 🔁 Core Workflows

### 1️⃣ Upload & Staging

1. Researcher uploads images
2. Images appear in `/upload` (staging)
3. Images are **not public**

---

### 2️⃣ Analysis

1. Researcher clicks **Analyze**
2. OCR extracts metadata
3. Results are stored and displayed
4. Researchers can edit metadata inline

---

### 3️⃣ Publishing

1. Image must have valid metadata
2. Researcher clicks **Publish**
3. Image becomes visible in `/gallery`

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

```bash
pip install django pillow pytesseract
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
    🔒 Open-state (lock) enforcement for photos & cameras
    🐾 Animal detection & classification
    🗺️ Map-based sightings view
    📊 Public activity log
    🚀 Deployment & background processing