Using https://takeout.google.com/ download all photos from google photos (including albums).
After the unzipping the structure of directories will look like this:

- Album 1
- Album 2
- Photos from 2023
- Photos from 2024
- Photos from 2025

All the photos from the album directories can be also found in directories from Photos from {year}.

All media will also have a json file that contain the metadata.

Create 2 separate directories for Albums and Photos per year and copy from Takeout directory the albums and photos per year to their specific directory.

Use `count.py` -> to count all media from `Albums` directory and all media from `Photos` directory to have an initial count. The count from `Photos` directory is the actual number of all media without duplicates.

`remove_duplicates.py` - will remove all media from `Photos` that is found in any directory from `Albums`. This script will create a file named `deduplication.log` with all the logs and there it can be seen if there was any error or warnings.

After removing of the duplicates copy all directories from `Photos` to `Albums` directory and create another directory `Albums_processed`.

`merge_metadata.py` - will add the metadata from the json file to the media. It will also convert WMV, AVI, MPG, 3GP files to MP4 and .nef files to .jpg. This script will create a file named `metadata_update.log` with all the logs and there it can be seen if there was any error or warnings. After the script is done the directory `Albums_processed` will contain all media with the correct metadata. Manually check all directories from `Albums` directory to see if there is any media files left there (if is there it means it was not processed) ignoring the json files.

At the end you can run `count.py` on `Albums_processed` directory to have a final count.
