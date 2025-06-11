#!/bin/bash

# Set strict error handling
set -euo pipefail
IFS=$'\n\t'

# Function to get file size
get_file_size() {
    local file="$1"
    if [[ "$OSTYPE" == "darwin"* ]]; then
        stat -f%z "$file"
    else
        stat -c%s "$file"
    fi
}

# Function to upload file to GoFile
upload_file() {
    local file="$1"
    local file_size
    file_size=$(get_file_size "$file")

    # Upload to GoFile
    local response
    response=$(curl -s -X POST \
        -H "Content-Type: multipart/form-data" \
        -H "Accept: application/json" \
        -H "User-Agent: Mozilla/5.0" \
        -H "Connection: keep-alive" \
        -F "file=@$file" \
        "https://upload.gofile.io/uploadFile")

    # Check if upload was successful
    if echo "$response" | grep -q '"status":"ok"'; then
        download_link=$(echo "$response" | grep -o '"downloadPage":"[^"]*' | cut -d'"' -f4)
        echo "$download_link"
        return 0
    else
        echo "Error: Upload failed - $response" >&2
        return 1
    fi
}

# Main execution
main() {
    if [[ $# -ne 1 ]]; then
        echo "Error: File path required" >&2
        exit 1
    fi

    local file="$1"
    if [[ ! -f "$file" ]]; then
        echo "Error: File not found: $file" >&2
        exit 1
    fi

    # Get file size and check if it's too large (max 10GB)
    local size
    size=$(get_file_size "$file")
    if (( size > 10737418240 )); then  # 10GB in bytes
        echo "Error: File size exceeds 10GB limit" >&2
        exit 1
    fi

    upload_file "$file"
}

# Execute main
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
