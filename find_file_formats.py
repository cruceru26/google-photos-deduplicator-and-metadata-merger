import os
import json
from exif import Image
import pathlib

def merge_metadata(media_folder):
    media_extensions = []

    for root, dirs, files in os.walk(media_folder):
        for file in files:
          extension = pathlib.Path(file).suffix
          if (extension != '.json') and (extension not in media_extensions):
            media_extensions.append(extension)

    print(media_extensions)
    # for root, dirs, files in os.walk(media_folder):
    #     for file in files:
    #         if '.' + file.split(".")[-1] in media_extensions:
    #             media_path = os.path.join(root, file)
    #             json_path = os.path.join(root, file + '.supplemental-metadata.json')
    #             if os.path.exists(json_path):
    #                 with open(json_path, 'r') as f:
    #                     metadata = json.load(f)

    #                 with open(media_path, 'rb') as f:
    #                     img = Image(f)

    #                 if 'photoTakenTime' in metadata:
    #                     img.datetime_original = str(metadata['photoTakenTime']['timestamp'])
    #                 if 'geoData' in metadata:
    #                     img.gps_latitude = metadata['geoData']['latitude']
    #                     img.gps_longitude = metadata['geoData']['longitude']
    #                 if 'description' in metadata:
    #                     img.image_description = metadata['description']

    #                 with open(media_path, 'wb') as f:
    #                     f.write(img.get_file())

# Set the folder containing your media and JSON files
media_folder = "E:\\google photos\\google photos\\Takeout\\Albums"
merge_metadata(media_folder)