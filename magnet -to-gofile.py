import libtorrent as lt
import time
import os
import requests
from telegram import Bot
import yaml

def load_config(filename):
    with open(filename, 'r') as file:
        return yaml.safe_load(file)

def download_magnet_link(magnet_link, download_path):
    # Create a session and add the torrent
    ses = lt.session()
    ses.listen_on(6881, 6891)
    
    params = {
        'save_path': download_path,
        'storage_mode': lt.storage_mode_t.storage_mode_sparse
    }
    
    handle = lt.add_magnet_uri(ses, magnet_link, params)
    print('Downloading Metadata...')
    
    while not handle.has_metadata():
        time.sleep(1)
    
    print('Metadata downloaded, starting to download...')
    
    # Start downloading
    while handle.status().state != lt.torrent_status.seeding:
        s = handle.status()
        print(f'Downloaded: {s.progress * 100:.2f}% - Download rate: {s.download_rate / 1000:.1f} kB/s - Upload rate: {s.upload_rate / 1000:.1f} kB/s')
        time.sleep(1)
    
    print('Download completed!')
    return handle.name()  # Return the original folder name

def upload_to_gofile(file_path):
    # Upload file to Gofile
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

def upload_folder_to_gofile(folder_path):
    links = []
    for root, dirs, files in os.walk(folder_path):
        for filename in files:
            file_path = os.path.join(root, filename)
            print(f'Uploading {file_path}...')
            link = upload_to_gofile(file_path)
            if link:
                links.append(link)
    return links

def send_to_telegram(bot_token, chat_id, message):
    bot = Bot(token=bot_token)
    bot.send_message(chat_id=chat_id, text=message)
    print('Message sent to Telegram.')

if __name__ == "__main__":
    config = load_config('.cirrus.yml')
    
    magnet_link = config['magnet_link']
    download_path = config['download_path']
    bot_token = config['bot_token']
    chat_id = config['chat_id']
    
    if not os.path.exists(download_path):
        os.makedirs(download_path)
    
    original_folder_name = download_magnet_link(magnet_link, download_path)
    
    downloaded_folder_path = os.path.join(download_path, original_folder_name)
    
    # Upload the folder to Gofile and collect links
    uploaded_links = upload_folder_to_gofile(downloaded_folder_path)
    
    # Send links to Telegram
    if uploaded_links:
        message = "Here are the links to the uploaded files:\n" + "\n".join(uploaded_links)
        send_to_telegram(bot_token, chat_id, message)
