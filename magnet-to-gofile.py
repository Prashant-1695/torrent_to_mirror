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

def upload_file_to_gofile(file_path):
    url = "https://store1.gofile.io/uploadFile"
    return upload_file(file_path, url, 'gofile')

def upload_file_to_buzzheavier(file_path):
    url = "https://buzzheavier.com/upload"  # Replace with the actual upload URL
    return upload_file(file_path, url, 'buzzheavier')

def upload_file_to_pixeldrain(file_path):
    url = "https://pixeldrain.com/api/file"
    files = {'file': open(file_path, 'rb')}
    response = requests.post(url, files=files)
    links = []

    if response.status_code == 200:
        response_json = response.json()
        links.append(response_json['id'])  # Link to the uploaded file
    else:
        print(f'Upload failed for {file_path} to Pixeldrain: {response.status_code} - {response.text}')

    return links

def upload_file(file_path, url, platform):
    links = []
    start_time = time.time()
    with open(file_path, 'rb') as file:
        response = requests.post(url, files={'file': file})
        if response.status_code == 200:
            response_json = response.json()
            if response_json['status'] == 'ok':
                if platform == 'gofile':
                    links.append(response_json['data']['downloadPage'])
                elif platform == 'buzzheavier':
                    links.append(response_json['downloadLink'])  # Update based on actual response structure
                print(f'Upload successful to {platform}: {links}')
            else:
                print(f'Upload failed for {file_path} to {platform}: {response_json["message"]}')
        else:
            print(f'Error uploading {file_path} to {platform}: {response.status_code} - {response.text}')

    elapsed_time = time.time() - start_time
    send_to_telegram(bot_id, chat_id, f"{platform.capitalize()} upload completed in {elapsed_time:.2f} seconds!")
    return links

def process_downloaded_files(downloaded_folder_path, uploader):
    for item in os.listdir(downloaded_folder_path):
        item_path = os.path.join(downloaded_folder_path, item)

        if os.path.isdir(item_path):
            zip_file_path = zip_folder(item_path, magnet_link)
            if zip_file_path:
                send_to_telegram(bot_id, chat_id, f"Uploading the zipped folder to {uploader}...")
                if uploader == 'gofile':
                    upload_links = upload_file_to_gofile(zip_file_path)
                elif uploader == 'buzzheavier':
                    upload_links = upload_file_to_buzzheavier(zip_file_path)
                elif uploader == 'pixeldrain':
                    upload_links = upload_file_to_pixeldrain(zip_file_path)
                # Handle upload process based on the uploader
                handle_upload_response(upload_links, uploader)

        else:
            if not item.endswith(('.zip', '.7z')):
                send_to_telegram(bot_id, chat_id, f"Uploading file: {item_path} to {uploader}...")
                if uploader == 'gofile':
                    upload_links = upload_file_to_gofile(item_path)
                elif uploader == 'buzzheavier':
                    upload_links = upload_file_to_buzzheavier(item_path)
                elif uploader == 'pixeldrain':
                    upload_links = upload_file_to_pixeldrain(item_path)
                handle_upload_response(upload_links, uploader)

def handle_upload_response(upload_links, uploader):
    if upload_links:
        combined_links = "\n".join(upload_links)
        send_to_telegram(bot_id, chat_id, f"Upload completed to {uploader}! Links:\n{combined_links}")
    else:
        send_to_telegram(bot_id, chat_id, f"Upload failed on {uploader}.")

if __name__ == "__main__":
    bot_id = os.environ.get('BOT_ID')
    chat_id = os.environ.get('CHAT_ID')

    # Example magnet link (Replace with actual magnet link)
    magnet_link = "magnet:?xt=urn:btih:V5XKF4FCGHEU2IJ6Y57A4IBGXC2SOUEI&tr=http%3A%2F%2Fnyaa.tracker.wf%3A7777%2Fannounce&tr=udp%3A%2F%2Fopen.stealth.si%3A80%2Fannounce&tr=udp%3A%2F%2Ftracker.opentrackr.org%3A1337%2Fannounce&tr=udp%3A%2F%2Fexodus.desync.com%3A6969%2Fannounce&tr=udp%3A%2F%2Ftracker.torrent.eu.org%3A451%2Fannounce&dn=%5BASW%5D%20Amagami-san%20Chi%20no%20Enmusubi%20-%2005%20%5B1080p%20HEVC%20x265%2010Bit%5D%5BAAC%5D"
    
    # Set download path
    download_path = "./downloads/"
    if not os.path.exists(download_path):
        os.makedirs(download_path)

    # Download magnet link
    downloaded_folder_path = download_magnet(magnet_link, download_path)

    # Specify the uploader type: 'gofile', 'buzzheavier', or 'pixeldrain'
    uploader = 'pixeldrain'  # Change this to your desired uploader
    process_downloaded_files(downloaded_folder_path, uploader)
