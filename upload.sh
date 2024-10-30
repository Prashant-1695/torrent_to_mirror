#!/bin/bash

# Usage: ./upload.sh <uploader> <file_path> <api_key>

uploader=$1
file_path=$2
api_key=$3

# Function to check if jq is installed
check_jq() {
    if ! command -v jq &> /dev/null; then
        echo "Error: jq is not installed. Please install jq to use this script."
        exit 1
    fi
}

upload_file_to_gofile() {
    local file="$1"
    local response
    response=$(curl -F "file=@${file}" https://store1.gofile.io/uploadFile)
    echo "$response" | grep -o '"downloadPage":"[^"]*' | cut -d'"' -f4
}

upload_file_to_buzzheavier() {
    local file="$1"
    local response
    response=$(curl -F "file=@${file}" https://buzzheavier.com/upload)
    echo "$response" | grep -o '"url":"[^"]*' | cut -d'"' -f4
}

upload_file_to_pixeldrain() {
    local file="$1"
    local token="$2"
    local response
    response=$(curl -X POST -H "Authorization: Bearer ${token}" -F "file=@${file}" https://pixeldrain.com/api/file)
    echo "$response" | jq -r '.id'
}

case $uploader in
    gofile)
        upload_file_to_gofile "$file_path"
        ;;
    buzzheavier)
        upload_file_to_buzzheavier "$file_path"
        ;;
    pixeldrain)
        upload_file_to_pixeldrain "$file_path" "$api_key"
        ;;
    *)
        echo "Unknown uploader: $uploader"
        exit 1
        ;;
esac
