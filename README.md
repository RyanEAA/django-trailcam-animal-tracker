# django-trailcam-animal-tracker

This project is a Django-based wildlife monitoring and research platform designed to support trail camera deployments. It enables researchers to upload and analyze trail camera images and general users to explore curated wildlife galleries. The system emphasizes reproducibility, traceability, and human-in-the-loop validation for ecological research.

Project Goals

Centralize trail camera image management

Support structured metadata extraction from trail camera overlays

Enable animal classification pipelines

Provide a review-and-publish workflow for researchers

Offer a clean, read-only gallery for public users

User Roles & Workflows

1. General Users (Public / Read-Only)

Who they are:

Students, faculty, or the public

No upload or modification permissions

What they can do:

Browse the Gallery

Filter images by:

Species

Location / Camera

Date range

View published images with verified metadata

What they cannot do:

Upload images

Modify metadata

Run analysis

This separation ensures data integrity and prevents unverified images from entering the public-facing gallery.

2. Researchers (Authenticated Users)

Who they are:

Approved researchers or administrators

Authenticated via Django’s auth system

High-Level Researcher Workflow:

Upload Images

Analyze Images (manual trigger)

Review & Edit Metadata

Publish to Gallery

This workflow intentionally introduces checkpoints to avoid accidental misclassification or metadata errors.

Detailed Researcher Workflow

Step 1: Image Upload

Researchers upload trail camera images through a Django form

Images are stored via Django’s media storage system

A Photo database record is created with minimal initial fields

Key idea: Uploading does not immediately publish or analyze the image.

Step 2: Image Analysis (Manual Trigger)

Each uploaded image displays an Analyze button.

When clicked, the backend:

Extracts overlay metadata from the bottom of the image:

Date

Time

Temperature (°C)

Pressure (inHg)

Runs the animal classification pipeline (if enabled)

Stores extracted values back into the database

Why manual analysis instead of automatic?

Avoids wasted compute on low-quality or test images

Allows batch uploads followed by selective analysis

Keeps researchers in control of data validation

Step 3: Metadata Review & Editing

After analysis:

Researchers can manually edit:

Species label

Confidence notes

Camera assignment

Metadata can be corrected if OCR or classification is imperfect

This step acknowledges that ML outputs are assistive, not authoritative.

Step 4: Publish to Gallery

Once validated, researchers can mark an image as published.

Published images:

Become visible in the public gallery

Are locked from further automated modification

Application Structure & File Responsibilities

Below is a conceptual overview of how files and modules interact.

Models (models.py)

Core database entities:

Photo

Image file

Extracted metadata (date, time, temperature, pressure)

Classification results

Publication status

Species

Canonical species labels

Used for filtering and consistency

Camera

Physical trail camera metadata

Location and deployment info

These models form the single source of truth for the system.

Forms (forms.py)

Responsible for:

Image upload validation

Metadata editing interfaces

Keeps validation logic centralized and reusable across views.

Views (views.py)

Orchestrates user interactions and workflows:

Upload views

Gallery views

Analyze endpoints

Publish actions

Views coordinate between:

Models (data)

Services (logic)

Templates (presentation)

Services Layer (services/)

Purpose: isolate complex logic from views.

Typical responsibilities:

Image processing

OCR-based metadata extraction

ML inference calls

Post-processing cleanup

This keeps views thin and testable.

Computer Vision Pipeline (cv/)

Handles:

Animal classification

Image preprocessing

Model loading and inference

Designed to be swappable so models can evolve without touching Django logic.

Templates (templates/)

Responsible for:

Upload forms

Researcher dashboards

Public gallery views

Templates reflect workflow states:

Uploaded

Analyzed

Published

Utilities (utils.py)

Common helpers such as:

Permission checks (e.g., researcher-only actions)

Reusable query logic

Design Principles

Human-in-the-loop ML: researchers validate results

Separation of concerns: views vs services vs CV

Reproducibility: metadata is explicit and traceable

Scalability: batch uploads + deferred analysis

Future Extensions

Batch analysis jobs

Confidence scores for OCR and classification

Temporal analytics (activity patterns)

Export tools for downstream ecological analysis

Summary

This project is designed not just as an image gallery, but as a research-grade data pipeline for wildlife monitoring. By separating upload, analysis, validation, and publication, it balances automation with scientific rigor.

If you are extending this system, aim to keep automation assistive and researcher intent explicit.