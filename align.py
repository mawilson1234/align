# align.py by Michael Wilson
# Based on transcription_extraction.py, gentle_align.sh, and gentle2r.py by Shota Momma
# Last update 12/13/2022
import os
import re
import sys
import json
import time
import glob
import shutil
import ctypes
import logging
import requests
import argparse
import traceback
import subprocess

import pandas as pd

from tqdm import tqdm
from typing import *

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

parser = argparse.ArgumentParser()
parser.add_argument(
	'transcription_files',
	help=(
		"Required argument to provide the path(s) to the CSV file(s) "
		"containing the transcriptions. Separate files must be separated by ':'."
	)
)
parser.add_argument(
	'sound_dirs', nargs='?', default='',
	help=(
		"Optional argument to provide the directories containing the mp3s. "
		"Default are the directories containing the files with the transcriptions. "
		"Multiple directories must be separated by ':'."
	)
)
parser.add_argument(
	'stimuli_files', nargs='?', default='',
	help=(
		"Optional argument to provide files containing stimuli information to join with the durations. "
		"The default are the files containing the transcription information. Note that if these files "
		"are different, item numbers must match; if they don't, the durations will be output in a separate "
		"file named 'all.csv'. Multiple files must be separated by ':'."
	)
)
parser.add_argument(
	'-t', '--transcription', nargs='?', default='transcription', type=str,
	help="Optional argument to provide the name of the column name containing the transcriptions. Default is 'transcription'."
)
parser.add_argument(
	'-i', '--item', nargs='?', default='Item', type=str,
	help="Optional argument to provide the name of the column name containing the item numbers. Default is 'Item'."
)
parser.add_argument(
	'-m', '--max_words', default=20, type=int,
	help='Optional argument to specify the maximum number of words in a sentence. Default is 20.'
)
parser.add_argument(
	'-p', '--port', default=8765, type=int,
	help="Optional argument to specify the port used for gentle. Default is 8765. This cannot be changed on a Mac currently. (You probably don't need to mess with this.)"
)
parser.add_argument(
	'-d', '--docker_location', default='"%ProgramFiles%/Docker/Docker/Docker Desktop.exe"', type=str,
	help=(
		'Optional argument to specify where Docker Desktop.exe is located if running on Windows. '
		'The default assumes it is in "%ProgramFiles%/Docker/Docker/Docker Desktop.exe". This '
		'argument is not used on Mac.'
	)
)
parser.add_argument(
	'-w', '--wait', default=75, type=int,
	help=(
		'Optional argument for how long to wait after starting Docker Desktop to open gentle. '
		'Default is 75 seconds. Not used on Mac.'
	)
)

class GentleListener():
	'''Handles opening and closing the lowerquality/gentle application.'''
	def __init__(self, port: int = 8765, docker_location: str = '', wait: int = 75):
		self.port = port
		self.docker_location = docker_location
		self.wait = wait
	
	def __enter__(self):
		'''Start the gentle listener (os.name == 'nt' is for Windows, else for Mac).'''
		log.info('Starting gentle listener')
		if os.name == 'nt':
			# can only start the docker service with admin privileges
			if is_admin():
				subprocess.call('net start com.docker.service')
				time.sleep(5)
			else:
				log.warning(
					'Cannot start docker service without admin privileges. '
					'You may run into issues if the service is not already '
					'running, or see an admin prompt to start it.'
				)
				if (cont := input('Would you like to open an administrator command prompt and continue? (y/n): ')).lower() == 'y':
					# This addresses an issue when not running using the "python" command but just calling the script
					sys.argv[0] = os.path.split(sys.argv[0])[1]
					ctypes.windll.shell32.ShellExecuteW(None, 'runas', sys.executable, ' '.join(sys.argv), None, 1)
					sys.exit(0)
				else:
					log.info(
						'Attempting to continue without admin privileges. '
						'You may run into permission issues running Docker.'
					)
			
			log.info('Opening Docker Desktop, please be patient...')
			subprocess.Popen(self.docker_location, shell=True)
			time.sleep(self.wait)
			subprocess.Popen(f'docker run -p {self.port}:{self.port} lowerquality/gentle')
		else:
			subprocess.Popen('open -a gentle', shell=True)
			
		# Make sure the listener has had time to start before we call it
		failures = 0
		r = ''
		while not r or not r.ok:
			try:
				r = requests.get(f'http://localhost:{self.port}')
			except requests.exceptions.ConnectionError:
				time.sleep(5)
				failures += 1
				if failures >= 12:
					log.error(
						'Unable to open gentle listener within 1 min. Halting execution. '
						'For Windows users, is the docker service running?'
					)
					# Close docker if on Windows
					if os.name == 'nt':
						if is_admin():
							subprocess.call('powershell net stop com.docker.service')
							time.sleep(5)
							subprocess.call(
								f'taskkill /F /IM "' + 
								re.findall(r'.*\.exe', os.path.split(self.docker_location)[-1])[0] + 
								'"'
							)
							subprocess.call('powershell stop-vm DockerDesktopVM')
						else:
							log.warning(
								'Docker service and VM cannot be terminated without admin '
								'privileges. Make sure to manually exit Docker Desktop via the tray menu.'
							)
					
					sys.exit(1)
	
	def __exit__(self, exc_type, exc_value, tb):
		if exc_type is not None:
			traceback.print_exception(exc_type, exc_value, tb)
		
		log.info('Closing gentle listener')
		'''Closes gentle and/or Docker correctly depending on OS.'''
		if os.name == 'nt':
			subprocess.call('powershell docker rm $(docker stop $(docker ps -a -q --filter ancestor=lowerquality/gentle))')
			time.sleep(5)
			# We have to be an admin to properly shut everything down from the command prompt. 
			# Otherwise, it has to be done from the tray menu.
			if is_admin():
				subprocess.call('powershell net stop com.docker.service')
				time.sleep(5)
				subprocess.call('taskkill /F /IM "' + re.findall(r'.*\.exe', os.path.split(self.docker_location)[-1])[0] + '"')
				subprocess.call('powershell Stop-VM DockerDesktopVM')
			else:
				log.warning(
					'Docker service and VM cannot be terminated without admin '
					'privileges. Make sure to manually exit Docker Desktop via the tray menu.'
				)
		else:
			subprocess.call("osascript -e 'quit app \"gentle\"'", shell=True)

class TempDir():
	'''Creates and closes a tmp dir.'''
	def __init__(self, prefix: str = '', suffix: str = 'tmp'):
		self.prefix = prefix
		self.suffix = suffix
	
	def __enter__(self):
		self.tmp_dir = make_new_dir(prefix=self.prefix, suffix=self.suffix)
		return self.tmp_dir
	
	def __exit__(self, exc_type, exc_value, tb):
		if exc_type is not None:
			traceback.print_exception(exc_type, exc_value, tb)
		
		shutil.rmtree(self.tmp_dir, ignore_errors=True)

def is_admin() -> bool:
	'''
	Checks if the current user is an admin on Windows.
	This is needed to start and close the Docker service.
	From https://raccoon.ninja/en/dev/using-python-to-check-if-the-application-is-running-as-an-administrator/
	'''
	is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
	return is_admin

def sort_human(l: List[str]) -> List[str]:
	'''
	Sort file names with numbers in a human-like way, instead of as strings.
	From https://stackoverflow.com/questions/3426108/how-to-sort-a-list-of-strings-numerically
	
		params:
			l (List[str]): a list of file names that contain non-zero padded numbers to sort
		
		returns:
			the list of file names, sorted in a human-like way
	'''
	convert = lambda text: float(text) if text.isdigit() else text
	alphanum = lambda key: [convert(c) for c in re.split(r'([-+]?[0-9]*)\.?([0-9]*)', key)]
	return sorted(l, key=alphanum)

def sort_flatten(l: List) -> List:
	'''Flattens a nested list of lists.'''
	return sort_human([item for sublist in l for item in sublist])

def parse_arguments() -> 'argparse.NameSpace':
	'''Parses and verifies command line arguments.'''
	# Read in the arguments
	args = parser.parse_args()
	
	# Can't set the port on a Mac
	if os.name != 'nt' and args.port != 8765:
		log.info('Cannot change default port for gentle on Mac. Setting port to 8765.')
		args.port = '8765'
	
	# No use for docker location argument on Mac
	if os.name != 'nt' and args.docker_location != '"%ProgramFiles%/Docker/Docker/Docker Desktop.exe"':
		log.info('--docker_location is not used on Mac.')
	
	# Add the exe extension to docker location if needed
	if os.name == 'nt' and (
		not re.findall(r'.*\.exe', os.path.split(args.docker_location)[-1]) or 
		not re.findall(r'.*\.exe', os.path.split(args.docker_location)[-1])[0][-4:] == '.exe'
	):
		args.docker_location += '.exe'
	
	# Get the list of transcription files
	args.transcription_files = args.transcription_files.split(':')
	
	# Use glob to allow for wildcards, and get back a flattened sorted list
	args.transcription_files = sort_human([
		f for l in [
			glob.glob(transcription_file, recursive=True) 
			for transcription_file in args.transcription_files
		] for f in l if f.endswith('.csv')
	])
	
	# Check that we found at least one transcription file
	if not args.transcription_files:
		log.error(
			'No transcription file(s) found. If you are '
			'sure you have specified the file name(s) correctly, '
			'please contact the developer to report this as a bug.'
		)
		sys.exit(1)
	
	# Check that the transcription files exist
	for transcription_file in args.transcription_files:
		if not os.path.isfile(transcription_file):
			log.error(f'Unable to find file {transcription_file!r}.')
			sys.exit(1)
	
	# Set the sound directories to the same directories containing the transcription files if not otherwise specified
	if not args.sound_dirs:
		args.sound_dirs = [os.path.dirname(transcription_file) for transcription_file in args.transcription_files]
	else:
		args.sound_dirs = args.sound_dirs.split(':')
	
	# Allow for wildcards
	args.sound_dirs = sort_flatten([glob.glob(sound_dir, recursive=True) for sound_dir in args.sound_dirs])
	
	# Workaround for when we are running from the sound directory
	if not args.sound_dirs:
		args.sound_dirs = [os.path.dirname(os.path.realpath(__file__))]
	
	# If we only get one sound_dir, assume it contains all the sound files for all the transcription files
	if len(args.sound_dirs) == 1 and not len(args.transcription_files) == 1:
		args.sound_dirs = [args.sound_dirs[0] for transcription_file in args.transcription_files]
	# If we get a non-matching number, then we don't know which sound dir corresponds to which transcription file, and we exit.
	elif len(args.sound_dirs) != len(args.transcription_files):
		log.error(
			f'Number of transcription files {len(args.transcription_files)} and '
			f'number of sound directories {len(args.sound_dirs)} do not match. '
			"I don't know which directory corresponds to which transcription file."
		)
		sys.exit(1)
	
	# Check that the sound_dirs exist and have audio files in them
	for sound_dir in args.sound_dirs:
		if not os.path.exists(sound_dir) or len([file for file in os.listdir(sound_dir) if file.endswith('.mp3')]) == 0:
			log.error(
				f'Error: directory {sound_dir!r} not found, '
				f'or it does not contain mp3 files.'
			)
			sys.exit(1)
	
	# Set the stimuli files to the transcription_files unless otherwise specified
	if not args.stimuli_files:
		args.stimuli_files = args.transcription_files
	else:
		args.stimuli_files = args.stimuli_files.split(':')
	
	# Use glob to allow for wildcards, and get back a flattened sorted list
	args.stimuli_files = sort_human([
		f for l in [
			glob.glob(stimuli_file, recursive=True) 
			for stimuli_file in args.stimuli_files
		] for f in l if f.endswith('.csv')
	])
	
	# Check that we've found at least one stimuli file
	if not args.stimuli_files:
		log.error(
			'No stimuli file(s) found. If you are '
			'sure you have specified the file name(s) correctly, '
			'please contact the developer to report this as a bug.'
		)
		sys.exit(1)
	
	# If we only get one stimuli file, assume that it contains all items
	if len(args.stimuli_files) == 1 and not len(args.transcription_files) == 1:
		args.stimuli_files == [args.stimuli_files[0] for transcription_file in args.transcription_files]
	# If we get a non-matching number, then we don't know which stimuli files go with which transcriptions, and we exit.
	elif len(args.stimuli_files) != len(args.transcription_files):
		log.error(
			f'Number of transcription files ({len(args.transcription_files)}) and '
			f'number of stimuli files ({len(args.stimuli_files)}) do not match. '
			"I don't know which stimuli file corrseponds to which transcription file."
		)
		sys.exit(1)
	
	# Check that the stimuli files exist
	for stimuli_file in args.stimuli_files:
		if not os.path.isfile(stimuli_file):
			log.error(f'File {stimuli_file!r} not found.')	
			sys.exit(1)
	
	if not os.name == 'nt' and not args.wait == 75:
		log.info('--wait argument is not used on Mac.')
	
	return args

def make_new_dir(prefix: str = '', suffix: str = 'tmp') -> str:
	'''Make a directory that won't overwrite an existing directory.'''
	tmp_dir = f'{prefix}{suffix}'
	counter = 1
	while os.path.exists(tmp_dir):
		tmp_dir = f'{prefix}{suffix}{counter}'
		counter += 1
	
	os.makedirs(tmp_dir)
	
	return tmp_dir

def save_transcriptions_to_text(
	transcription_file: str, 
	item_col: str, 
	transcription_col: str, 
	output_dir: str
) -> None:
	'''Saves transcriptions in a csv to text files to send to gentle.'''
	# write the transcriptions out in text files
	transcription_data = pd.read_csv(transcription_file)
	transcription_data = transcription_data.sort_values(by=[item_col], ascending=True)
	
	# For each row, save the transcription for that row in a file with the name being the item number
	transcriptions = dict(zip(transcription_data[item_col], transcription_data[transcription_col]))
	for item, transcription in transcriptions.items():
		with open(os.path.join(output_dir, f'{item}.txt'), 'wt') as file:
			file.write(re.sub(u'\u201d', "'", transcription))

def get_mp3_to_text_mapping(
	sound_dir: str, 
	text_dir: str, 
	transcription_file: str = ''
) -> Dict[str,str]:
	'''Gets the mapping between mp3 audio files and text files to send to gentle.'''
	# Read in and sort the audio file names and text file names
	audio_names = sort_human([file for file in os.listdir(sound_dir) if file.endswith('.mp3')])
	text_names  = sort_human([file for file in os.listdir(text_dir) if file.endswith('.txt')])
	
	if len(audio_names) != len(text_names):
		raise ValueError(
			f'Number of audio files ({len(audio_names)}) and '
			f'number of transcriptions ({len(text_names)}) do not match for '
			f'directory {sound_dir!r} and transcription file {transcription_file!r}.'
		)
	
	# Check that audio files begin with the item numbers from the transcription file
	audio_num = [re.findall('^[0-9]*', audio_name)[0].lstrip('0') for audio_name in audio_names]
	text_num  = [re.findall('^[0-9]*', text_name)[0].lstrip('0') for text_name in text_names]
	if audio_num != text_num:
		raise ValueError(f'Audio file numbers do not match item numbers in transcription file {transcription_file!r}.')
	
	audio_text = dict(zip(audio_names, text_names))
	
	return audio_text

def save_alignments(
	sound_dir: str, 
	text_dir: str, 
	transcription_file: str, 
	gentle_url: str, 
	gentle_params: Dict
) -> str:
	'''
	Uses gentle to get alignments between text and sound files. Saves results to disk.
	Returns the name of the directory where results are saved.
	'''
	audio_text = get_mp3_to_text_mapping(sound_dir=sound_dir, text_dir=text_dir, transcription_file=transcription_file)
	align_dir  = make_new_dir(prefix=os.path.join(sound_dir, 'gentle_align'), suffix='')
	for audio, text in audio_text.items():
		audio_file = os.path.join(sound_dir, audio)
		text_file  = os.path.join(text_dir, text)
		
		with open(audio_file, 'rb') as audio_mp3, open(text_file, 'rb') as text_txt:
			files = {
				'audio': (audio_file, audio_mp3, 'audio/mpeg'), 
				'transcript': (text_file, text_txt, 'text/plain')
			}
			
			# this gets the alignment data from gentle
			r = requests.post(gentle_url, params=gentle_params, files=files)
		
		with open(os.path.join(align_dir, text.replace('.txt', '.json')), 'wb') as out_file:
			out_file.write(r.content)
	
	return align_dir

def save_json_as_textgrid(
	file: str,
	max_words: int = 20,
	output_dir: str = '.',
	return_pd_series: bool = False,
	pd_colnames: List[str] = None
) -> pd.Series:
	'''
	Saves a json with duration information as a praat TextGrid.
	Optionally returns a pd Series containing duration information for each word.
	'''
	item_number = re.sub(r'\.json$', '', os.path.split(file)[-1])
	dur_row = [item_number]
	word_row = []
	
	# Load the alignment file
	with open(file, 'rt') as in_file:
		words = json.load(in_file)['words']
	
	# Remove entries without alignments
	words = [word for word in words if 'alignedWord' in word]
	
	# If gentle couldn't find any words, skip this one
	if not words:
		input(
			f'gentle found no words in {grid!r}. '
			'No durations will be saved for this item, '
			'and the TextGrid file will be empty. Press any key to continue.'
		)
		return
	
	textgrid_file = os.path.join(output_dir, f'{item_number}_praat.TextGrid')
	with open(textgrid_file, 'wt') as out_file:
		out_file.write('File type = "ooTextFile short"\n"TextGrid"')
		
		# Get the starting and end position of the grid by the beginning of first word and end of last word and write them to the TextGrid
		start = words[0]['startOffset']
		end = words[-1]['end']
		out_file.write(f'\n{start}')
		out_file.write(f'\n{end}')
		
		# Required TextGrid formatting
		out_file.write(f'\n<exists>\n1\n"IntervalTier"\n"word"\n{start}\n{end}')
		out_file.write(f'\n{len(words) + 1}\n')
		
		# For each word with alignment info
		for i, alignment in enumerate(words):
			# Get the word and its starting and ending position
			word = alignment['alignedWord']
			onset = alignment['start']
			offset = alignment['end']
			
			# If it's the first word, write silence before its onset
			if i == 0:
				out_file.write(f'0\n{onset}\n"{{SL}}"')
				diff = round(float(onset), 4) * 1000
				dur_row.append(diff)
				word_row.append('SOL')
			
			# Get the duration of the word
			# Starting point of the word
			pre = round(float(onset), 4) * 1000
			
			# If it's the last word, then the ending time is the end of that word
			if alignment == words[-1]:
				post = round(float(offset), 4) * 1000
			# Otherwise, the ending time is the starting point of the next word
			else:
				post = round(float(words[i+1]['start']), 4) * 1000
			
			# Duration is the difference between ending and starting time
			diff = post - pre
			dur_row.append(diff)
			
			# Add the word with that duration to the word row
			word_row.append(word)
			
			# Write its onset, offset, and text to the TextGrid
			out_file.write(f'\n{onset}')
			out_file.write(f'\n{offset}')
			out_file.write(f'\n"{word}"')
	
	if return_pd_series:
		# Fill out the durations row with zeros (have to add one because of the item number column)
		while len(dur_row) < max_words + 1:
			dur_row.append(0)
			
		# truncate if too long
		if len(dur_row) > max_words + 1:
			log.warning(
				f'The current sentence is longer ({len(dur_row)}) than the allowable maximum words ({max_words}). '
				'Duration data will be truncated. It is recommended that you rerun from scratch and set --max-words '
				'to a larger number.'
			)
			dur_row = dur_row[:max_words+1]
		
		# Fill out the words row with dashes (don't add one because there's no item number column)
		while len(word_row) < max_words:
			word_row.append('-')
			
		# truncate words past the max
		if len(word_row) > max_words:
			word_row = word_row[:max_words]
		
		# Add the words to the end of the durations
		row = dur_row + word_row
		
		# Add the row to the data frame
		row = pd.Series(row, index=pd_colnames if pd_colnames is not None else list(range(len(row))))
		
		return row

def save_durations(
	durations: pd.DataFrame,
	stimuli_file: str,
	item_col: str,
	transcription_file: str,
	output_dir: str
) -> None:
	'''
	Add information from the stimuli file to the durations.
	Saves results to the stimuli file name if the item numbers match;
	otherwise, saves just the durations to a file.
	'''
	try:
		stimuli = pd.read_csv(stimuli_file)
		stimuli = stimuli.drop(list(stimuli.filter(regex='R[0-9]*').columns), axis=1)
		stimuli[item_col] = pd.to_numeric(stimuli[item_col])
		durations[item_col] = pd.to_numeric(durations[item_col])
		if not all(stimuli[item_col] == durations[item_col]):
			raise ValueError
		
		stim_dur = pd.merge(stimuli, durations)
		stim_dur.to_csv(stimuli_file, index=False)
	except (FileNotFoundError, ValueError):
		log.warning(
			'Unable to find stimulus file, or else item numbers do '
			'not match in stimulus file and transcription file for '
			f'transcription file {transcription_file!r}. '
			'Outputting duration information in separate CSV.'
		)
		
		counter = 0
		all_csv = os.path.join(output_dir, 'all.csv')
		# Make sure that if we are using the same sound directory with multiple transcription files that we don't overwrite the duration output from a previous file
		while os.path.isfile(all_csv):
			counter += 1
			all_csv = os.path.join(output_dir, f'all{counter}.csv')
		
		durations.to_csv(all_csv, index=False)

def align_text_to_audio() -> None:
	'''
	Main function. Handles aligning text to audio
	and writing out results.
	'''
	args = parse_arguments()
	url = f'http://localhost:{args.port}/transcriptions'
	params = {'async' : 'false'}
	
	with GentleListener(port=args.port, docker_location=args.docker_location, wait=args.wait):
		for transcription_file, sound_dir, stimuli_file in tqdm(
			zip(args.transcription_files, args.sound_dirs, args.stimuli_files), 
			total=len(args.transcription_files)
		):
			with TempDir(prefix=os.path.join(sound_dir, 'transcription_')) as text_dir:
				save_transcriptions_to_text(
					transcription_file=transcription_file, 
					item_col=args.item, 
					transcription_col=args.transcription, 
					output_dir=text_dir
				)
				
				align_dir = save_alignments(
					sound_dir=sound_dir, 
					text_dir=text_dir, 
					transcription_file=transcription_file, 
					gentle_url=url, 
					gentle_params=params
				)
			
			# Get the list of json files with the gentle alignment info
			grids = sort_human([file for file in os.listdir(align_dir) if file.endswith('.json')])
			grids = [os.path.join(align_dir, grid) for grid in grids]
			
			# Set up a dataframe to hold the timing info
			durations = pd.DataFrame(
				columns = [args.item] + 
					[f'R{num:0{len(str(args.max_words))}d}' for num in range(args.max_words)] + 
					[f'W{num:0{len(str(args.max_words))}d}' for num in range(args.max_words)]
			)
			
			for grid in grids:
				row = save_json_as_textgrid(
					file=grid, 
					max_words=args.max_words, 
					output_dir=sound_dir, 
					return_pd_series=True,
					pd_colnames=durations.columns,
				)
				durations = durations.append(row, ignore_index=True)
			
			save_durations(
				durations=durations, 
				stimuli_file=stimuli_file, 
				item_col=args.item, 
				transcription_file=transcription_file, 
				output_dir=sound_dir
			)

if __name__ == '__main__':
	align_text_to_audio()
