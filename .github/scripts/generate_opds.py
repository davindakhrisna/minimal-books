import os
import glob
import yaml
import urllib.parse
from datetime import datetime, timezone
import uuid
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom

BOOKS_YAML = ".github/books.yaml"
CATALOG_XML = "catalog.xml"
SUPPORTED_EXTENSIONS = {".pdf": "application/pdf", ".epub": "application/epub+zip"}

def load_books():
    if os.path.exists(BOOKS_YAML):
        with open(BOOKS_YAML, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or []
    return []

def save_books(books):
    with open(BOOKS_YAML, "w", encoding="utf-8") as f:
        yaml.dump(books, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

def discover_files():
    files = []
    for ext in SUPPORTED_EXTENSIONS:
        files.extend(glob.glob(f"*{ext}"))
    return files

def update_books_yaml():
    books = load_books()
    existing_files = {b.get("file") for b in books if b.get("file")}
    discovered = discover_files()
    
    added_new = False
    for file in discovered:
        if file not in existing_files:
            # Create a placeholder entry
            title = os.path.splitext(file)[0].replace("_", " ").title()
            books.append({
                "title": title,
                "author": "Unknown",
                "genre": "Uncategorized",
                "summary": "No summary provided.",
                "cover": "",
                "tags": [],
                "file": file
            })
            added_new = True
            print(f"Added new book to metadata: {file}")
            
    if added_new:
        save_books(books)
    return books

def generate_opds(books):
    # Setup namespaces
    ATOM_NS = "http://www.w3.org/2005/Atom"
    DC_NS = "http://purl.org/dc/terms/"
    OPDS_NS = "http://opds-spec.org/2010/catalog"
    
    feed = Element("feed", {
        "xmlns": ATOM_NS,
        "xmlns:dc": DC_NS,
        "xmlns:opds": OPDS_NS
    })
    
    SubElement(feed, "id").text = "urn:uuid:github-pages-book-catalog"
    SubElement(feed, "title").text = "My Book Catalog"
    SubElement(feed, "updated").text = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    author = SubElement(feed, "author")
    SubElement(author, "name").text = "OPDS Generator"
    
    SubElement(feed, "link", {
        "rel": "self",
        "href": "catalog.xml",
        "type": "application/atom+xml;profile=opds-catalog;kind=navigation"
    })
    SubElement(feed, "link", {
        "rel": "start",
        "href": "catalog.xml",
        "type": "application/atom+xml;profile=opds-catalog;kind=navigation"
    })

    for book in books:
        if not book.get("file") or not os.path.exists(book["file"]):
            continue
            
        entry = SubElement(feed, "entry")
        
        SubElement(entry, "title").text = book.get("title", "Unknown Title")
        
        book_id = str(uuid.uuid5(uuid.NAMESPACE_URL, "urn:file:" + book["file"]))
        SubElement(entry, "id").text = f"urn:uuid:{book_id}"
        SubElement(entry, "updated").text = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        
        b_author = SubElement(entry, "author")
        SubElement(b_author, "name").text = book.get("author", "Unknown")
        
        SubElement(entry, "summary").text = book.get("summary", "")
        
        genre = book.get("genre")
        if genre:
            SubElement(entry, "category", {"term": genre, "label": genre})
            
        tags = book.get("tags") or []
        for tag in tags:
            SubElement(entry, "category", {"term": tag, "label": tag})
            
        cover = book.get("cover")
        if cover:
            SubElement(entry, "link", {
                "rel": "http://opds-spec.org/image",
                "href": urllib.parse.quote(cover),
                "type": "image/jpeg"
            })
            SubElement(entry, "link", {
                "rel": "http://opds-spec.org/image/thumbnail",
                "href": urllib.parse.quote(cover),
                "type": "image/jpeg"
            })
            
        # File acquisition link
        ext = os.path.splitext(book["file"])[1].lower()
        mime_type = SUPPORTED_EXTENSIONS.get(ext, "application/octet-stream")
        
        SubElement(entry, "link", {
            "rel": "http://opds-spec.org/acquisition",
            "href": urllib.parse.quote(book["file"]),
            "type": mime_type
        })
        
    xml_str = tostring(feed, "utf-8")
    parsed_xml = minidom.parseString(xml_str)
    pretty_xml = parsed_xml.toprettyxml(indent="  ")
    
    with open(CATALOG_XML, "w", encoding="utf-8") as f:
        f.write(pretty_xml)
        
    print(f"Generated {CATALOG_XML} with {len(books)} entries.")

if __name__ == "__main__":
    print("Updating books.yaml...")
    books = update_books_yaml()
    print("Generating catalog.xml...")
    generate_opds(books)
    print("Done!")
