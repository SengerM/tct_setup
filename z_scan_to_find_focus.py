from the_bureaucrat.bureaucrats import RunBureaucrat, TaskBureaucrat # https://github.com/SengerM/the_bureaucrat
from pathlib import Path
import datetime
import plotly.express as px
from scan_1D import TCT_1D_scan, plot_parsed_data_from_TCT_1D_scan
import numpy
from huge_dataframe.SQLiteDataFrame import load_whole_dataframe # https://github.com/SengerM/huge_dataframe
import plotly_utils
import logging

def create_list_of_positions_for_z_scan(scan_center:tuple, z_length:float, z_step:float):
		z = scan_center[2] + numpy.linspace(-z_length/2, z_length/2, int(z_length/z_step))
		x = scan_center[0] + z*0
		y = scan_center[1] + z*0
		return [(xx,yy,zz) for xx,yy,zz in zip(x,y,z)]

def z_scan_to_find_focus(bureaucrat:RunBureaucrat, scan_center:tuple, z_length:float, z_step:float, the_setup):
	bureaucrat.create_run(if_exists='skip')
	
	with bureaucrat.handle_task('z_scan_to_find_focus') as employee:
		subrun = employee.create_subrun(bureaucrat.run_name + '_TCT_1D_scan')
		TCT_1D_scan(
			bureaucrat = subrun,
			the_setup = the_setup,
			positions = create_list_of_positions_for_z_scan(
				scan_center = scan_center,
				z_length = z_length,
				z_step = z_step,
			),
			acquire_channels = list(range(16)),
			n_triggers_per_position = 11,
		)
		plot_parsed_data_from_TCT_1D_scan(bureaucrat = subrun)
		(subrun.path_to_directory_of_task('TCT_1D_scan')/'waveforms.sqlite').unlink() # Remove useless and heavy waveforms file.

def plot_z_scan_to_find_focus(bureaucrat:RunBureaucrat):
	bureaucrat.check_these_tasks_were_run_successfully('z_scan_to_find_focus')
	
	with bureaucrat.handle_task('plot_z_scan_to_find_focus') as employee:
		data = load_whole_dataframe(bureaucrat.list_subruns_of_task('z_scan_to_find_focus')[0].path_to_directory_of_task('TCT_1D_scan')/'parsed_from_waveforms.sqlite')
		position_data = load_whole_dataframe(bureaucrat.list_subruns_of_task('z_scan_to_find_focus')[0].path_to_directory_of_task('TCT_1D_scan')/'measured_data.sqlite')
		position_data = position_data[[f'{_} (m)' for _ in ['x','y','z']]]
		
		data = data.groupby(['n_position','n_pulse','n_channel']).agg([('average',numpy.nanmedian),('fluctuations',numpy.nanstd)])
		
		data.columns = [' '.join(col) for col in data.columns]
		
		data = data.merge(position_data, left_index=True, right_index=True)
		
		fig = plotly_utils.line(
			data_frame = data.reset_index(drop=False),
			x = 'z (m)',
			y = 'Amplitude (V) average',
			error_y = 'Amplitude (V) fluctuations',
			error_y_mode = 'bands',
			color = 'n_channel',
			line_dash = 'n_pulse',
			title = f'Amplitude vs z to find focus<br><sup>{bureaucrat.run_name}</sup>',
			labels = {
				'z (m) average': 'z (m)',
				'Amplitude (V) average': 'Amplitude (V)',
			},
		)
		fig.write_html(
			str(employee.path_to_directory_of_my_task/f'amplitude_vs_z.html'),
			include_plotlyjs = 'cdn',
		)

if __name__ == '__main__':
	import my_telegram_bots
	from configuration_files.current_run import Alberto
	from utils import create_a_timestamp
	from TheSetup import connect_me_with_the_setup
	import os
	from plotly_utils import set_my_template_as_default
	import sys
	
	logging.basicConfig(
		stream = sys.stderr, 
		level = logging.INFO,
		format = '%(asctime)s|%(levelname)s|%(funcName)s|%(message)s',
		datefmt = '%Y-%m-%d %H:%M:%S',
	)
	
	
	plot_z_scan_to_find_focus(RunBureaucrat(Path('/home/tct/power_storage/senger_matias/TCT_data/CNM_AC-LGAD/TCT_scans/subruns/20230816111533_CNM_AC-LGAD_testing_CAEN_z_scan_to_find_focus')))
	# ~ plot_parsed_data_from_TCT_1D_scan(RunBureaucrat(Path('/home/tct/power_storage/senger_matias/TCT_data/CNM_AC-LGAD/TCT_scans/subruns/20230816111533_CNM_AC-LGAD_testing_CAEN_z_scan_to_find_focus/z_scan_to_find_focus/subruns/20230816111533_CNM_AC-LGAD_testing_CAEN_z_scan_to_find_focus_TCT_1D_scan')))
	
	a
	
	####################################################################
	VOLTAGE = 111
	SCAN_CENTER = (-3817e-6,1914e-6+200e-6,75019e-6)
	Z_LENGTH = 11e-3
	Z_STEP = .2e-3
	LASER_DAC = 111
	CURRENT_COMPLIANCE_AMPERES = 11e-6
	####################################################################
	
	set_my_template_as_default()
	
	the_setup = connect_me_with_the_setup(who=f'z_scan_to_find_focus.py PID:{os.getpid()}')
	
	with Alberto.handle_task('TCT_scans', drop_old_data=False) as employee:
		with the_setup.hold_control_of_bias(), the_setup.hold_tct_control():
			try:
				Mariano = employee.create_subrun(create_a_timestamp() + '_' + f'{input("Device name? ")}_z_scan_to_find_focus')
				
				the_setup.set_current_compliance(amperes=CURRENT_COMPLIANCE_AMPERES)
				the_setup.set_bias_output_status('on')
				the_setup.set_laser_DAC(LASER_DAC)
				the_setup.set_laser_frequency(1000)
				the_setup.set_laser_status('on')
				logging.info(f'Setting bias voltage to {VOLTAGE} V...')
				the_setup.set_bias_voltage(volts=VOLTAGE)
				
				z_scan_to_find_focus(
					bureaucrat = Mariano,
					the_setup = the_setup,
					scan_center = SCAN_CENTER,
					z_length = Z_LENGTH,
					z_step = Z_STEP,
				)
				plot_z_scan_to_find_focus(Mariano)
			finally:	
				logging.info('Finalizing scan...')
				logging.info('Turning off bias voltage... (patience please)')
				the_setup.set_bias_output_status('off')
				logging.info('Turning laser off...')
				the_setup.set_laser_status('off')
				logging.info('High voltage and laser are off.')
