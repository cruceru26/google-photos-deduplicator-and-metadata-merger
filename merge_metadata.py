import os
import json
import logging
import shutil
import subprocess
from PIL import Image
import piexif
from mutagen.mp4 import MP4, MP4Tags
from datetime import datetime
import ffmpeg  # Import ffmpeg module

# Set up logging
logging.basicConfig(
    level=logging.INFO,  # Log all messages
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("metadata_update.log", mode='w'),  # Overwrite log file each run
        logging.StreamHandler()  # Log to console
    ]
)
logger = logging.getLogger(__name__)

def remove_thumbnail(exif_dict):
    """Remove the thumbnail from the EXIF data."""
    if 'thumbnail' in exif_dict:
        del exif_dict['thumbnail']
    return exif_dict

def validate_exif_value(value):
    """Ensure the EXIF value is of the correct type and within valid range."""
    if isinstance(value, int):
        # Ensure the integer is within the valid range for EXIF tags
        if -2147483648 <= value <= 2147483647:
            return value
        else:
            logger.warning(f"Invalid integer value for EXIF tag: {value}")
            return None
    elif isinstance(value, float):
        # Convert floats to integers if possible
        if -2147483648 <= value <= 2147483647:
            return int(value)
        else:
            logger.warning(f"Invalid float value for EXIF tag: {value}")
            return None
    elif isinstance(value, str):
        # Convert strings to bytes
        return value.encode('utf-8')
    elif isinstance(value, bytes):
        return value
    elif isinstance(value, tuple):
        # Convert tuples to a string representation
        return str(value).encode('utf-8')
    else:
        logger.warning(f"Unsupported EXIF value type: {type(value)}")
        return None

def clean_exif_dict(exif_dict):
    """Clean the EXIF dictionary to remove or fix invalid tags."""
    for ifd in exif_dict:
        if ifd == 'thumbnail':
            continue  # Skip the thumbnail
        for tag in list(exif_dict[ifd].keys()):
            try:
                # Handle the problematic tag 41729 (SceneType)
                if tag == 41729:
                    logger.warning(f"Removing invalid EXIF tag {tag} in {ifd}")
                    del exif_dict[ifd][tag]  # Remove the invalid tag
                else:
                    # Validate the value for other tags
                    validate_exif_value(exif_dict[ifd][tag])
            except Exception as e:
                logger.warning(f"Removing invalid EXIF tag {tag} in {ifd}: {e}")
                del exif_dict[ifd][tag]  # Remove the invalid tag
    return exif_dict

def parse_timestamp(timestamp):
    """Parse the timestamp from the JSON metadata."""
    try:
        # Convert the timestamp to a datetime object
        dt = datetime.fromtimestamp(int(timestamp))
        return dt.strftime("%Y-%m-%d %H:%M:%S")  # Format for FFmpeg
    except Exception as e:
        logger.error(f"Failed to parse timestamp {timestamp}: {e}")
        return None

def convert_nef_to_jpg(nef_path, jpg_path, exif_bytes):
    """Convert a .nef file to .jpg while preserving metadata."""
    try:
        logger.info(f"Converting .nef file to .jpg: {nef_path}")
        with Image.open(nef_path) as img:
            # Save as .jpg with the provided EXIF metadata
            img.save(jpg_path, "jpeg", exif=exif_bytes, quality=95)  # Adjust quality as needed
            logger.info(f"Successfully converted {nef_path} to {jpg_path}")
            return True
    except Exception as e:
        logger.error(f"Failed to convert .nef file {nef_path} to .jpg: {e}")
        return False

def update_photo_metadata(media_path, metadata, directory_photo_taken_time):
    """Update metadata for photo files."""
    try:
        if media_path.lower().endswith(('.jpg', '.jpeg', '.png', '.nef')):
            # Handle JPG, PNG, and NEF files using piexif
            logger.info(f"Processing photo: {media_path}")

            # Check if the file is corrupted or truncated
            try:
                img = Image.open(media_path)
                img.verify()  # Verify the file integrity
                img.close()  # Close and reopen the file for processing
                img = Image.open(media_path)
            except Exception as e:
                logger.error(f"Corrupted or truncated image file: {media_path}. Skipping. Error: {e}")
                return False

            # Initialize an empty EXIF dictionary if no EXIF metadata exists
            if "exif" not in img.info:
                logger.info(f"No EXIF metadata found in: {media_path}. Creating new EXIF metadata.")
                exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "Interop": {}, "1st": {}, "thumbnail": None}
            else:
                exif_dict = piexif.load(img.info['exif'])

            # Remove the thumbnail to avoid "Given thumbnail is too large" error
            exif_dict = remove_thumbnail(exif_dict)

            # Clean the EXIF dictionary to remove or fix invalid tags
            exif_dict = clean_exif_dict(exif_dict)

            # Update the DateTimeOriginal field
            if metadata and 'photoTakenTime' in metadata:
                timestamp = metadata['photoTakenTime'].get('timestamp')
            elif directory_photo_taken_time:
                # Use the directory's photoTakenTime if no metadata is found
                timestamp = directory_photo_taken_time
            else:
                logger.warning(f"No timestamp found in metadata or directory for: {media_path}")
                img.close()  # Close the image before returning
                return False

            if timestamp:
                datetime_original = parse_timestamp(timestamp)
                if datetime_original:
                    # Ensure DateTimeOriginal is set in the Exif IFD
                    exif_dict['Exif'][piexif.ExifIFD.DateTimeOriginal] = datetime_original
                    # Also set DateTime in the 0th IFD (optional, for compatibility)
                    exif_dict['0th'][piexif.ImageIFD.DateTime] = datetime_original
                else:
                    logger.warning(f"Invalid timestamp in metadata for: {media_path}")
            else:
                logger.warning(f"No timestamp found in metadata for: {media_path}")

            if metadata and 'geoData' in metadata:
                latitude = metadata['geoData'].get('latitude')
                longitude = metadata['geoData'].get('longitude')
                if latitude is not None and longitude is not None:
                    exif_dict['GPS'][piexif.GPSIFD.GPSLatitude] = [(int(latitude), 1)]
                    exif_dict['GPS'][piexif.GPSIFD.GPSLongitude] = [(int(longitude), 1)]

            if metadata and 'description' in metadata:
                description = validate_exif_value(metadata['description'])
                if description is not None:
                    exif_dict['0th'][piexif.ImageIFD.ImageDescription] = description

            # Dump the EXIF dictionary to bytes
            exif_bytes = piexif.dump(exif_dict)

            # Handle .nef files by converting them to .jpg
            if media_path.lower().endswith('.nef'):
                jpg_path = os.path.splitext(media_path)[0] + ".jpg"
                if convert_nef_to_jpg(media_path, jpg_path, exif_bytes):
                    # Close the original image before deleting the .nef file
                    img.close()
                    # Delete the original .nef file after successful conversion
                    os.remove(media_path)
                    media_path = jpg_path  # Update the media_path to the new .jpg file
                    # Reopen the new .jpg file for further processing
                    img = Image.open(media_path)
                else:
                    img.close()
                    return False

            # Save the image with the updated EXIF metadata
            if media_path.lower().endswith(('.jpg', '.jpeg')):
                img.save(media_path, "jpeg", exif=exif_bytes)
            elif media_path.lower().endswith('.png'):
                # For PNG files, we need to use the `pnginfo` parameter
                png_info = img.info
                png_info["exif"] = exif_bytes
                img.save(media_path, "png", **png_info)
            img.close()

            logger.info(f"Successfully updated metadata for photo: {media_path}")
            return True

        elif media_path.lower().endswith('.gif'):
            # Handle GIF files (skip metadata updates)
            logger.warning(f"Skipping metadata update for .gif file: {media_path} (GIF metadata not supported)")
            return False

        else:
            logger.warning(f"Unsupported photo format: {media_path}")
            return False

    except Exception as e:
        logger.error(f"Failed to update metadata for photo {media_path}: {e}")
        return False

def update_video_metadata(media_path, metadata, processed_folder):
    """Update metadata for video files."""
    try:
        if media_path.lower().endswith(('.mp4', '.mov')):
            # Handle MP4/MOV files using mutagen
            logger.info(f"Processing video: {media_path}")
            video = MP4(media_path)
            tags = {}

            if metadata and 'photoTakenTime' in metadata:
                timestamp = metadata['photoTakenTime'].get('timestamp')
                if timestamp:
                    creation_time = parse_timestamp(timestamp)
                    if creation_time:
                        tags['\xa9day'] = creation_time  # Set creation date
                    else:
                        logger.warning(f"Invalid timestamp in metadata for: {media_path}")
                else:
                    logger.warning(f"No timestamp found in metadata for: {media_path}")

            if metadata and 'description' in metadata:
                tags['\xa9nam'] = metadata['description']

            video.update(tags)
            video.save()

            logger.info(f"Successfully updated metadata for video: {media_path}")
            return True

        elif media_path.lower().endswith(('.wmv', '.avi', '.mpg', '.3gp')):
            # Handle WMV, AVI, MPG, 3GP files by converting them to MP4
            logger.info(f"Processing video: {media_path}")
            creation_time = None
            if metadata and 'photoTakenTime' in metadata:
                timestamp = metadata['photoTakenTime'].get('timestamp')
                if timestamp:
                    creation_time = parse_timestamp(timestamp)
                    if not creation_time:
                        logger.warning(f"Invalid timestamp in metadata for: {media_path}")
                else:
                    logger.warning(f"No timestamp found in metadata for: {media_path}")

            description = metadata['description'] if metadata and 'description' in metadata else None

            # Create a new MP4 file path
            mp4_path = os.path.splitext(media_path)[0] + ".mp4"

            # Format metadata as key=value strings
            metadata_args = []
            if creation_time:
                metadata_args.append(f"creation_time={creation_time}")
            if description:
                metadata_args.append(f"comment={description}")

            # Log the metadata arguments being passed to FFmpeg
            logger.info(f"FFmpeg metadata_args: {metadata_args}")

            # Use FFmpeg to convert the video to MP4 and set metadata
            try:
                (
                    ffmpeg.input(media_path)
                    .output(
                        mp4_path,
                        format='mp4',
                        vcodec='libx264',
                        acodec='aac',
                        metadata=metadata_args  # Pass metadata as a list of key=value strings
                    )
                    .overwrite_output()
                    .run()
                )
                logger.info(f"FFmpeg conversion completed for: {media_path}")
            except ffmpeg.Error as e:
                logger.error(f"FFmpeg error: {e.stderr.decode('utf-8') if e.stderr else 'Unknown error'}")
                return False
            except Exception as e:
                logger.error(f"Unexpected error during ffmpeg processing: {e}")
                return False

            # Use exiftool to ensure metadata is correctly embedded
            if creation_time:
                try:
                    subprocess.run(
                        ['exiftool', '-overwrite_original', '-CreateDate=' + creation_time, mp4_path],
                        check=True
                    )
                    logger.info(f"Successfully set creation_time for {mp4_path} using exiftool")
                except subprocess.CalledProcessError as e:
                    logger.error(f"Failed to set creation_time for {mp4_path} using exiftool: {e}")
                    return False

            # Move the new MP4 file to the processed folder
            relative_path = os.path.relpath(mp4_path, media_folder)
            processed_path = os.path.join(processed_folder, relative_path)

            # Create the processed directory if it doesn't exist
            os.makedirs(os.path.dirname(processed_path), exist_ok=True)

            # Move the file
            try:
                shutil.move(mp4_path, processed_path)
                logger.info(f"Moved file: {mp4_path} -> {processed_path}")
            except Exception as e:
                logger.error(f"Failed to move file {mp4_path} to {processed_path}: {e}")
                return False

            # Delete the original file (e.g., .wmv, .avi, .3gp) after successful conversion and move
            try:
                os.remove(media_path)
                logger.info(f"Deleted original file: {media_path}")
            except Exception as e:
                logger.error(f"Failed to delete original file {media_path}: {e}")
                return False

            return True

        else:
            logger.warning(f"Unsupported video format: {media_path}")
            return False

    except Exception as e:
        logger.error(f"Failed to update metadata for video {media_path}: {e}")
        return False

def get_metadata_from_json(json_path):
    """Load metadata from a JSON file."""
    if os.path.exists(json_path):
        try:
            with open(json_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load JSON file {json_path}: {e}")
            return {}
    return {}

def find_json_file_for_media(media_path):
    """Find the corresponding JSON file for a media file."""
    base_name = os.path.splitext(media_path)[0]
    directory = os.path.dirname(media_path)

    # Look for any JSON file that starts with the base name and ends with .json
    for file in os.listdir(directory):
        if file.startswith(os.path.basename(base_name)) and file.endswith(".json"):
            return os.path.join(directory, file)
    
    return None

def get_photo_taken_time_from_directory(directory):
    """Get the photoTakenTime from any media file in the directory."""
    for root, _, files in os.walk(directory):
        for file in files:
            if not file.endswith('.json'):
                media_path = os.path.join(root, file)
                json_path = find_json_file_for_media(media_path)

                if json_path:
                    metadata = get_metadata_from_json(json_path)
                    if metadata and 'photoTakenTime' in metadata:
                        return metadata['photoTakenTime'].get('timestamp')
    return None

def merge_metadata(media_folder, processed_folder):
    """Merge metadata from JSON files into media files."""
    logger.info(f"Starting metadata update for folder: {media_folder}")

    # Dictionary to store results for each directory
    results = {}

    for root, dirs, files in os.walk(media_folder):
        # Initialize counters for the current directory
        initial_file_count = 0
        updated_file_count = 0
        unprocessed_file_count = 0

        # Get the photoTakenTime from any media file in the directory
        directory_photo_taken_time = get_photo_taken_time_from_directory(root)

        # List to store paths of successfully updated files
        updated_files = []

        for file in files:
            if not file.endswith('.json'):
                media_path = os.path.join(root, file)
                json_path = find_json_file_for_media(media_path)

                # Debug: Print media file and JSON file paths
                logger.debug(f"Media file: {media_path}")
                logger.debug(f"JSON file: {json_path}")

                # Increment initial file count
                initial_file_count += 1

                metadata = get_metadata_from_json(json_path) if json_path else {}

                if metadata or directory_photo_taken_time:
                    if file.lower().endswith(('.jpg', '.jpeg', '.png', '.nef')):
                        # Handle photos (including .dng files if no corresponding .JPG exists)
                        if update_photo_metadata(media_path, metadata, directory_photo_taken_time):
                            updated_file_count += 1
                            # Add the updated file to the list (use the new .jpg path if it was converted from .nef)
                            if media_path.lower().endswith('.nef'):
                                updated_files.append(os.path.splitext(media_path)[0] + ".jpg")
                            else:
                                updated_files.append(media_path)
                        else:
                            unprocessed_file_count += 1

                    elif file.lower().endswith(('.mp4', '.mov', '.avi', '.wmv', '.mpg', '.3gp')):
                        # Handle videos
                        if update_video_metadata(media_path, metadata, processed_folder):
                            updated_file_count += 1
                            updated_files.append(media_path)  # Add to updated_files list
                        else:
                            unprocessed_file_count += 1

                    elif file.lower().endswith('.gif'):
                        # Handle GIF files (copy without modifying metadata)
                        updated_file_count += 1
                        updated_files.append(media_path)  # Add to updated_files list

                    else:
                        logger.warning(f"Skipping unsupported file type: {file}")
                        unprocessed_file_count += 1
                else:
                    logger.warning(f"No JSON file or directory timestamp found for: {file}")
                    unprocessed_file_count += 1

        # Store results for the current directory
        results[root] = {
            "initial_file_count": initial_file_count,
            "updated_file_count": updated_file_count,
            "unprocessed_file_count": unprocessed_file_count,
        }

        # Move updated files to the processed folder
        logger.info(f"Moving updated files to: {processed_folder}")
        for media_path in updated_files:
            relative_path = os.path.relpath(media_path, media_folder)
            processed_path = os.path.join(processed_folder, relative_path)

            # Create the processed directory if it doesn't exist
            os.makedirs(os.path.dirname(processed_path), exist_ok=True)

            # Move the file
            try:
                shutil.move(media_path, processed_path)
                logger.info(f"Moved file: {media_path} -> {processed_path}")
            except Exception as e:
                logger.error(f"Failed to move file {media_path} to {processed_path}: {e}")

    # Log the results for each directory
    for directory, stats in results.items():
        logger.info(f"Directory: {directory}")
        logger.info(f"  Initial file count: {stats['initial_file_count']}")
        logger.info(f"  Updated file count: {stats['updated_file_count']}")
        logger.info(f"  Unprocessed file count: {stats['unprocessed_file_count']}")

    logger.info("Metadata update and file move completed.")

# Set the folder containing your media and JSON files
media_folder = "E:\\google photos\\Andreea's photos\\Albums"
processed_folder = "E:\\google photos\\Andreea's photos\\Albums_processed"

merge_metadata(media_folder, processed_folder)