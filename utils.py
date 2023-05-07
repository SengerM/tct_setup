import datetime
import time
from scipy.stats import median_abs_deviation
import sqlite3
import pandas
from pathlib import Path
from huge_dataframe.SQLiteDataFrame import load_only_index_without_repeated_entries, SQLiteDataFrameDumper # https://github.com/SengerM/huge_dataframe
from signals.PeakSignal import PeakSignal, compress_PeakSignal_V230507, decompress_PeakSignal_V230507 # https://github.com/SengerM/signals
import pickle
import zipfile

def create_a_timestamp():
	time.sleep(1) # This is to ensure that no two timestamps are the same.
	return datetime.datetime.now().strftime("%Y%m%d%H%M%S")

def integrate_distance_given_path(points:list):
	"""Given a list of points of the form `[(x0,y0,z0),(x1,y1,z1),...]`
	it calculates the distance at each point, starting from 0 and assuming
	linear interpolation."""
	def calculate_distance(p1, p2):
		return sum([(x1-x2)**2 for x1,x2 in zip(p1,p2)])**.5
	
	distance = [0]
	for i,p in enumerate(points):
		if i == 0:
			continue
		distance.append(distance[-1] + calculate_distance(points[i-1],p))
	return distance

def kMAD(x,nan_policy='omit'):
	"""Calculates the median absolute deviation multiplied by 1.4826... 
	which should converge to the standard deviation for Gaussian distributions,
	but is much more robust to outliers than the std."""
	k_MAD_TO_STD = 1.4826 # https://en.wikipedia.org/wiki/Median_absolute_deviation#Relation_to_standard_deviation
	return k_MAD_TO_STD*median_abs_deviation(x,nan_policy=nan_policy)

def interlace(lst):
	# https://en.wikipedia.org/wiki/Interlacing_(bitmaps)
	lst = sorted(lst)[::-1]
	if len(lst) == 1:
		return lst
	result = [lst[0], lst[-1]]
	ranges = [(1, len(lst) - 1)]
	for start, stop in ranges:
		if start < stop:
			middle = (start + stop) // 2
			result.append(lst[middle])
			ranges += (start, middle), (middle + 1, stop)
	return result

def compress_waveforms_sqlite(path_to_file:Path):
	"""Compress a `waveforms.sqlite` file which contains signals from
	LGADs, PMTs, etc. The compression is almost lossless and compression 
	rates range between 10 and 40 times smaller after compression."""
	waveforms_connection = sqlite3.connect(path_to_file)
	waveforms_index = load_only_index_without_repeated_entries(Path(path_to_file))
	
	path_to_temporary_pickle_file = path_to_file.parent/'compressed_waveforms.pickle'
	with zipfile.ZipFile(path_to_file.with_suffix('.zip'), 'w', zipfile.ZIP_DEFLATED) as myzip:
		with open(path_to_temporary_pickle_file, 'a+b') as pickle_file:
			for idx, row in waveforms_index.iterrows():
				waveform = pandas.read_sql(
					sql = f"SELECT * from dataframe_table WHERE " + " AND ".join([f"{name} is {val}" for name,val in zip(waveforms_index.columns, row)]),
					con = waveforms_connection,
				)
				signal = PeakSignal(
					time = waveform['Time (s)'],
					samples = waveform['Amplitude (V)'],
				)
				compressed_waveform = compress_PeakSignal_V230507(signal)
				pickle.dump(
					obj = compressed_waveform, 
					file = pickle_file
				)
		
		myzip.write(path_to_temporary_pickle_file)
		myzip.write(Path(__file__).resolve(), Path(__file__).parts[-1])
	path_to_temporary_pickle_file.unlink()

def decompress_waveforms_into_sqlite(path_to_file:Path):
	"""Decompress a file that was compressed with `compress_waveforms_sqlite`."""
	path_to_temporary_pickle_file = path_to_file.with_suffix('.pickle')
	with zipfile.ZipFile(path_to_file, 'r') as zip_file:
		with open(path_to_temporary_pickle_file, 'wb') as pickle_file:
			pickle_file.write(zip_file.read('compressed_waveforms.pickle'))
	
	with SQLiteDataFrameDumper(path_to_file.with_suffix('.sqlite'), dump_after_n_appends=1111) as sqlite_dumper:
		with open(path_to_temporary_pickle_file, 'rb') as pickle_file:
			n_waveform = 0
			while True:
				try:
					compressed_waveform = pickle.load(pickle_file)
					decompressed_signal = decompress_PeakSignal_V230507(compressed_waveform)
					
					waveform_df = pandas.DataFrame(
						{
							'Time (s)': decompressed_signal.time,
							'Amplitude (V)': decompressed_signal.samples,
						}
					)
					waveform_df['n_waveform'] = n_waveform
					waveform_df.set_index('n_waveform', inplace=True)
					sqlite_dumper.append(waveform_df)
					n_waveform += 1
				except EOFError:
					break
	path_to_temporary_pickle_file.unlink()

def save_dataframe(df, name:str, location:Path):
	for extension,method in {'pickle':df.to_pickle,'csv':df.to_csv}.items():
		method(location/f'{name}.{extension}')
