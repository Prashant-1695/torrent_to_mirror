#!/usr/bin/env python3

import os
import time
import json
import base64
import re
import requests
import subprocess
import libtorrent as lt
import logging
from typing import Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from requests_toolbelt import MultipartEncoder, MultipartEncoderMonitor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler("torrent_downloader.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


class UploadService(Enum):
    GOFILE = "go"


class TelegramNotifier:
    def __init__(self, bot_id: str, chat_id: str):
        self.bot_id = bot_id
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{bot_id}/sendMessage"
        self.max_retries = 3
        self.retry_delay = 5

    def send_message(self, message: str) -> requests.Response:
        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        }

        for attempt in range(self.max_retries):
            try:
                response = requests.post(self.base_url, json=payload, timeout=10)
                logger.info(
                    f"Telegram API Response: {response.status_code} - {response.text}"
                )

                if response.status_code == 200:
                    logger.info("Message sent successfully")
                    return response
                elif response.status_code == 429:
                    retry_after = (
                        response.json()
                        .get("parameters", {})
                        .get("retry_after", self.retry_delay)
                    )
                    logger.warning(f"Rate limited. Waiting {retry_after}s")
                    time.sleep(retry_after)
                else:
                    logger.error(
                        f"Send failed: {response.status_code} - {response.text}"
                    )
                    time.sleep(self.retry_delay)
            except requests.exceptions.RequestException as e:
                logger.error(f"Request failed: {str(e)}")
                time.sleep(self.retry_delay)
        return None


class ProgressMessage:
    def __init__(self, notifier: TelegramNotifier):
        self.notifier = notifier
        self.message_id = None
        self.last_update_time = 0
        self.min_update_interval = 3
        self.rate_limit_delay = 1
        self.max_rate_limit_delay = 30
        self.last_text = None

    def send_initial(self, text: str) -> None:
        logger.info(f"Sending initial message: {text}")
        response = self.notifier.send_message(text)
        try:
            if response and response.status_code == 200:
                self.message_id = response.json()["result"]["message_id"]
                self.last_text = text
                logger.info(f"Initial message sent with ID: {self.message_id}")
            else:
                logger.error("Failed to get message ID")
        except (AttributeError, KeyError, json.JSONDecodeError) as e:
            logger.error(f"Failed to get message ID: {str(e)}")

    def update(self, text: str) -> None:
        current_time = time.time()

        # Skip update if text hasn't changed
        if text == self.last_text:
            logger.debug("Skipping update - text unchanged")
            return

        logger.info(f"Updating progress message: {text}")

        # Ensure minimum interval between updates
        if current_time - self.last_update_time < self.min_update_interval:
            time.sleep(self.min_update_interval)
            current_time = time.time()

        if not self.message_id:
            logger.info("No message ID - sending initial message")
            self.send_initial(text)
            return

        url = f"https://api.telegram.org/bot{self.notifier.bot_id}/editMessageText"
        payload = {
            "chat_id": self.notifier.chat_id,
            "message_id": self.message_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        }

        max_retries = 5
        current_retry = 0

        while current_retry < max_retries:
            try:
                response = requests.post(url, json=payload, timeout=10)
                logger.info(
                    f"Message update response: {response.status_code} - {response.text}"
                )

                if response.status_code == 200:
                    self.last_update_time = current_time
                    self.last_text = text
                    self.rate_limit_delay = 1
                    logger.info("Message successfully updated")
                    break
                elif response.status_code == 429:
                    retry_after = (
                        response.json()
                        .get("parameters", {})
                        .get("retry_after", self.retry_delay)
                    )
                    logger.warning(f"Rate limited. Waiting {retry_after}s")
                    time.sleep(retry_after)
                    current_retry += 1
                else:
                    logger.error(
                        f"Update failed: {response.status_code} - {response.text}"
                    )
                    time.sleep(self.retry_delay)
                    current_retry += 1

            except requests.exceptions.RequestException as e:
                logger.error(f"Request failed: {str(e)}")
                time.sleep(self.retry_delay)
                current_retry += 1

        if current_retry >= max_retries:
            logger.error("Max retries reached for message update")
            # Try sending as new message if update fails
            self.notifier.send_message(text)


@dataclass
class DownloadStatus:
    progress: float
    download_speed: float
    upload_speed: float
    num_peers: int
    state: str
    total_size: int
    downloaded: int


class TorrentDownloader:
    def __init__(self, download_path: str, progress_message: ProgressMessage):
        self.download_path = download_path
        self.progress_message = progress_message
        self.session = self._configure_session()

    def _configure_session(self) -> lt.session:
        session = lt.session()
        session.listen_on(6881, 6891)

        settings = {
            "active_downloads": -1,
            "active_seeds": -1,
            "active_limit": 500,
            "download_rate_limit": 0,
            "upload_rate_limit": 0,
            "max_out_request_queue": 1500,
            "peer_connect_timeout": 2,
            "request_timeout": 10,
            "seed_time_limit": 0,
            "dht_announce_interval": 30,
            "alert_mask": lt.alert.category_t.all_categories,
            "enable_dht": True,
            "enable_lsd": True,
            "enable_upnp": True,
            "enable_natpmp": True,
        }
        session.apply_settings(settings)
        return session

    @staticmethod
    def extract_name_from_magnet(magnet_link: str) -> str:
        try:
            match = re.search(r"dn=([^&]+)", magnet_link)
            if match:
                return requests.utils.unquote(match.group(1))
        except Exception as e:
            logger.error(f"Name extraction failed: {str(e)}")
        return "Unknown_torrent"

    def get_download_status(self, handle: lt.torrent_handle) -> DownloadStatus:
        status = handle.status()

        states = [
            "queued",
            "checking",
            "downloading metadata",
            "downloading",
            "finished",
            "seeding",
            "allocating",
        ]
        state = states[status.state] if status.state < len(states) else "unknown"

        return DownloadStatus(
            progress=status.progress * 100,
            download_speed=status.download_rate / 1_048_576,  # MB/s
            upload_speed=status.upload_rate / 1_048_576,  # MB/s
            num_peers=status.num_peers,
            state=state,
            total_size=handle.status().total_wanted,
            downloaded=handle.status().total_wanted_done,
        )

    def _create_progress_bar(self, percentage: float, width: int = 25) -> str:
        filled = int(width * percentage / 100)
        return "█" * filled + "░" * (width - filled)

    def download_torrent(self, magnet_link: str) -> Tuple[bool, Optional[str]]:
        torrent_name = self.extract_name_from_magnet(magnet_link)
        logger.info(f"Starting download: {torrent_name}")

        try:
            params = {
                "save_path": self.download_path,
                "storage_mode": lt.storage_mode_t.storage_mode_sparse,
            }
            handle = lt.add_magnet_uri(self.session, magnet_link, params)

            self.progress_message.update(
                f"📥 Starting: {torrent_name}\n" f"Status: Waiting for metadata..."
            )

            while not handle.has_metadata():
                time.sleep(1)
                if not handle.is_valid():
                    raise RuntimeError("Failed to get metadata")

            start_time = time.time()
            last_update_time = 0
            update_interval = 1

            while not handle.is_seed():
                status = self.get_download_status(handle)
                current_time = time.time()

                if current_time - last_update_time >= update_interval:
                    if status.download_speed > 0:
                        remaining = status.total_size - status.downloaded
                        eta_seconds = remaining / (status.download_speed * 1_048_576)
                        eta = f"{int(eta_seconds//3600)}h {int((eta_seconds%3600)//60)}m {int(eta_seconds%60)}s"
                    else:
                        eta = "calculating..."

                    progress_bar = self._create_progress_bar(status.progress)
                    message = (
                        f"📥 Downloading: {torrent_name}\n\n"
                        f"▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰\n"
                        f"{progress_bar} {status.progress:.1f}%\n"
                        f"▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰\n\n"
                        f"⬇️ Speed: {status.download_speed:.2f} MB/s\n"
                        f"⬆️ Upload: {status.upload_speed:.2f} MB/s\n"
                        f"👥 Peers: {status.num_peers}\n"
                        f"⏳ ETA: {eta}\n"
                        f"💾 Size: {status.total_size/(1024**3):.2f} GB\n"
                        f"📊 Status: {status.state}"
                    )

                    self.progress_message.update(message)
                    last_update_time = current_time

                if not handle.is_valid():
                    raise RuntimeError("Download handle became invalid")

                time.sleep(0.1)

            return True, torrent_name

        except Exception as e:
            error_msg = f"❌ Download failed: {str(e)}"
            self.progress_message.update(error_msg)
            logger.error(f"Download failed: {str(e)}")
            return False, None

    def cleanup(self):
        try:
            if self.session:
                self.session.pause()
                for torrent in self.session.get_torrents():
                    self.session.remove_torrent(torrent)
                self.session = None
        except Exception as e:
            logger.error(f"Cleanup error: {str(e)}")


class FileUploader:
    def __init__(self, progress_message: ProgressMessage):
        self.progress_message = progress_message
        self.upload_script = "./upload.sh"
        self.retries = 3
        self.retry_delay = 5
        self.max_file_size = 10 * 1024 * 1024 * 1024  # 10GB in bytes

    def _format_size(self, size_bytes: float) -> str:
        """Format bytes into human readable format"""
        for unit in ["B", "KB", "MB", "GB"]:
            if size_bytes < 1024:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.2f} TB"

    def _upload_file(self, file_path: str, was_compressed: bool = False) -> bool:
        """Internal method to handle file upload"""
        file_size = os.path.getsize(file_path)
        filename = os.path.basename(file_path)

        # Check file size
        if file_size > self.max_file_size:
            error_msg = f"File size ({self._format_size(file_size)}) exceeds 10GB limit"
            self.progress_message.update(
                "✅ Download Complete!\n"
                f"{'✅ Compression Complete!' if was_compressed else '📝 No compression needed'}\n"
                "❌ Upload Failed!\n\n"
                f"Error Details: {error_msg}"
            )
            return False

        logger.info(
            f"Starting upload of {filename} (Size: {self._format_size(file_size)})"
        )

        # Update message to show upload started
        self.progress_message.update(
            "✅ Download Complete!\n"
            f"{'✅ Compression Complete!' if was_compressed else '📝 No compression needed'}\n"
            "📤 Uploading file to GoFile..."
        )

        try:
            # Start upload process
            process = subprocess.Popen(
                [self.upload_script, file_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
            )

            # Wait for completion
            stdout, stderr = process.communicate()

            if process.returncode == 0 and stdout.strip():
                download_link = stdout.strip()

                # Format success message
                final_parts = [
                    "✅ Download Complete!",
                    "✅ Compression Complete!"
                    if was_compressed
                    else "📝 No compression needed",
                    "✅ Upload Complete!",
                    "",
                    f"📁 File: {filename}",
                    f"🔗 Download Link: {download_link}",
                    f"💾 Size: {self._format_size(file_size)}",
                ]

                final_message = "\n".join(final_parts)
                logger.info(f"Upload successful: {download_link}")

                self.progress_message.update(final_message)
                return True
            else:
                error_msg = stderr.strip() if stderr else "Unknown error"
                raise Exception(f"Upload failed: {error_msg}")

        except Exception as e:
            logger.error(f"Upload error: {str(e)}")
            error_parts = [
                "✅ Download Complete!",
                "✅ Compression Complete!"
                if was_compressed
                else "📝 No compression needed",
                "❌ Upload Failed!",
                "",
                f"Error Details: {str(e)}",
            ]
            self.progress_message.update("\n".join(error_parts))
            return False

    def upload_file(self, file_path: str, was_compressed: bool = False) -> bool:
        """Public method to upload a file with retries"""
        if not os.path.exists(file_path):
            self.progress_message.update("❌ File not found")
            return False

        if not os.path.exists(self.upload_script):
            error_msg = f"❌ Upload script not found: {self.upload_script}"
            logger.error(error_msg)
            self.progress_message.update(error_msg)
            return False

        # Make upload script executable
        try:
            os.chmod(self.upload_script, 0o755)
        except Exception as e:
            logger.error(f"Failed to make upload script executable: {e}")

        # Attempt upload with retries
        for attempt in range(self.retries):
            try:
                logger.info(f"Upload attempt {attempt + 1} of {self.retries}")
                if self._upload_file(file_path, was_compressed):
                    return True

                if attempt < self.retries - 1:
                    wait_time = self.retry_delay * (attempt + 1)
                    logger.warning(
                        f"Upload attempt {attempt + 1} failed, waiting {wait_time}s before retry"
                    )
                    time.sleep(wait_time)
            except Exception as e:
                logger.error(f"Upload attempt {attempt + 1} error: {str(e)}")
                if attempt < self.retries - 1:
                    wait_time = self.retry_delay * (attempt + 1)
                    time.sleep(wait_time)

        error_msg = f"Upload failed after {self.retries} attempts"
        logger.error(error_msg)
        self.progress_message.update(f"❌ {error_msg}")
        return False


class FileCompressor:
    def __init__(self, progress_message: ProgressMessage):
        self.progress_message = progress_message

    def _has_subdirectories(self, folder_path: str) -> bool:
        """Check if the folder has any subdirectories"""
        try:
            return any(
                os.path.isdir(os.path.join(folder_path, item))
                for item in os.listdir(folder_path)
            )
        except Exception as e:
            logger.error(f"Subdirectory check failed: {str(e)}")
            return False

    def _get_subdirectories(self, folder_path: str) -> list:
        """Get list of all subdirectories in the folder"""
        try:
            return [
                os.path.join(folder_path, item)
                for item in os.listdir(folder_path)
                if os.path.isdir(os.path.join(folder_path, item))
            ]
        except Exception as e:
            logger.error(f"Failed to get subdirectories: {str(e)}")
            return []

    def _get_files_in_directory(self, directory: str) -> list:
        """Get all files in a directory and its subdirectories"""
        files = []
        try:
            for root, _, filenames in os.walk(directory):
                for filename in filenames:
                    file_path = os.path.join(root, filename)
                    if os.path.isfile(file_path):
                        files.append(file_path)
        except Exception as e:
            logger.error(f"Failed to get files in directory {directory}: {str(e)}")
        return files

    def _get_total_size(self, files: list) -> int:
        """Calculate total size of files"""
        return sum(os.path.getsize(f) for f in files if os.path.isfile(f))

    def _format_size(self, size_bytes: float) -> str:
        """Format size in bytes to human readable format"""
        for unit in ["B", "KB", "MB", "GB"]:
            if size_bytes < 1024:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.2f} TB"

    def _create_progress_bar(self, percentage: float, width: int = 25) -> str:
        """Create a progress bar with the given percentage"""
        filled = int(width * percentage / 100)
        return "█" * filled + "░" * (width - filled)

    def compress_folder(self, folder_path: str, output_name: str) -> Optional[str]:
        """Compress only subdirectories, skip files in root folder"""
        if not os.path.exists(folder_path) or not os.path.isdir(folder_path):
            logger.warning(f"Invalid directory: {folder_path}")
            return None

        # Check for subdirectories
        subdirs = self._get_subdirectories(folder_path)
        if not subdirs:
            self.progress_message.update(
                "✅ Download Complete!\n"
                "📝 No subdirectories to compress\n"
                "📤 Preparing upload..."
            )
            return None

        try:
            # Collect all files from subdirectories
            files = []
            total_size = 0
            for subdir in subdirs:
                subdir_files = self._get_files_in_directory(subdir)
                files.extend(subdir_files)
                total_size += self._get_total_size(subdir_files)

            if not files:
                logger.warning("No files found in subdirectories to compress")
                self.progress_message.update(
                    "✅ Download Complete!\n"
                    "📝 No files to compress\n"
                    "📤 Preparing upload..."
                )
                return None

            zip_path = f"{output_name}.7z"

            self.progress_message.update(
                "✅ Download Complete!\n" "🗜️ Preparing compression..."
            )

            # Start 7z compression with progress output
            command = [
                "7z",
                "a",  # Add files to archive
                "-t7z",  # 7z archive type
                "-m0=lzma2",  # LZMA2 compression method
                "-mx=0",
                "-mmt=on",  # Enable multithreading
                "-aoa",  # Overwrite all existing files
                "-bsp1",  # Show progress
                zip_path,  # Output archive path
            ]

            # Add only subdirectories to compress
            command.extend(subdirs)

            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                bufsize=1,
            )

            start_time = time.time()
            processed_size = 0
            speeds = []
            last_progress = 0

            while True:
                if process.poll() is not None:
                    break

                line = process.stderr.readline().strip()
                if not line:
                    continue

                try:
                    # Parse 7z progress output
                    if "%" in line:
                        # Extract progress percentage and filename
                        progress_match = re.search(r"(\d+)%", line)
                        file_match = re.search(r"\s-\s(.+)$", line)

                        if progress_match:
                            progress = float(progress_match.group(1))
                            current_file = (
                                file_match.group(1) if file_match else "Processing..."
                            )

                            # Calculate speed only if progress changed
                            if progress > last_progress:
                                current_time = time.time()
                                elapsed = current_time - start_time
                                if elapsed > 0:
                                    current_processed = (total_size * progress) / 100
                                    speed = (
                                        (current_processed - processed_size)
                                        / elapsed
                                        / 1048576
                                    )  # MB/s
                                    processed_size = current_processed

                                    speeds.append(speed)
                                    if len(speeds) > 5:
                                        speeds.pop(0)

                                    # Format progress message
                                    message_parts = [
                                        "✅ Download Complete!",
                                        "🗜️ Compressing Directories:",
                                        "",
                                        f"📁 Current: {current_file}",
                                        "▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰",
                                        f"{self._create_progress_bar(progress)} {progress:.1f}%",
                                        "▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰",
                                        "",
                                        f"⚡ Speed: {speed:.2f} MB/s",
                                        f"📊 Avg Speed: {sum(speeds)/len(speeds):.2f} MB/s",
                                        f"💾 Size: {self._format_size(processed_size)} / {self._format_size(total_size)}",
                                    ]

                                    self.progress_message.update(
                                        "\n".join(message_parts)
                                    )
                                    start_time = current_time
                                    last_progress = progress

                except Exception as e:
                    logger.error(f"Progress parsing error: {str(e)}")
                    continue

            # Check compression result
            stdout, stderr = process.communicate()

            if process.returncode == 0:
                self.progress_message.update(
                    "✅ Download Complete!\n"
                    "✅ Compression Complete!\n"
                    "📤 Preparing upload..."
                )
                return zip_path
            else:
                error_output = stderr if stderr else stdout
                raise subprocess.CalledProcessError(
                    process.returncode,
                    command,
                    f"7z compression failed: {error_output}",
                )

        except Exception as e:
            logger.error(f"Compression failed: {str(e)}")
            self.progress_message.update(
                f"✅ Download Complete!\n"
                f"❌ Compression failed: {str(e)}\n"
                f"📤 Uploading original files..."
            )
            return None


def get_magnet_link_from_github(
    repo: str, path: str, branch: str = "main"
) -> Optional[str]:
    raw_url = f"https://raw.githubusercontent.com/{repo}/{branch}/{path}"

    try:
        headers = {"User-Agent": "MagnetLinkFetcher/1.0"}
        response = requests.get(raw_url, headers=headers, timeout=10)

        if response.status_code == 200:
            magnet_link = response.text.strip()
            logger.info("Magnet link retrieved")
            return magnet_link

        logger.error(f"Fetch failed: HTTP {response.status_code}")
        return None

    except requests.exceptions.RequestException as e:
        logger.error(f"Fetch error: {str(e)}")
        return None


def main():
    logger.info("Script started")

    bot_id = os.getenv("BOT_ID")
    chat_id = os.getenv("CHAT_ID")
    if not all([bot_id, chat_id]):
        logger.error("Missing environment variables")
        return

    notifier = TelegramNotifier(bot_id, chat_id)
    progress_message = ProgressMessage(notifier)
    download_path = os.path.join(os.getcwd(), "downloads")
    os.makedirs(download_path, exist_ok=True)

    try:
        github_repo = "Prashant-1695/magnet_url"
        magnet_link = get_magnet_link_from_github(github_repo, "magnet_link.txt")

        if not magnet_link:
            error_msg = "Failed to get magnet link"
            logger.error(error_msg)
            progress_message.update(f"❌ {error_msg}")
            return

        progress_message.send_initial("✨ Starting download...")
        downloader = TorrentDownloader(download_path, progress_message)

        download_success, torrent_name = downloader.download_torrent(magnet_link)
        if download_success and torrent_name:
            # Use torrent name directly without timestamp
            base_name = torrent_name

            compressor = FileCompressor(progress_message)
            compressed_file = compressor.compress_folder(download_path, base_name)

            uploader = FileUploader(progress_message)
            if compressed_file:
                uploader.upload_file(compressed_file, was_compressed=True)
            else:
                files = [
                    f
                    for f in os.listdir(download_path)
                    if os.path.isfile(os.path.join(download_path, f))
                ]
                if files:
                    file_to_upload = os.path.join(download_path, files[0])
                    uploader.upload_file(file_to_upload, was_compressed=False)
                else:
                    progress_message.update(
                        "✅ Download Complete!\n" "❌ No files to upload"
                    )

    except KeyboardInterrupt:
        logger.info("User interrupted")
        progress_message.update("⚠️ User interrupted")
    except Exception as e:
        error_msg = f"Error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        progress_message.update(f"❌ {error_msg}")
    finally:
        if "downloader" in locals():
            downloader.cleanup()
        logger.info("Script finished")


if __name__ == "__main__":
    main()
