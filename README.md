<div align="center">
  <img src=".github/assets/logo.webp" alt="Minimal Books Logo" width="200" />
  <h1>Minimal Books</h1>
</div>

A minimalist, human-readable repository for storing and indexing books. This repository automatically generates a standard OPDS (Open Publication Distribution System) feed from the provided books, making them accessible to any standard e-reader or library software.

## Architecture

This project uses a simple architecture designed for easy maintenance:
1. **Books**: PDF and EPUB files are stored directly in the `contents/` directory.
2. **Metadata**: A central `.github/books.yaml` file allows maintainers to index and tag books with titles, authors, genres, and summaries.
3. **Automation**: A GitHub Actions workflow runs a Python script on every push. It reads the metadata, discovers new files, and generates a standard `catalog.xml` OPDS feed.
4. **Hosting**: The entire repository, including the books and the OPDS feed, is served statically via GitHub Pages.

## Connecting Directly to the OPDS Feed

Because the repository is hosted on GitHub Pages, the OPDS feed is available publicly. You can connect any OPDS-compatible e-reader (such as Moon+ Reader, FBReader, or Apple Books) directly to this repository.

1. Open your e-reader application.
2. Navigate to the Network Libraries or OPDS Catalogs section.
3. Add a new catalog and enter the following URL:
   `https://davindakhrisna.github.io/minimal-books/catalog.xml`
4. You can now browse, search, and download books directly to your device.

## Pairing with Kavita or Calibre

You can also use dedicated library management software like Kavita or Calibre to host or manage this library.

### Using Kavita as a Local Server

If you prefer to have a dedicated web interface and self-hosted server for your library, you can use Kavita to index the raw files.

1. Clone this repository to your local machine or server:
   ```bash
   git clone https://github.com/davindakhrisna/minimal-books.git
   ```
2. Set up Kavita (via Docker or standalone installation). If using Docker Compose:
   ```yaml
   version: '3.9'
   services:
     kavita:
       image: jvmilazz0/kavita:latest
       container_name: kavita
       volumes:
         - ./minimal-books/contents:/books
         - ./kavita-config:/kavita/config
       ports:
         - "5000:5000"
       restart: unless-stopped
   ```
3. Start the container and navigate to `http://localhost:5000`.
4. In Kavita's server settings, add a new Library of type "Book" and point it to the `/books` folder.
5. Kavita will automatically scan the PDFs and EPUBs and serve them through its own interface.

### Using Calibre

Calibre can be used to manage the files locally. 

1. Clone the repository to your computer.
2. Open Calibre and click the "Add books" dropdown.
3. Select "Add books from directories, including sub-directories".
4. Point it to the `contents/` directory of the cloned repository.
5. Calibre will import all the books and extract their internal metadata.

## Managing Metadata

To add or update metadata for the OPDS feed:
1. Open `.github/books.yaml`.
2. Find the entry for the book you want to modify, or add a new entry if the file was just added.
3. Modify the `title`, `author`, `genre`, `summary`, or `tags`.
4. Commit and push the changes. The GitHub Action will automatically regenerate the `catalog.xml` feed.
