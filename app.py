from flask import (
    Flask,
    request,
    render_template,
    send_file,
    redirect,
    url_for,
    flash,
    after_this_request,
    make_response,
)
from PIL import Image
import os
from werkzeug.utils import secure_filename
import uuid
import logging
import subprocess
import shutil
import time

app = Flask(__name__)

# --- Configuration ---
app.config["SECRET_KEY"] = os.environ.get(
    "FLASK_SECRET_KEY", "dev_secret_key_video_image_converter_001"
)  # Change for production
app.config["UPLOAD_FOLDER"] = "uploads"
app.config["CONVERTED_IMAGES_FOLDER"] = "converted_images"
app.config["CONVERTED_VIDEOS_FOLDER"] = "converted_videos"
app.config["MAX_CONTENT_LENGTH"] = (
    128 * 1024 * 1024
)  # Increased to 128 MB for video (adjust as needed)

ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "bmp", "tiff"}
ALLOWED_VIDEO_EXTENSIONS = {"mp4", "mov", "avi", "mkv", "webm", "flv", "wmv"}

# --- Configure logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s [%(name)s:%(lineno)d]",
)
# For Flask specific logs, you can also use app.logger
# app.logger.setLevel(logging.INFO)

# --- Ensure directories exist ---
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
os.makedirs(app.config["CONVERTED_IMAGES_FOLDER"], exist_ok=True)
os.makedirs(app.config["CONVERTED_VIDEOS_FOLDER"], exist_ok=True)


# --- Helper Functions ---
def allowed_file(filename, allowed_extensions_set):
    return (
        "." in filename and filename.rsplit(".", 1)[1].lower() in allowed_extensions_set
    )


def is_ffmpeg_installed():
    return shutil.which("ffmpeg") is not None


# --- IMAGE CONVERSION LOGIC ---
def convert_image_logic(
    pil_image, conversion_type, scale_factor, jpeg_quality=75, output_format_pref="JPEG"
):
    original_width, original_height = pil_image.size
    img_copy = pil_image.copy()
    if (
        (conversion_type == "to_low" and scale_factor < 1.0)
        or (conversion_type == "to_high" and scale_factor > 1.0)
        or (scale_factor != 1.0)
    ):
        new_width = int(original_width * scale_factor)
        new_height = int(original_height * scale_factor)
        if new_width < 1 or new_height < 1:
            flash("Error: Calculated image dimensions are too small.", "danger")
            return None, None, None
        try:
            img_copy = img_copy.resize(
                (new_width, new_height), Image.Resampling.LANCZOS
            )
        except Exception as e:
            flash(f"Error during image resizing: {e}", "danger")
            return None, None, None
    actual_output_format = output_format_pref.upper()
    if actual_output_format == "JPEG":
        if img_copy.mode == "RGBA" or img_copy.mode == "P":
            try:
                img_copy = img_copy.convert("RGB")
            except Exception as e:
                flash(f"Error converting image to RGB for JPEG: {e}", "danger")
                return None, None, None
    elif actual_output_format == "PNG":
        pass
    else:
        flash(f"Unsupported image output format: {output_format_pref}", "danger")
        return None, None, None
    return img_copy, actual_output_format, jpeg_quality


# --- VIDEO CONVERSION LOGIC (with FFmpeg scale fix) ---
def convert_video_ffmpeg(
    input_path, output_path, target_resolution, video_bitrate, audio_bitrate="128k"
):
    if not is_ffmpeg_installed():
        flash(
            "FFmpeg is not installed or not found in PATH. Video conversion is unavailable.",
            "danger",
        )
        app.logger.error("FFmpeg not found.")
        return False

    ffmpeg_cmd = ["ffmpeg", "-y", "-i", input_path]

    if target_resolution and target_resolution.lower() != "original":
        parts = target_resolution.lower().split("x")
        scale_filter_value = ""
        if len(parts) == 2:
            w_part, h_part = parts[0], parts[1]
            final_w = "-2" if w_part == "-1" else w_part
            final_h = "-2" if h_part == "-1" else h_part
            if final_w == "-2" and final_h == "-2":
                app.logger.warning(
                    "Both width and height for scaling are auto (-2). Skipping scale filter."
                )
            elif (
                final_w == "-2"
                or final_h == "-2"
                or (final_w.isdigit() and final_h.isdigit())
            ):
                scale_filter_value = f"scale={final_w}:{final_h}"
            else:
                app.logger.warning(
                    f"Invalid resolution parts for scale: {target_resolution}. Skipping scale filter."
                )
        if scale_filter_value:
            ffmpeg_cmd.extend(["-vf", scale_filter_value])

    ffmpeg_cmd.extend(["-c:v", "libx264"])
    if video_bitrate:
        ffmpeg_cmd.extend(["-b:v", video_bitrate])
    ffmpeg_cmd.extend(["-preset", "medium", "-pix_fmt", "yuv420p"])
    ffmpeg_cmd.extend(["-c:a", "aac"])
    if audio_bitrate:
        ffmpeg_cmd.extend(["-b:a", audio_bitrate])
    ffmpeg_cmd.append(output_path)

    app.logger.info(f"Executing FFmpeg command: {' '.join(ffmpeg_cmd)}")
    try:
        process = subprocess.run(
            ffmpeg_cmd,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        app.logger.info(f"FFmpeg stdout: {process.stdout}")
        app.logger.info(f"FFmpeg stderr: {process.stderr}")
        return True
    except subprocess.CalledProcessError as e:
        failed_command = (
            " ".join(e.cmd) if hasattr(e, "cmd") else "Command not available"
        )
        flash(f"FFmpeg error (code {e.returncode}): {e.stderr}", "danger")
        app.logger.error(f"FFmpeg CalledProcessError running: {failed_command}")
        app.logger.error(f"FFmpeg stderr: {e.stderr}")
        app.logger.error(f"FFmpeg stdout: {e.stdout}")
        return False
    except FileNotFoundError:
        flash("FFmpeg command not found. Ensure it's installed and in PATH.", "danger")
        app.logger.error("FFmpeg FileNotFoundError during subprocess.run")
        return False
    except Exception as e:
        flash(f"An unexpected error occurred during video conversion: {e}", "danger")
        app.logger.error(f"Unexpected video conversion error: {e}", exc_info=True)
        return False


# --- IMAGE CONVERTER ROUTE ---
@app.route("/", methods=["GET", "POST"])
def index_image_converter():
    if request.method == "POST":
        input_filepath = None
        output_filepath = None
        input_image_format = None
        if "file" not in request.files:
            flash("No file part.", "danger")
            return redirect(request.url)
        file = request.files["file"]
        if file.filename == "":
            flash("No selected file.", "warning")
            return redirect(request.url)

        if file and allowed_file(file.filename, ALLOWED_IMAGE_EXTENSIONS):
            original_filename = secure_filename(file.filename)
            unique_id = str(uuid.uuid4())
            temp_input_filename = f"{unique_id}_{original_filename}"
            input_filepath = os.path.join(
                app.config["UPLOAD_FOLDER"], temp_input_filename
            )
            try:
                file.save(input_filepath)
                with Image.open(input_filepath) as tif:
                    input_image_format = tif.format.upper() if tif.format else None
            except Exception as e:
                flash(f"Error saving/reading image: {e}", "danger")
                if input_filepath and os.path.exists(input_filepath):
                    os.remove(input_filepath)
                return redirect(request.url)

            conversion_type = request.form.get("conversion_type", "to_low")
            try:
                scale_factor = float(request.form.get("scale_factor", "0.5"))
                jpeg_quality = int(request.form.get("jpeg_quality", "75"))
                output_format_pref = request.form.get("output_format", "JPEG").upper()
            except ValueError:
                flash("Invalid image parameters. Please enter numbers.", "danger")
                if input_filepath and os.path.exists(input_filepath):
                    os.remove(input_filepath)
                return redirect(request.url)
            # Add more specific parameter validation if needed

            try:
                with Image.open(input_filepath) as img_pil:
                    converted_pil_image, output_format, final_jpeg_quality = (
                        convert_image_logic(
                            img_pil,
                            conversion_type,
                            scale_factor,
                            jpeg_quality,
                            output_format_pref,
                        )
                    )
                if converted_pil_image:
                    base_name, _ = os.path.splitext(original_filename)
                    output_filename = (
                        f"{unique_id}_{base_name}_converted.{output_format.lower()}"
                    )
                    output_filepath = os.path.join(
                        app.config["CONVERTED_IMAGES_FOLDER"], output_filename
                    )

                    if output_format == "JPEG":
                        subsampling_setting = 0 if final_jpeg_quality > 90 else 2
                        if input_image_format == "JPEG" and final_jpeg_quality <= 90:
                            subsampling_setting = "keep"
                        converted_pil_image.save(
                            output_filepath,
                            "JPEG",
                            quality=final_jpeg_quality,
                            optimize=True,
                            subsampling=subsampling_setting,
                        )
                    elif output_format == "PNG":
                        converted_pil_image.save(output_filepath, "PNG", optimize=True)
                    else:
                        raise Exception("Unknown image output format for saving")

                    response = make_response(
                        send_file(
                            output_filepath,
                            as_attachment=True,
                            download_name=f"{base_name}_converted.{output_format.lower()}",
                        )
                    )
                    response.set_cookie(
                        "fileDownloadComplete",
                        "true",
                        max_age=20,
                        path="/",
                        samesite="Lax",
                        httponly=False,
                    )

                    @after_this_request
                    def cleanup_image_task(r_img):
                        local_input_img = input_filepath
                        local_output_img = output_filepath
                        time.sleep(0.2)  # Short delay
                        try:
                            if local_input_img and os.path.exists(local_input_img):
                                os.remove(local_input_img)
                            if local_output_img and os.path.exists(local_output_img):
                                os.remove(local_output_img)
                        except PermissionError as pe:
                            app.logger.warning(
                                f"Img cleanup PermissionError: {pe.filename}. Retrying once..."
                            )
                            time.sleep(0.5)
                            try:
                                if (
                                    local_output_img
                                    and os.path.exists(local_output_img)
                                    and pe.filename
                                    and local_output_img in pe.filename
                                ):
                                    os.remove(local_output_img)
                                elif (
                                    local_input_img
                                    and os.path.exists(local_input_img)
                                    and pe.filename
                                    and local_input_img in pe.filename
                                ):
                                    os.remove(local_input_img)
                            except Exception as e_retry:
                                app.logger.error(f"Img cleanup retry error: {e_retry}")
                        except Exception as e_clean:
                            app.logger.error(f"Img cleanup general error: {e_clean}")
                        return r_img

                    return response
                else:  # conversion logic failed
                    if input_filepath and os.path.exists(input_filepath):
                        os.remove(input_filepath)
                    return redirect(request.url)
            except Exception as e:
                flash(f"Error processing image: {e}", "danger")
                app.logger.error(f"Image processing error: {e}", exc_info=True)
                if input_filepath and os.path.exists(input_filepath):
                    os.remove(input_filepath)
                if output_filepath and os.path.exists(output_filepath):
                    os.remove(output_filepath)
                return redirect(request.url)
        else:
            flash(
                f"Invalid image file type. Allowed: {', '.join(ALLOWED_IMAGE_EXTENSIONS)}",
                "danger",
            )
            return redirect(request.url)
    return render_template("index.html")


# --- VIDEO CONVERTER ROUTE ---
@app.route("/video", methods=["GET", "POST"])
def video_converter_route():
    if not is_ffmpeg_installed():
        flash(
            "FFmpeg is not installed or not found in PATH. Video conversion is unavailable.",
            "danger",
        )

    if request.method == "POST":
        input_filepath = None
        output_filepath = None
        if "file" not in request.files:
            flash("No video file part.", "danger")
            return redirect(request.url)
        file = request.files["file"]
        if file.filename == "":
            flash("No video file selected.", "warning")
            return redirect(request.url)

        if file and allowed_file(file.filename, ALLOWED_VIDEO_EXTENSIONS):
            original_filename = secure_filename(file.filename)
            unique_id = str(uuid.uuid4())
            temp_input_filename = f"{unique_id}_{original_filename}"
            input_filepath = os.path.join(
                app.config["UPLOAD_FOLDER"], temp_input_filename
            )
            try:
                file.save(input_filepath)
            except Exception as e:
                flash(f"Error saving uploaded video: {e}", "danger")
                if input_filepath and os.path.exists(input_filepath):
                    os.remove(input_filepath)
                return redirect(request.url)

            target_resolution = request.form.get("resolution", "-1x480")
            video_bitrate = request.form.get("video_bitrate", "1M")
            audio_bitrate = request.form.get("audio_bitrate", "128k")
            # Add validation for bitrate formats here if needed

            base_name, input_ext = os.path.splitext(original_filename)
            # Standardize output to MP4 or try to keep original if common
            common_vid_exts = [".mp4", ".mov", ".mkv", ".webm"]
            output_extension = (
                input_ext.lower()
                if input_ext and input_ext.lower() in common_vid_exts
                else ".mp4"
            )
            converted_video_filename = (
                f"{unique_id}_{base_name}_converted{output_extension}"
            )
            output_filepath = os.path.join(
                app.config["CONVERTED_VIDEOS_FOLDER"], converted_video_filename
            )

            conversion_success = convert_video_ffmpeg(
                input_filepath,
                output_filepath,
                target_resolution,
                video_bitrate,
                audio_bitrate,
            )

            if conversion_success:
                response = make_response(
                    send_file(
                        output_filepath,
                        as_attachment=True,
                        download_name=f"{base_name}_converted{output_extension}",
                    )
                )
                response.set_cookie(
                    "fileDownloadComplete",
                    "true",
                    max_age=30,
                    path="/",
                    samesite="Lax",
                    httponly=False,
                )

                @after_this_request
                def cleanup_video_task(r_vid):
                    local_input_vid = input_filepath
                    local_output_vid = output_filepath
                    time.sleep(0.5)  # Longer delay for video files
                    try:
                        if local_input_vid and os.path.exists(local_input_vid):
                            os.remove(local_input_vid)
                        if local_output_vid and os.path.exists(local_output_vid):
                            os.remove(local_output_vid)
                    except PermissionError as pe:
                        app.logger.warning(
                            f"Video cleanup PermissionError: {pe.filename}. Retrying once..."
                        )
                        time.sleep(1.0)
                        try:
                            if (
                                local_output_vid
                                and os.path.exists(local_output_vid)
                                and pe.filename
                                and local_output_vid in pe.filename
                            ):
                                os.remove(local_output_vid)
                            elif (
                                local_input_vid
                                and os.path.exists(local_input_vid)
                                and pe.filename
                                and local_input_vid in pe.filename
                            ):
                                os.remove(local_input_vid)
                        except Exception as e_retry:
                            app.logger.error(f"Video cleanup retry error: {e_retry}")
                    except Exception as e_clean:
                        app.logger.error(f"Video cleanup general error: {e_clean}")
                    return r_vid

                return response
            else:  # video conversion failed
                if input_filepath and os.path.exists(input_filepath):
                    os.remove(input_filepath)
                if output_filepath and os.path.exists(output_filepath):
                    os.remove(output_filepath)  # If FFmpeg created a partial file
                return redirect(request.url)
        else:
            flash(
                f"Invalid video file type. Allowed: {', '.join(ALLOWED_VIDEO_EXTENSIONS)}",
                "danger",
            )
            return redirect(request.url)
    return render_template("video_converter.html")


if __name__ == "__main__":
    app.run(debug=True)
