
# `align.py`

This script helps with getting duration information for transcribed speech.

## Requirements:
`pandas`

`requests`

`tqdm`

gentle (standalone version installed in Applications folder on Mac; installed via Docker on Windows)

Docker Desktop (Windows only)

## Usage:

From the command prompt/terminal, run:

`python align.py transcription_files [sound_dirs] [stimuli_files] [-t] [-i] [-m] [-p] [-d] [-w]`

- `transcription_files`: required. The (relative) path to the CSV(s) containing your transcriptions + item numbers. You do not need to include the file extension. You may include paths to multiple CSVs, in which case they should each be separated by `:`. Wildcards (`*`) and recursive wildcards (`**`) are allowed, and results will be sorted alphanumerically.

- `sound_dirs`: optional. The (relative) path to the directory/directories containing your (previously trimmed) mp3s. The default for each transcription file is the directory where that transcription file is located. If specifying multiple sound directories, they must be separated by `:`. Wildcards and recursive wildcards are allowed, and results will be sorted alphanumerically. The order of the sound directories should correspond to the order of the transcription files. If you include multiple transcription files, but only specify one sound directory, it will be assumed that this sound directory is the same for each transcription file. If you specify multiple sound directories, you must specify one for each transcription file in the same order as each's corresponding transcription file. NOTE: Sound files must begin with a number corresponding to the item number from `transcription_file` to which they correspond (any leading zeros will be ignored; the script will work with or without them present). The number of mp3 files in each `sound_dir` and the corresponding transcription file must match.

- `stimuli_files`: optional. The (relative) path to the file(s) containing stimuli information for the sentences you are processing. The script will add duration information for each word to the stimuli file. The default assumes that this is the same as transcription_file for each transcription file. In case item numbers in the stimuli file and the transcription file are different, or the stimuli file cannot be found, the durations will be output in a separate file named `all.csv` in `sound_dir`, as a failsafe. Multiple stimuli files must be separated by `:`. Wildcards and recursive wildcards are allowed, and results will be sorted alphanumerically. If multiple transcription files are specified, but only one stimuli file is specified, it will be assumed that the same stimuli file should hold the output for all transcription files. If specifying multiple stimuli files, you must specify a number of stimuli files equal to the number of transcription files, in the same order as each's corresponding transcription file.

- `-t` or `--transcription`: optional. The name of the column with the transcriptions in `transcription_file`. Default is `transcription`.

- `-i` or `--item`: optional. The name of the column with the item numbers in `transcription_file`. Default is `Item`.

- `-m` or `--max_words`: optional. The maximum number of words to allow for in the sentences you are processing. The default is `20`.

- `-p` or `--port`: optional, Windows only. The port to use for gentle on Windows. Default is `8765`. This argument is not used on Mac, since (as far as I can tell) this cannot be changed with gentle standalone on Mac.

- `-d` or `--docker_location`: optional, Windows only. The location of `Docker Desktop.exe`. The default location is the default installation location for Docker: `%ProgramFiles%/Docker/Docker/Docker Desktop.exe`. You should include the name of the executable file if modifying this. Not used on Mac, as the script assumes you are using the standalone version of gentle available for Mac.

- `-w` or `--wait`: optional, Windows only. How long to wait for Docker Desktop to launch in seconds before attempting to launch gentle. Docker Desktop can take a long time to start up on Windows, so it's necessary to wait a while before trying to start gentle. The default is `75` (seconds), which works great for my computer. If you get errors that involve docker not being able to find the file, you should increase this. If Docker launches quicker on your computer, you could set a lower value to save time. Not used on Mac, since standalone gentle seems to launch fast.

### Note 

If running on Windows, `align.py` will work best if run from an administrator command prompt. If you are not running from an administrator command prompt, there will be minor inconveniences:

1. The `com.docker.service` process must be running before you run `align.py`.
2. You must exit Docker Desktop manually after the `align.py` finishes.

If you are running `align.py` from an administrator command prompt, these will be handled automatically. If you are not running from an administrator command prompt, you will be prompted for admin privileges.

## Output:

1. Word duration information for each aligned word (added to the transcription file/stimuli file)
2. A folder named `gentle_align` in `sound_dir` with the JSON files output by gentle.
3. A `_praat.TextGrid` file for each aligned sentence (saved in `sound_dir`).

### Notes

You should not have gentle running before you run the script; it will be opened for you (on Windows and Mac). Gentle will be closed after it's finished aligning everything. On Mac, gentle must be installed in your Applications folder, and must have been launched previously at least once (in order to bypass the warning message about non-App Store apps). On Windows, you should not have Docker running; it will launch it for you (which can take a while), and close it after gentle has been closed.

# `convert_trim.py`

This script converts `.webm` files to `.mp3` files to facilitate aligning them with gentle. It will also trim them by a preset amount. If you want to use this script personally, you will probably need to modify it for your purposes, since the trim amounts and the criteria for which items to trim are specific for our purposes.

## Requirements

`pydub`

## Usage

From a command prompt/terminal, run:

`python convert_trim.py [directories] [-dd] [-co]`

- `directories`: optional. The relative path(s) to the directories containing the sound files to convert and trim. `convert_trim.py` will also unzip any zip archives in these directories, in case your sound files are archived there. The default is the directory containing `convert_trim.py`. Unix-style wildcards (`*`, `**`) are supported.

- `-dd` or `--dont_delete`: don't delete the original `.webm` or `.zip` files.

- `-co` or `--convert_only`: don't trim the `.webm` files, just convert them.

## Output

Versions of the `.webm` files converted to `.mp3`. If trimmed, the files will be named `[item_number]_trimmed.mp3`; otherwise, they will have the original file name but be in `.mp3` format.
