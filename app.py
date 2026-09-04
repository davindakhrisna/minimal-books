#!/usr/bin/env python3
"""
Minimal OPDS Server & 90s Web Manager
A single-file, zero-dependency, self-hosted OPDS 1.2 catalog and book manager.
Runs with Python standard library only.
"""

import os
import sys
import sqlite3
import zipfile
import hashlib
import uuid
import posixpath
import urllib.parse
import mimetypes
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import xml.etree.ElementTree as ET
from xml.dom import minidom

# Optional high-resolution PDF cover renderer
try:
    import pypdfium2 as pdfium
    HAS_PDFIUM = True
except ImportError:
    HAS_PDFIUM = False

# Force UTF-8 stdout/stderr on Windows to prevent cp1252 encoding errors
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONTENTS_DIR = os.path.join(BASE_DIR, "contents")
COVERS_DIR = os.path.join(BASE_DIR, "covers")
DB_PATH = os.path.join(BASE_DIR, "library.db")

os.makedirs(CONTENTS_DIR, exist_ok=True)
os.makedirs(COVERS_DIR, exist_ok=True)

# Register custom MIME types
mimetypes.add_type("application/epub+zip", ".epub")
mimetypes.add_type("application/pdf", ".pdf")
mimetypes.add_type("application/atom+xml", ".xml")
mimetypes.add_type("application/atom+xml", ".opds")
mimetypes.add_type("image/svg+xml", ".svg")

# ----------------------------------------------------------------------
# Database Management (SQLite)
# ----------------------------------------------------------------------

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS books (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                author TEXT DEFAULT 'Unknown',
                category TEXT DEFAULT 'Uncategorized',
                summary TEXT DEFAULT '',
                filename TEXT NOT NULL UNIQUE,
                format TEXT NOT NULL,
                size_bytes INTEGER DEFAULT 0,
                cover_path TEXT,
                updated_at TEXT
            );
        """)
        conn.commit()

def format_size(size_bytes):
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"

# ----------------------------------------------------------------------
# Metadata & Cover Extraction
# ----------------------------------------------------------------------

def generate_pdf_svg_cover(book_id, title, author):
    """Generates a retro 90s monochrome bordered SVG cover for PDFs."""
    cover_filename = f"{book_id}.svg"
    cover_filepath = os.path.join(COVERS_DIR, cover_filename)
    
    clean_title = title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")[:45]
    clean_author = author.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")[:35]
    
    svg = f"""<svg xmlns="http://www.w3.org/2005/svg" width="120" height="160" viewBox="0 0 120 160">
  <rect width="120" height="160" fill="#ffffff" stroke="#000000" stroke-width="2"/>
  <line x1="10" y1="0" x2="10" y2="160" stroke="#000000" stroke-width="1"/>
  <text x="65" y="24" font-family="monospace" font-size="11" font-weight="bold" text-anchor="middle" fill="#000000">[PDF]</text>
  <foreignObject x="18" y="45" width="94" height="75">
    <div xmlns="http://www.w3.org/1999/xhtml" style="font-family:monospace;font-size:10px;font-weight:bold;color:#000000;text-align:center;word-wrap:break-word;line-height:1.2;">
      {clean_title}
    </div>
  </foreignObject>
  <text x="65" y="145" font-family="monospace" font-size="8" text-anchor="middle" fill="#333333">{clean_author}</text>
</svg>"""
    with open(cover_filepath, "w", encoding="utf-8") as f:
        f.write(svg)
        
    return f"covers/{cover_filename}"

def extract_metadata_and_cover(filepath):
    filename = os.path.basename(filepath)
    ext = os.path.splitext(filename)[1].lower()
    base_title = os.path.splitext(filename)[0].replace("_", " ").strip()
    book_id = hashlib.sha256(filename.encode("utf-8")).hexdigest()[:12]
    
    meta = {
        "id": book_id,
        "title": base_title,
        "author": "Unknown",
        "category": "General",
        "summary": "",
        "filename": filename,
        "format": ext.replace(".", "").upper(),
        "size_bytes": os.path.getsize(filepath) if os.path.exists(filepath) else 0,
        "cover_path": None,
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    }

    # EPUB Extraction
    if ext == ".epub":
        try:
            with zipfile.ZipFile(filepath, "r") as z:
                container_data = z.read("META-INF/container.xml")
                c_tree = ET.fromstring(container_data)
                opf_path = None
                for rf in c_tree.findall(".//{*}rootfile"):
                    if rf.attrib.get("media-type") == "application/oebps-package+xml" or "full-path" in rf.attrib:
                        opf_path = rf.attrib["full-path"]
                        break
                
                if opf_path and opf_path in z.namelist():
                    opf_dir = posixpath.dirname(opf_path)
                    opf = ET.fromstring(z.read(opf_path))
                    
                    t_el = opf.find(".//{http://purl.org/dc/elements/1.1/}title")
                    if t_el is not None and t_el.text:
                        meta["title"] = t_el.text.strip()
                        
                    creators = [c.text.strip() for c in opf.findall(".//{http://purl.org/dc/elements/1.1/}creator") if c.text and c.text.strip()]
                    if creators:
                        meta["author"] = ", ".join(creators)
                        
                    desc_el = opf.find(".//{http://purl.org/dc/elements/1.1/}description")
                    if desc_el is not None and desc_el.text:
                        meta["summary"] = desc_el.text.strip()
                        
                    subjects = [s.text.strip() for s in opf.findall(".//{http://purl.org/dc/elements/1.1/}subject") if s.text and s.text.strip()]
                    if subjects:
                        meta["category"] = subjects[0]
                        
                    # Cover Extraction
                    manifest = {item.attrib.get("id", ""): item.attrib for item in opf.findall(".//{http://www.idpf.org/2007/opf}item")}
                    cover_href = None
                    cover_mime = None
                    
                    # EPUB 3 cover-image
                    for it in manifest.values():
                        if "cover-image" in it.get("properties", "").split():
                            cover_href = it.get("href")
                            cover_mime = it.get("media-type")
                            break
                    # EPUB 2 meta cover
                    if not cover_href:
                        for m in opf.findall(".//{http://www.idpf.org/2007/opf}meta"):
                            if m.attrib.get("name") == "cover":
                                cid = m.attrib.get("content")
                                if cid in manifest:
                                    cover_href = manifest[cid].get("href")
                                    cover_mime = manifest[cid].get("media-type")
                                    break
                    # Fallback keyword match
                    if not cover_href:
                        for it in manifest.values():
                            if it.get("media-type", "").startswith("image/") and "cover" in (it.get("id", "") + it.get("href", "")).lower():
                                cover_href = it.get("href")
                                cover_mime = it.get("media-type")
                                break
                                
                    if cover_href:
                        full_c_path = posixpath.normpath(posixpath.join(opf_dir, cover_href)) if opf_dir else cover_href
                        if full_c_path in z.namelist():
                            img_bytes = z.read(full_c_path)
                            ext_img = ".jpg"
                            if cover_mime == "image/png":
                                ext_img = ".png"
                            elif cover_mime == "image/webp":
                                ext_img = ".webp"
                            c_filename = f"{book_id}{ext_img}"
                            c_dest = os.path.join(COVERS_DIR, c_filename)
                            with open(c_dest, "wb") as img_f:
                                img_f.write(img_bytes)
                            meta["cover_path"] = f"covers/{c_filename}"
        except Exception as e:
            print(f"Notice: Failed to parse EPUB metadata for '{filename}': {e}")
            
    # PDF Metadata & Cover Extraction
    elif ext == ".pdf":
        # Guess category based on title keywords if present
        lower_t = base_title.lower()
        if any(k in lower_t for k in ["algorithm", "c++", "programming", "machine learning", "computer"]):
            meta["category"] = "Computer Science"
        elif any(k in lower_t for k in ["philosophy", "political", "prince"]):
            meta["category"] = "Philosophy"
        elif any(k in lower_t for k in ["fiction", "cyberpunk", "novel"]):
            meta["category"] = "Science Fiction"

        cover_rendered = False
        if HAS_PDFIUM:
            try:
                pdf = pdfium.PdfDocument(filepath)
                if len(pdf) > 0:
                    p = pdf[0]
                    # Compute scale to yield crisp ~300px wide cover image
                    scale = max(300.0 / p.get_width(), 1.0)
                    img = p.render(scale=scale).to_pil()
                    cover_filename = f"{book_id}.jpg"
                    cover_dest = os.path.join(COVERS_DIR, cover_filename)
                    img.save(cover_dest, "JPEG", quality=85)
                    meta["cover_path"] = f"covers/{cover_filename}"
                    cover_rendered = True
            except Exception as e:
                print(f"Notice: Failed to render PDF page 1 for '{filename}': {e}")

        if not cover_rendered:
            meta["cover_path"] = generate_pdf_svg_cover(book_id, meta["title"], meta["author"])

    # If EPUB had no cover, generate fallback
    if not meta["cover_path"]:
        meta["cover_path"] = generate_pdf_svg_cover(book_id, meta["title"], meta["author"])
        
    return meta

def sync_library_from_disk():
    """Scans contents/ directory and reconciles with SQLite database."""
    init_db()
    with get_db() as conn:
        existing_filenames = {row["filename"]: row for row in conn.execute("SELECT * FROM books").fetchall()}
        
        disk_files = []
        if os.path.exists(CONTENTS_DIR):
            for f in os.listdir(CONTENTS_DIR):
                if f.lower().endswith((".epub", ".pdf")):
                    disk_files.append(f)
                    
        added = 0
        for f in disk_files:
            if f not in existing_filenames:
                fpath = os.path.join(CONTENTS_DIR, f)
                meta = extract_metadata_and_cover(fpath)
                conn.execute("""
                    INSERT INTO books (id, title, author, category, summary, filename, format, size_bytes, cover_path, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    meta["id"], meta["title"], meta["author"], meta["category"],
                    meta["summary"], meta["filename"], meta["format"],
                    meta["size_bytes"], meta["cover_path"], meta["updated_at"]
                ))
                added += 1

        # Upgrade existing books to real JPG covers if currently missing or SVG
        for row in conn.execute("SELECT * FROM books").fetchall():
            fname = row["filename"]
            fpath = os.path.join(CONTENTS_DIR, fname)
            curr_cov = row["cover_path"]
            if os.path.exists(fpath):
                cov_full = os.path.join(BASE_DIR, curr_cov) if curr_cov else ""
                if not curr_cov or not os.path.exists(cov_full) or (curr_cov.endswith(".svg") and HAS_PDFIUM):
                    upgraded = extract_metadata_and_cover(fpath)
                    if upgraded.get("cover_path") and upgraded["cover_path"] != curr_cov:
                        conn.execute("UPDATE books SET cover_path = ? WHERE id = ?", (upgraded["cover_path"], row["id"]))
                
        # Remove files from DB that no longer exist on disk
        removed = 0
        for fname in existing_filenames:
            if fname not in disk_files:
                conn.execute("DELETE FROM books WHERE filename = ?", (fname,))
                removed += 1
                
        conn.commit()
        if added > 0 or removed > 0:
            print(f"[Sync] Index updated: {added} added, {removed} removed.")

# ----------------------------------------------------------------------
# OPDS Feed Generator
# ----------------------------------------------------------------------

def generate_opds_xml(books, base_url=""):
    ATOM_NS = "http://www.w3.org/2005/Atom"
    DC_NS = "http://purl.org/dc/terms/"
    OPDS_NS = "http://opds-spec.org/2010/catalog"
    
    feed = ET.Element("feed", {
        "xmlns": ATOM_NS,
        "xmlns:dc": DC_NS,
        "xmlns:opds": OPDS_NS
    })
    
    ET.SubElement(feed, "id").text = "urn:uuid:minimal-opds-server"
    ET.SubElement(feed, "title").text = "Minimal OPDS Catalog"
    ET.SubElement(feed, "updated").text = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    author = ET.SubElement(feed, "author")
    ET.SubElement(author, "name").text = "Minimal OPDS"
    
    ET.SubElement(feed, "link", {
        "rel": "self",
        "href": f"{base_url}/catalog.xml",
        "type": "application/atom+xml;profile=opds-catalog;kind=acquisition"
    })
    ET.SubElement(feed, "link", {
        "rel": "start",
        "href": f"{base_url}/catalog.xml",
        "type": "application/atom+xml;profile=opds-catalog;kind=acquisition"
    })

    for b in books:
        entry = ET.SubElement(feed, "entry")
        ET.SubElement(entry, "title").text = b["title"]
        ET.SubElement(entry, "id").text = f"urn:uuid:{b['id']}"
        ET.SubElement(entry, "updated").text = b["updated_at"] or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        
        b_auth = ET.SubElement(entry, "author")
        ET.SubElement(b_auth, "name").text = b["author"] or "Unknown"
        
        if b["category"]:
            ET.SubElement(entry, "category", {"term": b["category"], "label": b["category"]})
            
        ET.SubElement(entry, "summary").text = b["summary"] or ""
        
        # Cover Links
        if b["cover_path"] and os.path.exists(os.path.join(BASE_DIR, b["cover_path"])):
            c_ext = os.path.splitext(b["cover_path"])[1].lower()
            c_mime = "image/svg+xml" if c_ext == ".svg" else ("image/png" if c_ext == ".png" else "image/jpeg")
            c_url = f"{base_url}/{b['cover_path']}"
            ET.SubElement(entry, "link", {
                "rel": "http://opds-spec.org/image",
                "href": c_url,
                "type": c_mime
            })
            ET.SubElement(entry, "link", {
                "rel": "http://opds-spec.org/image/thumbnail",
                "href": c_url,
                "type": c_mime
            })
            
        # Acquisition Link
        file_mime = "application/epub+zip" if b["format"].lower() == "epub" else "application/pdf"
        file_url = f"{base_url}/contents/{urllib.parse.quote(b['filename'])}"
        ET.SubElement(entry, "link", {
            "rel": "http://opds-spec.org/acquisition",
            "href": file_url,
            "type": file_mime
        })

    xml_bytes = ET.tostring(feed, encoding="utf-8")
    parsed_xml = minidom.parseString(xml_bytes)
    return parsed_xml.toprettyxml(indent="  ", encoding="utf-8")

# ----------------------------------------------------------------------
# 90s Minimal HTML Page Generator
# ----------------------------------------------------------------------

def render_90s_html(books, query="", host_port="localhost:8080"):
    total_books = len(books)
    epub_count = sum(1 for b in books if b["format"] == "EPUB")
    pdf_count = sum(1 for b in books if b["format"] == "PDF")
    total_size = sum(b["size_bytes"] for b in books)
    
    rows_html = []
    for b in books:
        cover_tag = ""
        if b["cover_path"]:
            cover_tag = f'<img src="/{b["cover_path"]}" width="45" height="60" border="1" alt="cover" style="object-fit:cover; display:block;">'
        else:
            cover_tag = '<div style="width:45px; height:60px; border:1px solid #000; text-align:center; line-height:60px; font-size:10px;">[NO]</div>'
            
        esc_id = urllib.parse.quote(b["id"])
        esc_title = b["title"].replace('"', '&quot;').replace("'", "&#39;")
        esc_author = (b["author"] or "Unknown").replace('"', '&quot;').replace("'", "&#39;")
        esc_category = (b["category"] or "General").replace('"', '&quot;').replace("'", "&#39;")
        esc_summary = (b["summary"] or "").replace('"', '&quot;').replace("'", "&#39;")
        
        row = f"""
        <tr>
          <td align="center">{cover_tag}</td>
          <td>
            <b>{b['title']}</b>
            {f'<div style="font-size:11px; color:#444; margin-top:3px;">{b["summary"]}</div>' if b["summary"] else ''}
          </td>
          <td>{b['author']}</td>
          <td>{b['category']}</td>
          <td align="center">{b['format']}</td>
          <td align="right">{format_size(b['size_bytes'])}</td>
          <td align="center" nowrap>
            <a class="btn" href="/contents/{urllib.parse.quote(b['filename'])}" download>[Get]</a>
            <button class="btn" onclick="openEditModal('{esc_id}', '{esc_title}', '{esc_author}', '{esc_category}', '{esc_summary}')">[Edit]</button>
            <form style="display:inline;" method="post" action="/api/delete" onsubmit="return confirm('Delete this book?');">
              <input type="hidden" name="id" value="{b['id']}">
              <input type="submit" value="[Del]">
            </form>
          </td>
        </tr>
        """
        rows_html.append(row)
        
    empty_msg = '<tr><td colspan="7" align="center" style="padding:20px;">No books found matching criteria.</td></tr>' if not rows_html else ""

    return f"""<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN" "http://www.w3.org/TR/html4/loose.dtd">
<html>
<head>
  <title>Minimal OPDS Server</title>
  <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
  <style type="text/css">
    body {{
      font-family: 'Courier New', Courier, monospace, monospace;
      background-color: #ffffff;
      color: #000000;
      margin: 18px;
    }}
    h1, h2, h3 {{
      font-family: 'Courier New', Courier, monospace, monospace;
      margin-bottom: 6px;
    }}
    .box {{
      border: 1px solid #000000;
      padding: 10px 14px;
      margin-bottom: 14px;
      background-color: #fafafa;
    }}
    table {{
      border-collapse: collapse;
      width: 100%;
      margin-top: 10px;
    }}
    th, td {{
      border: 1px solid #000000;
      padding: 6px 8px;
      font-size: 13px;
      vertical-align: top;
    }}
    th {{
      background-color: #e5e5e5;
      text-align: left;
    }}
    input[type="text"], textarea {{
      font-family: 'Courier New', Courier, monospace;
      font-size: 13px;
      border: 1px solid #000000;
      padding: 3px 5px;
      background: #ffffff;
    }}
    input[type="submit"], button, .btn {{
      font-family: 'Courier New', Courier, monospace;
      font-size: 12px;
      background-color: #e5e5e5;
      color: #000000;
      border: 1px solid #000000;
      padding: 2px 6px;
      cursor: pointer;
      text-decoration: none;
      display: inline-block;
    }}
    input[type="submit"]:hover, button:hover, .btn:hover {{
      background-color: #cccccc;
    }}
    /* Simple 90s Modal Dialog */
    #editModal {{
      display: none;
      position: fixed;
      top: 0; left: 0;
      width: 100%; height: 100%;
      background: rgba(0,0,0,0.5);
    }}
    #editModalContent {{
      background: #ffffff;
      border: 2px solid #000000;
      width: 480px;
      margin: 80px auto;
      padding: 16px;
    }}
  </style>
</head>
<body>

  <h1>=== MINIMAL OPDS SERVER ===</h1>
  
  <div class="box">
    <b>LIBRARY STATUS:</b> {total_books} books total ({epub_count} EPUB, {pdf_count} PDF) | {format_size(total_size)} total storage<br>
    <b>OPDS 1.2 FEED URL:</b> <a href="/catalog.xml">http://{host_port}/catalog.xml</a> (or <a href="/opds">/opds</a>)<br>
    <small>Connect Moon+ Reader, KOReader, Apple Books, or FBReader to the URL above to browse &amp; download directly.</small>
  </div>

  <div class="box">
    <table border="0" cellpadding="0" cellspacing="0" width="100%">
      <tr>
        <!-- Upload Form -->
        <td valign="top" style="border:none; padding:0;">
          <form action="/api/upload" method="post" enctype="multipart/form-data">
            <b>[+] UPLOAD BOOK:</b><br>
            <input type="file" name="file" accept=".epub,.pdf" required>
            <input type="submit" value="Upload &amp; Auto-Index">
          </form>
        </td>
        <!-- Search Form -->
        <td valign="top" align="right" style="border:none; padding:0;">
          <form method="get" action="/">
            <b>SEARCH:</b><br>
            <input type="text" name="q" value="{query.replace('"', '&quot;')}" placeholder="Title, author, category...">
            <input type="submit" value="Filter">
            <a class="btn" href="/">[Reset]</a>
          </form>
        </td>
      </tr>
    </table>
  </div>

  <table border="1">
    <thead>
      <tr>
        <th width="45">Cover</th>
        <th>Title &amp; Summary</th>
        <th width="160">Author</th>
        <th width="140">Category</th>
        <th width="55">Format</th>
        <th width="75">Size</th>
        <th width="150">Actions</th>
      </tr>
    </thead>
    <tbody>
      {''.join(rows_html)}
      {empty_msg}
    </tbody>
  </table>

  <!-- Minimal Edit Modal -->
  <div id="editModal">
    <div id="editModalContent">
      <h3>=== EDIT BOOK METADATA ===</h3>
      <form action="/api/edit" method="post">
        <input type="hidden" name="id" id="formEditId">
        
        <p><b>Title:</b><br>
        <input type="text" name="title" id="formEditTitle" style="width:96%;"></p>
        
        <p><b>Author:</b><br>
        <input type="text" name="author" id="formEditAuthor" style="width:96%;"></p>
        
        <p><b>Category:</b><br>
        <input type="text" name="category" id="formEditCategory" style="width:96%;"></p>
        
        <p><b>Summary:</b><br>
        <textarea name="summary" id="formEditSummary" rows="4" style="width:96%;"></textarea></p>
        
        <p align="right" style="margin-top:15px;">
          <input type="button" value="[Cancel]" onclick="closeEditModal()">
          <input type="submit" value="[Save Changes]">
        </p>
      </form>
    </div>
  </div>

  <script type="text/javascript">
    function openEditModal(id, title, author, category, summary) {{
      document.getElementById('formEditId').value = id;
      document.getElementById('formEditTitle').value = title;
      document.getElementById('formEditAuthor').value = author;
      document.getElementById('formEditCategory').value = category;
      document.getElementById('formEditSummary').value = summary;
      document.getElementById('editModal').style.display = 'block';
    }}
    function closeEditModal() {{
      document.getElementById('editModal').style.display = 'none';
    }}
    window.onclick = function(event) {{
      if (event.target == document.getElementById('editModal')) {{
        closeEditModal();
      }}
    }}
  </script>

</body>
</html>"""

# ----------------------------------------------------------------------
# HTTP Request Handler
# ----------------------------------------------------------------------

class OPDSHandler(BaseHTTPRequestHandler):

    def send_data(self, data, content_type, status=200):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def redirect(self, location="/"):
        self.send_response(303)
        self.send_header("Location", location)
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        # 1. 90s Web Management Page
        if path == "/" or path == "/index.html":
            query_params = urllib.parse.parse_qs(parsed.query)
            q = query_params.get("q", [""])[0].strip()
            
            with get_db() as conn:
                if q:
                    pattern = f"%{q}%"
                    books = conn.execute("""
                        SELECT * FROM books 
                        WHERE title LIKE ? OR author LIKE ? OR category LIKE ? OR summary LIKE ?
                        ORDER BY title ASC
                    """, (pattern, pattern, pattern, pattern)).fetchall()
                else:
                    books = conn.execute("SELECT * FROM books ORDER BY title ASC").fetchall()
                    
            host_port = self.headers.get("Host", "localhost:8080")
            html = render_90s_html(books, query=q, host_port=host_port)
            self.send_data(html.encode("utf-8"), "text/html; charset=utf-8")
            return

        # 2. OPDS Feed (both /catalog.xml and /opds)
        if path in ["/catalog.xml", "/opds", "/feed.xml"]:
            with get_db() as conn:
                books = conn.execute("SELECT * FROM books ORDER BY title ASC").fetchall()
                
            host_header = self.headers.get("Host", "localhost:8080")
            base_url = f"http://{host_header}"
            xml_bytes = generate_opds_xml(books, base_url=base_url)
            self.send_data(xml_bytes, "application/atom+xml; profile=opds-catalog; kind=acquisition; charset=utf-8")
            return

        # 3. Static Covers
        if path.startswith("/covers/"):
            filename = os.path.basename(urllib.parse.unquote(path))
            cover_file = os.path.join(COVERS_DIR, filename)
            if os.path.exists(cover_file):
                mime, _ = mimetypes.guess_type(cover_file)
                mime = mime or "image/jpeg"
                with open(cover_file, "rb") as f:
                    self.send_data(f.read(), mime)
                return
            self.send_error(404, "Cover not found")
            return

        # 4. Static Book Files with Range Support
        if path.startswith("/contents/"):
            filename = os.path.basename(urllib.parse.unquote(path))
            book_file = os.path.join(CONTENTS_DIR, filename)
            if not os.path.exists(book_file):
                self.send_error(404, "File not found")
                return
                
            file_size = os.path.getsize(book_file)
            mime, _ = mimetypes.guess_type(book_file)
            mime = mime or "application/octet-stream"

            range_header = self.headers.get("Range")
            if range_header and range_header.startswith("bytes="):
                try:
                    ranges = range_header.replace("bytes=", "").split("-")
                    start = int(ranges[0]) if ranges[0] else 0
                    end = int(ranges[1]) if len(ranges) > 1 and ranges[1] else file_size - 1
                    end = min(end, file_size - 1)
                    length = end - start + 1

                    self.send_response(206)
                    self.send_header("Content-Type", mime)
                    self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
                    self.send_header("Content-Length", str(length))
                    self.send_header("Accept-Ranges", "bytes")
                    self.end_headers()

                    with open(book_file, "rb") as f:
                        f.seek(start)
                        remaining = length
                        while remaining > 0:
                            chunk = f.read(min(remaining, 65536))
                            if not chunk:
                                break
                            self.wfile.write(chunk)
                            remaining -= len(chunk)
                    return
                except Exception as e:
                    pass

            # Full file delivery
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(file_size))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            with open(book_file, "rb") as f:
                while True:
                    chunk = f.read(65536)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
            return

        self.send_error(404, "Not Found")

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        content_length = int(self.headers.get("Content-Length", 0))

        # 1. Upload Book
        if path == "/api/upload":
            content_type = self.headers.get("Content-Type", "")
            
            # Form Multipart Upload
            if "multipart/form-data" in content_type:
                boundary = content_type.split("boundary=")[1].strip()
                boundary_bytes = ("--" + boundary).encode()
                
                raw_body = self.rfile.read(content_length)
                parts = raw_body.split(boundary_bytes)
                
                for part in parts:
                    if b'filename="' in part:
                        headers_part, file_body = part.split(b"\r\n\r\n", 1)
                        # Remove trailing \r\n-- or \r\n
                        if file_body.endswith(b"\r\n"):
                            file_body = file_body[:-2]
                        if file_body.endswith(b"--"):
                            file_body = file_body[:-2]
                            
                        # Extract filename
                        header_lines = headers_part.decode("utf-8", errors="ignore")
                        for line in header_lines.splitlines():
                            if 'filename="' in line:
                                fname = line.split('filename="')[1].split('"')[0]
                                clean_fname = os.path.basename(urllib.parse.unquote(fname))
                                if clean_fname.lower().endswith((".epub", ".pdf")):
                                    dest_path = os.path.join(CONTENTS_DIR, clean_fname)
                                    with open(dest_path, "wb") as f:
                                        f.write(file_body)
                                    # Trigger auto-indexing into SQLite
                                    sync_library_from_disk()
                self.redirect("/")
                return

            # Direct stream upload (?filename=...)
            params = urllib.parse.parse_qs(parsed.query)
            fname = params.get("filename", [""])[0] or self.headers.get("X-Filename", "")
            clean_fname = os.path.basename(urllib.parse.unquote(fname))
            if clean_fname.lower().endswith((".epub", ".pdf")):
                dest_path = os.path.join(CONTENTS_DIR, clean_fname)
                remaining = content_length
                with open(dest_path, "wb") as f:
                    while remaining > 0:
                        chunk = self.rfile.read(min(remaining, 65536))
                        if not chunk:
                            break
                        f.write(chunk)
                        remaining -= len(chunk)
                sync_library_from_disk()
                self.send_data(b'{"success":true}', "application/json")
                return

            self.redirect("/")
            return

        # 2. Edit Book
        if path == "/api/edit":
            body = self.rfile.read(content_length).decode("utf-8")
            params = urllib.parse.parse_qs(body)
            
            book_id = params.get("id", [""])[0]
            title = params.get("title", [""])[0].strip()
            author = params.get("author", [""])[0].strip()
            category = params.get("category", [""])[0].strip()
            summary = params.get("summary", [""])[0].strip()
            
            if book_id:
                with get_db() as conn:
                    conn.execute("""
                        UPDATE books 
                        SET title = ?, author = ?, category = ?, summary = ?, updated_at = ?
                        WHERE id = ?
                    """, (
                        title, author, category, summary,
                        datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                        book_id
                    ))
                    conn.commit()
            self.redirect("/")
            return

        # 3. Delete Book
        if path == "/api/delete":
            body = self.rfile.read(content_length).decode("utf-8")
            params = urllib.parse.parse_qs(body)
            book_id = params.get("id", [""])[0]
            
            if book_id:
                with get_db() as conn:
                    row = conn.execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()
                    if row:
                        file_path = os.path.join(CONTENTS_DIR, row["filename"])
                        if os.path.exists(file_path):
                            try:
                                os.remove(file_path)
                            except OSError:
                                pass
                                
                        if row["cover_path"]:
                            cov_path = os.path.join(BASE_DIR, row["cover_path"])
                            if os.path.exists(cov_path):
                                try:
                                    os.remove(cov_path)
                                except OSError:
                                    pass
                                    
                        conn.execute("DELETE FROM books WHERE id = ?", (book_id,))
                        conn.commit()
                        
            self.redirect("/")
            return

        self.send_error(404, "Not Found")

# ----------------------------------------------------------------------
# Main Runner
# ----------------------------------------------------------------------

def run_server(port=8080, host="0.0.0.0"):
    print("Initializing SQLite database...")
    init_db()
    print("Syncing contents/ directory...")
    sync_library_from_disk()
    
    server_address = (host, port)
    httpd = ThreadingHTTPServer(server_address, OPDSHandler)
    print(f"\n=======================================================")
    print(f"Minimal OPDS Server is running:")
    print(f"  - Web Manager: http://localhost:{port}/")
    print(f"  - OPDS Feed:   http://localhost:{port}/catalog.xml (or /opds)")
    print(f"=======================================================\n")
    print("Press Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    run_server(port=port)
