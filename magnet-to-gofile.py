import os
import libtorrent as lt
import time
import requests

# Function to download folder or file from a magnet link using libtorrent
def download_magnet(magnet_link, download_path):
    ses = lt.session()
    ses.listen_on(6881, 6891)

    params = {
        'save_path': download_path,
        'storage_mode': lt.storage_mode_t.storage_mode_sparse,
    }
    handle = lt.add_magnet_uri(ses, magnet_link, params)

    print(f"Downloading {magnet_link}...")

    # Wait for the metadata to be downloaded
    while not handle.has_metadata():
        time.sleep(1)

    print("Metadata downloaded, starting to download files...")

    # Download the files
    while handle.status().state != lt.torrent_status.seeding:
        s = handle.status()
        print(f'Downloaded: {s.progress * 100:.2f}% - '
              f'Download rate: {s.download_rate / 1000:.1f} kB/s - '
              f'Upload rate: {s.upload_rate / 1000:.1f} kB/s')
        time.sleep(1)

    print("Download completed!")
    return handle.name()  # Return the original folder or file name

# Function to upload files to GoFile and return the download link
def upload_to_gofile(file_path):
    url = "https://store1.gofile.io/uploadFile"

    with open(file_path, 'rb') as file:
        response = requests.post(url, files={'file': file})

    if response.status_code == 200:
        response_json = response.json()
        if response_json['status'] == 'ok':
            return response_json["data"]["downloadPage"]
        else:
            print(f'Upload failed: {response_json["message"]}')
            return None
    else:
        print(f'Error: {response.status_code} - {response.text}')
        return None

# Function to send message via Telegram
def send_to_telegram(bot_id, chat_id, message):
    url = f"https://api.telegram.org/bot{bot_id}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': message
    }
    requests.post(url, json=payload)
    print('Message sent to Telegram.')

# Main execution
if __name__ == "__main__":
    # Retrieve BOT_ID and CHAT_ID from environment variables
    bot_id = os.environ.get('BOT_ID')  # Set in .cirrus.yml
    chat_id = os.environ.get('CHAT_ID')  # Set in .cirrus.yml

    magnet_link = "magnet:?xt=urn:btih:OGKQEU6XRYD7PIPDS3Y5OCDLVA4IZNFI&tr=http%3A%2F%2Fnyaa.tracker.wf%3A7777%2Fannounce&tr=udp%3A%2F%2Fopen.stealth.si%3A80%2Fannounce&tr=udp%3A%2F%2Ftracker.opentrackr.org%3A1337%2Fannounce&tr=udp%3A%2F%2Fexodus.desync.com%3A6969%2Fannounce&tr=udp%3A%2F%2Ftracker.torrent.eu.org%3A451%2Fannounce&dn=%5BJOHNTiTOR%5D%20Elfen%20Lied%20S01%20v3%20%28BD%201080p%20HEVC%20Opus%29%20%5BDual-Audio%5D"    
    download_path = "./downloads/"  # Folder to save downloaded files

    # Create download directory if it doesn't exist
    if not os.path.exists(download_path):
        os.makedirs(download_path)

    # Send starting message
    send_to_telegram(bot_id, chat_id, "Starting download...")

    # Download the folder or file from the magnet link
    original_name = download_magnet(magnet_link, download_path)

    # Upload the downloaded file to GoFile
    file_path = os.path.join(download_path, original_name)
    upload_link = upload_to_gofile(file_path)

    # Send upload link to Telegram
    if upload_link:
        send_to_telegram(bot_id, chat_id, f"Upload completed! Download link: {upload_link}")
    else:
        send_to_telegram(bot_id, chat_id, "Upload failed.")
