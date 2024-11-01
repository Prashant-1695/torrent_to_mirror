import os
import time
import requests
import libtorrent as lt
import base64
import subprocess

def send_to_telegram(bot_id, chat_id, message):
    """Send a message to a specified Telegram chat."""
    url = f"https://api.telegram.org/bot{bot_id}/sendMessage"
    payload = {'chat_id': chat_id, 'text': message}

    response = requests.post(url, json=payload)

    if response.status_code == 200:
        print('Message sent to Telegram.')
    else:
        print(f'Failed to send message: {response.status_code}')

def download_magnet(magnet_link, download_path):
    """Download files from a magnet link."""
    ses = lt.session()
    ses.listen_on(6881, 6891)

    # Set parameters for the download
    params = {
        'save_path': download_path,
        'storage_mode': lt.storage_mode_t.storage_mode_sparse,
    }

    handle = lt.add_magnet_uri(ses, magnet_link, params)
    print(f"Downloading {magnet_link}...")

    # Wait for metadata to be downloaded
    while not handle.has_metadata():
        time.sleep(1)

    print("Metadata downloaded, starting to download files...")
    send_to_telegram(bot_id, chat_id, "Starting download...")

    start_time = time.time()

    # Download files until seeding is complete
    while handle.status().state != lt.torrent_status.seeding:
        status = handle.status()
        print(f'Downloaded: {status.progress * 100:.2f}% '
              f'- Download rate: {status.download_rate / 1000:.1f} kB/s '
              f'- Upload rate: {status.upload_rate / 1000:.1f} kB/s')
        time.sleep(1)

    elapsed_time = time.time() - start_time
    print("Download completed!")
    send_to_telegram(bot_id, chat_id, f"Download completed in {elapsed_time:.2f} seconds!")
    return download_path

def zip_folder(folder_path, magnet_link, bot_id, chat_id):
    if not os.path.isdir(folder_path):
        send_to_telegram(bot_id, chat_id, f"Skipping zipping. The path {folder_path} is not a directory.")
        return None

    try:
        # Safely extract the folder name
        folder_name_segment = magnet_link.split('dn=')[1] if 'dn=' in magnet_link else ''
        folder_name = requests.utils.unquote(folder_name_segment.split('&')[0]) if folder_name_segment else 'downloaded_files'

        zip_file_path = os.path.join(os.path.dirname(folder_path), f"{folder_name}.7z")
        send_to_telegram(bot_id, chat_id, "Zipping the folder...")

        start_time = time.time()
        subprocess.run(['7z', 'a', '-mx=0', zip_file_path, folder_path], check=True)

        elapsed_time = time.time() - start_time
        send_to_telegram(bot_id, chat_id, f"Zipping completed in {elapsed_time:.2f} seconds!")
        return zip_file_path
    except Exception as e:
        send_to_telegram(bot_id, chat_id, f"Error zipping folder: {str(e)}")
        return None

def get_magnet_link_from_github(repo, path, branch="main"):
    """Retrieve a magnet link from a GitHub repository."""
    url = f"https://api.github.com/repos/{repo}/contents/{path}?ref={branch}"
    response = requests.get(url)

    if response.status_code == 200:
        content = response.json()['content']
        decoded_content = base64.b64decode(content).decode('utf-8').strip()
        return decoded_content
    else:
        print(f"Failed to fetch magnet link: {response.status_code} - {response.text}")
        return None

if __name__ == "__main__":
    # Load environment variables for bot_id and chat_id
    bot_id = os.getenv('BOT_ID')
    chat_id = os.getenv('CHAT_ID')

    # Configuration for GitHub repository and the file path
    github_repo = "Prashant-1695/magnet_url"  # Update with actual GitHub repo
    file_path = "magnet_link.txt"  # Update with actual file path

    # Get the magnet link from the specified GitHub repository
    magnet_link = get_magnet_link_from_github(github_repo, file_path)

    if not magnet_link:
        print("Magnet link could not be retrieved. Exiting...")
        exit(1)

    # Set the download directory
    download_path = "./downloads/"
    os.makedirs(download_path, exist_ok=True)  # Create directory if it doesn't exist

    # Start downloading the magnet link
    download_magnet(magnet_link, download_path)

    # Optionally zip the downloaded folder
    zip_folder(download_path, magnet_link, bot_id, chat_id)
