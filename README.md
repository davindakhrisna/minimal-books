<div align="center">
  <img src=".github/assets/logo.png" alt="Minimal Books Logo" width="200" />
  <h1>📚 Minimal OPDS</h1>
</div>

A minimalist, human-readable repository for storing and indexing books. This repository automatically generates a standard OPDS (Open Publication Distribution System) feed from the provided books, making them accessible to any standard e-reader or library software.

## 🏗️ Architecture

This project uses a simple architecture designed for easy maintenance:
1. **Books**: PDF and EPUB files are stored directly in the `contents/` directory.
2. **Metadata**: A central `.github/books.yaml` file allows maintainers to index and tag books with titles, authors, genres, and summaries.
3. **Automation**: A GitHub Actions workflow runs a Python script on every push. It reads the metadata, discovers new files, and generates a standard `catalog.xml` OPDS feed.
4. **Hosting**: The entire repository, including the books and the OPDS feed, is served statically via GitHub Pages.

## 🌐 Connecting Directly to the OPDS Feed

Because the repository is hosted on GitHub Pages, the OPDS feed is available publicly. You can connect any OPDS-compatible e-reader (such as Moon+ Reader, FBReader, or Apple Books) directly to this repository.

1. Open your e-reader application.
2. Navigate to the Network Libraries or OPDS Catalogs section.
3. Add a new catalog and enter the following URL:
   `https://davindakhrisna.github.io/minimal-books/catalog.xml`
4. You can now browse, search, and download books directly to your device.

### ✍️ Managing Metadata

To add or update metadata for the OPDS feed:
1. Open `.github/books.yaml`.
2. Find the entry for the book you want to modify, or add a new entry if the file was just added.
3. Modify the `title`, `author`, `genre`, `summary`, or `tags`.
4. Commit and push the changes. The GitHub Action will automatically regenerate the `catalog.xml` feed. (Ignore this if you are self hosting)

## 🖥️ Self-Hosting (Standalone)

Because the OPDS feed and the books are entirely static, you can easily host this repository yourself on any server using a basic static file web server like Nginx, without needing GitHub Pages at all.

1. Clone the repository to your server:
   ```bash
   git clone https://github.com/davindakhrisna/minimal-books.git
   ```
2. Make sure you run `python .github/scripts/generate_opds.py` locally to generate your `catalog.xml` before hosting.
3. Use the included `docker-compose.yml` to spin up a lightweight Nginx server:
   ```bash
   docker-compose up -d
   ```
4. Your OPDS feed is now live on your server at `http://localhost:8080/catalog.xml`. Point your e-reader apps here!

### Syncing Updates Locally

If you are self-hosting and adding books directly to your server (instead of pushing to GitHub), your `catalog.xml` won't automatically update. You have two options to keep it synced:

**Option 1: Sync Manually**
Whenever you drop a new PDF or EPUB into the `contents/` folder, manually run the generator:
```bash
python .github/scripts/generate_opds.py
```

**Option 2: Run the Watcher**
You can run the included watcher script in the background. It will continuously monitor your `contents/` directory and `.github/books.yaml` for changes, and automatically regenerate the feed when it detects a new file or edit:
```bash
python .github/scripts/watch.py
```

## 📖 Alternative Library Management

You can also use dedicated library management software to host or manage this library:
- [Using Kavita as a Local Server](.github/docs/kavita.md)
- [Using Calibre](.github/docs/calibre.md)
