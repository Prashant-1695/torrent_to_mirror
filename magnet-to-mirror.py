import os
import time
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

    params = {
        'save_path': download_path,
        'storage_mode': lt.storage_mode_t.storage_mode_sparse,
    }

    handle = lt.add_magnet_uri(ses, magnet_link, params)

    send_to_telegram(bot_id, chat_id, f"Downloading: {torrent_name}")

    print("Downloading...")
    start_time = time.time()

    while handle.status().state != lt.torrent_status.seeding:
        status = handle.status()
        download_rate_mb_s = status.download_rate / 1_048_576  # Convert to MB/s
        upload_rate_mb_s = status.upload_rate / 1_048_576      # Convert to MB/s

        print(f'Downloaded: {status.progress * 100:.2f}% - '
              f'Download rate: {download_rate_mb_s:.2f} MB/s - '
              f'Upload rate: {upload_rate_mb_s:.2f} MB/s')

        time.sleep(1)

    elapsed_time = time.time() - start_time
    elapsed_minutes = int(elapsed_time // 60)  # Get the total minutes
    elapsed_seconds = int(elapsed_time % 60)   # Get the remaining seconds

    print("Download complete!")
    send_to_telegram(bot_id, chat_id, f"Download complete! '{torrent_name}' Total elapsed time: {elapsed_minutes} minutes and {elapsed_seconds} seconds.")

def zip_folder(folder_path, magnet_link, bot_id, chat_id):
    """Zip the specified folder using p7zip without compressing its contents."""

    # Check if the provided path is a file
    if os.path.isfile(folder_path):
        send_to_telegram(bot_id, chat_id, f"Skipping zipping. The path {folder_path} is a file, not a directory.")
        return None

    # Check if the provided path is a directory
    if not os.path.isdir(folder_path):
        send_to_telegram(bot_id, chat_id, f"Skipping zipping. The path {folder_path} is not a directory.")
        return None

    # Check if the directory is empty
    if not os.listdir(folder_path):
        send_to_telegram(bot_id, chat_id, f"Skipping zipping. The directory {folder_path} is empty.")
        return None

    # Prepare to zip directories found in folder_path
    directories_to_zip = [d for d in os.listdir(folder_path) if os.path.isdir(os.path.join(folder_path, d))]

    if not directories_to_zip:
        send_to_telegram(bot_id, chat_id, "No subdirectories found to zip.")
        return None

    try:
        # Create the zip file from the first found directory or use a default name
        folder_name = magnet_link.split('dn=')[1] if 'dn=' in magnet_link else 'downloaded_files'
        folder_name = requests.utils.unquote(folder_name.split('&')[0])  # Decode folder name
        zip_file_path = os.path.join(os.path.dirname(folder_path), f"{folder_name}.7z")

        send_to_telegram(bot_id, chat_id, "Zipping subdirectories in the downloaded folder using p7zip...")
        start_time = time.time()

        # Command to create a zip file using p7zip (7z)
        # Only zip the identified subdirectories
        command = ["7z", "a", "-mx0", zip_file_path] + [os.path.join(folder_path, d) for d in directories_to_zip]

        # Execute the command
        subprocess.run(command, check=True)

        elapsed_time = time.time() - start_time
        send_to_telegram(bot_id, chat_id, f"Zipping completed in {elapsed_time:.2f} seconds!")
        return zip_file_path

    except subprocess.CalledProcessError as e:
        send_to_telegram(bot_id, chat_id, f"Error zipping folder: {str(e)}")
    except Exception as e:
        send_to_telegram(bot_id, chat_id, f"Unexpected error: {str(e)}")

    return None
       
if __name__ == "__main__":
    # Load environment variables for bot_id and chat_id
    bot_id = os.getenv('BOT_ID')
    chat_id = os.getenv('CHAT_ID')

    if not all([bot_id, chat_id]):
        print("Error: Both BOT_ID and CHAT_ID environment variables must be set.")
        exit(1)

    # Directly set the magnet link here
    magnet_link = "magnet:?xt=urn:btih:IAVEF7757OUOJGKH7MSGUS7O2J3EVQKO&tr=http%3A%2F%2Fanidex.moe%3A6969%2Fannounce&dn=%5BCleo%5D%20Beck%3A%20Mongolian%20Chop%20Squad%20%5BDual%20Audio%2010bit%20BD1080p%5D%5BHEVC-x265%5D"

    # Set the download directory
    download_path = "./downloads/"
    os.makedirs(download_path, exist_ok=True)

    # Start downloading the magnet link
    download_torrent(magnet_link, download_path, bot_id, chat_id)

    # Optionally zip the downloaded folder without compressing files
    zip_folder(download_path, magnet_link, bot_id, chat_id)