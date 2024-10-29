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

def zip_folder(folder_path, magnet_link):
    # Extract the desired folder name from the magnet link
    folder_name = magnet_link.split('dn=')[1].split('&')[0]  # Get name from magnet link
    folder_name = requests.utils.unquote(folder_name)  # Decode URL-encoded characters
    # Create the .7z file path
    zip_file_path = os.path.join(os.path.dirname(folder_path), f"{folder_name}.7z")

    send_to_telegram(bot_id, chat_id, "Zipping the folder...")  # Notify before zipping
    start_time = time.time()  # Start timing the zipping process

    # Create the .7z archive
    subprocess.run(['7z', 'a', zip_file_path, folder_path])

    elapsed_time = time.time() - start_time  # Calculate elapsed time
    send_to_telegram(bot_id, chat_id, f"Zipping completed in {elapsed_time:.2f} seconds!")  # Notify after zipping
    return zip_file_path

def upload_files_to_gofile(file_path):
    url = "https://store1.gofile.io/uploadFile"
    links = []

    # Upload the file (the zipped folder)
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
    send_to_telegram(bot_id, chat_id, f"Upload completed in {elapsed_time:.2f} seconds!")  # Notify after upload
    return links

if __name__ == "__main__":
    bot_id = os.environ.get('BOT_ID')  # Set in environment
    chat_id = os.environ.get('CHAT_ID')  # Set in environment

    magnet_link = "magnet:?xt=urn:btih:13B27290E2CFFA916693CE2D59D292811FD77AE9&dn=@Torrent_Searche_bot&tr=http%3A%2F%2Fp4p.arenabg.com%3A1337%2Fannounce&tr=udp%3A%2F%2F47.ip-51-68-199.eu%3A6969%2Fannounce&tr=udp%3A%2F%2F9.rarbg.me%3A2780%2Fannounce&tr=udp%3A%2F%2F9.rarbg.to%3A2710%2Fannounce&tr=udp%3A%2F%2F9.rarbg.to%3A2730%2Fannounce&tr=udp%3A%2F%2F9.rarbg.to%3A2920%2Fannounce&tr=udp%3A%2F%2Fopen.stealth.si%3A80%2Fannounce&tr=udp%3A%2F%2Fopentracker.i2p.rocks%3A6969%2Fannounce&tr=udp%3A%2F%2Ftracker.coppersurfer.tk%3A6969%2Fannounce&tr=udp%3A%2F%2Ftracker.cyberia.is%3A6969%2Fannounce&tr=udp%3A%2F%2Ftracker.dler.org%3A6969%2Fannounce&tr=udp%3A%2F%2Ftracker.internetwarriors.net%3A1337%2Fannounce&tr=udp%3A%2F%2Ftracker.leechers-paradise.org%3A6969%2Fannounce&tr=udp%3A%2F%2Ftracker.openbittorrent.com%3A6969%2Fannounce&tr=udp%3A%2F%2Ftracker.opentrackr.org%3A1337&tr=udp%3A%2F%2Ftracker.pirateparty.gr%3A6969%2Fannounce&tr=udp%3A%2F%2Ftracker.tiny-vps.com%3A6969%2Fannounce&tr=udp%3A%2F%2Ftracker.torrent.eu.org%3A451%2Fannounce" # Replace with your actual magnet link
    download_path = "./downloads/"  # Folder to save downloaded files

    if not os.path.exists(download_path):
        os.makedirs(download_path)

    downloaded_folder_path = download_magnet(magnet_link, download_path)

    # Zip the downloaded folder using the magnet link for naming
    zip_file_path = zip_folder(downloaded_folder_path, magnet_link)

    # Upload the zipped folder to GoFile
    send_to_telegram(bot_id, chat_id, "Uploading the zipped folder...")
    upload_links = upload_files_to_gofile(zip_file_path)

    if upload_links:
        combined_links = "\n".join(upload_links)
        send_to_telegram(bot_id, chat_id, f"Upload completed! Links:\n{combined_links}")
    else:
        send_to_telegram(bot_id, chat_id, "Upload failed or no files found.")
