# align.py by Michael Wilson
# Based on transcription_extraction.py, gentle_align.sh, and gentle2r.py by Shota Momma
# Last update 12/08/2020
import requests, argparse, os, re, subprocess, json, pandas, time, sys, shutil, ctypes, glob

# Define a function to determine if the current user is an admin on Windows (this is necessary on Windows to start the docker service and close out the docker VM correctly)
# From https://raccoon.ninja/en/dev/using-python-to-check-if-the-application-is-running-as-an-administrator/
def is_admin():
	is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
	return is_admin

# Define a function to sort the file names correctly based on number
# From https://stackoverflow.com/questions/3426108/how-to-sort-a-list-of-strings-numerically
def sort_human(l):
	convert = lambda text: float(text) if text.isdigit() else text
	alphanum = lambda key: [convert(c) for c in re.split('([-+]?[0-9]*)\.?([0-9]*)', key)]
	l.sort(key = alphanum)
	return l

def sort_flatten(l):
	return sort_human([item for sublist in l for item in sublist])

# Define a function to read in a csv in either the default encoding or latin1
def my_read_csv(csv):
	try:
		data = pandas.read_csv(csv)
	except:
		try: 
			data = pandas.read_csv(csv, encoding = 'latin1')
		except:
			print('Error: unable to read "' + csv + '". Exiting.')
			sys.exit(1)

	return data

# Function to close gentle/docker depending on os
def close_gentle():
	if os.name == 'nt':
		subprocess.call('powershell docker rm $(docker stop $(docker ps -a -q --filter ancestor=lowerquality/gentle))')
		time.sleep(5)
		# We have to be an admin to properly shut everything down from the command prompt. Otherwise, it has to be done from the tray menu
		if is_admin():
			subprocess.call('powershell net stop com.docker.service')
			time.sleep(5)
			subprocess.call('taskkill /F /IM "' + re.findall(r'.*\.exe', os.path.split(args.docker_location)[-1])[0] + '"')
			subprocess.call('powershell stop-vm DockerDesktopVM')
		else:
			print('Warning: Docker service and VM cannot be terminated without admin privileges. Make sure to manually exit Docker Desktop via the tray menu.')
	else:
		subprocess.call("osascript -e 'quit app \"gentle\"'", shell = True)

parser = argparse.ArgumentParser()
parser.add_argument('transcription_files',
	help = "Required argument to provide the path(s) to the CSV file(s) containing the transcriptions. Separate files must be separated by ':'.")
parser.add_argument('sound_dirs', nargs = '?', default = '',
	help = "Optional argument to provide the directories containing the mp3s. Default are the directories containing the files with the transcriptions. Multiple directories must be separated by ':'.")
parser.add_argument('stimuli_files', nargs = '?', default = '',
	help = "Optional argument to provide files containing stimuli information to join with the durations. The default are the files containing the transcription information. Note that if these files are different, item numbers must match; if they don't, the durations will be output in a separate file named 'all.csv'. Multiple files must be separated by ':'.")
parser.add_argument('-t', '--transcription', nargs = '?', default = 'transcription', type = str,
	help = "Optional argument to provide the name of the column name containing the transcriptions. Default is 'transcription'.")
parser.add_argument('-i', '--item', nargs = '?', default = 'Item', type = str,
	help = "Optional argument to provide the name of the column name containing the item numbers. Default is 'Item'.")
parser.add_argument('-m', '--max_words', default = 20, type = int,
	help = 'Optional argument to specify the maximum number of words in a sentence. Default is 20.')
parser.add_argument('-p', '--port', default = 8765, type = int,
	help = "Optional argument to specify the port used for gentle. Default is 8765. This cannot be changed on a Mac currently. (You probably don't need to mess with this.)")
parser.add_argument('-d', '--docker_location', default = '"%ProgramFiles%/Docker/Docker/Docker Desktop.exe"', type = str,
	help = 'Optional argument to specify where Docker Desktop.exe is located if running on Windows. The default assumes it is in "%ProgramFiles%/Docker/Docker/Docker Desktop.exe". This argument is not used on Mac.')
parser.add_argument('-w', '--wait', default = 75, type = int,
	help = 'Optional argument for how long to wait after starting Docker Desktop to open gentle. Default is 75 seconds. Not used on Mac.')

# Read in the arguments
args = parser.parse_args()
saved_args = args

# Convert port to a string
args.port = str(args.port)

# Can't set the port on a Mac
if not os.name == 'nt' and not args.port == '8765':
	print('Cannot change default port for gentle on Mac. Setting port to 8765.')
	args.port = '8765'

# No use for docker location argument on Mac
if not os.name == 'nt' and not args.docker_location == '"%ProgramFiles%/Docker/Docker/Docker Desktop.exe"':
	print('--docker_location is not used on Mac.')

# Add the exe extension to docker location if needed
if not re.findall(r'.*\.exe', os.path.split(args.docker_location)[-1]) or not re.findall(r'.*\.exe', os.path.split(args.docker_location)[-1])[0][-4:] == '.exe':
	args.docker_location += '.exe'

# Get the list of transcription files
args.transcription_files = args.transcription_files.split(':')

# Use glob to allow for wildcards, and get back a flattened sorted list
args.transcription_files = sort_flatten([glob.glob(transcription_file, recursive = True) if transcription_file[-4:] =='.csv' else [item for sublist in [glob.glob(transcription_file, recursive = True)] for item in sublist if item[-4:] =='.csv'] if transcription_file[-2:] == '**' else glob.glob(transcription_file + '.csv', recursive = True) for transcription_file in args.transcription_files])

# Check that we found at least one transcription file
if len(args.transcription_files) == 0:
	print('Error: no transcription file(s) found. If you are sure you have specified the file name(s) correctly, please contact the developer to report this as a bug.')
	sys.exit(1)

# Check that the transcription files exist
for transcription_file in args.transcription_files:
	if not os.path.isfile(transcription_file):
		print('Error: unable to find file "' + transcription_file + '". Halting execution.')
		sys.exit(1)

# Set the sound directories to the same directories containing the transcription files if not otherwise specified
if not args.sound_dirs:
	args.sound_dirs = [os.path.split(transcription_file)[0] for transcription_file in args.transcription_files]
else:
	# Otherwise, figure out the separate sound directories. If we've only specified one, repeat it for each transcription file. If there are multiple specified, the number of specified ones must match the number of transcription files, since otherwise we don't know which sound directory goes with which transcription file.
	args.sound_dirs = args.sound_dirs.split(':')

# Allow for wildcards
args.sound_dirs = sort_flatten([glob.glob(sound_dir, recursive = True) for sound_dir in args.sound_dirs])

# Workaround for when we are running from the sound directory
if len(args.sound_dirs) == 0:
	args.sound_dirs = [os.path.dirname(os.path.realpath(__file__))]

# If we only get one sound_dir, assume it contains all the sound files for all the transcription files
if len(args.sound_dirs) == 1 and not len(args.transcription_files) == 1:
	args.sound_dirs == [args.sound_dirs[0] for transcription_file in args.transcription_files]
# If we get a non-matching number, then we don't know which sound dir corresponds to which transcription file, and we exit.
elif not len(args.sound_dirs) == len(args.transcription_files):
	print(str(len(args.sound_dirs)) + ' ' + str(len(args.transcription_files)))
	print("Error: number of transcription files and sound directories do not match. I don't know which directory corresponds to which transcription file. Halting execution.")
	sys.exit(1)

# Check that the sound_dirs exist and have audio files in them
for sound_dir in args.sound_dirs:
	if not os.path.exists(sound_dir) or len([file for file in os.listdir(sound_dir) if file[-4:] == '.mp3']) == 0:
		print('Error: directory "' + sound_dir + '" not found, or it does not contain mp3 files. Halting execution.')
		sys.exit(1)

# Set the stimuli files to the transcription_files unless otherwise specified
if not args.stimuli_files:
	args.stimuli_files = args.transcription_files
else:
	args.stimuli_files = args.stimuli_files.split(':')

# Use glob to allow for wildcards, and get back a flattened sorted list
args.stimuli_files = sort_flatten([glob.glob(stimuli_file, recursive = True) if stimuli_file[-4:] =='.csv' else [item for sublist in [glob.glob(stimuli_file, recursive = True)] for item in sublist if item[-4:] =='.csv'] if stimuli_file[-2:] == '**' else glob.glob(stimuli_file + '.csv', recursive = True) for stimuli_file in args.stimuli_files])

# Check that we've found at least one stimuli file
if len(args.stimuli_files) == 0:
	print('Error: no stimuli file(s) found. If you are sure you have specified the file name(s) correctly, please contact the developer to report this as a bug.')
	sys.exit(1)

# If we only get one stimuli file, assume that it contains all items
if len(args.stimuli_files) == 1 and not len(args.transcription_files) == 1:
	args.stimuli_files == [args.stimuli_files[0] for transcription_file in args.transcription_files]
# If we get a non-matching number, then we don't know which stimuli files go with which transcriptions, and we exit.
elif not len(args.stimuli_files) == len(args.transcription_files):
	print("Error: number of transcription files and stimuli files do not match. I don't know which stimuli file corrseponds to which transcription file. Halting execution.")
	sys.exit(1)

# Check that the stimuli files exist
for stimuli_file in args.stimuli_files:
	if not os.path.isfile(stimuli_file):
		print('Error: file "' + stimuli_file + '" not found. Halting execution.')
		sys.exit(1)

if not os.name == 'nt' and not args.wait == 75:
	print('--wait argument is not used on Mac.')

# Combine the transcription file, sound dir, and stimuli files into a list of tuples
tf_sd_sf = list(zip(args.transcription_files, args.sound_dirs, args.stimuli_files))

# Start the gentle listener (os.name == 'nt' is for Windows, else for Mac)
if os.name == 'nt':
	# can only start the docker service with admin privileges
	if is_admin():
		subprocess.call('net start com.docker.service')
		time.sleep(5)
	else:
		print('Warning: cannot start docker service without admin privileges. You may run into issues if the service is not already running, or see an admin prompt to start it.')
		if (cont := input('Would you like to open an administrator command prompt and continue? (y/n): ')).lower() == 'y':
			# This addresses an issue when not running using the "python" command but just calling the script
			sys.argv[0] = os.path.split(sys.argv[0])[1]
			ctypes.windll.shell32.ShellExecuteW(None, 'runas', sys.executable, ' '.join(sys.argv), None, 1)
			sys.exit(0)
		else:
			print('Attempting to continue without admin privileges. You may run into permission issues running Docker.')

	print('Opening Docker Desktop, please be patient...')
	subprocess.Popen(args.docker_location, shell = True)
	time.sleep(args.wait)
	subprocess.Popen('docker run -p ' + args.port + ':' + args.port + ' lowerquality/gentle')
else:
	subprocess.Popen('open -a gentle', shell = True)

url = 'http://localhost:' + args.port + '/transcriptions'
params = {'async' : 'false'}

# Make sure the listener has had time to start before we call it
failures = 0
while not 'r' in globals() or not r.ok:
	try:
		r = requests.get('http://localhost:' + args.port)
	except:
		time.sleep(5)
		failures += 1
		if failures >= 12:
			print('Unable to open gentle listener within 1 min. Halting execution. For Windows users, is the docker service running?')
			shutil.rmtree(text_dir, ignore_errors = True)
			# Close docker if on Windows
			if os.name == 'nt':
				if is_admin():
					subprocess.call('powershell net stop com.docker.service')
					time.sleep(5)
					subprocess.call('taskkill /F /IM "' + re.findall(r'.*\.exe', os.path.split(args.docker_location)[-1])[0] + '"')
					subprocess.call('powershell stop-vm DockerDesktopVM')
				else:
					print('Warning: Docker service and VM cannot be terminated without admin privileges. Make sure to manually exit Docker Desktop via the tray menu.')
			sys.exit(1)

# Once gentle is open, for each transcription file, sound directory, and stimuli file...
for transcription_file, sound_dir, stimuli_file in tf_sd_sf:

	# Read in the transcription data and sort by item number
	try:
		transcription_data = my_read_csv(transcription_file)
	except:
		print('Unable to find or read file containing transcriptions. Halting execution.')
		close_gentle()
		sys.exit(1)

	if not args.item in transcription_data:
		print('Unable to find column named "' + args.item + '" in ' + transcription_file + '. Halting execution.')
		close_gentle()
		sys.exit(1)

	if not args.transcription in transcription_data:
		print('Unable to find column named "' + args.transcription + '" in ' + transcription_file + '. Halting execution.')
		close_gentle()
		sys.exit(1)

	transcription_data = transcription_data.sort_values(by = [args.item], ascending = True)

	# Create a place to leave the output, but don't overwrite an existing dir
	text_dir = sound_dir + '/transcription_tmp'
	counter = 1
	while os.path.exists(text_dir):
		text_dir = sound_dir + '/transcription_tmp' + str(counter)
		counter += 1	

	os.makedirs(text_dir)

	# For each row, save the transcription for that row in a file with the name being the item number
	transcriptions = [{str(it) : tr} for it, tr in zip(transcription_data[args.item], transcription_data[args.transcription])]
	for transcription in transcriptions:
		for it in transcription:
			with open(text_dir + '/' + it + '.txt', 'w') as file:
				file.write(re.sub(u'\u201d', "'", str(transcription[it])))

	# Read in and sort the audio file names and text file names
	audio_names = [file for file in os.listdir(sound_dir) if file[-4:] == ".mp3"]
	sort_human(audio_names)

	text_names = [file for file in os.listdir(text_dir) if file[-4:] == ".txt"]
	sort_human(text_names)

	# Pair them in a dictionary
	if not len(audio_names) == len(text_names):
		print('Error: number of audio files and number of transcriptions do not match for directory "' + sound_dir + '" and transcription file "' + transcription_file + '". Halting execution.')
		shutil.rmtree(text_dir, ignore_errors = True)
		close_gentle()
		sys.exit(1)

	# Check that audio files begin with the item numbers from the transcription file
	audio_num = [re.findall('^[0-9]*', audio_name)[0].lstrip('0') for audio_name in audio_names]
	text_num = [re.findall('^[0-9]*', text_name)[0].lstrip('0') for text_name in text_names]
	if not audio_num == text_num:
		print('Error: audio file numbers do not match item numbers in transcription file. Halting execution.')
		shutil.rmtree(text_dir, ignore_errors = True)
		close_gentle()
		sys.exit(1)

	audio_text = {audio_names[i] : text_names[i] for i in range(len(audio_names))}

	# Define the directory to output the alignment file and create it if it doesn't exist
	align_dir = sound_dir + '/gentle_align'

	counter = 1
	while os.path.exists(align_dir):
		align_dir = sound_dir + '/gentle_align' + str(counter)
		counter += 1

	os.makedirs(align_dir)

	# Align each audio file with its text file
	for audio, text in audio_text.items():

		# Define the arguments to pass to the gentle listener
		audio_file = sound_dir + '/' + audio
		text_file = text_dir + '/' + text

		with open(audio_file, 'rb') as audio_mp3, open(text_file, 'rb') as text_txt:
			files = {'audio':(audio_file, audio_mp3, 'audio/mpeg'), 'transcript':(text_file, text_txt, 'text/plain')}

			# Get the alignment file and write it out
			print('Aligning item ' + text[:-4] + ' from ' + transcription_file + '...')
			r = requests.post(url, params = params, files = files)
		
		with open(align_dir + '/' + text[:-4] + '.json', 'wb') as file:
			file.write(r.content)

	# Delete the temporary transcription files
	shutil.rmtree(text_dir, ignore_errors = True)

	# Get the list of json files with the gentle alignment info
	grids = sort_human([file for file in os.listdir(align_dir) if file[-5:] == '.json'])
	grids = [align_dir + '/' + grid for grid in grids]

	# Set up a dataframe to hold the timing info
	durations = pandas.DataFrame(columns = [args.item] + 
		['R' + num for num in list(map(str, list(range(0, args.max_words))))] + 
		['W' + num for num in list(map(str, list(range(0, args.max_words))))])

	# For each alignment file
	for grid in grids:

		# Get the item number from the json file name
		item_number = os.path.split(grid)[-1][:-5]

		# Set up a row for the durations for that file in the data frame
		dur_row = [item_number]

		# Set up a row for the words for that file in the data frame
		word_row = []

		# Define a corresponding textgrid_file and open it + write the preamble
		textgrid_file = sound_dir + '/' + item_number + '_praat.TextGrid'
		with open(textgrid_file, 'w') as f:
			f.write('File type = "ooTextFile short"\n"TextGrid"')

			# Load the alignment file
			words = json.load(open(grid, 'r'))['words']

			# Remove entries without alignments
			words = [word for word in words if 'alignedWord' in word]

			# If gentle couldn't find any words, skip this one
			if not words:
				input('Warning: gentle found no words in "' + grid + '". No durations will be saved for this item, and the textgrid file will be empty. Press any key to continue.')
			else:
				# Get the starting and end position of the grid by the beginning of first word and end of last word and write them to the TextGrid
				start = words[0]['startOffset']
				end = words[-1]['end']
				f.write('\n' + str(start))
				f.write('\n' + str(end))

				# Required TextGrid formatting
				f.write('\n<exists>\n1\n"IntervalTier"\n"word"\n' + str(start) + '\n' + str(end))
				f.write('\n' + str(len(words) + 1) + '\n')

				# For each word with alignment info
				for i, alignment in enumerate(words):

					# Get the word and its starting and ending position
					word = alignment['alignedWord']
					onset = alignment['start']
					offset = alignment['end']

					# If it's the first word, write silence before its onset
					if alignment == words[0]:
						f.write('0\n' + str(onset) + '\n"{SL}"')

						# The start point of first word is speech onset latency
						diff = round(float(onset), 4) * 1000

						# Add it to the row
						dur_row.append(diff)

						# Add a pre-speech marker to the words (Speech Onset Latency)
						word_row.append('SOL')

					# Get the duration of the word
					# Starting point of the word
					pre = round(float(onset), 4) * 1000

					# If it's the last word, then the ending time is the end of that word
					if alignment == words[-1]:
						post = round(float(offset), 4) * 1000
					# Otherwise, the ending time is the starting point of the next word
					else:
						post = round(float(words[i + 1]['start']), 4) * 1000
					
					# Duration is the difference between ending and starting time
					diff = post - pre
					dur_row.append(diff)

					# Add the word with that duration to the word row
					word_row.append(word)

					# Write its onset, offset, and text to the TextGrid
					f.write('\n' + str(onset))
					f.write('\n' + str(offset))
					f.write('\n"' + word + '"')

		# Fill out the durations row with zeros (have to add one because of the item number column)
		while len(dur_row) < args.max_words + 1:
			dur_row.append(0)

		# Fill out the words row with dashes (don't add one becaus there's no item number column)
		while len(word_row) < args.max_words:
			word_row.append('-')

		# Add the words to the end of the durations
		row = dur_row + word_row

		# Add the row to the data frame
		row = pandas.Series(row, index = durations.columns)
		durations = durations.append(row, ignore_index = True)

	# Combine durations with a stimulus file that has matching item numbers
	print('Writing out durations for ' + transcription_file + '...')
	try:
		stimuli = my_read_csv(stimuli_file)
		stimuli = stimuli.drop(list(stimuli.filter(regex = 'R[0-9]*').columns), axis = 1)
		stimuli[args.item] = pandas.to_numeric(stimuli[args.item])
		durations[args.item] = pandas.to_numeric(durations[args.item])
		if not all(stimuli[args.item] == durations[args.item]):
			raise Exception

		stim_dur = pandas.merge(stimuli, durations)
		stim_dur.to_csv(stimuli_file, index = False)
	except:
		print('Unable to find stimulus file, or else item numbers do not match in stimulus file and transcription file for transcription file "' + transcription_file + '". Outputting duration information in separate CSV.')
		counter = 0
		all_csv = sound_dir + '/all.csv'
		# Make sure that if we are using the same sound directory with multiple transcription files that we don't overwrite the duration output from a previous file
		while os.path.isfile(all_csv):
			counter += 1
			all_csv = sound_dir + '/all' + str(counter) + '.csv'

		durations.to_csv(all_csv, index = False)

close_gentle()