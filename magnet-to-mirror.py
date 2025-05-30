import os
import time
import base64
import re
import requests
import subprocess
import libtorrent as lt

def send_to_telegram(bot_id, chat_id, message):
    """Send a message to a specified Telegram chat with retry logic."""
    url = f"https://api.telegram.org/bot{bot_id}/sendMessage"
    payload = {'chat_id': chat_id, 'text': message}
    retry_after = 0

    while True:
        response = requests.post(url, json=payload)
        if response.status_code == 200:
            print('Message sent to Telegram.')
            break
        elif response.status_code == 429:
            retry_after = response.json().get('parameters', {}).get('retry_after', 1)
            print(f"Rate limit exceeded. Retrying after {retry_after} seconds.")
            time.sleep(retry_after)
        else:
            print(f'Failed to send message: {response.status_code} - {response.text}')
            break

def extract_name_from_magnet(magnet_link):
    """Extract the name from the magnet link."""
    # Use regex to find the 'dn' parameter (display name) in the magnet link
    match = re.search(r'dn=([^&]+)', magnet_link)
    if match:
        # Decode the URL-encoded name
        return requests.utils.unquote(match.group(1))
    return "Unknown file"

def download_torrent(magnet_link, download_path, bot_id, chat_id):
    """Download files from a torrent/magnet link using libtorrent."""

    print(f"Starting download for: {magnet_link}")

    # Extract the name of the torrent
    torrent_name = extract_name_from_magnet(magnet_link)
    print(f"Torrent name extracted: {torrent_name}")

    ses = lt.session()
    ses.listen_on(6881, 6891)

    # Optimize session settings for maximum download speed
    settings = {
        'active_downloads': 10,
        'active_seeds': 10,
        'active_limit': 500,
        'download_rate_limit': 0,  # No limit
        'upload_rate_limit': 0,  # No limit
        'max_out_request_queue': 1500,
        'peer_connect_timeout': 2,
        'request_timeout': 10,
        'seed_time_limit': 0,
        'dht_announce_interval': 30,
    }
    ses.apply_settings(settings)

    params = {
        'save_path': download_path,
        'storage_mode': lt.storage_mode_t.storage_mode_sparse,
    }

    # Add the magnet URI
    handle = lt.add_magnet_uri(ses, magnet_link, params)

    send_to_telegram(bot_id, chat_id, f"📥 Downloading: {torrent_name}")

    print("Downloading...")
    start_time = time.time()

    while not handle.is_seed():
        status = handle.status()
        download_rate_mb_s = status.download_rate / 1_048_576  # Convert to MB/s
        upload_rate_mb_s = status.upload_rate / 1_048_576      # Convert to MB/s

        print(f'Downloaded: {status.progress * 100:.2f}% - '
              f'Download rate: {download_rate_mb_s:.2f} MB/s - '
              f'Upload rate: {upload_rate_mb_s:.2f} MB/s - '
              f'Peers: {status.num_peers}')

        time.sleep(1)

    elapsed_time = time.time() - start_time
    elapsed_minutes = int(elapsed_time // 60)  # Get the total minutes
    elapsed_seconds = int(elapsed_time % 60)   # Get the remaining seconds

    print("Download complete!")
    send_to_telegram(bot_id, chat_id, f"✅ Download complete! '{torrent_name}'\n⏱️ Total elapsed time: {elapsed_minutes} minutes and {elapsed_seconds} seconds.")

    return torrent_name

def zip_folder(folder_path, magnet_link, bot_id, chat_id, enable_zip=True):
    """Zip the specified folder using p7zip without compressing its contents."""

    if not enable_zip:
        print("ZIP functionality is disabled. Skipping zipping.")
        send_to_telegram(bot_id, chat_id, "📁 ZIP functionality is disabled. Files remain uncompressed.")
        return None

    # Check if the provided path is a file
    if os.path.isfile(folder_path):
        send_to_telegram(bot_id, chat_id, f"⚠️ Skipping zipping. The path {folder_path} is a file, not a directory.")
        return None

    # Check if the provided path is a directory
    if not os.path.isdir(folder_path):
        send_to_telegram(bot_id, chat_id, f"⚠️ Skipping zipping. The path {folder_path} is not a directory.")
        return None

    # Check if the directory is empty
    if not os.listdir(folder_path):
        send_to_telegram(bot_id, chat_id, f"⚠️ Skipping zipping. The directory {folder_path} is empty.")
        return None

    # Prepare to zip directories found in folder_path
    directories_to_zip = [d for d in os.listdir(folder_path) if os.path.isdir(os.path.join(folder_path, d))]

    if not directories_to_zip:
        send_to_telegram(bot_id, chat_id, "ℹ️ No subdirectories found to zip.")
        return None

    try:
        # Create the zip file from the first found directory or use a default name
        folder_name = magnet_link.split('dn=')[1] if 'dn=' in magnet_link else 'downloaded_files'
        folder_name = requests.utils.unquote(folder_name.split('&')[0])  # Decode folder name
        zip_file_path = os.path.join(os.path.dirname(folder_path), f"{folder_name}.7z")

        send_to_telegram(bot_id, chat_id, "🗜️ Zipping subdirectories in the downloaded folder using p7zip...")
        start_time = time.time()

        # Command to create a zip file using p7zip (7z)
        # Only zip the identified subdirectories
        command = ["7z", "a", "-mx0", zip_file_path] + [os.path.join(folder_path, d) for d in directories_to_zip]

        # Execute the command
        subprocess.run(command, check=True)

        elapsed_time = time.time() - start_time
        zip_size = os.path.getsize(zip_file_path) / (1024 * 1024)  # Size in MB
        send_to_telegram(bot_id, chat_id, f"✅ Zipping completed in {elapsed_time:.2f} seconds!\n📦 Archive size: {zip_size:.2f} MB")
        return zip_file_path

    except subprocess.CalledProcessError as e:
        send_to_telegram(bot_id, chat_id, f"❌ Error zipping folder: {str(e)}")
        print(f"ZIP Error: {str(e)}")
    except Exception as e:
        send_to_telegram(bot_id, chat_id, f"❌ Unexpected error during zipping: {str(e)}")
        print(f"Unexpected ZIP Error: {str(e)}")

    return None

def get_magnet_link_from_github(repo, path, branch="main"):
    """Retrieve a magnet link from a GitHub repository."""
    url = f"https://api.github.com/repos/{repo}/contents/{path}?ref={branch}"
    try:
        response = requests.get(url, timeout=30)
        if response.status_code == 200:
            content = response.json()['content']
            decoded_content = base64.b64decode(content).decode('utf-8').strip()
            return decoded_content
        else:
            print(f"Failed to fetch magnet link: {response.status_code} - {response.text}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Network error while fetching magnet link: {str(e)}")
        return None
    except Exception as e:
        print(f"Unexpected error while fetching magnet link: {str(e)}")
        return None

def get_configuration():
    """Load configuration from environment variables with validation and defaults."""
    config = {
        'bot_id': os.getenv('BOT_ID'),
        'chat_id': os.getenv('CHAT_ID'),
        'enable_zip': os.getenv('ENABLE_ZIP', 'true').lower() in ('true', '1', 'yes', 'on'),
        'github_repo': os.getenv('GITHUB_REPO', 'Prashant-1695/magnet_url'),
        'file_path': os.getenv('MAGNET_FILE_PATH', 'magnet_link.txt'),
        'download_path': os.getenv('DOWNLOAD_PATH', './Downloads/'),
        'github_branch': os.getenv('GITHUB_BRANCH', 'main')
    }

    # Validate required environment variables
    missing_vars = []
    if not config['bot_id']:
        missing_vars.append('BOT_ID')
    if not config['chat_id']:
        missing_vars.append('CHAT_ID')

    if missing_vars:
        print(f"Error: The following required environment variables are missing: {', '.join(missing_vars)}")
        return None

    return config

def print_configuration(config):
    """Print current configuration settings."""
    print("=" * 50)
    print("TORRENT DOWNLOADER CONFIGURATION")
    print("=" * 50)
    print(f"GitHub Repository: {config['github_repo']}")
    print(f"Magnet File Path: {config['file_path']}")
    print(f"GitHub Branch: {config['github_branch']}")
    print(f"Download Path: {config['download_path']}")
    print(f"ZIP Enabled: {'Yes' if config['enable_zip'] else 'No'}")
    print(f"Telegram Bot ID: {config['bot_id'][:10]}***")
    print(f"Telegram Chat ID: {config['chat_id']}")
    print("=" * 50)

def cleanup_on_exit(download_path, zip_file_path=None):
    """Clean up temporary files if needed."""
    try:
        # Optional: Remove downloaded files after processing
        cleanup_downloads = os.getenv('CLEANUP_DOWNLOADS', 'false').lower() in ('true', '1', 'yes', 'on')
        if cleanup_downloads and os.path.exists(download_path):
            import shutil
            shutil.rmtree(download_path)
            print(f"Cleaned up download directory: {download_path}")
    except Exception as e:
        print(f"Error during cleanup: {str(e)}")

def main():
    """Main function with enhanced error handling and configuration management."""
    try:
        # Load and validate configuration
        config = get_configuration()
        if not config:
            exit(1)

        # Print configuration
        print_configuration(config)

        # Send startup notification
        send_to_telegram(config['bot_id'], config['chat_id'],
                        f"🚀 Torrent Downloader Started\n"
                        f"📁 ZIP: {'Enabled' if config['enable_zip'] else 'Disabled'}\n"
                        f"📂 Download Path: {config['download_path']}")

        # Get the magnet link from the specified GitHub repository
        print(f"Fetching magnet link from {config['github_repo']}/{config['file_path']}...")
        magnet_link = get_magnet_link_from_github(config['github_repo'], config['file_path'], config['github_branch'])

        if not magnet_link:
            error_msg = "❌ Magnet link could not be retrieved. Exiting..."
            print(error_msg)
            send_to_telegram(config['bot_id'], config['chat_id'], error_msg)
            exit(1)

        print(f"Magnet link retrieved successfully: {magnet_link[:100]}...")

        # Create download directory
        os.makedirs(config['download_path'], exist_ok=True)

        # Start downloading the magnet link
        torrent_name = download_torrent(magnet_link, config['download_path'], config['bot_id'], config['chat_id'])

        # Handle zipping based on configuration
        zip_file_path = None
        if config['enable_zip']:
            print("ZIP is enabled. Attempting to zip downloaded content...")
            zip_file_path = zip_folder(config['download_path'], magnet_link, config['bot_id'], config['chat_id'], True)

            if zip_file_path:
                print(f"Successfully created ZIP file: {zip_file_path}")
            else:
                print("ZIP file creation failed or was skipped.")
        else:
            print("ZIP functionality is disabled by configuration.")
            send_to_telegram(config['bot_id'], config['chat_id'],
                           f"📁 Download completed for '{torrent_name}'\n"
                           f"🔧 ZIP is disabled - files remain uncompressed")

        # Send completion notification
        completion_msg = f"🎉 Process completed successfully!\n"
        completion_msg += f"📥 Downloaded: {torrent_name}\n"
        if config['enable_zip']:
            if zip_file_path:
                completion_msg += f"📦 ZIP Created: {os.path.basename(zip_file_path)}"
            else:
                completion_msg += f"📦 ZIP: Skipped (no suitable content found)"
        else:
            completion_msg += f"📦 ZIP: Disabled"

        send_to_telegram(config['bot_id'], config['chat_id'], completion_msg)
        print("All operations completed successfully!")

    except KeyboardInterrupt:
        print("\n⚠️ Process interrupted by user.")
        if 'config' in locals():
            send_to_telegram(config['bot_id'], config['chat_id'], "⚠️ Torrent download process was interrupted by user.")
    except Exception as e:
        error_msg = f"❌ Unexpected error occurred: {str(e)}"
        print(error_msg)
        if 'config' in locals():
            send_to_telegram(config['bot_id'], config['chat_id'], error_msg)
        exit(1)
    finally:
        # Cleanup if configured
        if 'config' in locals() and 'zip_file_path' in locals():
            cleanup_on_exit(config['download_path'], zip_file_path)

if __name__ == "__main__":
    main()
