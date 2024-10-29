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
    folder_name = magnet_link.split('dn=')[1].split('&')[0]
    folder_name = requests.utils.unquote(folder_name)
    zip_file_path = os.path.join(os.path.dirname(folder_path), f"{folder_name}.7z")

    send_to_telegram(bot_id, chat_id, "Zipping the folder...")
    start_time = time.time()

    subprocess.run(['7z', 'a', zip_file_path, folder_path])

    elapsed_time = time.time() - start_time
    send_to_telegram(bot_id, chat_id, f"Zipping completed in {elapsed_time:.2f} seconds!")
    return zip_file_path

def upload_files_to_gofile(file_path):
    url = "https://store1.gofile.io/uploadFile"
    links = []

    start_time = time.time()
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

    elapsed_time = time.time() - start_time
    send_to_telegram(bot_id, chat_id, f"GoFile upload completed in {elapsed_time:.2f} seconds!")
    return links

def upload_files_to_buzzheavier(file_path):
    url = "https://buzzheavier.com/upload"  # Replace with the actual upload URL
    links = []

    start_time = time.time()
    with open(file_path, 'rb') as file:
        response = requests.post(url, files={'file': file})
        if response.status_code == 200:
            response_json = response.json()
            if response_json.get('success'):
                links.append(response_json['downloadLink'])  # Adjust based on actual response structure
            else:
                print(f'Upload failed for {file_path}: {response_json.get("message")}')
        else:
            print(f'Error uploading {file_path} to BuzzHeavier: {response.status_code} - {response.text}')

    elapsed_time = time.time() - start_time
    send_to_telegram(bot_id, chat_id, f"BuzzHeavier upload completed in {elapsed_time:.2f} seconds!")
    return links

if __name__ == "__main__":
    bot_id = os.environ.get('BOT_ID')
    chat_id = os.environ.get('CHAT_ID')

    # Example magnet link (Replace with actual magnet link)
    magnet_link = "magnet:?xt=urn:btih:13B27290E2CFFA916693CE2D59D292811FD77AE9&dn=@Torrent_Searche_bot&tr=http%3A%2F%2Fp4p.arenabg.com%3A1337%2Fannounce"
    
    # Set download path
    download_path = "./downloads/"
    if not os.path.exists(download_path):
        os.makedirs(download_path)

    # Download magnet link
    downloaded_folder_path = download_magnet(magnet_link, download_path)

    # Zip the downloaded folder
    zip_file_path = zip_folder(downloaded_folder_path, magnet_link)

    # Upload the zipped folder to GoFile first
    send_to_telegram(bot_id, chat_id, "Uploading the zipped folder to GoFile...")
    upload_links = upload_files_to_gofile(zip_file_path)

    # If GoFile upload fails, try BuzzHeavier
    if not upload_links:
        send_to_telegram(bot_id, chat_id, "GoFile upload failed. Trying BuzzHeavier...")
        buzzheavier_links = upload_files_to_buzzheavier(zip_file_path)
        if buzzheavier_links:
            combined_links = "\n".join(buzzheavier_links)
            send_to_telegram(bot_id, chat_id, f"BuzzHeavier upload completed! Links:\n{combined_links}")
        else:
            send_to_telegram(bot_id, chat_id, "Upload failed on both platforms.")
    else:
        combined_links = "\n".join(upload_links)
        send_to_telegram(bot_id, chat_id, f"Upload completed to GoFile! Links:\n{combined_links}")
