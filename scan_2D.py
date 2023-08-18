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
from multiprocessing import Process
from plotly_utils import scatter_histogram
import plotly.graph_objects as go
import logging

def TCT_2D_scan(bureaucrat:RunBureaucrat, the_setup, positions:list, acquire_channels:list, n_triggers_per_position:int=1, reporter:SafeTelegramReporter4Loops=None):
	"""Perform a 2D scan with the TCT setup.
	
	Arguments
	----------
	bureaucrat: RunBureaucrat
		The bureaucrat that will handle the measurement.
	the_setup:
		An object to control the hardware.
	positions: list of lists of tuples
		A 2 dimensional list of lists of tuples specifying the positions
		to measure. Each position is a tuple of float of the form `(x,y,z)`
		or `None` if it is going to be skipped. This 2 dimensional list
		must be of M×N, i.e. all rows and columns are complete and filled
		with `None` in those places to be skipped.
	acquire_channels: list of int
		A list with the number of the channels to acquire from the oscilloscope.
	n_triggers_per_position: int
		Number of triggers to record at each position.
	reporter: SafeTelegramReporter4Loops
		A reporter to report the progress of the script. Optional.
	"""
	bureaucrat.create_run(if_exists='skip')
	
	if len(set([len(l) for l in positions])) != 1:
		raise ValueError(f'`positions` is not a "matrix" in the sense that it is not M×N, it has rows of different lenghts. ')
	
	with bureaucrat.handle_task('TCT_2D_scan') as employee:
		n_position = 0
		flattened_positions = []
		df = []
		for n_y,l1 in enumerate(positions):
			for n_x,pos in enumerate(l1):
				if pos is None:
					continue
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
				n_position += 1
		df = pandas.DataFrame.from_records(df).set_index(['n_position','n_x','n_y'])
		utils.save_dataframe(df, 'positions', employee.path_to_directory_of_my_task)
		
		TCT_1D_scan(
			bureaucrat = employee.create_subrun(bureaucrat.run_name + '_Flattened1DScan'), 
			the_setup = the_setup, 
			positions = flattened_positions, 
			acquire_channels = acquire_channels, 
			n_triggers_per_position = n_triggers_per_position, 
			reporter = reporter, 
		)

def compress_waveforms_file_in_2D_scan(bureaucrat:RunBureaucrat):
	if len(bureaucrat.list_subruns_of_task('TCT_2D_scan')) != 1:
		raise RuntimeError(f'Run {repr(bureaucrat.run_name)} located in "{bureaucrat.path_to_run_directory}" seems to be corrupted because I was expecting only a single subrun for the task "TCT_2D_scan" but it actually has {len(bureaucrat.list_subruns_of_task("TCT_2D_scan"))} subruns...')
	flattened_1D_scan_subrun_bureaucrat = bureaucrat.list_subruns_of_task('TCT_2D_scan')[0]	
	path_to_waveforms_file = flattened_1D_scan_subrun_bureaucrat.path_to_directory_of_task('TCT_1D_scan')/'waveforms.sqlite'
	logging.info(f'Compressing waveforms file in "{path_to_waveforms_file}"...')
	utils.compress_waveforms_sqlite(path_to_waveforms_file)
	logging.info(f'Finished compressing waveforms file in "{path_to_waveforms_file}". ')
	path_to_waveforms_file.unlink()

def plot_everything_from_TCT_2D_scan(bureaucrat:RunBureaucrat):
	"""Produce a set of general plots to explore the results from a 2D scan."""
	bureaucrat.check_these_tasks_were_run_successfully('TCT_2D_scan')
	
	with bureaucrat.handle_task('plot_everything_from_TCT_2D_scan') as employee:
		logging.info(f'Reading data from {repr(bureaucrat.run_name)}...')
		if len(bureaucrat.list_subruns_of_task('TCT_2D_scan')) != 1:
			raise RuntimeError(f'Run {repr(bureaucrat.run_name)} located in "{bureaucrat.path_to_run_directory}" seems to be corrupted because I was expecting only a single subrun for the task "TCT_2D_scan" but it actually has {len(bureaucrat.list_subruns_of_task("TCT_2D_scan"))} subruns...')
		flattened_1D_scan_subrun_bureaucrat = bureaucrat.list_subruns_of_task('TCT_2D_scan')[0]
		data = load_whole_dataframe(flattened_1D_scan_subrun_bureaucrat.path_to_directory_of_task('TCT_1D_scan')/'parsed_from_waveforms.sqlite')
		
		positions_data = pandas.read_pickle(bureaucrat.path_to_directory_of_task('TCT_2D_scan')/'positions.pickle')
		positions_data.reset_index(['n_x','n_y'], drop=False, inplace=True)
		for _ in {'x','y'}: # Remove offset so (0,0) is the center...
			positions_data[f'{_} (m)'] -= positions_data[f'{_} (m)'].mean()
		
		# ~ utils.create_parallel_xy_grid_from_tilted_xy_grid(positions_data)

		data = data.query('n_pulse==1')
		averages = data.groupby(['n_position','n_channel']).agg(numpy.nanmedian)
		
		averages = averages.merge(positions_data, left_index=True, right_index=True)
		
		# Plot as function of nx,ny:
		logging.info('Producing plots as function of n_x,n_y...')
		averages.reset_index(inplace=True, drop=False)
		averages.set_index(['n_y','n_x','n_channel'], inplace=True)
		path_for_nx_ny_plots = employee.path_to_directory_of_my_task/'nx_ny'
		path_for_nx_ny_plots.mkdir()
		for col in averages.columns.get_level_values(0).drop_duplicates():
			if col in {'n_position'}:
				continue
			data_to_plot_xarray = averages[col].to_xarray()
			fig = px.imshow(
				title = f'{col}<br><sup>{bureaucrat.run_name}</sup>',
				img = data_to_plot_xarray,
				aspect = 'equal',
				facet_col = 'n_channel',
				width = 555*len(data_to_plot_xarray.coords['n_channel']),
				origin = 'lower',
			)
			fig.update_coloraxes(colorbar_title_side='right')
			fig.write_html(
				path_for_nx_ny_plots/f'{col}_nx_ny.html',
				include_plotlyjs = 'cdn',
			)
		fig = px.imshow(
			title = f'sum(Amplitude (V))<br><sup>{bureaucrat.run_name}</sup>',
			img = averages['Amplitude (V)'].groupby(['n_y','n_x']).sum().to_xarray(),
			aspect = 'equal',
			origin = 'lower',
		)
		fig.update_coloraxes(colorbar_title_side='right')
		fig.write_html(
			path_for_nx_ny_plots/f'sum(Amplitude (V))_nx_ny.html',
			include_plotlyjs = 'cdn',
		)
		
		# Plot as function of x,y:
		logging.info('Producing plots as a function of x,y...')
		xy_table = pandas.pivot_table(
			data = averages,
			values = averages.columns,
			index = ['y (m)','n_channel'],
			columns = 'x (m)',
		)
		path_for_x_y_plots = employee.path_to_directory_of_my_task/'xy'
		path_for_x_y_plots.mkdir()
		for col in set(xy_table.columns.get_level_values(0)):
			numpy_array = numpy.array([numpy.flip(xy_table[col].query(f'n_channel=={n_channel}').to_numpy(),axis=1) for n_channel in sorted(set(xy_table[col].index.get_level_values('n_channel')))])
			fig = px.imshow(
				numpy_array,
				title = f'{col} as a function of position<br><sup>{bureaucrat.run_name}</sup>',
				aspect = 'equal',
				labels = dict(
					color = col,
					x = 'x (m)',
					y = 'y (m)',
				),
				x = xy_table[col].columns,
				y = xy_table[col].index.get_level_values(0).drop_duplicates(),
				facet_col = 0,
				origin = 'lower',
				width = 555*len(numpy_array),
			)
			fig.update_coloraxes(colorbar_title_side='right')
			for i,n_channel in enumerate(sorted(set(xy_table[col].index.get_level_values('n_channel')))):
				fig.layout.annotations[i].update(text=f'n_channel:{n_channel}')
			fig.write_html(
				path_for_x_y_plots/f'{col}.html',
				include_plotlyjs = 'cdn',
			)
		
		# Plot some histograms:
		logging.info('Producing histogram plots...')
		for col in {'t_50 (s)','Amplitude (V)'}:
			fig = go.Figure()
			for n_channel in sorted(set(data.index.get_level_values('n_channel'))):
				fig.add_trace(
					scatter_histogram(
						samples = data.query('n_pulse==1').query(f'n_channel=={n_channel}')[col],
						name = f'n_channel={n_channel}',
					)
				)
			fig.update_yaxes(type="log", title='counts')
			fig.update_xaxes(title=col)
			fig.update_layout(
				title = f'{col} distribution<br><sup>{bureaucrat.run_name}</sup>',
			)
			fig.write_html(
				employee.path_to_directory_of_my_task/f'{col}_histogram.html',
				include_plotlyjs = 'cdn',
			)
	logging.info('Finished plotting 2D scan!')

def TCT_2D_scans_sweeping_bias_voltage(bureaucrat:RunBureaucrat, the_setup, voltages:list, positions:list, acquire_channels:list, n_triggers_per_position:int=1, reporter:SafeTelegramReporter4Loops=None, compress_waveforms_files:bool=True):
	bureaucrat.create_run(if_exists='skip')
	
	with bureaucrat.handle_task('TCT_2D_scans_sweeping_bias_voltage') as employee:
		with reporter.report_loop(len(voltages), bureaucrat.run_name) if reporter is not None else nullcontext() as reporter:
			for voltage in voltages:
				logging.info(f'Setting bias voltage to {voltage} V...')
				the_setup.set_bias_voltage(volts=voltage)
				
				b = employee.create_subrun(f'{bureaucrat.run_name}_{int(voltage)}V')
				TCT_2D_scan(
					bureaucrat = b,
					the_setup = the_setup,
					positions = positions,
					acquire_channels = acquire_channels,
					n_triggers_per_position = n_triggers_per_position,
					reporter = reporter.create_subloop_reporter() if reporter is not None else None,
				)
				
				logging.info(f'Producing plots for {b.run_name}...')
				plot_everything_from_TCT_2D_scan(b)
				
				if compress_waveforms_files:
					logging.info(f'Compressing waveforms file...')
					p = Process(target=compress_waveforms_file_in_2D_scan, args=(b, False))
					p.start() # Let's hope this ends before the next 2D scan finishes, otherwise this becomes a snowball...
				
				reporter.update(1) if reporter is not None else None

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
	
	#######################################################
	
	X_SPAN = 1111e-6
	Y_SPAN = X_SPAN
	X_STEP = 25e-6
	Y_STEP = X_STEP
	DEVICE_NAME = 'AC70'
	DEVICE_CENTER = (-3817e-6,1914e-6+200e-6,74292e-6)
	ROTATION_ANGLE_DEG = 45
	VOLTAGES = [111]
	LASER_DAC = 111
	N_TRIGGERS_PER_POSITION = 22
	CURRENT_COMPLIANCE_AMPERES = 11e-6
	REMOVE_PADS = None#dict(
		# ~ pitch = 500e-6,
		# ~ size = 200e-6,
		# ~ shape = 'square',
	# ~ )
	
	#######################################################
	
	set_my_template_as_default()
	
	def create_list_of_positions(device_center_xyz:tuple, x_span:float, y_span:float, x_step:float, y_step:float, rotation_angle_deg:float, readout_pads_to_remove:dict=None):
		x = numpy.linspace(-x_span/2, x_span/2, int(x_span/x_step+1))
		y = numpy.linspace(-y_span/2, y_span/2, int(y_span/y_step+1))
		
		xx, yy = numpy.meshgrid(x, y)
		
		# Apply rotation
		phi = numpy.arctan2(yy,xx)
		cos = numpy.cos(rotation_angle_deg*numpy.pi/180+phi)
		sin = numpy.sin(rotation_angle_deg*numpy.pi/180+phi)
		rr = (xx**2+yy**2)**.5
		xx, yy = rr*cos, rr*sin
		
		xx += device_center_xyz[0]
		yy += device_center_xyz[1]
		zz = xx*0 + device_center_xyz[2]
		
		remove_these = numpy.full(xx.shape, False)
		if isinstance(readout_pads_to_remove, dict):
			pitch = readout_pads_to_remove['pitch']
			size = readout_pads_to_remove['size']
			if readout_pads_to_remove['shape'] != 'square':
				raise ValueError('Only implemented for square pads. ')
			for row in [-1,1]:
				for col in [-1,1]:
					remove_these |= (xx-device_center_xyz[0]>(col*pitch-size)/2) & (xx-device_center_xyz[0]<(col*pitch+size)/2) & (yy-device_center_xyz[1]>(row*pitch-size)/2) & (yy-device_center_xyz[1]<(row*pitch+size)/2)
		
		positions = [[(xx[nx,ny],yy[nx,ny],zz[nx,ny]) if remove_these[nx,ny]==False else None for ny in range(len(xx[nx]))] for nx in range(len(xx))]
		
		return positions
	
	is_preview = input("Preview? (yes/no) ")
	if is_preview not in {'yes','no'}:
		raise ValueError(f'Your answer has to be either yes or no, but you said {repr(is_preview)}.')
	is_preview = is_preview == 'yes'
	
	if is_preview:
		logging.info('Preview mode enabled!')
		X_STEP = X_SPAN/8
		Y_STEP = Y_SPAN/8
		VOLTAGES = [VOLTAGES[0]]
	
	the_setup = connect_me_with_the_setup(who=f'scan_2D.py PID:{os.getpid()}')
	with Alberto.handle_task('TCT_scans', drop_old_data=False) as employee:
		with the_setup.hold_control_of_bias(), the_setup.hold_tct_control():
			try:
				Mariano = employee.create_subrun(create_a_timestamp() + '_' + DEVICE_NAME + ('_preview' if is_preview else '') + f'_Step{X_STEP*1e6:.0f}um' + f'_n_trigs{N_TRIGGERS_PER_POSITION}')
			
				the_setup.set_current_compliance(amperes=CURRENT_COMPLIANCE_AMPERES)
				the_setup.set_bias_output_status('on')
				the_setup.set_laser_DAC(LASER_DAC)
				the_setup.set_laser_frequency(1000)
				the_setup.set_laser_status('on')
				
				TCT_2D_scans_sweeping_bias_voltage(
					bureaucrat = Mariano,
					the_setup = the_setup,
					voltages = VOLTAGES,
					positions = create_list_of_positions(
						device_center_xyz = DEVICE_CENTER,
						x_span = X_SPAN,
						y_span = Y_SPAN,
						x_step = X_STEP,
						y_step = Y_STEP,
						readout_pads_to_remove = REMOVE_PADS,
						rotation_angle_deg = ROTATION_ANGLE_DEG,
					),
					acquire_channels = list(range(16)),
					n_triggers_per_position = N_TRIGGERS_PER_POSITION,
					reporter = SafeTelegramReporter4Loops(
						bot_token = my_telegram_bots.robobot.token, 
						chat_id = my_telegram_bots.chat_ids['Robobot TCT setup'],
					),
					compress_waveforms_files = True,
				)
			finally:
				logging.info('Finalizing scan...')
				logging.info('Turning off bias voltage... (patience please)')
				the_setup.set_bias_output_status('off')
				logging.info('Turning laser off...')
				the_setup.set_laser_status('off')
				logging.info('High voltage and laser are off.')
