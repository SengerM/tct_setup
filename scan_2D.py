from the_bureaucrat.bureaucrats import RunBureaucrat # https://github.com/SengerM/the_bureaucrat
from pathlib import Path
import pandas
from contextlib import nullcontext
from progressreporting.TelegramProgressReporter import SafeTelegramReporter4Loops # https://github.com/SengerM/progressreporting
from scan_1D import TCT_1D_scan
import numpy
import utils
from huge_dataframe.SQLiteDataFrame import load_whole_dataframe
import plotly.express as px

def TCT_2D_scan(bureaucrat:RunBureaucrat, the_setup, positions:list, acquire_channels:list, n_triggers_per_position:int=1, silent=True, reporter:SafeTelegramReporter4Loops=None, compress_waveforms_file:bool=True):
	"""Perform a 2D scan with the TCT setup.
	
	Arguments
	----------
	bureaucrat: RunBureaucrat
		The bureaucrat that will handle the measurement.
	the_setup:
		An object to control the hardware.
	positions: list of lists of tuples
		A 2 dimensional list of lists of tuples specifying the positions
		to measure. Each position is a tuple of float of the form `(x,y,z)`.
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
	bureaucrat.create_run(if_exists='skip')
	
	with bureaucrat.handle_task('TCT_2D_scan') as employee:
		n_x = 0
		n_position = 0
		flattened_positions = []
		df = []
		for l1 in positions:
			n_y = 0
			for pos in l1:
				df.append(
					{
						'n_x': n_x,
						'n_y': n_y,
						'n_position': n_position,
						'x (m)': pos[0],
						'y (m)': pos[1],
						'z (m)': pos[2],
					}
				)
				flattened_positions.append(pos)
				n_y += 1
				n_position += 1
			n_x += 1
		df = pandas.DataFrame.from_records(df).set_index(['n_position','n_x','n_y'])
		utils.save_dataframe(df, 'positions', employee.path_to_directory_of_my_task)
		
		TCT_1D_scan(
			bureaucrat = employee.create_subrun(bureaucrat.run_name + '_Flattened1DScan'), 
			the_setup = the_setup, 
			positions = flattened_positions, 
			acquire_channels = acquire_channels, 
			n_triggers_per_position = n_triggers_per_position, 
			silent = silent, 
			reporter = reporter, 
			compress_waveforms_file = compress_waveforms_file
		)

def plot_everything_from_TCT_2D_scan(bureaucrat:RunBureaucrat):
	bureaucrat.check_these_tasks_were_run_successfully('TCT_2D_scan')
	
	with bureaucrat.handle_task('plot_everything_from_TCT_2D_scan') as employee:
		if len(bureaucrat.list_subruns_of_task('TCT_2D_scan')) != 1:
			raise RuntimeError(f'Run {repr(bureaucrat.run_name)} located in "{bureaucrat.path_to_run_directory}" seems to be corrupted because I was expecting only a single subrun for the task "TCT_2D_scan" but it actually has {len(bureaucrat.list_subruns_of_task("TCT_2D_scan"))} subruns...')
		flattened_1D_scan_subrun_bureaucrat = bureaucrat.list_subruns_of_task('TCT_2D_scan')[0]
		parsed_from_waveforms = load_whole_dataframe(flattened_1D_scan_subrun_bureaucrat.path_to_directory_of_task('TCT_1D_scan')/'parsed_from_waveforms.sqlite')
		positions_data = pandas.read_pickle(bureaucrat.path_to_directory_of_task('TCT_2D_scan')/'positions.pickle')
		positions_data.reset_index(['n_x','n_y'], drop=False, inplace=True)

		data = parsed_from_waveforms.merge(positions_data, left_index=True, right_index=True)
		data.set_index(['n_x','n_y'], append=True, inplace=True)
		for _ in {'x','y'}:
			data[f'{_} (m)'] -= data[f'{_} (m)'].mean()
		averages = data.groupby(['n_pulse','n_channel','n_x','n_y']).agg(numpy.nanmedian)
		averages = averages.query('n_pulse==1')
		
		xy_table = pandas.pivot_table(
			data = averages,
			values = averages.columns,
			index = ['y (m)','n_channel'],
			columns = 'x (m)',
		)
		for col in set(xy_table.columns.get_level_values(0)):
			numpy_array = numpy.array([xy_table[col].query(f'n_channel=={n_channel}').to_numpy() for n_channel in sorted(set(xy_table[col].index.get_level_values('n_channel')))])
			
			fig = px.imshow(
				numpy_array,
				title = f'{col}<br><sup>{bureaucrat.run_name}</sup>',
				aspect = 'equal',
				labels = dict(
					color = col,
					x = 'x (m)',
					y = 'y (m)',
				),
				x = xy_table[col].columns,
				y = xy_table[col].index.get_level_values(0).drop_duplicates(),
				facet_col = 0,
			)
			for i,n_channel in enumerate(sorted(set(xy_table[col].index.get_level_values('n_channel')))):
				fig.layout.annotations[i].update(text=f'n_channel:{n_channel}')
			fig.write_html(
				employee.path_to_directory_of_my_task/f'{col}.html',
				include_plotlyjs = 'cdn',
			)

if __name__ == '__main__':
	import my_telegram_bots
	from configuration_files.current_run import Alberto
	from utils import create_a_timestamp
	from TheSetup import connect_me_with_the_setup
	import os
	from grafica.plotly_utils.utils import set_my_template_as_default
	
	set_my_template_as_default()
	
	def create_list_of_positions(device_center_xyz:tuple, x_span:float, y_span:float, x_step:float, y_step:float):
		x = numpy.linspace(-x_span/2, x_span/2, int(x_span/x_step+1))
		y = numpy.linspace(-y_span/2, y_span/2, int(y_span/y_step+1))
		
		xx, yy = numpy.meshgrid(x, y)
		zz = xx*0 + device_center_xyz[2]
		
		xx += device_center_xyz[0]
		yy += device_center_xyz[1]
		
		positions = [[(xx[nx,ny],yy[nx,ny],zz[nx,ny]) for ny in range(len(xx[nx]))] for nx in range(len(xx))]
		
		return positions
	
	the_setup = connect_me_with_the_setup(who=f'iv_curve.py PID:{os.getpid()}')
	
	with Alberto.handle_task('TCT_scans', drop_old_data=False) as employee:
		with the_setup.hold_control_of_bias(), the_setup.hold_tct_control():
			try:
				plot_everything_from_TCT_2D_scan(RunBureaucrat(Path('/home/tct/power_storage/senger_matias/TCT_data/deleteme/TCT_scans/subruns/20230507225347_DEBUGGING_TCT2DScan')))
				# ~ Mariano = employee.create_subrun(create_a_timestamp() + '_' + f'DEBUGGING_TCT2DScan')
			
				# ~ the_setup.set_current_compliance(amperes=20e-6)
				# ~ the_setup.set_bias_output_status('on')
				# ~ the_setup.set_laser_DAC(600)
				# ~ the_setup.set_laser_frequency(1000)
				# ~ the_setup.set_laser_status('on')
				
				# ~ the_setup.set_bias_voltage(volts=222)
				
				# ~ TCT_2D_scan(
					# ~ bureaucrat = Mariano,
					# ~ the_setup = the_setup,
					# ~ positions = create_list_of_positions(
						# ~ device_center_xyz = (-3620e-6,-145e-6,67957e-6),
						# ~ x_span = 500e-6,
						# ~ y_span = 500e-6,
						# ~ x_step = 25e-6,
						# ~ y_step = 25e-6,
					# ~ ),
					# ~ acquire_channels = [1,2,3,4],
					# ~ n_triggers_per_position = 22,
					# ~ silent = False, 
					# ~ reporter = SafeTelegramReporter4Loops(
						# ~ bot_token = my_telegram_bots.robobot.token, 
						# ~ chat_id = my_telegram_bots.chat_ids['Robobot TCT setup'],
					# ~ )
				# ~ )
				# ~ plot_everything_from_TCT_2D_scan(Mariano)
			finally:	
				# ~ the_setup.set_bias_output_status('off')
				the_setup.set_laser_status('off')
