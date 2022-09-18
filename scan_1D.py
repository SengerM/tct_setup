from the_bureaucrat.bureaucrats import RunBureaucrat # https://github.com/SengerM/the_bureaucrat
from pathlib import Path
from time import sleep
import pandas
import datetime
from huge_dataframe.SQLiteDataFrame import SQLiteDataFrameDumper, load_whole_dataframe # https://github.com/SengerM/huge_dataframe
from contextlib import nullcontext
from progressreporting.TelegramProgressReporter import TelegramReporter # https://github.com/SengerM/progressreporting
import threading
from parse_waveforms import parse_waveforms
import plotly.express as px
from utils import integrate_distance_given_path, kMAD, interlace
from grafica.plotly_utils.utils import line
import numpy as np

def TCT_1D_scan(bureaucrat:RunBureaucrat, the_setup, positions:list, acquire_channels:list, n_triggers_per_position:int=1, silent=True, reporter:TelegramReporter=None):
	"""Perform a 1D scan with the TCT setup.
	
	Arguments
	----------
	bureaucrat: RunBureaucrat
		The bureaucrat that will handle the measurement.
	the_setup:
		An object to control the hardware.
	positions: list of tuples
		A list of tuples specifying the positions to measure. Each position
		is a tuple of float of the form `(x,y,z)`.
	acquire_channels: list of int
		A list with the number of the channels to acquire from the oscilloscope.
	n_triggers_per_position: int
		Number of triggers to record at each position.
	silent: bool, default True
		If `True`, not messages will be printed. If `False`, messages will
		be printed showing the progress of the measurement.
	reporter: TelegramReporter
		A reporter to report the progress of the script. Optional.
	"""
	Raúl = bureaucrat
	
	Raúl.create_run()
	
	with Raúl.handle_task('TCT_1D_scan') as Raúls_employee:
		if not silent:
			print(f'Waiting to acquire exclusive control of the hardware...')
		with the_setup.hold_control_of_bias(), the_setup.hold_signal_acquisition(), the_setup.hold_tct_control():
			if not silent:
				print(f'Control of hardware acquired!')
			the_setup.configure_oscilloscope_for_two_pulses()
			the_setup.configure_oscilloscope_sequence_acquisition(n_sequences_per_trigger = n_triggers_per_position)
			the_setup.set_laser_status(status='on') # Make sure the laser is on...
			
			report_progress = reporter is not None
			with reporter.report_for_loop(len(positions), f'{Raúl.run_name}') if report_progress else nullcontext() as reporter:
				with SQLiteDataFrameDumper(
					Raúls_employee.path_to_directory_of_my_task/Path('waveforms.sqlite'), 
					dump_after_n_appends = 1111, # Use this to limit the amount of RAM memory consumed.
					dump_after_seconds = 60, # Use this to ensure the data is stored after some time.
				) as waveforms_dumper:
					with SQLiteDataFrameDumper(
						Raúls_employee.path_to_directory_of_my_task/Path('measured_data.sqlite'), 
						dump_after_n_appends = 1111, # Use this to limit the amount of RAM memory consumed.
						dump_after_seconds = 60, # Use this to ensure the data is stored after some time.
					) as extra_data_dumper: # The `with` statement ensures all the data that was ever appended will be stored in disk.
						n_waveform = 0
						for n_position, target_position in enumerate(positions):
							the_setup.move_to(**{xyz: n for xyz,n in zip(['x','y','z'],target_position)})
							sleep(0.5) # Wait for any transient after moving the motors.
							position = the_setup.get_stages_position()
							if not silent:
								print(f'Measuring: n_position={n_position}/{len(positions)-1}...')
							the_setup.wait_for_trigger()
							extra_data = {
								'x (m)': position[0],
								'y (m)': position[1],
								'z (m)': position[2],
								'When': datetime.datetime.now(),
								'Bias voltage (V)': the_setup.measure_bias_voltage(),
								'Bias current (A)': the_setup.measure_bias_current(),
								'Laser DAC': the_setup.get_laser_DAC(),
								'Temperature (°C)': the_setup.measure_temperature(),
								'Humidity (%RH)': the_setup.measure_humidity(),
								'n_position': n_position,
							}
							for n_channel in acquire_channels:
								data_from_oscilloscope = the_setup.get_waveform(n_channel=n_channel)
								for n_trigger,raw_data in enumerate(data_from_oscilloscope):
									raw_data_each_pulse = {}
									for n_pulse in [1,2]:
										raw_data_each_pulse[n_pulse] = {}
										for variable in ['Time (s)','Amplitude (V)']:
											if n_pulse == 1:
												raw_data_each_pulse[n_pulse][variable] = raw_data[variable][:int(len(raw_data[variable])/2)]
											if n_pulse == 2:
												raw_data_each_pulse[n_pulse][variable] = raw_data[variable][int(len(raw_data[variable])/2):]
										
										waveform_df = pandas.DataFrame(
											{
												'Time (s)': raw_data_each_pulse[n_pulse]['Time (s)'],
												'Amplitude (V)': raw_data_each_pulse[n_pulse]['Amplitude (V)'],
												'n_waveform': n_waveform
											}
										)
										waveform_df.set_index('n_waveform', inplace=True)
										
										extra_data['n_waveform'] = n_waveform
										extra_data['n_trigger'] = n_trigger
										extra_data['n_pulse'] = n_pulse
										extra_data['n_channel'] = n_channel
										extra_data_df = pandas.DataFrame(extra_data, index=[0])
										extra_data_df.set_index(
											['n_waveform','n_position','n_trigger','n_channel','n_pulse'],
											inplace=True
										)
										
										waveforms_dumper.append(waveform_df)
										extra_data_dumper.append(extra_data_df)
										
										n_waveform += 1
							if report_progress:
								reporter.update(1)

def plot_parsed_data_from_TCT_1D_scan(bureaucrat:RunBureaucrat, draw_main_plots:bool=True, draw_distributions:bool=False, strict_task_checking:bool=True):
	"""Plot data parsed from a TCT 1D scan.
	
	Arguments
	---------
	bureaucrat: RunBureaucrat
		The bureaucrat that will handle the measurement.
	draw_main_plots: bool, default True
		Specify whether or not to produce the "main plots", i.e. the most
		relevant plots when inspecting the scan.
	draw_distributions: bool, default False
		Specify whether or not to produce distribution plots.
	strict_task_checking: bool, default False
		If `True` then an error will be raised if the required tasks were
		not fully completed previously in the run handled by `bureaucrat`. 
		If `False` this check is skipped and it will try to produce the
		plots. Switching to `False` is useful for partially completed
		scans, e.g. if there was an error in the middle.
	"""
	Néstor = bureaucrat
	
	if strict_task_checking:
		Néstor.check_these_tasks_were_run_successfully(['TCT_1D_scan','parse_waveforms'])
	
	with Néstor.handle_task('plot_parsed_data_from_TCT_1D_scan') as Néstors_employee:
		parsed_data_df = load_whole_dataframe(Néstor.path_to_directory_of_task('parse_waveforms')/'parsed_from_waveforms.sqlite')
		measured_data_df = load_whole_dataframe(Néstor.path_to_directory_of_task('TCT_1D_scan')/'measured_data.sqlite')
		
		data_df = measured_data_df.merge(parsed_data_df, left_index=True, right_index=True)
		
		data_df['Distance (m)'] = integrate_distance_given_path(list(data_df[['x (m)', 'y (m)', 'z (m)']].to_numpy()))
		
		averaged_in_position_df = data_df.groupby(['n_position','n_channel','n_pulse']).agg([np.nanmedian, kMAD])
		averaged_in_position_df.columns = [f'{col[0]} {col[1]}' for col in averaged_in_position_df.columns]

		if draw_main_plots:
			for var in {'Amplitude (V)','Collected charge (V s)','SNR'}:
				fig = line(
					data_frame = averaged_in_position_df.reset_index(drop=False),
					x = 'Distance (m) nanmedian',
					y = f'{var} nanmedian',
					error_y = f'{var} kMAD',
					error_y_mode = 'bands',
					color = 'n_channel',
					line_dash = 'n_pulse',
					title = f'{var} vs distance<br><sup>Run: {Néstor.run_name}</sup>',
					labels = {
						'Distance (m) nanmedian': 'Distance (m)',
						f'{var} nanmedian': var,
					},
				)
				fig.write_html(
					str(Néstors_employee.path_to_directory_of_my_task/f'{var} vs distance.html'),
					include_plotlyjs = 'cdn',
				)
		
		if draw_distributions:
			store_distributions_here = Néstors_employee.path_to_directory_of_my_task/'distributions'
			store_distributions_here.mkdir(exist_ok=True)
			for var in {'Humidity (%RH)','Temperature (°C)',}:
				fig = px.ecdf(
					data_df.loc[data_df[var].notna()],
					x = var,
					title = f'{var} distribution<br><sup>Run: {Néstor.run_name}</sup>',
				)
				fig.write_html(
					str(store_distributions_here/var) + '.html',
					include_plotlyjs = 'cdn',
				)

def scan_and_parse(bureaucrat:RunBureaucrat, the_setup, delete_waveforms_file:bool, positions:list, acquire_channels:list, n_triggers_per_position:int=1, silent=True, reporter:TelegramReporter=None):
	"""Perform a `TCT_1D_scan` and parse in parallel."""
	Ernestino = bureaucrat
	TCT_still_scanning = True
	
	def parsing_thread_function():
		args = dict(
			bureaucrat = Ernestino, 
			name_of_task_that_produced_the_waveforms_to_parse = 'TCT_1D_scan',
			silent = silent, 
			continue_from_where_we_left_last_time = True,
		)
		while TCT_still_scanning:
			try:
				parse_waveforms(**args)
			except:
				pass
			sleep(1)
		parse_waveforms(**args) # This last call is in case there is a bunch of waveforms left.
	
	parsing_thread = threading.Thread(target=parsing_thread_function)
	
	try:
		parsing_thread.start()
		TCT_1D_scan(
			bureaucrat = Ernestino, 
			the_setup = the_setup, 
			positions = positions, 
			acquire_channels = acquire_channels, 
			n_triggers_per_position = n_triggers_per_position, 
			silent = silent,
			reporter = reporter,
		)
	finally:
		TCT_still_scanning = False
		while parsing_thread.is_alive():
			sleep(1)
		
		if delete_waveforms_file == True:
			(Ernestino.path_to_directory_of_task('TCT_1D_scan')/'waveforms.sqlite').unlink()
	
	plot_parsed_data_from_TCT_1D_scan(bureaucrat=Ernestino)

def TCT_1D_scan_sweeping_bias_voltage(bureaucrat:RunBureaucrat, the_setup, delete_waveforms_file:bool, voltages:list, positions:list, acquire_channels:list, n_triggers_per_position:int=1, silent=True, reporter:TelegramReporter=None):
	"""Perform a several 1D scans with the TCT setup, one at each voltage.
	
	Arguments
	----------
	bureaucrat: RunBureaucrat
		The bureaucrat that will handle the measurement.
	the_setup:
		An object to control the hardware.
	voltages: list of float
		Voltages at which to measure.
	positions: list of tuples
		A list of tuples specifying the positions to measure. Each position
		is a tuple of float of the form `(x,y,z)`.
	acquire_channels: list of int
		A list with the number of the channels to acquire from the oscilloscope.
	n_triggers_per_position: int
		Number of triggers to record at each position.
	silent: bool, default True
		If `True`, not messages will be printed. If `False`, messages will
		be printed showing the progress of the measurement.
	reporter: TelegramReporter
		A reporter to report the progress of the script. Optional.
	"""
	Lorenzo = bureaucrat
	Lorenzo.create_run()
	
	with Lorenzo.handle_task('TCT_1D_scan_sweeping_bias_voltage') as Lorenzos_employee:
		if not silent:
			print(f'Waiting for acquiring the control of the hardware...')
		with the_setup.hold_control_of_bias(), the_setup.hold_tct_control():
			if not silent:
				print(f'Control of hardware acquired!')
			report_progress = reporter is not None
			with reporter.report_for_loop(len(voltages), f'{Lorenzo.run_name}') if report_progress else nullcontext() as reporter:
				for voltage in voltages:
					if not silent:
						print('Setting bias voltage...')
					the_setup.set_bias_voltage(volts=voltage)
					Lorenzos_son = Lorenzos_employee.create_subrun(subrun_name=f'{Lorenzo.run_name}_{int(voltage)}V')
					scan_and_parse(
						bureaucrat = Lorenzos_son,
						delete_waveforms_file = delete_waveforms_file,
						the_setup = the_setup,
						positions = positions,
						n_triggers_per_position = n_triggers_per_position,
						acquire_channels = acquire_channels,
						silent = silent,
						reporter = TelegramReporter(
							telegram_token = my_telegram_bots.robobot.token, 
							telegram_chat_id = my_telegram_bots.chat_ids['Robobot TCT setup'],
						) if report_progress else None,
					)
					if not silent:
						print(f'Finished {Lorenzos_son.run_name}.')
					reporter.update(1)

########################################################################

# The following things are defined here such that they can be imported from other scripts.

DEVICE_CENTER = {
	'x': -3355.810546875e-6,
	'y': 1565.5078125e-6,
	'z': 71538.876953125e-6,
}
SCAN_STEP = 1e-6 # meters
SCAN_LENGTH = 333e-6 # meters
SCAN_ANGLE_DEG = 90 # deg

if __name__ == '__main__':
	import my_telegram_bots
	from configuration_files.current_run import Alberto
	from utils import create_a_timestamp
	from TheSetup import connect_me_with_the_setup
	import os
	
	with Alberto.handle_task('TCT_scans', drop_old_data=False) as task_bureaucrat:
		Mariano = task_bureaucrat.create_subrun(create_a_timestamp() + '_' + input('Measurement name? ').replace(' ','_'))
	
		x = DEVICE_CENTER['x'] + np.arange(-SCAN_LENGTH/2,SCAN_LENGTH/2, SCAN_STEP)*np.cos(SCAN_ANGLE_DEG*np.pi/180)
		y = DEVICE_CENTER['y'] + np.arange(-SCAN_LENGTH/2,SCAN_LENGTH/2, SCAN_STEP)*np.sin(SCAN_ANGLE_DEG*np.pi/180)
		z = DEVICE_CENTER['z'] + 0*x + 0*y
		positions = []
		for i in range(len(y)):
			positions.append( [ x[i],y[i],z[i] ] )
		
		the_setup = connect_me_with_the_setup(who=f'iv_curve.py PID:{os.getpid()}')
		
		with the_setup.hold_control_of_bias(), the_setup.hold_tct_control():
			the_setup.set_current_compliance(amperes=10e-6)
			the_setup.set_bias_output_status('on')
			the_setup.set_bias_voltage(200)
			the_setup.set_laser_DAC(650)
			the_setup.set_laser_frequency(1000)
			
			scan_and_parse(
				bureaucrat = Mariano,
				delete_waveforms_file = True,
				# ~ voltages = interlace(np.linspace(100,220,33)),
				the_setup = the_setup,
				positions = positions,
				n_triggers_per_position = 555,
				acquire_channels = [1,4],
				silent = False,
				reporter = TelegramReporter(
					telegram_token = my_telegram_bots.robobot.token, 
					telegram_chat_id = my_telegram_bots.chat_ids['Robobot TCT setup'],
				),
			)
			
			the_setup.set_bias_output_status('off')
