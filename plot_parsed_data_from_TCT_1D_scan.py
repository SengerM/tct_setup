from scan_1D import plot_parsed_data_from_TCT_1D_scan
from the_bureaucrat.bureaucrats import RunBureaucrat # https://github.com/SengerM/the_bureaucrat
from pathlib import Path

if __name__ == '__main__':
	import argparse

	parser = argparse.ArgumentParser()
	parser.add_argument('--dir',
		metavar = 'path', 
		help = 'Path to the base measurement directory.',
		required = True,
		dest = 'directory',
		type = str,
	)
	
	args = parser.parse_args()
	
	Enrique = RunBureaucrat(Path(args.directory))
	plot_parsed_data_from_TCT_1D_scan(
		bureaucrat = Enrique,
		strict_task_checking = False,
	)
