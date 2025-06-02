import subprocess
import os
import requests
import re


def get_latest_github_version():
    """Fetches the latest release version from the GitHub repository."""
    try:
       # response = requests.get(
       #     "https://github.com/Evilvir-us/MacReplay/releases/latest"
       # )
       # response.raise_for_status()
       # release_data = response.json()
       # latest_version = release_data["tag_name"]  # 'v2.2.1'
       # return latest_version.lstrip("v")  # Remove the leading 'v' to get '2.2.1'
        return '2.2.1'
    except requests.RequestException as e:
        print(f"Error fetching the latest GitHub version: {e}")
        raise


def compare_versions(version1, version2):
    """Compares two version strings in the format 'x.y.z'."""
    version1_parts = [int(part) for part in version1.split(".")]
    version2_parts = [int(part) for part in version2.split(".")]

    # Compare part by part
    return (version1_parts > version2_parts) - (version1_parts < version2_parts)


def increment_version(version):
    """Increments the version by 1 (increases the patch version)."""
    version_parts = version.split(".")
    version_parts[-1] = str(int(version_parts[-1]) + 1)  # Increment the patch version
    return ".".join(version_parts)


def update_version_in_file(file_path, new_version):
    """Updates the VERSION line in the app.py file."""
    try:
        with open(file_path, "r", encoding="utf-8") as file:  # Open with UTF-8 encoding
            content = file.read()

        # Find and update the VERSION line, accounting for quotes around the version
        content = re.sub(
            r'VERSION = "\d+\.\d+\.\d+"', f'VERSION = "{new_version}"', content
        )

        with open(
            file_path, "w", encoding="utf-8"
        ) as file:  # Write with UTF-8 encoding
            file.write(content)

        print(f"Updated VERSION to {new_version} in {file_path}")
    except Exception as e:
        print(f"Error updating the version in file: {e}")
        raise


def run_pyinstaller():
    """Runs PyInstaller to create the executable with custom options."""
    try:
        print("Running PyInstaller with custom options...")
        subprocess.check_call(
            [
                "pyinstaller",
                "--onefile",
                "--add-data=templates/*;templates",  # Add templates directory to the build
                "--add-data=static/*;static",  # Add static directory to the build
                "--add-data=ffmpeg/*;ffmpeg",  # Add ffmpeg directory to the build
                "--hidden-import=stb",
                "--hidden-import=waitress",
                "--icon=replay.ico",
                "app.py",
            ]
        )
        print("PyInstaller finished successfully.")
    except subprocess.CalledProcessError as e:
        print(f"Error running PyInstaller: {e}")
        raise


def copy_executable():
    """Copies the generated executable to the current directory."""
    try:
        print("Copying MacReplay.exe to the current directory...")
        source_path = os.path.join("dist", "app.exe")
        destination_path = ".\MacReplay.exe"
        subprocess.check_call(["copy", source_path, destination_path], shell=True)
        print("Executable copied successfully.")
    except subprocess.CalledProcessError as e:
        print(f"Error copying executable: {e}")
        raise


def modify_python_file(file_path, github_version):
    """Check and update the version and logging config in the file if necessary."""
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            content = file.read()

        # Extract the current version from the file
        current_version_match = re.search(r'VERSION = "(\d+\.\d+\.\d+)"', content)
        if current_version_match:
            current_version = current_version_match.group(1)
            print(f"Current VERSION = {current_version}")
            # Compare the current version with the GitHub version
            if compare_versions(current_version, github_version) < 0:
                print(
                    f"Current version {current_version} is lower than GitHub version {github_version}. Updating..."
                )
                new_version = increment_version(github_version)
                update_version_in_file(file_path, new_version)
            elif compare_versions(current_version, github_version) == 0:
                print(
                    f"Current version {current_version} is the same as GitHub version {github_version}. Incrementing version..."
                )
                new_version = increment_version(current_version)
                update_version_in_file(file_path, new_version)
            else:
                print("Current version is up-to-date.")
        else:
            print("No VERSION line found in the file.")

    except Exception as e:
        print(f"Error modifying file: {e}")
        raise


def main():
    """Main function to execute all steps."""
    github_version = get_latest_github_version()  # Get latest version from GitHub
    modify_python_file(
        "app.py", github_version
    )  # Modify file with the new version and logging config
    run_pyinstaller()  # Build the executable
    copy_executable()  # Copy the executable to the current directory
    input("Process complete. Press Enter to exit...")


if __name__ == "__main__":
    main()
