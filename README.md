
## Prerequisites

*   **Python 3.7+**
*   **pip** (Python package installer)
*   **FFmpeg:** Must be installed on the system where the application will run and be accessible in the system's PATH.
    *   Download from [ffmpeg.org](https://ffmpeg.org/download.html) or install via your system's package manager (e.g., `apt`, `yum`, `brew`).
## Demo Expalin
 

https://github.com/user-attachments/assets/6978fefd-6d0a-49b8-8960-1155a4110380



   ```
## Setup and Installation (Local Development)

1.  **Clone the repository (if applicable):**
    ```bash
    git clone <your-repository-url>
    cd image_converter_web
    ```

2.  **Create and activate a virtual environment (recommended):**
    ```bash
    python3 -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    ```

3.  **Install Python dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
    The `requirements.txt` should include:
    ```
    Flask
    Pillow
    Werkzeug
    gunicorn  # (Optional for local dev, but good for consistency with production)
    ```

4.  **Verify FFmpeg Installation:**
    Open a terminal and type:
    ```bash
    ffmpeg -version
    ```
    If this command is not found, you need to install FFmpeg and/or add it to your system's PATH.

5.  **Set Flask Secret Key (Optional for local dev, but good practice):**
    The application uses a default secret key for development. For better security, you can set an environment variable:
    ```bash
    export FLASK_SECRET_KEY='your_very_strong_random_secret_key' # Linux/macOS
    # set FLASK_SECRET_KEY=your_very_strong_random_secret_key    # Windows CMD
    # $env:FLASK_SECRET_KEY='your_very_strong_random_secret_key' # Windows PowerShell
    ```

6.  **Run the Flask development server:**
    ```bash
    flask run
    ```
    Or, if you prefer to run directly:
    ```bash
    python app.py
    ```
    The application should be accessible at `http://127.0.0.1:5000/`.

## Usage

1.  Navigate to `http://127.0.0.1:5000/` for the Image Converter or `http://127.0.0.1:5000/video` for the Video Converter.
2.  **Choose a file** to upload.
3.  **Select conversion settings** from the form.
4.  Click the "Convert and Download" button.
5.  A loading GIF will appear while the file is processed.
6.  Once complete, the converted file will automatically download.

## Configuration (in `app.py`)

*   `app.config['SECRET_KEY']`: Flask secret key for session management.
*   `app.config['UPLOAD_FOLDER']`: Directory for storing uploaded files temporarily.
*   `app.config['CONVERTED_IMAGES_FOLDER']`: Directory for storing converted images temporarily.
*   `app.config['CONVERTED_VIDEOS_FOLDER']`: Directory for storing converted videos temporarily.
*   `app.config['MAX_CONTENT_LENGTH']`: Maximum allowed file upload size (e.g., `128 * 1024 * 1024` for 128MB).

## Deployment

This application is designed to be deployed using a WSGI server (like Gunicorn or uWSGI) behind a reverse proxy (like Nginx or Apache).

**Key Deployment Steps:**

1.  **Install FFmpeg** on the production server.
2.  Set up a **WSGI server** (e.g., Gunicorn):
    ```bash
    gunicorn --bind 0.0.0.0:5000 app:app # Or bind to a Unix socket
    ```
3.  Configure a **reverse proxy** (e.g., Nginx) to:
    *   Serve static files from the `static/` directory.
    *   Proxy dynamic requests to the Gunicorn process.
    *   Handle SSL/TLS termination for HTTPS.
    *   Set `client_max_body_size` to accommodate large file uploads.
4.  Use a **process manager** (e.g., `systemd`, `supervisor`) to keep the Gunicorn process running.
5.  Ensure appropriate **file permissions** for the `uploads/`, `converted_images/`, and `converted_videos/` directories.

(See the [Flask Deployment Docs](https://flask.palletsprojects.com/en/latest/deploying/) for more general guidance.)

## Potential Future Enhancements

*   **Background Task Queue (Celery/RQ):** For long video conversions to prevent HTTP request timeouts and improve user experience. The user could be notified when the conversion is done (e.g., via email or a status page).
*   **User Authentication:** If you want to restrict access or save user preferences.
*   **More Advanced FFmpeg Options:** Expose more FFmpeg parameters to the user (e.g., different codecs, CRF quality settings, audio track selection).
*   **Progress Bar for Conversions:** More complex, especially for FFmpeg, might require parsing FFmpeg's output or using a library that wraps FFmpeg and provides progress.
*   **Batch Processing:** Allow users to upload and convert multiple files at once.
*   **Cloud Storage:** Store uploaded and converted files on cloud storage (e.g., AWS S3, Google Cloud Storage) instead of the local server filesystem, especially for scalable deployments.

## Troubleshooting

*   **`PermissionError: [WinError 32]` (File in use):** This can sometimes occur on Windows if the cleanup task tries to delete a file too quickly after `send_file`. The `time.sleep()` and retry logic in the cleanup tasks aim to mitigate this.
*   **FFmpeg Errors:** Check the Flask console output for detailed FFmpeg error messages. Ensure FFmpeg is installed correctly and that the input video format is supported by your FFmpeg build. The "Invalid size" error for video scaling was addressed by changing `-1xHEIGHT` to `-2xHEIGHT` in FFmpeg commands.
*   **Large File Uploads:** Ensure `MAX_CONTENT_LENGTH` in Flask and `client_max_body_size` in your reverse proxy (e.g., Nginx) are set appropriately.

