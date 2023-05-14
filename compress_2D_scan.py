from scan_2D import compress_waveforms_file_in_2D_scan
from the_bureaucrat.bureaucrats import RunBureaucrat # https://github.com/SengerM/the_bureaucrat
from pathlib import Path

if __name__ == '__main__':
	import argparse
	from grafica.plotly_utils.utils import set_my_template_as_default
	
	set_my_template_as_default()
	
	parser = argparse.ArgumentParser()
	parser.add_argument('--dir',
		metavar = 'path', 
		help = 'Path to the base measurement directory.',
		required = True,
		dest = 'directory',
		type = str,
	)
	
	args = parser.parse_args()
	
	bureaucrat = RunBureaucrat(Path(args.directory))
	compress_waveforms_file_in_2D_scan(bureaucrat, silent=False)
