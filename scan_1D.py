from the_bureaucrat.bureaucrats import RunBureaucrat, TaskBureaucrat # https://github.com/SengerM/the_bureaucrat
from pathlib import Path
from time import sleep
import pandas
import datetime
from huge_dataframe.SQLiteDataFrame import SQLiteDataFrameDumper, load_whole_dataframe, load_only_index_without_repeated_entries # https://github.com/SengerM/huge_dataframe
from contextlib import nullcontext
from progressreporting.TelegramProgressReporter import SafeTelegramReporter4Loops # https://github.com/SengerM/progressreporting
import threading
from parse_waveforms import parse_waveform
import plotly.express as px
from utils import integrate_distance_given_path, kMAD, interlace, compress_waveforms_sqlite
from grafica.plotly_utils.utils import line
import numpy as np
from signals.PeakSignal import PeakSignal, draw_in_plotly # https://github.com/SengerM/signals
import sqlite3

def TCT_1D_scan(bureaucrat:RunBureaucrat, the_setup, positions:list, acquire_channels:list, n_triggers_per_position:int=1, silent=True, reporter:SafeTelegramReporter4Loops=None, compress_waveforms_file:bool=True):
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
	reporter: SafeTelegramReporter4Loops
		A reporter to report the progress of the script. Optional.
	"""
	Raúl = bureaucrat
	
	Raúl.create_run(if_exists='skip')
	
	with Raúl.handle_task('TCT_1D_scan') as Raúls_employee:
		if not silent:
			print(f'Waiting to acquire exclusive control of the hardware...')
		with the_setup.hold_control_of_bias(), the_setup.hold_signal_acquisition(), the_setup.hold_tct_control():
			if not silent:
				print(f'Control of hardware acquired!')
			the_setup.configure_oscilloscope_for_two_pulses()
			the_setup.configure_oscilloscope_sequence_acquisition(n_sequences_per_trigger = int(n_triggers_per_position))
			the_setup.set_laser_status(status='on') # Make sure the laser is on...
			path_to_waveforms_file = Raúls_employee.path_to_directory_of_my_task/'waveforms.sqlite'
			with \
				reporter.report_loop(len(positions), Raúl.run_name) if reporter is not None else nullcontext() as reporter, \
				SQLiteDataFrameDumper(Raúls_employee.path_to_directory_of_my_task/Path('parsed_from_waveforms.sqlite'), dump_after_n_appends = 7777, dump_after_seconds = 60) as parsed_data_dumper, \
				SQLiteDataFrameDumper(Raúls_employee.path_to_directory_of_my_task/Path('measured_data.sqlite'), dump_after_n_appends = 1111, dump_after_seconds = 60) as measured_data_dumper, \
				SQLiteDataFrameDumper(path_to_waveforms_file, dump_after_n_appends = 1111, dump_after_seconds = 60) as waveforms_dumper \
			:
				n_waveform = 0
				for n_position, target_position in enumerate(positions):
					the_setup.move_to(**{xyz: n for xyz,n in zip(['x','y','z'],target_position)})
					sleep(0.5) # Wait for any transient after moving the motors.

					if not silent:
						print(f'Measuring: n_position={n_position}/{len(positions)-1}...')
					
					the_setup.wait_for_trigger()
					
					position = the_setup.get_stages_position()
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
					extra_data = pandas.DataFrame(extra_data, index=[0])
					extra_data.set_index('n_position', inplace=True)
					measured_data_dumper.append(extra_data)
					
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
								
								waveform = pandas.DataFrame(raw_data_each_pulse[n_pulse])
								waveform['n_waveform'] = n_waveform
								waveform.set_index('n_waveform', inplace=True)
								waveforms_dumper.append(waveform)
								
								parsed_from_waveform = parse_waveform(
									PeakSignal(
										time = raw_data_each_pulse[n_pulse]['Time (s)'], 
										samples = raw_data_each_pulse[n_pulse]['Amplitude (V)']
									)
								)
								parsed_from_waveform['n_waveform'] = n_waveform
								parsed_from_waveform['n_position'] = n_position
								parsed_from_waveform['n_trigger'] = n_trigger
								parsed_from_waveform['n_pulse'] = n_pulse
								parsed_from_waveform['n_channel'] = n_channel
								parsed_from_waveform = pandas.DataFrame(
									parsed_from_waveform,
									index = [0],
								)
								parsed_from_waveform.set_index(
									['n_waveform','n_position','n_trigger','n_channel','n_pulse'],
									inplace = True,
								)
								parsed_data_dumper.append(parsed_from_waveform)
								
								n_waveform += 1
					reporter.update(1) if reporter is not None else None
		if not silent:
			print(f'Finished measuring!')
		
		if not silent:
			print(f'Producing some plots of some of the waveforms...')
		plot_some_random_waveforms(Raúls_employee, n_waveform, 20)
		
		if compress_waveforms_file:
			if not silent:
				print(f'Compressing waveforms file...')
			compress_waveforms_sqlite(path_to_waveforms_file)
			path_to_waveforms_file.unlink()

def plot_some_random_waveforms(bureaucrat:TaskBureaucrat, total_number_of_waveforms:int, number_of_triggers_to_plot:int=20):
	if not isinstance(bureaucrat, TaskBureaucrat):
		raise TypeError(f'`bureaucrat` must be an instance of {repr(TaskBureaucrat)}, received object of type {type(bureaucrat)}. ')
	random_n_waveforms = set(np.random.randint(0, total_number_of_waveforms, number_of_triggers_to_plot))
	indices = load_only_index_without_repeated_entries(bureaucrat.path_to_directory_of_my_task/'parsed_from_waveforms.sqlite')
	_ = indices.query(f'n_waveform in {repr(list(random_n_waveforms))}')[['n_position','n_trigger']].sort_values(['n_position','n_trigger'])
	for df in [_,indices]:
		df.set_index(['n_position','n_trigger'], inplace=True)
	waveforms_to_plot = indices.loc[_.index].set_index(['n_channel','n_pulse'], append=True)
	
	waveforms_sqlite_connection = sqlite3.connect(bureaucrat.path_to_directory_of_my_task/'waveforms.sqlite')
	
	path_to_plots_dir = bureaucrat.path_to_directory_of_my_task/'plots_of_some_waveforms'
	path_to_plots_dir.mkdir(exist_ok = True)
	for idx, row in waveforms_to_plot.iterrows():
		n_waveform = row['n_waveform']
		waveform = pandas.read_sql(
			sql = f"SELECT * from dataframe_table WHERE n_waveform IS {n_waveform}",
			con = waveforms_sqlite_connection,
			index_col = 'n_waveform',
		)
		fig = draw_in_plotly(PeakSignal(time=waveform['Time (s)'], samples=waveform['Amplitude (V)']))
		title_stuff = ", ".join([f"{var}={val}" for var,val in zip(waveforms_to_plot.index.names, idx)])
		fig.update_layout(
			title = f'n_waveform={n_waveform}, {title_stuff}<br><sup>{bureaucrat.run_name}</sup>',
			xaxis_title = 'Time (s)',
			yaxis_title = 'Amplitude (V)',
		)
		fig.write_html(
			path_to_plots_dir/f'{title_stuff.replace(", ","_")}.html',
			include_plotlyjs = 'cdn',
		)

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
		Néstor.check_these_tasks_were_run_successfully(['TCT_1D_scan'])
	
	with Néstor.handle_task('plot_parsed_data_from_TCT_1D_scan') as Néstors_employee:
		parsed_data_df = load_whole_dataframe(Néstor.path_to_directory_of_task('TCT_1D_scan')/'parsed_from_waveforms.sqlite')
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

def TCT_1D_scan_sweeping_bias_voltage(bureaucrat:RunBureaucrat, the_setup, voltages:list, positions:list, acquire_channels:list, n_triggers_per_position:int=1, silent=True, reporter:SafeTelegramReporter4Loops=None):
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
					TCT_1D_scan(
						bureaucrat = Lorenzos_son,
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
					try:
						plot_parsed_data_from_TCT_1D_scan(bureaucrat=Lorenzos_son)
					except Exception:
						pass
					if not silent:
						print(f'Finished {Lorenzos_son.run_name}.')
					reporter.update(1)

if __name__ == '__main__':
	
	import my_telegram_bots
	from configuration_files.current_run import Alberto
	from utils import create_a_timestamp
	from TheSetup import connect_me_with_the_setup
	import os
	
	bureaucrat = TaskBureaucrat(
		Path('/home/tct/power_storage/senger_matias/TCT_data/CNM_AC-LGAD/TCT_scans/subruns/20230508101732_AC42/TCT_2D_scans_sweeping_bias_voltage/subruns/20230508101732_AC42_500V/TCT_2D_scan/subruns/20230508101732_AC42_500V_Flattened1DScan'),
		task_name = 'TCT_1D_scan',
		drop_old_data = False,
	)
	plot_some_random_waveforms(bureaucrat, 35*22*2*4)
	
	# ~ def create_list_of_positions(device_center_xyz:tuple, scan_length:float, scan_angle_deg:float, scan_step:float):
		# ~ x = device_center_xyz[0] + np.arange(-scan_length/2,scan_length/2,scan_step)*np.cos(scan_angle_deg*np.pi/180)
		# ~ y = device_center_xyz[1] + np.arange(-scan_length/2,scan_length/2,scan_step)*np.sin(scan_angle_deg*np.pi/180)
		# ~ z = device_center_xyz[2] + 0*x + 0*y
		# ~ return [(xx,yy,zz) for xx,yy,zz in zip(x,y,z)]
	
	# ~ scans_config = pandas.read_csv('configuration_files/automatic_scans.csv').set_index('device_name')
	# ~ scans_config['acquire_channels'] = scans_config['acquire_channels'].apply(lambda x: [int(n_channel) for n_channel in x.split(',')])
	
	# ~ preview_mode = input(f'Is this a preview? (yes/no) ')
	
	# ~ if preview_mode == 'yes':
		# ~ print('Preview mode enabled!')
		# ~ scans_config['scan_step (µm)'] = 10
		# ~ scans_config['n_voltages'] = 1
		# ~ scans_config['n_triggers_per_position'] = 11
	# ~ elif preview_mode not in {'no',''}:
		# ~ raise ValueError(f'Wrong answer!')
	
	# ~ the_setup = connect_me_with_the_setup(who=f'iv_curve.py PID:{os.getpid()}')
	
	# ~ with Alberto.handle_task('TCT_scans', drop_old_data=False) as employee:
		# ~ with the_setup.hold_control_of_bias(), the_setup.hold_tct_control():
			# ~ try:
				# ~ for device_name in scans_config.index:
					# ~ Mariano = employee.create_subrun(create_a_timestamp() + '_' + f'{device_name}_TCT1DScan' + ('_preview' if preview_mode=='yes' else ''))
				
					# ~ the_setup.set_current_compliance(amperes=20e-6)
					# ~ the_setup.set_bias_output_status('on')
					# ~ the_setup.set_laser_DAC(600)
					# ~ the_setup.set_laser_frequency(1000)
					# ~ the_setup.set_laser_status('on')
					
					# ~ the_setup.set_bias_voltage(volts=222)
					
					# ~ TCT_1D_scan(
						# ~ bureaucrat = Mariano,
						# ~ the_setup = the_setup,
						# ~ positions = create_list_of_positions(
							# ~ device_center_xyz = tuple([scans_config.loc[device_name,coord]*1e-6 for coord in ('x_center (µm)','y_center (µm)','z_center (µm)')]),
							# ~ scan_length = scans_config.loc[device_name,'scan_length (µm)']*1e-6,
							# ~ scan_angle_deg = scans_config.loc[device_name,'scan_angle (deg)'],
							# ~ scan_step = scans_config.loc[device_name,'scan_step (µm)']*1e-6,
						# ~ ),
						# ~ acquire_channels = scans_config.loc[device_name,'acquire_channels'],
						# ~ n_triggers_per_position = scans_config.loc[device_name,'n_triggers_per_position'],
						# ~ silent = False, 
						# ~ reporter = SafeTelegramReporter4Loops(
							# ~ bot_token = my_telegram_bots.robobot.token, 
							# ~ chat_id = my_telegram_bots.chat_ids['Robobot TCT setup'],
						# ~ )
					# ~ )
					
					# ~ plot_parsed_data_from_TCT_1D_scan(Mariano)
			# ~ finally:	
				# ~ the_setup.set_bias_output_status('off')
				# ~ the_setup.set_laser_status('off')
