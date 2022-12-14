from the_bureaucrat.bureaucrats import RunBureaucrat # https://github.com/SengerM/the_bureaucrat
from pathlib import Path
from time import sleep
import pandas
import plotly.express as px
import datetime
from grafica.plotly_utils.utils import line
from huge_dataframe.SQLiteDataFrame import SQLiteDataFrameDumper, load_whole_dataframe # https://github.com/SengerM/huge_dataframe
from contextlib import nullcontext
from progressreporting.TelegramProgressReporter import TelegramReporter # https://github.com/SengerM/progressreporting

def iv_curve_measure(bureaucrat:RunBureaucrat, the_setup, voltages:list, current_limit_amperes:float, n_measurements_per_voltage:int, time_between_each_measurement_seconds:float, time_after_changing_voltage_seconds:float, silent:bool=True, reporter:TelegramReporter=None):
	"""Perform an IV curve measurement using the high voltage power supply.
	
	Arguments
	----------
	bureaucrat: RunBureaucrat
		The bureaucrat that will handle the measurement.
	the_setup:
		An object to control the hardware.
	voltages: list of float
		Voltages at which to measure.
	current_limit_amperes: float
		Value for the limit of current in Ampere.
	n_measurements_per_voltage: int
		Number of measurements at each fixed voltage.
	time_between_each_measurement_seconds: float
		Number of seconds to wait between two consecutive measurements 
		at the same voltage.
	time_after_changing_voltage_seconds: float
		Number of seconds to wait after a new voltage has been applied 
		before start to taking data.
	silent: bool, default True
		If `True`, not messages will be printed. If `False`, messages will
		be printed showing the progress of the measurement.
	reporter: TelegramReporter
		A reporter to report the progress of the script. Optional.
	"""
	current_current_compliance = the_setup.get_current_compliance()
	try:
		JuanCarlos = bureaucrat
		the_setup.set_laser_status('off')
		with JuanCarlos.handle_task('iv_curve_measure') as JuanCarlos_employee:
			the_setup.set_current_compliance(amperes=current_limit_amperes)
			the_setup.set_bias_output_status(status='on')
			report_progress = reporter is not None
			with reporter.report_for_loop(len(voltages)*n_measurements_per_voltage, f'{JuanCarlos.run_name}') if report_progress else nullcontext() as reporter:
				with SQLiteDataFrameDumper(
					JuanCarlos_employee.path_to_directory_of_my_task/'measured_data.sqlite',
					dump_after_n_appends = 1e3,
					dump_after_seconds = 10,
				) as data_dumper:
					for n_voltage, voltage in enumerate(voltages):
						the_setup.set_bias_voltage(volts=voltage)
						sleep(time_after_changing_voltage_seconds)
						for n_measurement in range(n_measurements_per_voltage):
							if not silent:
								print(f'Measuring n_voltage={n_voltage}/{len(voltages)-1} n_measurement={n_measurement}/{n_measurements_per_voltage-1}')
							sleep(time_between_each_measurement_seconds)
							measured_data_df = pandas.DataFrame(
								{
									'n_voltage': n_voltage,
									'n_measurement': n_measurement,
									'When': datetime.datetime.now(),
									'Bias voltage (V)': the_setup.measure_bias_voltage(),
									'Bias current (A)': the_setup.measure_bias_current(),
									'Temperature (??C)': the_setup.measure_temperature(),
									'Humidity (%RH)': the_setup.measure_humidity(),
								},
								index = [0],
							)
							measured_data_df.set_index(['n_voltage','n_measurement'], inplace=True)
							data_dumper.append(measured_data_df)
							if report_progress:
								reporter.update(1)
	finally:
		the_setup.set_current_compliance(amperes=current_current_compliance)

def iv_curve_plot(bureaucrat:RunBureaucrat):
	JuanCarlos = bureaucrat
	
	with JuanCarlos.handle_task('iv_curve_plot') as JuanCarlos_employee:
		# Do a plot ---
		measured_data_df = load_whole_dataframe(JuanCarlos.path_to_directory_of_task('iv_curve_measure')/'measured_data.sqlite').reset_index()
		mean_measured_data_df = measured_data_df.groupby(by='n_voltage').mean().reset_index()
		mean_measured_data_df['Bias current std (A)'] = measured_data_df.groupby(by='n_voltage').std()['Bias current (A)']
		mean_measured_data_df['Bias current (A)'] *= -1 # So the logarithmic plot don't fails.
		mean_measured_data_df['Bias voltage (V)'] *= -1 # So the curve is in the positive quadrant.
		fig = line(
			data_frame = mean_measured_data_df,
			x = 'Bias voltage (V)',
			y = 'Bias current (A)',
			error_y = 'Bias current std (A)',
			error_y_mode = 'band',
			title = f'IV curve<br><sup>Measurement: {JuanCarlos.run_name}</sup>',
			markers = '.',
			# ~ hover_data = ['Temperature (??C)','Humidity (%RH)','n_voltage'],
		)
		fig.write_html(str(JuanCarlos_employee.path_to_directory_of_my_task/Path(f'iv_curve_lin_scale.html')), include_plotlyjs='cdn')
		fig.update_yaxes(type='log')
		fig.write_html(str(JuanCarlos_employee.path_to_directory_of_my_task/Path(f'iv_curve_log_scale.html')), include_plotlyjs='cdn')

if __name__ == '__main__':
	import numpy as np
	import my_telegram_bots
	from configuration_files.current_run import Alberto
	from utils import create_a_timestamp
	from TheSetup import connect_me_with_the_setup
	import os
	
	VOLTAGES = np.linspace(0,166,11)
	
	with Alberto.handle_task('iv_curves', drop_old_data=False) as iv_curves_task_bureaucrat:
		Mariano = iv_curves_task_bureaucrat.create_subrun(create_a_timestamp() + '_' + input('Measurement name? ').replace(' ','_'))
		
		iv_curve_measure(
			bureaucrat = Mariano,
			voltages = list(VOLTAGES) + list(VOLTAGES)[::-1],
			current_limit_amperes = 10e-6,
			n_measurements_per_voltage = 2,
			time_between_each_measurement_seconds = .1,
			time_after_changing_voltage_seconds = 1,
			the_setup = connect_me_with_the_setup(who=f'iv_curve.py PID:{os.getpid()}'),
			silent = False,
			reporter = TelegramReporter(
				telegram_token = my_telegram_bots.robobot.token, 
				telegram_chat_id = my_telegram_bots.chat_ids['Robobot TCT setup'],
			)
		)
		
		iv_curve_plot(bureaucrat = Mariano)
