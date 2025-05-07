import os
import json
import re
import logging
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("deduplication.log", mode='w', encoding='utf-8'),  # Log to a file with UTF-8 encoding
        logging.StreamHandler()  # Log to the console
    ]
)

def find_metadata_file(media_file):
    """Find the corresponding metadata file for a media file, handling all naming patterns."""
    base_name = os.path.basename(media_file)
    base_name_without_ext, ext = os.path.splitext(base_name)
    directory = os.path.dirname(media_file)

    # Extract the counter suffix (e.g., "(507)") from the media file name
    counter_match = re.match(r"^(.*?)\((\d+)\)$", base_name_without_ext)
    if counter_match:
        base_name_without_counter = counter_match.group(1)
        counter = counter_match.group(2)
    else:
        base_name_without_counter = base_name_without_ext
        counter = None

    # Search for metadata files matching the patterns
    for file in os.listdir(directory):
        if file.endswith(".json"):
            # Case 1: {originalfilename}.json (exact match)
            if file == f"{base_name}.json":
                return os.path.join(directory, file)

            # Case 2: {originalfilename}.{originalfileextension}.{sometext}.json (no counter)
            metadata_match_case2 = re.match(
                rf"^{re.escape(base_name)}\.[^()]+\.json$",
                file,
                re.IGNORECASE  # Case-insensitive matching
            )
            if metadata_match_case2:
                return os.path.join(directory, file)

            # Case 3: {originalfilename}.{sometext}{counter}.json
            if counter:
                metadata_match_case3 = re.match(
                    rf"^{re.escape(base_name_without_counter)}\..+?\({counter}\)\.json$",
                    file,
                    re.IGNORECASE  # Case-insensitive matching
                )
                if metadata_match_case3:
                    return os.path.join(directory, file)

            # Case 4: {originalfilename}{counter}.{originalfileextension}.{sometext}.json
            if counter:
                metadata_match_case4 = re.match(
                    rf"^{re.escape(base_name_without_counter)}\({counter}\)\{re.escape(ext)}\..+?\.json$",
                    file,
                    re.IGNORECASE  # Case-insensitive matching
                )
                if metadata_match_case4:
                    return os.path.join(directory, file)

    return None

def load_metadata(media_file):
    """Load metadata from the corresponding JSON file."""
    metadata_file = find_metadata_file(media_file)
    if metadata_file and os.path.exists(metadata_file):
        with open(metadata_file, "r") as f:
            return {"path": metadata_file, "data": json.load(f)}
    return None

def get_photo_taken_time(metadata):
    """Extract the photoTakenTime from the metadata."""
    if metadata and "photoTakenTime" in metadata:
        return metadata["photoTakenTime"]["timestamp"]
    return None

def get_title(metadata):
    """Extract the title from the metadata."""
    if metadata and "title" in metadata:
        return str(metadata["title"]).lower()
    return None

def group_files_by_name_and_metadata(directory):
    """Group files by their base name and photoTakenTime, preserving directory structure."""
    name_to_files = defaultdict(list)
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith(".json"):  # Skip metadata files
                continue
            file_path = os.path.join(root, file)
            base_name = os.path.splitext(file)[0].lower()  # Normalize name
            metadata_file = load_metadata(file_path)
            metadata_json = ""
            metadata_path = ""
            photo_taken_time = ""
            title = ""
            if metadata_file:
                metadata_json = metadata_file["data"]
                metadata_path = metadata_file["path"]
                photo_taken_time = get_photo_taken_time(metadata_json)
                title = get_title(metadata_json)
            else:
                title = base_name
            
            obj = {"base_name": file, "photo_taken_time": photo_taken_time, "file_path": file_path, "json_path": metadata_path}
            name_to_files[title].append(obj)
    return name_to_files

def find_duplicates(albums_directory, photos_directory, max_workers=8):
    """Find duplicate files in the Photos directory that exist in the Albums directory."""
    # Step 1: Group files by base name and photoTakenTime in both directories
    albums_name_to_files = group_files_by_name_and_metadata(albums_directory)
    photos_name_to_files = group_files_by_name_and_metadata(photos_directory)
    duplicates = []
    count_media = 0
    
    # Step 2: Compare files with the same base name and photoTakenTime
    for title, photos_files in photos_name_to_files.items():
        if title in albums_name_to_files:
            album_files = albums_name_to_files[title]
            if len(photos_files) == 1 and len(album_files) == 1:
                # These files are duplicates
                duplicates.append(photos_files[0]["file_path"])
                duplicates.append(photos_files[0]["json_path"])
                count_media = count_media + 1
                logging.info(f"Duplicate found: {album_files[0]["file_path"]} -> {photos_files[0]["file_path"]}")
            elif len(photos_files) > 1 and len(album_files) == 1:
                logging.info(f"{title}: {photos_files}")
                for gp in photos_files:
                    if album_files[0]["photo_taken_time"] == gp["photo_taken_time"]:
                        duplicates.append(gp["file_path"])
                        duplicates.append(gp["json_path"])
                        count_media = count_media + 1
                        logging.info(f"Duplicate found: {album_files[0]["file_path"]} -> {gp["file_path"]}")
            elif len(photos_files) == 1 and len(album_files) > 1:
                logging.info(f"{title}: {album_files}")
                for alb in album_files:
                    if photos_files[0]["photo_taken_time"] == alb["photo_taken_time"]:
                        duplicates.append(photos_files[0]["file_path"])
                        duplicates.append(photos_files[0]["json_path"])
                        count_media = count_media + 1
                        logging.info(f"Duplicate found: {alb["file_path"]} -> {photos_files[0]["file_path"]}")
            elif len(photos_files) > 1 and len(album_files) > 1:
                logging.info(f"{title}: {album_files} -> {photos_files}")
                for gp in photos_files:
                    for alb in album_files:
                        if gp["photo_taken_time"] == alb["photo_taken_time"]:
                            duplicates.append(gp["file_path"])
                            duplicates.append(gp["json_path"])
                            count_media = count_media + 1
                            logging.info(f"Duplicate found: {alb["file_path"]} -> {gp["file_path"]}")
                            break
    duplicates = list(set(duplicates))
    logging.info(f"Found {count_media} duplicates.")

    return duplicates

def remove_duplicates(duplicates):
    """Remove duplicate files from the Photos directory."""
    for file_path in duplicates:
        try:
            logging.info(f"Removing duplicate: {file_path}")
            os.remove(file_path)
        except (IOError, OSError) as e:
            logging.error(f"Failed to remove {file_path}: {e}")

# Define directories
albums_directory = "E:\\google photos\\Andreea's photos\\Albums"  # Directory containing your albums
photos_directory = "E:\\google photos\\Andreea's photos\\GooglePhotos"  # Directory to clean up

# Find and remove duplicates
logging.info("Starting duplicate detection...")
duplicates = find_duplicates(albums_directory, photos_directory, max_workers=8)

logging.info("Starting duplicate removal...")
remove_duplicates(duplicates)
logging.info("Duplicate removal completed.")

print(f"Removed duplicates from '{photos_directory}'.")