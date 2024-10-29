import os
import time
import requests
import libtorrent as lt

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

    while handle.status().state != lt.torrent_status.seeding:
        s = handle.status()
        print(f'Downloaded: {s.progress * 100:.2f}% - '
              f'Download rate: {s.download_rate / 1000:.1f} kB/s - '
              f'Upload rate: {s.upload_rate / 1000:.1f} kB/s')
        time.sleep(1)

    print("Download completed!")
    send_to_telegram(bot_id, chat_id, "Download completed!")
    return download_path

def upload_folder_to_gofile(folder_path):
    url = "https://store1.gofile.io/uploadFile"
    files = []
    
    # Collect all files in the folder
    for root, _, filenames in os.walk(folder_path):
        for filename in filenames:
            file_path = os.path.join(root, filename)
            with open(file_path, 'rb') as file:
                files.append(('file', (filename, file)))

    # Upload all files to GoFile
    response = requests.post(url, files=files)

    if response.status_code == 200:
        response_json = response.json()
        if response_json['status'] == 'ok':
            return response_json['data']['downloadPage']
        else:
            print(f'Upload failed: {response_json["message"]}')
            return None
    else:
        print(f'Error: {response.status_code} - {response.text}')
        return None

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

if __name__ == "__main__":
    bot_id = os.environ.get('BOT_ID')  # Set in .cirrus.yml
    chat_id = os.environ.get('CHAT_ID')  # Set in .cirrus.yml

    magnet_link = "magnet:?xt=urn:btih:IZAXKUIE4T5DO6RAYDJ2BIWZDBSZNPOB&tr=http%3A%2F%2Fnyaa.tracker.wf%3A7777%2Fannounce&tr=udp%3A%2F%2Fopen.stealth.si%3A80%2Fannounce&tr=udp%3A%2F%2Ftracker.opentrackr.org%3A1337%2Fannounce&tr=udp%3A%2F%2Fexodus.desync.com%3A6969%2Fannounce&tr=udp%3A%2F%2Ftracker.torrent.eu.org%3A451%2Fannounce&dn=%5BEMBER%5D%20My%20Hero%20Academia%20%282024%29%20%28Season%207%29%20%5B1080p%5D%20%5BDual%20Audio%20HEVC%20WEBRip%5D%20%28Boku%20no%20Hero%20Academia%207th%20Season%29%20%28Batch%29"  # Replace with your actual magnet link
    download_path = "./downloads/"  # Folder to save downloaded files

    if not os.path.exists(download_path):
        os.makedirs(download_path)

    downloaded_folder_path = download_magnet(magnet_link, download_path)

    # Upload the downloaded folder to GoFile
    send_to_telegram(bot_id, chat_id, "Uploading files...")
    upload_link = upload_folder_to_gofile(downloaded_folder_path)

    if upload_link:
        send_to_telegram(bot_id, chat_id, f"Upload completed! Download link: {upload_link}")
    else:
        send_to_telegram(bot_id, chat_id, "Upload failed.")
