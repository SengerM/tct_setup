from the_bureaucrat.bureaucrats import RunBureaucrat # https://github.com/SengerM/the_bureaucrat
from pathlib import Path
from time import sleep
import pandas
import datetime
from huge_dataframe.SQLiteDataFrame import SQLiteDataFrameDumper # https://github.com/SengerM/huge_dataframe
from contextlib import nullcontext
from progressreporting.TelegramProgressReporter import TelegramReporter # https://github.com/SengerM/progressreporting
import threading
from parse_waveforms import parse_waveforms

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
	
	with Raúl.handle_task('TCT_1D_scan') as Raúls_employee:
		if not silent:
			print(f'Waiting to acquire exclusive control of the hardware...')
		with the_setup.hold_control_of_bias(), the_setup.hold_signal_acquisition(), the_setup.hold_tct_control():
			if not silent:
				print(f'Control of hardware acquired!')
			the_setup.configure_oscilloscope_for_two_pulses()
			the_setup.set_laser_status(status='on') # Make sure the laser is on...
			
			report_progress = reporter is not None
			with reporter.report_for_loop(len(positions)*n_triggers_per_position, f'{Raúl.run_name}') if report_progress else nullcontext() as reporter:
				with SQLiteDataFrameDumper(
					Raúls_employee.path_to_directory_of_my_task/Path('waveforms.sqlite'), 
					dump_after_n_appends = 100, # Use this to limit the amount of RAM memory consumed.
					dump_after_seconds = 60, # Use this to ensure the data is stored after some time.
				) as waveforms_dumper:
					with SQLiteDataFrameDumper(
						Raúls_employee.path_to_directory_of_my_task/Path('measured_data.sqlite'), 
						dump_after_n_appends = 100, # Use this to limit the amount of RAM memory consumed.
						dump_after_seconds = 60, # Use this to ensure the data is stored after some time.
					) as extra_data_dumper: # The `with` statement ensures all the data that was ever appended will be stored in disk.
						n_waveform = 0
						for n_position, target_position in enumerate(positions):
							the_setup.move_to(**{xyz: n for xyz,n in zip(['x','y','z'],target_position)})
							sleep(0.5) # Wait for any transient after moving the motors.
							position = the_setup.get_stages_position()
							for n_trigger in range(n_triggers_per_position):
								if not silent:
									print(f'Measuring: n_position={n_position}/{len(positions)-1}, n_trigger={n_trigger}/{n_triggers_per_position-1}...')
								if report_progress:
									reporter.update(1)
								
								the_setup.wait_for_trigger()
								for n_channel in acquire_channels:
									raw_data = the_setup.get_waveform(n_channel=n_channel)
									raw_data_each_pulse = {}
									for n_pulse in [1,2]:
										raw_data_each_pulse[n_pulse] = {}
										for variable in ['Time (s)','Amplitude (V)']:
											if n_pulse == 1:
												raw_data_each_pulse[n_pulse][variable] = raw_data[variable][:int(len(raw_data[variable])/2)]
											if n_pulse == 2:
												raw_data_each_pulse[n_pulse][variable] = raw_data[variable][int(len(raw_data[variable])/2):]
										
										# Because measuring bias voltage and current takes a long time (don't know why), I do the following ---
										measure_slow_things_in_this_iteration = False
										if 'last_time_slow_things_were_measured' not in locals() or (datetime.datetime.now()-last_time_slow_things_were_measured).seconds >= 11:
											measure_slow_things_in_this_iteration = True
											last_time_slow_things_were_measured = datetime.datetime.now()
										
										waveform_df = pandas.DataFrame(
											{
												'Time (s)': raw_data_each_pulse[n_pulse]['Time (s)'],
												'Amplitude (V)': raw_data_each_pulse[n_pulse]['Amplitude (V)'],
												'n_waveform': n_waveform
											}
										)
										waveform_df.set_index('n_waveform', inplace=True)
										extra_data_df = pandas.DataFrame(
											{
												'x (m)': position[0],
												'y (m)': position[1],
												'z (m)': position[2],
												'When': datetime.datetime.now(),
												'Bias voltage (V)': the_setup.measure_bias_voltage() if measure_slow_things_in_this_iteration else float('NaN'),
												'Bias current (A)': the_setup.measure_bias_current() if measure_slow_things_in_this_iteration else float('NaN'),
												'Laser DAC': the_setup.get_laser_DAC(),
												'Temperature (°C)': the_setup.measure_temperature() if measure_slow_things_in_this_iteration else float('NaN'),
												'Humidity (%RH)': the_setup.measure_humidity() if measure_slow_things_in_this_iteration else float('NaN'),
												'n_waveform': n_waveform,
												'n_position': n_position,
												'n_trigger': n_trigger,
												'n_channel': n_channel,
												'n_pulse': n_pulse,
											},
											index = [0],
										)
										extra_data_df.set_index(
											['n_waveform','n_position','n_trigger','n_channel','n_pulse'],
											inplace=True
										)
										
										waveforms_dumper.append(waveform_df)
										extra_data_dumper.append(extra_data_df)
										
										n_waveform += 1

def scan_and_parse(bureaucrat:RunBureaucrat, the_setup, positions:list, acquire_channels:list, n_triggers_per_position:int=1, silent=True, reporter:TelegramReporter=None):
	"""Perform a `TCT_1D_scan` and parse in parallel."""
	Ernestino = bureaucrat
	TCT_still_scanning = True
	
	def parsing_thread_function():
		while TCT_still_scanning:
			try:
				parse_waveforms(
					bureaucrat = Ernestino, 
					name_of_task_that_produced_the_waveforms_to_parse = 'TCT_1D_scan',
					silent = True, 
					continue_from_where_we_left_last_time = True,
				)
			except:
				pass
			sleep(1)
	
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

########################################################################

# The following things are defined here such that they can be imported from other scripts.

DEVICE_CENTER = {
	'x': -2.96578125e-3,
	'y': 1.430810546875e-3,
	'z': 67.3390039e-3,
}
SCAN_STEP = 10e-6 # meters
SCAN_LENGTH = 333e-6 # meters
SCAN_ANGLE_DEG = 90 # deg
LASER_DAC = 0
N_TRIGGERS_PER_POSITION = 55

if __name__ == '__main__':
	import numpy as np
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
		
		scan_and_parse(
			bureaucrat = Mariano,
			the_setup = connect_me_with_the_setup(who=f'iv_curve.py PID:{os.getpid()}'),
			positions = positions,
			n_triggers_per_position = N_TRIGGERS_PER_POSITION,
			acquire_channels = [1,4],
			silent = False,
			reporter = TelegramReporter(
				telegram_token = my_telegram_bots.robobot.token, 
				telegram_chat_id = my_telegram_bots.chat_ids['Robobot TCT setup'],
			),
		)
