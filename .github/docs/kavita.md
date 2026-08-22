# Using Kavita as a Local Server

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
