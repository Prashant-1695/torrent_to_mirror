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

def upload_file(file_path, uploader, api_key):
    if uploader == 'gofile':
        return upload_file_to_gofile(file_path)
    elif uploader == 'buzzheavier':
        return upload_file_to_buzzheavier(file_path)
    elif uploader == 'pixeldrain':
        return upload_file_to_pixeldrain(file_path, api_key)

def upload_file_to_gofile(file_path):
    url = "https://store1.gofile.io/uploadFile"
    return upload_file(file_path, url, 'gofile')

def upload_file_to_buzzheavier(file_path):
    url = "https://buzzheavier.com/upload"  # Replace with the actual upload URL
    return upload_file(file_path, url, 'buzzheavier')

def upload_file_to_pixeldrain(file_path, api_key):
    url = "https://pixeldrain.com/api/file"
    headers = {'Authorization': f'Bearer {api_key}'}

    with open(file_path, 'rb') as file:
        response = requests.post(url, files={'file': file}, headers=headers)
        links = []

        if response.status_code == 200:
            response_json = response.json()
            links.append(response_json['id'])  # Link to the uploaded file
        else:
            print(f'Upload failed for {file_path} to Pixeldrain: {response.status_code} - {response.text}')

    return links

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

def handle_upload_response(upload_links, uploader):
    if upload_links:
        combined_links = "\n".join(upload_links)
        send_to_telegram(bot_id, chat_id, f"Upload completed to {uploader}! Links:\n{combined_links}")
    else:
        send_to_telegram(bot_id, chat_id, f"Upload failed on {uploader}.")

if __name__ == "__main__":
    # Load environment variables for bot_id, chat_id, and pixeldrain_api_key
    bot_id = os.environ.get('BOT_ID')
    chat_id = os.environ.get('CHAT_ID')
    pixeldrain_api_key = os.environ.get('PIXELDRAIN_API_KEY')

    # Example magnet link (Replace with actual magnet link)
    magnet_link = "magnet:?xt=urn:btih:FCPUZRUUMFPT6LOTFBITQTUGDWB6R47W&tr=http%3A%2F%2Fnyaa.tracker.wf%3A7777%2Fannounce&tr=udp%3A%2F%2Fopen.stealth.si%3A80%2Fannounce000&tr=udp%3A%2F%2Fexodus.desync.com%3A6969%2Fannounce&tr=udp%3A%2F%2Ftracker.cyberia.is%3A6969%2Fannounce&tr=udp%3A%2F%2Ftracker.opentrackr.org%3A1337%2Fannounce&dn=%5BBreeze%5D%20Kami%20no%20Tou%20%7C%20Tower%20of%20God%20-%20S02E17%20%5B1080p%20AV1%5D%5Bmultisub%5D%20%28weekly%29"

    # Set download path
    download_path = "./downloads/"
    if not os.path.exists(download_path):
        os.makedirs(download_path)

    # Download magnet link
    downloaded_folder_path = download_magnet(magnet_link, download_path)

    # Default uploader is 'gofile'
    uploader = 'pixeldrain'  # Change this to your desired uploader (e.g., 'pixeldrain', 'buzzheavier')
    process_downloaded_files(downloaded_folder_path, uploader, pixeldrain_api_key)
