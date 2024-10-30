import os
import time
import requests
import libtorrent as lt
import subprocess
import json  # Importing json to parse curl output
import base64

def send_to_telegram(bot_id, chat_id, message):
    url = f"https://api.telegram.org/bot{bot_id}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': message
    }
    response = requests.post(url, json=payload)
    if response.status_code == 200:
        print('Message sent to Telegram.')
    else:
        print(f'Failed to send message: {response.status_code}')

def download_magnet(magnet_link, download_path):
    ses = lt.session()
    ses.listen_on(6881, 6891)

    params = {
        'save_path': download_path,
        'storage_mode': lt.storage_mode_t.storage_mode_sparse,
    }

    handle = lt.add_magnet_uri(ses, magnet_link, params)
    print(f"Downloading {magnet_link}...")

    while not handle.has_metadata():
        time.sleep(1)

    print("Metadata downloaded, starting to download files...")
    send_to_telegram(bot_id, chat_id, "Starting download...")

    start_time = time.time()
    while handle.status().state != lt.torrent_status.seeding:
        s = handle.status()
        print(f'Downloaded: {s.progress * 100:.2f}% - '
              f'Download rate: {s.download_rate / 1000:.1f} kB/s - '
              f'Upload rate: {s.upload_rate / 1000:.1f} kB/s')
        time.sleep(1)

    elapsed_time = time.time() - start_time
    print("Download completed!")
    send_to_telegram(bot_id, chat_id, f"Download completed in {elapsed_time:.2f} seconds!")
    return download_path

def zip_folder(folder_path, magnet_link):
    if not os.path.isdir(folder_path):
        send_to_telegram(bot_id, chat_id, f"Skipping zipping. The path {folder_path} is not a directory.")
        return None

    folder_name = magnet_link.split('dn=')[1].split('&')[0]
    folder_name = requests.utils.unquote(folder_name)
    zip_file_path = os.path.join(os.path.dirname(folder_path), f"{folder_name}.7z")

    send_to_telegram(bot_id, chat_id, "Zipping the folder...")
    start_time = time.time()

    subprocess.run(['7z', 'a', zip_file_path, folder_path])

    elapsed_time = time.time() - start_time
    send_to_telegram(bot_id, chat_id, f"Zipping completed in {elapsed_time:.2f} seconds!")
    return zip_file_path

def process_downloaded_files(downloaded_folder_path, uploader, api_key):
    for item in os.listdir(downloaded_folder_path):
        item_path = os.path.join(downloaded_folder_path, item)

        if os.path.isdir(item_path):
            zip_file_path = zip_folder(item_path, magnet_link)
            if zip_file_path:
                send_to_telegram(bot_id, chat_id, f"Uploading the zipped folder to {uploader}...")
                upload_links = upload_file(zip_file_path, uploader, api_key)
                handle_upload_response(upload_links, uploader)

        else:
            if not item.endswith(('.zip', '.7z')):
                send_to_telegram(bot_id, chat_id, f"Uploading file: {item_path} to {uploader}...")
                upload_links = upload_file(item_path, uploader, api_key)
                handle_upload_response(upload_links, uploader)

def upload_to_external_service(file_path, uploader, api_key):
    # Call the upload.sh script with the necessary parameters
    result = subprocess.run(['bash', 'upload.sh', uploader, file_path, api_key], capture_output=True, text=True)

    if result.returncode == 0:
        return result.stdout.splitlines()  # Split the output into lines (assumed to be links)
    else:
        print(f'Upload failed: {result.stderr}')
        return []

def handle_upload_response(upload_links, uploader):
    if upload_links:
        combined_links = "\n".join(upload_links)
        send_to_telegram(bot_id, chat_id, f"Upload completed to {uploader}! Links:\n{combined_links}")
    else:
        send_to_telegram(bot_id, chat_id, f"Upload failed on {uploader}.")

def get_magnet_link_from_github(repo, path, branch="main"):
    url = f"https://api.github.com/repos/{repo}/contents/{path}?ref={branch}"
    response = requests.get(url)
    if response.status_code == 200:
        content = response.json()['content']
        decoded_content = base64.b64decode(content).decode('utf-8')
        return decoded_content.strip()
    else:
        print(f"Failed to fetch magnet link: {response.status_code} - {response.text}")
        return None

if __name__ == "__main__":
    # Load environment variables for bot_id, chat_id, and pixeldrain_api_key
    bot_id = os.environ.get('BOT_ID')
    chat_id = os.environ.get('CHAT_ID')
    pixeldrain_api_key = os.environ.get('PIXELDRAIN_API_KEY')

    # Example GitHub repository and file path
    github_repo = "username/repo"  # Replace with the actual GitHub username/repo
    file_path = "path/to/magnet_link.txt"  # Replace with the actual path to the magnet_link.txt file

    # Get the magnet link from the GitHub repository
    magnet_link = get_magnet_link_from_github(github_repo, file_path)

    if not magnet_link:
        print("Magnet link could not be retrieved. Exiting...")
        exit(1)

    # Set download path
    download_path = "./downloads/"
    if not os.path.exists(download_path):
        os.makedirs(download_path)

    # Download magnet link
    downloaded_folder_path = download_magnet(magnet_link, download_path)

    # Default uploader is 'gofile'
    uploader = 'pixeldrain'  # Change this to your desired uploader (e.g., 'pixeldrain', 'buzzheavier')
    process_downloaded_files(downloaded_folder_path, uploader, pixeldrain_api_key)
