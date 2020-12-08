import glob
import re
import argparse
import os
import zipfile
import sys
import pandas as pd
import requests
from pydub import AudioSegment

parser = argparse.ArgumentParser()
parser.add_argument('directories', nargs = '?', default = os.path.dirname(os.path.realpath(__file__)),
	help = 'Optional argument to specify the directory containing the webm files.')
#parser.add_argument('--experiencer_only', '-e', default = False, action = 'store_true',
#	help = 'Optional argument to avoid converting and just delete the control/raising files.')
#parser.add_argument('--controlraising_only', '-cr', default = False, action = 'store_true',
#	help = 'Optional argument to avoid converting and just delete the experiencer/garden-path files.')
parser.add_argument('--dont_delete', '-dd', default = False, action = 'store_true',
	help = 'Optional argument to save all files.')
parser.add_argument('--convert_only', '-co', default = False, action = 'store_true',
	help = 'Optional argument to convert to mp3 only (and not trim).')
parser.add_argument('--no_groups', '-ng', default = False, action = 'store_true',
	help = 'Optional argument to not automatically get groups. Getting groups has only been tested for experiencer and garden-path items.')
#parser.add_argument('--auto_transcribe', '-at', default = False, action = 'store_true',
#	help = 'Optional argument to auto_transcribe the files we\'re converting.')
#parser.add_argument('--groups_list', '-g', default = '',
#	help = 'Optional argument containing a list of groups to use to generate transcription templates (if you are not getting them automatically from the zip files).')

args = parser.parse_args()

# Figure out the sound directories
#if args.auto_transcribe:
#	auto_transcribe_directories = args.directories

args.directories = args.directories.split(':')

# Allow for wildcards
args.directories = [item for sublist in [glob.glob(directory) for directory in args.directories] for item in sublist]

# Unzip the zip files if any exist, and use their filenames to get the groups
zipfiles = [item for sublist in [[f'{directory}/{file}' for file in os.listdir(directory) if file.endswith('.zip')] for directory in args.directories] for item in sublist]
if zipfiles:
	for file in zipfiles:
		with zipfile.ZipFile(file, 'r') as f:
			print(f'\rExtracting {file}...', end = '', flush = True)
			f.extractall(os.path.split(file)[0])

		if not args.dont_delete:
			os.remove(file)

	print('\n', end = '')
	#if args.auto_transcribe:
	subject_ids = [os.path.split(file)[1] for file in zipfiles]

	try:
		# Get the newest results file
		print('Downloading the latest results file...')
		s = requests.Session()
		pcibex_url = 'https://expt.pcibex.net'
		with open('pw.txt', 'r') as f:
			params = f.readlines()

		s.get(f'{pcibex_url}/login')
		s.post(f'{pcibex_url}/login', data = {'username' : params[0][:-1], 'password' : params[1][:-1]})
		results = s.get(f'{pcibex_url}/ajax/download/{params[2]}/results/results')

		with open('results.txt', 'wb') as file:
			file.write(results.content)
	except:
		print('Unable to download latest results file. Groups will not be automatically determined if there are subjects not in the local version of the results file.')

	if not args.no_groups:
		# Load the results file
		try:
			results = pd.read_csv('results.txt', comment = '#',
				names = ['time_rec', 'IP', 'controller', 'item_id', 'element', 'type', 'sub_experiment', 
						 'element_type', 'element_name', 'parameter', 'value', 'event_time', 'category', 
						 'group', 'item', 'sentence_type', 'relatedness', 'sentence', 'martrix_verb', 
						 'prob1', 'prob2', 'prob3', 'prob4', 'wait1', 'wait2', 'wait3', 'wait4', 'comments'])
				
			# We have to use a for loop in case the results are not in the order of the subject identifiers
			subject_ips = []
			for subject_id in subject_ids:
				subject_ips.append(results.loc[results.value == subject_id].IP.tolist()[0])
				
			if len(subject_ids) == len(subject_ips):
				exp_groups = [results.loc[results.IP == subject_ip].loc[results.category == 'Experiencer'].iloc[1,:].group for subject_ip in subject_ips]
				gp_groups = [results.loc[results.IP == subject_ip].loc[results.category == 'Garden-Path'].iloc[1,:].group for subject_ip in subject_ips]
				args.groups_list = ':'.join([','.join([exp, gp]) for (exp, gp) in list(zip(exp_groups, gp_groups))])
			else:
				print('Warning: number of zipfiles and subjects do not match. Groups will not be determined.')
				args.groups_list = ''
		except:
			print('Unable to load latest results file. Groups will not be determined.')
			args.groups_list = ''
		
files = [item for sublist in [[f'{directory}/{file}' for file in os.listdir(directory) if file.endswith('.webm')] for directory in args.directories] for item in sublist]

#if args.experiencer_only:
#	unneeded = [file for file in files if re.search('([1-6][0-9]])|(7[0-4])', os.path.split(file)[1])]
#	files = [file for file in files if not file in unneeded]
#
#	# Get rid of the unneeded groups so we don't create an unnecessary csv
#	groups = [groups.split(',') for groups in args.groups_list.split(':')]
#	args.groups_list = ':'.join([','.join(subj_groups[:-1] + ['']) if len(subj_groups) == 3 else ','.join(subj_groups) for subj_groups in groups])
#
#	if not args.dont_delete:
#		for file in unneeded:
#			success = False
#			while not success:
#				try:
#					os.remove(file)
#					success = True
#				except:
#					pass

#if args.controlraising_only:
#	unneeded = [file for file in files if re.search(r'(^[1-9]{1}\.)|([1-3][0-9])|(4[0-8])', os.path.split(file)[1])]
#	files = [file for file in files if not file in unneeded]
#
#	# Get rid of the unneeded groups so we don't create an unneccesary csv
#	groups = [groups.split(',') for groups in args.groups_list.split(':')]
#	args.groups_list = ':'.join([','.join(['', '', subj_groups[-1]]) if len(subj_groups) == 3 else subj_groups for subj_groups in groups])
#	
#	if not args.dont_delete:
#		for file in unneeded:
#			success = False
#			while not success:
#				try:
#					os.remove(file)
#					success = True
#				except:
#					pass

if not files:
	print('No files found to convert. Exiting...')
	sys.exit(1)

for f in files:
	print(f'\rConverting and trimming {f}...', end = '', flush = True)

	# Read in the sound file
	sound = AudioSegment.from_file(f)

	# Trim if we're doing that
	if not args.convert_only:

		# Find the stimulus number
		num = int(re.search(r'^[1-9][0-9]?', os.path.split(f)[1]).group())
		
		# Only trim if the sound is long enough
		if len(sound) > 10000:

			# Experiencer items
			if num < 33:
				# If item number is 1, 4, 7, etc. then there are two nonce words (+100 ms buffer)
				if num % 3 == 1:
					sound = sound[4100:]

				# If item number is 2, 5, 8, etc. then there are three nonce words (+50 ms buffer)
				if num % 3 == 2:
					sound = sound[6050:]

				# If item number is 3, 6, 9, etc. then there are four nonce words (no buffer)
				if num % 3 == 0:
					sound = sound[8000:]
			else:
				if num % 3 == 0:
					sound = sound[4100:]

				if num % 3 == 1:
					sound = sound[6050:]

				if num % 3 == 2:
					sound = sound[8000:]

			directory = f'{os.path.split(f)[0]}/'

		# Export the trimmed sound
		sound.export(directory + str(num) + "_trimmed.mp3", format = 'mp3')
	# Otherwise, just convert the audio
	else:
		sound.export(directory + '/' + os.path.splitext(os.path.basename(f))[0] + '.mp3', format = 'mp3')

	if not args.dont_delete:
		success = False
		while not success:
			try:
				os.remove(f)
				success = True
			except:
				pass

# Call the auto_trancribe script if we want that
#if args.auto_transcribe:
#	os.system(f'python auto_transcribe.py {auto_transcribe_directories} {args.groups_list}')

# If we are getting groups, places files into the appropriate directories and add transcription templates
if not args.no_groups:
	# Get the groups for each subject
	groups_list = args.groups_list.split(':')

	# Iterate through the groups and directories for each subject
	for groups, directory in tuple(zip(groups_list, args.directories)):

		# Get the mp3 files
		files = [f for f in os.listdir(directory) if f.endswith('.mp3')]

		# Create directories and move files to the corresponding directories
		if not os.path.isdir(f'{directory}/Experiencer'): os.makedirs(f'{directory}/Experiencer')
		if not os.path.isdir(f'{directory}/Garden-Path'): os.makedirs(f'{directory}/Garden-Path')
		for mp3 in files:
			if re.findall(r'^([1-9]\_|[1-2][0-9]\_|3[0-2]\_)', mp3):
				os.rename(f'{directory}/{mp3}', f'{directory}/Experiencer/{mp3}')
			elif re.findall(r'^(3[3-9]\_|[4-5][0-9]\_|6[0-4]\_)', mp3):
				os.rename(f'{directory}/{mp3}', f'{directory}/Garden-Path/{mp3}')

		# Save CSV files with the transcription templates for each group
		exp_group = groups.split(',')[0]
		gp_group = groups.split(',')[1]

		exp_template = pd.read_excel('groups_exp.xlsx', sheet_name = f'Group {exp_group}')
		exp_template['Subject'] = re.sub('S', '', os.path.split(directory)[-1])
		exp_template = exp_template.reindex(columns = (['Group', 'Subject'] + list([a for a in exp_template.columns if not a in ['Group', 'Subject']])))
		exp_template.to_csv(f'{directory}/Experiencer/{os.path.split(directory)[-1]}_exp.csv', index = False)

		gp_template = pd.read_excel('groups_garden-path.xlsx', sheet_name = f'Group {gp_group}')
		gp_template['Subject'] = re.sub('S', '', os.path.split(directory)[-1])
		gp_template = gp_template.reindex(columns = (['Group', 'Subject'] + list([a for a in gp_template.columns if not a in ['Group', 'Subject']])))
		gp_template.to_csv(f'{directory}/Garden-Path/{os.path.split(directory)[-1]}_gp.csv', index = False)