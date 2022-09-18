from the_bureaucrat.bureaucrats import RunBureaucrat # https://github.com/SengerM/the_bureaucrat
from pathlib import Path
import pandas
import datetime
import time
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from TheSetup import connect_me_with_the_setup
from huge_dataframe.SQLiteDataFrame import SQLiteDataFrameDumper, load_whole_dataframe # https://github.com/SengerM/huge_dataframe
import threading
import warnings
from signals.PeakSignal import PeakSignal, draw_in_plotly # https://github.com/SengerM/signals
from progressreporting.TelegramProgressReporter import TelegramReporter # https://github.com/SengerM/progressreporting
import my_telegram_bots
import numpy
from utils import interlace

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

def trigger_and_measure_stuff(the_setup):
	elapsed_seconds = 9999
	while elapsed_seconds > 5: # Because of multiple threads locking the different elements of the_setup, it can happen that this gets blocked for a long time. Thus, the measured data will no longer belong to a single point in time as we expect...:
		the_setup.wait_for_trigger()
		trigger_time = time.time()
		measured_stuff = {
			'Bias voltage (V)': the_setup.measure_bias_voltage(),
			'Bias current (A)': the_setup.measure_bias_current(),
			'Temperature (°C)': the_setup.measure_temperature(),
			'Humidity (%RH)': the_setup.measure_humidity(),
			'When': datetime.datetime.now(),
		}
		elapsed_seconds = trigger_time - time.time()
	return measured_stuff

def plot_waveform(signal):
	fig = draw_in_plotly(signal)
	fig.update_layout(
		xaxis_title = "Time (s)",
		yaxis_title = "Amplitude (V)",
	)
	MARKERS = { # https://plotly.com/python/marker-style/#custom-marker-symbols
		10: 'circle',
		20: 'square',
		30: 'diamond',
		40: 'cross',
		50: 'x',
		60: 'star',
		70: 'hexagram',
		80: 'star-triangle-up',
		90: 'star-triangle-down',
	}
	for pp in [10,20,30,40,50,60,70,80,90]:
		try:
			fig.add_trace(
				go.Scatter(
					x = [signal.find_time_at_rising_edge(pp)],
					y = [signal(signal.find_time_at_rising_edge(pp))],
					mode = 'markers',
					name = f'Time at {pp} %',
					marker=dict(
						color = 'rgba(0,0,0,.5)',
						size = 11,
						symbol = MARKERS[pp]+'-open-dot',
						line = dict(
							color = 'rgba(0,0,0,.5)',
							width = 2,
						)
					),
				)
			)
		except Exception as e:
			pass
	return fig

def beta_scan(bureaucrat:RunBureaucrat, the_setup, n_triggers:int, bias_voltage:float, n_channels:list, software_trigger=None, silent=False):
	"""Perform a beta scan.
	
	Parameters
	----------
	bureaucrat: RunBureaucrat
		The bureaucrat that will manage this measurement.
	n_triggers: int
		Number of triggers to record.
	the_setup:
		Object to access the measuring setup.
	n_channels: list of int
		Channel numbers to read from the oscilloscope.
	software_trigger: callable, optional
		A callable that receives a dictionary of waveforms of type `PeakSignal`
		and returns `True` or `False`, that will be called for each trigger.
		If `software_trigger(waveforms_dict)` returns `True`, the trigger
		will be considered as nice, otherwise it will be discarded and a
		new trigger will be taken. Example:
		```
		def software_trigger(signals_dict):
			DUT_signal = signals_dict['DUT']
			PMT_signal = signals_dict['reference_trigger']
			return abs(DUT_signal.peak_start_time - PMT_signal.peak_start_time) < 2e-9
		```
	bias_voltage: float
		The value for the voltage.
	silent: bool, default False
		If `True`, no progress messages are printed.
	
	Returns
	-------
	path_to_measurement_base_directory: Path
		A path to the directory where the measurement's data was stored.
	"""
	
	John = bureaucrat
	John.create_run()
	
	reporter = TelegramReporter(
		telegram_token = my_telegram_bots.robobot.token,
		telegram_chat_id = my_telegram_bots.chat_ids['Robobot TCT setup'],
	)
	
	if not silent:
		print('Waiting for acquiring control of the hardware...')
	with the_setup.hold_signal_acquisition(), the_setup.hold_control_of_bias():
		if not silent:
			print('Control of hardware acquired.')
		with John.handle_task('beta_scan') as beta_scan_task_bureaucrat:
			with SQLiteDataFrameDumper(beta_scan_task_bureaucrat.path_to_directory_of_my_task/Path('measured_stuff.sqlite'), dump_after_n_appends=1e3, dump_after_seconds=66) as measured_stuff_dumper, SQLiteDataFrameDumper(beta_scan_task_bureaucrat.path_to_directory_of_my_task/Path('parsed_from_waveforms.sqlite'), dump_after_n_appends=1e3, dump_after_seconds=66) as parsed_from_waveforms_dumper:
				if not silent:
					print(f'Setting bias voltage {bias_voltage} V...')
				the_setup.set_bias_voltage(volts=bias_voltage)
				
				with reporter.report_for_loop(n_triggers, John.run_name) as reporter:
					n_waveform = -1
					for n_trigger in range(n_triggers):
						# Acquire ---
						if not silent:
							print(f'Acquiring n_trigger={n_trigger}/{n_triggers-1}...')
						
						do_they_like_this_trigger = False
						while do_they_like_this_trigger == False:
							this_trigger_measured_stuff = trigger_and_measure_stuff(the_setup) # Hold here until there is a trigger.
							
							this_trigger_measured_stuff['n_trigger'] = n_trigger
							this_trigger_measured_stuff_df = pandas.DataFrame(this_trigger_measured_stuff, index=[0]).set_index(['n_trigger'])
							
							this_trigger_waveforms_dict = {}
							for n_channel in n_channels:
								waveform_data = the_setup.get_waveform(n_channel=n_channel)
								this_trigger_waveforms_dict[n_channel] = PeakSignal(
									time = waveform_data['Time (s)'],
									samples = waveform_data['Amplitude (V)']
								)
							
							if software_trigger is None:
								do_they_like_this_trigger = True
							else:
								do_they_like_this_trigger = software_trigger(this_trigger_waveforms_dict)
						
						# Parse and save data ---
						measured_stuff_dumper.append(this_trigger_measured_stuff_df)
						for n_channel in n_channels:
							n_waveform += 1
							
							waveform_df = pandas.DataFrame({'Time (s)': this_trigger_waveforms_dict[n_channel].time, 'Amplitude (V)': this_trigger_waveforms_dict[n_channel].samples})
							waveform_df['n_waveform'] = n_waveform
							waveform_df.set_index('n_waveform', inplace=True)
							
							parsed_from_waveform = parse_waveform(this_trigger_waveforms_dict[n_channel])
							parsed_from_waveform['n_trigger'] = n_trigger
							parsed_from_waveform['n_channel'] = n_channel
							parsed_from_waveform['n_waveform'] = n_waveform
							parsed_from_waveform_df = pandas.DataFrame(
								parsed_from_waveform,
								index = [0],
							).set_index(['n_trigger','n_channel'])
							parsed_from_waveforms_dumper.append(parsed_from_waveform_df)
						
						# Plot some of the signals ---
						if numpy.random.rand()<20/n_triggers:
							for n_channel in n_channels:
								fig = plot_waveform(this_trigger_waveforms_dict[n_channel])
								fig.update_layout(
									title = f'n_trigger {n_trigger}, n_channel {n_channel}<br><sup>Run: {John.run_name}</sup>',
								)
								path_to_save_plots = beta_scan_task_bureaucrat.path_to_directory_of_my_task/Path('plots of some of the waveforms')
								path_to_save_plots.mkdir(exist_ok=True)
								fig.write_html(
									str(path_to_save_plots/Path(f'n_trigger {n_trigger} n_channel {n_channel}.html')),
									include_plotlyjs = 'cdn',
								)
						reporter.update(1) 
	
	if not silent:
		print('Beta scan finished.')

def beta_scan_sweeping_bias_voltage(bureaucrat:RunBureaucrat, the_setup, n_triggers:int, bias_voltages:list, n_channels:list, software_trigger=None, silent=False):
	reporter = TelegramReporter(
		telegram_token = my_telegram_bots.robobot.token,
		telegram_chat_id = my_telegram_bots.chat_ids['Robobot TCT setup'],
	)
	
	with the_setup.hold_signal_acquisition(), the_setup.hold_control_of_bias():
		with reporter.report_for_loop(len(bias_voltages), bureaucrat.run_name) as reporter:
			with bureaucrat.handle_task('beta_scan_sweeping_bias_voltage') as employee:
				for bias_voltage in bias_voltages:
					beta_scan(
						bureaucrat = employee.create_subrun(f'{bureaucrat.run_name}_{int(bias_voltage)}V'),
						the_setup = the_setup,
						n_triggers = n_triggers,
						bias_voltage = bias_voltage,
						n_channels = n_channels,
						software_trigger = software_trigger,
						silent = silent,
					)

if __name__ == '__main__':
	import my_telegram_bots
	from configuration_files.current_run import Alberto
	from utils import create_a_timestamp
	from TheSetup import connect_me_with_the_setup
	import os
	
	def software_trigger(signals_dict):
		min_peak_time = 17e-9
		max_peak_time = 22e-9
		return any([min_peak_time<s.peak_start_time<max_peak_time for k,s in signals_dict.items()])
	
	with Alberto.handle_task('beta_scans', drop_old_data=False) as task_bureaucrat:
		Mariano = task_bureaucrat.create_subrun(create_a_timestamp() + '_' + input('Measurement name? ').replace(' ','_'))
		the_setup = connect_me_with_the_setup(who=f'beta_scan.py PID:{os.getpid()}')
		
		with the_setup.hold_control_of_bias():
			the_setup.set_current_compliance(amperes=10e-6)
			the_setup.set_bias_output_status('on')
			
			beta_scan_sweeping_bias_voltage(	
				bureaucrat = Mariano, 
				the_setup = the_setup, 
				n_triggers = 3333, 
				bias_voltages = interlace(numpy.linspace(99,220,33)),
				n_channels = [1,2,3,4], 
				software_trigger = software_trigger, 
				silent = False,
			)
