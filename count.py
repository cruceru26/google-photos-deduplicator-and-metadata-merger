import os

def count_files(directory):
    # Initialize a counter for files
    file_count = 0

    # Walk through the directory and its subdirectories
    for root, dirs, files in os.walk(directory):
        for file in files:
            # Check if the file is not a JSON file
            if not file.endswith('.json'):
                file_count += 1

    return file_count

if __name__ == "__main__":
    # Specify the directory you want to count files in
    target_directory = "E:\\takeout\\Takeout\\Albums_processed\\"
    target_directory1 = "E:\\takeout\\Takeout\\Photos\\"

    # Call the function to count files
    total_files = count_files(target_directory)
    total_files1 = count_files(target_directory1)

    print(f"album: {total_files} gp: {total_files1} diff: {total_files1 - total_files}")

    # Print the result
    # print(f"Total number of files (excluding JSON): {total_files}")