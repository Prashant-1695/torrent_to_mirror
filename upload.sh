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
    local download_link=https://buzzheavier.com/f/$(curl -#o - -T "$1" https://w.buzzheavier.com/t/$1 | cut -d : -f 2 | cut -d } -f 1 | grep -Po '[^"]*')
}

upload_file_to_pixeldrain() {
    local file="$1"
    local token="$2"
    local response

    # Perform the upload to Pixeldrain using the API key
    response=$(curl -T "${file}" -u ":${token}" "https://pixeldrain.com/api/file")

    # Extract the URL from the response using jq
    local download_link=$(echo "$response" | jq -r '.id')

}

case $uploader in
    gofile)
        upload_file_to_gofile "$file_path"
        ;;
    buzzheavier)
        upload_file_to_buzzheavier "$file_path"
        ;;
    pixeldrain)
        check_jq  # Check if jq is installed before proceeding
        upload_file_to_pixeldrain "$file_path" "$api_key"
        ;;
    *)
        echo "Unknown uploader: $uploader"
        exit 1
        ;;
esac
