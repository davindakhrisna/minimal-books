# Minimal OPDS Server & 90s Web Manager

A self-contained, lightweight OPDS 1.2 server and web-based book manager built from scratch.
Runs with **zero external dependencies** using the Python 3 standard library only.

## Features

- **Zero dependencies**: Pure Python standard library (`sqlite3`, `http.server`, `zipfile`, `xml.etree`).
- **90s Minimal Web UI**: Fast, light, bordered HTML table (`/`). Zero bloated CSS frameworks.
- **CRUD Operations**: Upload `.epub` or `.pdf` files, edit titles/authors/categories/summaries, and delete books directly from the web page.
- **Automatic Metadata & Covers**:
  - **EPUB**: Automatically extracts Dublin Core title, author, category, summary, and cover art from the package.
  - **PDF**: Automatically titles and generates clean retro monochrome SVG book covers.
- **OPDS 1.2 Feed**: Serves standard acquisition feed at `/catalog.xml` and `/opds` with HTTP Range streaming for e-readers (Moon+ Reader, KOReader, Apple Books, FBReader).

---

## How to Run

1. Place your `.epub` and `.pdf` files into the `contents/` folder (or upload them through the web page).
2. Start the server:
   ```bash
   python app.py
   ```
3. Open your browser:
   - **Web Manager**: `http://localhost:8080/`
   - **OPDS Feed**: `http://localhost:8080/catalog.xml` (or `/opds`)

---

## Custom Port or Remote Hosting

To run on a custom port:
```bash
PORT=9000 python app.py
```
*(On Windows PowerShell: `$env:PORT=9000; python app.py`)*

To run in the background on a Linux server:
```bash
nohup python app.py > server.log 2>&1 &
```
