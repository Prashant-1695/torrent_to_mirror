#!/bin/bash

# Usage: ./upload.sh <uploader> <file_path> <api_key>

uploader=$1
cd downloads

tg () {
curl -s "https://api.telegram.org/bot${BOT_ID}/sendmessage" --data "text=$1&chat_id=${CHAT_ID}"
}

# Function to check if jq is installed
check_jq() {
    if ! command -v jq &> /dev/null; then
        echo "Error: jq is not installed. Please install jq to use this script."
        exit 1
    fi
}

upload_file_to_gofile() {
    SECONDS=0
    local file="$1"
    response=$(curl -F "file=@${file}" https://store1.gofile.io/uploadFile)
    golink=$(echo "$response" | grep -o '"downloadPage":"[^"]*' | cut -d'"' -f4)
    tg "- Filename $1 Uploaded Successfully!
File Size: $(ls -sh ${PWD}/"$1" | cut -d - -f 1 | cut -d / -f 1)
Time Took: $(($SECONDS / 60)) minute(s) and $(($SECONDS % 60)) second(s).
Download Link: $golink"
}

upload_file_to_buzzheavier() {
    SECONDS=0
    local file="$1"

    # Check if file exists
    if [ ! -f "$file" ]; then
        tg "Error: File $file does not exist."
        return 1
    fi

    # Perform the upload and capture the response
    response=$(curl -# -T "$file" https://w.buzzheavier.com/t/$1 | cut -d : -f 2 | cut -d } -f 1 | grep -Po '[^"]*')

    # Check if the upload was successful
    download_link=$(echo "$response")
    tg "- Filename $file Uploaded Successfully!
File Size: $(ls -sh "$file" | awk '{print $1}')
Time Took: $(($SECONDS / 60)) minute(s) and $(($SECONDS % 60)) second(s).
Download Link: https://buzzheavier.com/f/$download_link"
}

upload () {
case $uploader in
    go)
        tg "- $(echo "$1" | tr -d '[:cntrl:]' | tr ' ' '_') Upload Started on GoFile!"
        upload_file_to_gofile "$1"
        ;;
    buzz)
        sanitized_filename=$(echo "$1" | tr -d '[:cntrl:]' | tr '[]() ' '_')
        mv "$1" "$sanitized_filename"
        tg "- $sanitized_filename Upload Started on BuzzHeavier!"
        check_jq
        upload_file_to_buzzheavier "$sanitized_filename"
        ;;
    *)
        check_jq
        # goup
        tg "- $(echo "$1" | tr -d '[:cntrl:]' | tr ' ' '_') Upload Started on GoFile!"
        upload_file_to_gofile "$1"
        # buzz
        sanitized_filename=$(echo "$1" | tr -d '[:cntrl:]' | tr '[]() ' '_')
        mv "$1" "$sanitized_filename"
        tg "- $sanitized_filename Upload Started on BuzzHeavier!"
        upload_file_to_buzzheavier "$sanitized_filename"
        ;;
esac
}

# Check if there are files in the downloads folder
shopt -s nullglob  # Avoid errors if no files match
files=(*)
if [ ${#files[@]} -gt 0 ]; then
    filename="${files[0]}"

    # Check if the file is a zip file or a 7z file
    if [[ "$filename" == *.zip ]]; then
        tg "- Detected a zip file: $filename"
    elif [[ "$filename" == *.7z ]]; then
        tg "- Detected a 7z file: $filename"
    else
        tg "- Detected a non-zip/non-7z file: $filename"
    fi

    upload "${filename}"
else
    tg "No files found to upload."
fi
