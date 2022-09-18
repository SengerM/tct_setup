from the_bureaucrat.bureaucrats import RunBureaucrat # https://github.com/SengerM/the_bureaucrat
from pathlib import Path
import pandas
from huge_dataframe.SQLiteDataFrame import SQLiteDataFrameDumper, load_whole_dataframe, load_only_index_without_repeated_entries # https://github.com/SengerM/huge_dataframe
import sqlite3
from signals.PeakSignal import PeakSignal, draw_in_plotly # https://github.com/SengerM/signals

def parse_waveform(signal:PeakSignal):
	parsed = {
		'Amplitude (V)': signal.amplitude,
		'Noise (V)': signal.noise,
		'Rise time (s)': signal.rise_time,
		'Collected charge (V s)': signal.peak_integral,
		'Time over noise (s)': signal.time_over_noise,
		'Peak start time (s)': signal.peak_start_time,
		'Whole signal integral (V s)': signal.integral_from_baseline,
		'SNR': signal.SNR
	}
	for threshold_percentage in [10,20,30,40,50,60,70,80,90]:
		try:
			time_over_threshold = signal.find_time_over_threshold(threshold_percentage)
		except Exception:
			time_over_threshold = float('NaN')
		parsed[f'Time over {threshold_percentage}% (s)'] = time_over_threshold
	for pp in [10,20,30,40,50,60,70,80,90]:
		try:
			time_at_this_pp = float(signal.find_time_at_rising_edge(pp))
		except Exception:
			time_at_this_pp = float('NaN')
		parsed[f't_{pp} (s)'] = time_at_this_pp
	return parsed

def parse_waveforms(bureaucrat:RunBureaucrat, name_of_task_that_produced_the_waveforms_to_parse:str, continue_from_where_we_left_last_time:bool=True, silent:bool=True):
	Quique = bureaucrat
	
	with Quique.handle_task('parse_waveforms', drop_old_data=not continue_from_where_we_left_last_time) as Quiques_employee:
		try:
			index_of_waveforms_already_parsed_in_the_past = set(load_whole_dataframe(Quiques_employee.path_to_directory_of_my_task/'parsed_from_waveforms.sqlite').index)
		except FileNotFoundError:
			index_of_waveforms_already_parsed_in_the_past = set()
		
		path_to_waveforms_file = Quiques_employee.path_to_directory_of_task(name_of_task_that_produced_the_waveforms_to_parse)/'waveforms.sqlite'
		
		sqlite_connection = sqlite3.connect(path_to_waveforms_file)
		
		if not silent:
			print(f'Determining the total number of waveforms to be processed...')
		number_of_waveforms_to_process = load_only_index_without_repeated_entries(path_to_waveforms_file)['n_waveform'].max()
		index_of_all_waveforms = set(range(number_of_waveforms_to_process))
		index_of_waveforms_to_be_parsed = index_of_all_waveforms - index_of_waveforms_already_parsed_in_the_past
		
		if not silent:
			print(f'{len(index_of_waveforms_to_be_parsed)} waveforms still need to be parsed. The others were already parsed beforehand. Will now proceed...')
		
		with SQLiteDataFrameDumper(Quiques_employee.path_to_directory_of_my_task/Path('parsed_from_waveforms.sqlite'), dump_after_n_appends = 1111, dump_after_seconds = 60, delete_database_if_already_exists=False) as parsed_data_dumper: 
			for i,n_waveform in enumerate(sorted(index_of_waveforms_to_be_parsed)):
				if not silent:
					print(f'Parsing n_waveform={n_waveform} ({i}/{len(index_of_waveforms_to_be_parsed)-1})')
				waveform_df = pandas.read_sql_query(
					f'SELECT * from dataframe_table where n_waveform=={n_waveform}',
					sqlite_connection,
				)
				parsed_from_waveform = parse_waveform(PeakSignal(time=waveform_df['Time (s)'], samples=waveform_df['Amplitude (V)']))
				parsed_from_waveform['n_waveform'] = n_waveform
				parsed_from_waveform_df = pandas.DataFrame(
					parsed_from_waveform,
					index = [0],
				).set_index(['n_waveform'])
				parsed_data_dumper.append(parsed_from_waveform_df)

if __name__=='__main__':
	import argparse

	parser = argparse.ArgumentParser(description='Cleans a beta scan according to some criterion.')
	parser.add_argument('--dir',
		metavar = 'path',
		help = 'Path to the base measurement directory.',
		required = True,
		dest = 'directory',
		type = str,
	)

	args = parser.parse_args()
	parse_waveforms(
		bureaucrat = RunBureaucrat(Path(args.directory)),
		name_of_task_that_produced_the_waveforms_to_parse = 'TCT_1D_scan',
		silent = False,
		continue_from_where_we_left_last_time = True,
	)
