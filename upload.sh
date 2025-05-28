#!/bin/bash
set -euo pipefail  # Exit on error, undefined vars, pipe failures

# Configuration
API_URL="https://pixeldrain.com/api/file"
TELEGRAM_API_URL="https://api.telegram.org/bot${BOT_ID:-}/sendMessage"
SCRIPT_START_TIME=$(date +%s)
UPLOAD_COUNT=0
FAILED_COUNT=0
LOG_FILE="/tmp/ci/upload_log_$(date +%Y%m%d_%H%M%S).log"

# Colors for output (if terminal supports it)
if [[ -t 1 ]]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    BLUE='\033[0;34m'
    NC='\033[0m' # No Color
else
    RED='' GREEN='' YELLOW='' BLUE='' NC=''
fi

# Logging function
log() {
    local level="$1"
    shift
    local message="$*"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] [$level] $message" | tee -a "$LOG_FILE"
}

log_info() { log "INFO" "$*"; }
log_warn() { log "WARN" "$*"; }
log_error() { log "ERROR" "$*"; }
log_success() { log "SUCCESS" "$*"; }

# Enhanced configuration loader with better error handling
load_cirrus_config() {
    log_info "Loading configuration..."

    # Check if running in CI environment
    if [[ "${CI:-false}" == "true" || "${CIRRUS_CI:-false}" == "true" ]]; then
        log_info "Running in CI environment"
        # In CI, variables should already be exported
        return 0
    fi

    if [[ -f /tmp/ci/.cirrus.yml ]]; then
        log_info "Loading configuration from /tmp/ci/.cirrus.yml..."

        # Extract variables with better parsing
        PIXELDRAIN_API_KEY=$(yq eval '.env.PIXELDRAIN_API_KEY // ""' /tmp/ci/.cirrus.yml 2>/dev/null || \
                              grep -A 20 "env:" /tmp/ci/.cirrus.yml | grep "PIXELDRAIN_API_KEY:" | \
                              sed 's/.*PIXELDRAIN_API_KEY: *//;s/ENCRYPTED\[//;s/\]$//' | tr -d '"' || echo "")

        BOT_ID=$(yq eval '.env.BOT_ID // ""' /tmp/ci/.cirrus.yml 2>/dev/null || \
                 grep -A 20 "env:" /tmp/ci/.cirrus.yml | grep "BOT_ID:" | \
                 sed 's/.*BOT_ID: *//;s/ENCRYPTED\[//;s/\]$//' | tr -d '"' || echo "")

        CHAT_ID=$(yq eval '.env.CHAT_ID // ""' /tmp/ci/.cirrus.yml 2>/dev/null || \
                  grep -A 20 "env:" /tmp/ci/.cirrus.yml | grep "CHAT_ID:" | \
                  sed 's/.*CHAT_ID: *//;s/ENCRYPTED\[//;s/\]$//' | tr -d '"' || echo "")

        # Export variables
        [[ -n "$PIXELDRAIN_API_KEY" ]] && export PIXELDRAIN_API_KEY
        [[ -n "$BOT_ID" ]] && export BOT_ID
        [[ -n "$CHAT_ID" ]] && export CHAT_ID

    elif [[ -f /tmp/ci/.env ]]; then
        log_warn "/tmp/ci/.cirrus.yml not found, using /tmp/ci/.env as fallback..."
        set -a  # automatically export all variables
        source /tmp/ci/.env
        set +a
    else
        log_error "No configuration file found (/tmp/ci/.cirrus.yml or /tmp/ci/.env)"
        return 1
    fi
}

# Enhanced validation with detailed error messages
validate_config() {
    log_info "Validating configuration..."

    local errors=0

    if [[ -z "${PIXELDRAIN_API_KEY:-}" ]]; then
        log_error "PIXELDRAIN_API_KEY not found or empty"
        ((errors++))
    else
        log_info "PixelDrain API key: ✓"
    fi

    if [[ -z "${BOT_ID:-}" ]] || [[ -z "${CHAT_ID:-}" ]]; then
        log_warn "Telegram notifications disabled - missing BOT_ID or CHAT_ID"
        TELEGRAM_ENABLED=false
    else
        TELEGRAM_ENABLED=true
        log_info "Telegram notifications: ✓"
    fi

    # Test API connectivity
    if ! curl -s --connect-timeout 10 "$API_URL" > /dev/null; then
        log_warn "Cannot reach PixelDrain API - uploads may fail"
    else
        log_info "PixelDrain API connectivity: ✓"
    fi

    return $errors
}

# Enhanced Telegram notification with retry logic
send_telegram() {
    local message="$1"
    local max_retries=3
    local retry_count=0

    [[ "$TELEGRAM_ENABLED" != "true" ]] && return 0

    while [[ $retry_count -lt $max_retries ]]; do
        if curl -s --connect-timeout 10 --max-time 30 -X POST "$TELEGRAM_API_URL" \
            -d chat_id="$CHAT_ID" \
            -d text="$message" \
            -d parse_mode="Markdown" > /dev/null 2>&1; then
            return 0
        fi

        ((retry_count++))
        log_warn "Telegram notification failed (attempt $retry_count/$max_retries)"
        [[ $retry_count -lt $max_retries ]] && sleep 2
    done

    log_error "Failed to send Telegram notification after $max_retries attempts"
    return 1
}

# Enhanced file upload with better error handling and progress tracking
upload_file() {
    local file="$1"
    local filename=$(basename "$file")
    local filesize=$(stat -f%z "$file" 2>/dev/null || stat -c%s "$file" 2>/dev/null || echo "unknown")

    log_info "Uploading: $filename (${filesize} bytes)"

    # Check file exists and is readable
    if [[ ! -f "$file" ]] || [[ ! -r "$file" ]]; then
        log_error "File not found or not readable: $file"
        ((FAILED_COUNT++))
        return 1
    fi

    # Upload with timeout and retry logic
    local max_retries=2
    local retry_count=0
    local response

    while [[ $retry_count -le $max_retries ]]; do
        response=$(curl --silent --show-error --connect-timeout 30 --max-time 1800 \
                       -u ":$PIXELDRAIN_API_KEY" -F "file=@$file" "$API_URL" 2>&1)

        if [[ $? -eq 0 ]] && echo "$response" | grep -q '"success":true'; then
            file_id=$(echo "$response" | grep -o '"id":"[^"]*"' | cut -d'"' -f4)
            download_url="https://pixeldrain.com/u/$file_id"

            log_success "Upload successful: $filename"
            echo -e "${GREEN}✅ Success!${NC}\n   URL: $download_url"

            send_telegram "✅ *Upload Success*
📁 File: \`$filename\`
📊 Size: \`$filesize bytes\`
🔗 URL: [$download_url]($download_url)"

            ((UPLOAD_COUNT++))
            return 0
        fi

        ((retry_count++))
        if [[ $retry_count -le $max_retries ]]; then
            log_warn "Upload failed for $filename (attempt $retry_count/$((max_retries + 1)))"
            sleep 5
        fi
    done

    # Extract error message
    local error_msg="Unknown error"
    if [[ -n "$response" ]]; then
        error_msg=$(echo "$response" | grep -o '"value":"[^"]*"' | cut -d'"' -f4 || echo "$response")
    fi

    log_error "Upload failed for $filename: $error_msg"
    echo -e "${RED}❌ Failed!${NC}\n   Error: $error_msg"

    send_telegram "❌ *Upload Failed*
📁 File: \`$filename\`
⚠️ Error: \`$error_msg\`"

    ((FAILED_COUNT++))
    return 1
}

# Enhanced directory processing with better file discovery
process_directory() {
    local dir="$1"
    log_info "Scanning directory: $dir"

    if [[ ! -d "$dir" ]]; then
        log_error "Directory not found: $dir"
        return 1
    fi

    # Video extensions
    local video_extensions=("mp4" "mkv" "avi" "mov" "flv" "wmv" "webm" "m4v" "3gp" "ogv")

    # Build find command
    local find_cmd="find \"$dir\" -type f \\("
    for i in "${!video_extensions[@]}"; do
        [[ $i -gt 0 ]] && find_cmd+=" -o"
        find_cmd+=" -iname \"*.${video_extensions[$i]}\""
    done
    find_cmd+=" \\) -print0"

    local file_count=0
    while IFS= read -r -d '' file; do
        ((file_count++))
        upload_file "$file"

        # Add small delay to avoid overwhelming the server
        sleep 1
    done < <(eval "$find_cmd")

    log_info "Found $file_count video files in $dir"
    return 0
}

# Cleanup function
cleanup() {
    local exit_code=$?
    log_info "Cleaning up..."

    # Send final report
    local duration=$(($(date +%s) - SCRIPT_START_TIME))
    local summary="🏁 *Upload Script Completed*
⏱️ Duration: ${duration}s
📊 Uploaded: $UPLOAD_COUNT files
❌ Failed: $FAILED_COUNT files"

    if [[ $UPLOAD_COUNT -eq 0 && $FAILED_COUNT -eq 0 ]]; then
        summary="ℹ️ *No video files found*"
    fi

    send_telegram "$summary"
    log_info "Script completed. Uploaded: $UPLOAD_COUNT, Failed: $FAILED_COUNT, Duration: ${duration}s"

    # Archive log file in CI environment
    if [[ "${CI:-false}" == "true" ]]; then
        # Copy log to a location that persists after task completion
        cp "$LOG_FILE" "/tmp/ci/" 2>/dev/null || true
        echo "::set-output name=upload_count::$UPLOAD_COUNT"
        echo "::set-output name=failed_count::$FAILED_COUNT"
        echo "::set-output name=log_file::$LOG_FILE"
    fi

    exit $exit_code
}

# Set trap for cleanup
trap cleanup EXIT INT TERM

# Main function
main() {
    echo -e "${BLUE}🚀 Starting Upload Script${NC}"
    log_info "Upload script started"

    # Load and validate configuration
    if ! load_cirrus_config; then
        log_error "Configuration loading failed"
        exit 1
    fi

    if ! validate_config; then
        log_error "Configuration validation failed"
        exit 1
    fi

    # Send start notification
    send_telegram "🚀 *Upload Script Started*
🖥️ Environment: ${CI:+CI}${CIRRUS_CI:+Cirrus CI}
📂 Working Directory: \`$(pwd)\`"

    # Determine target directory (prioritize /tmp/ci structure)
    local target_dirs=()

    # Check for Downloads in CI working directory first
    if [[ -d "/tmp/ci/Downloads" ]]; then
        target_dirs+=("/tmp/ci/Downloads")
    elif [[ -d "Downloads" ]]; then
        target_dirs+=("Downloads")
    fi

    # Add CI working directory or current directory
    if [[ ${#target_dirs[@]} -eq 0 ]] || [[ "${SCAN_CURRENT_DIR:-false}" == "true" ]]; then
        if [[ -d "/tmp/ci" ]]; then
            target_dirs+=("/tmp/ci")
        else
            target_dirs+=(".")
        fi
    fi

    # Process each directory
    for dir in "${target_dirs[@]}"; do
        process_directory "$dir"
    done

    log_info "All directories processed"
}

# Run main function
main "$@"
