import os
import time
import requests
import libtorrent as lt
import subprocess

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

    start_time = time.time()  # Start timing the download
    while handle.status().state != lt.torrent_status.seeding:
        s = handle.status()
        print(f'Downloaded: {s.progress * 100:.2f}% - '
              f'Download rate: {s.download_rate / 1000:.1f} kB/s - '
              f'Upload rate: {s.upload_rate / 1000:.1f} kB/s')
        time.sleep(1)

    elapsed_time = time.time() - start_time  # Calculate elapsed time
    print("Download completed!")
    send_to_telegram(bot_id, chat_id, f"Download completed in {elapsed_time:.2f} seconds!")
    return download_path

def zip_folder(folder_path):
    # Get the original folder name
    folder_name = os.path.basename(os.path.normpath(folder_path))
    # Create the .7z file path
    zip_file_path = os.path.join(os.path.dirname(folder_path), f"{folder_name}.7z")
    # Create the .7z archive
    subprocess.run(['7z', 'a', zip_file_path, folder_path])
    return zip_file_path

def upload_files_to_gofile(file_path):
    url = "https://store1.gofile.io/uploadFile"
    links = []

    if os.path.isdir(file_path):
        # If it's a directory, zip it first
        zip_file_path = zip_folder(file_path)
        file_path = zip_file_path  # Update file_path to the zip file path

    # Upload the file (or zipped folder)
    start_time = time.time()  # Start timing the upload
    with open(file_path, 'rb') as file:
        response = requests.post(url, files={'file': file})
        if response.status_code == 200:
            response_json = response.json()
            if response_json['status'] == 'ok':
                links.append(response_json['data']['downloadPage'])
            else:
                print(f'Upload failed for {file_path}: {response_json["message"]}')
        else:
            print(f'Error uploading {file_path}: {response.status_code} - {response.text}')

    elapsed_time = time.time() - start_time  # Calculate elapsed time
    print(f"Upload completed in {elapsed_time:.2f} seconds!")
    return links

if __name__ == "__main__":
    bot_id = os.environ.get('BOT_ID')  # Set in environment
    chat_id = os.environ.get('CHAT_ID')  # Set in environment

    magnet_link = "magnet:?xt=urn:btih:IZAXKUIE4T5DO6RAYDJ2BIWZDBSZNPOB&tr=http%3A%2F%2Fnyaa.tracker.wf%3A7777%2Fannounce&tr=udp%3A%2F%2Fopen.stealth.si%3A80%2Fannounce&tr=udp%3A%2F%2Ftracker.opentrackr.org%3A1337%2Fannounce&tr=udp%3A%2F%2Fexodus.desync.com%3A6969%2Fannounce&tr=udp%3A%2F%2Ftracker.torrent.eu.org%3A451%2Fannounce&dn=%5BEMBER%5D%20My%20Hero%20Academia%20%282024%29%20%28Season%207%29%20%5B1080p%5D%20%5BDual%20Audio%20HEVC%20WEBRip%5D%20%28Boku%20no%20Hero%20Academia%207th%20Season%29%20%28Batch%29"  # Replace with your actual magnet link
    download_path = "./downloads/"  # Folder to save downloaded files

    if not os.path.exists(download_path):
        os.makedirs(download_path)

    downloaded_folder_path = download_magnet(magnet_link, download_path)

    # Upload the downloaded folder (zipped if necessary) to GoFile
    send_to_telegram(bot_id, chat_id, "Uploading files...")
    upload_links = upload_files_to_gofile(downloaded_folder_path)

    if upload_links:
        combined_links = "\n".join(upload_links)
        send_to_telegram(bot_id, chat_id, f"Upload completed! Links:\n{combined_links}")
    else:
        send_to_telegram(bot_id, chat_id, "Upload failed or no files found.")
