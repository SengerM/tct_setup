import PyticularsTCT # https://github.com/SengerM/PyticularsTCT
from PyticularsTCT.find_ximc_stages import map_coordinates_to_serial_ports # https://github.com/SengerM/PyticularsTCT
import TeledyneLeCroyPy # https://github.com/SengerM/TeledyneLeCroyPy
from keithley.Keithley2470 import Keithley2470SafeForLGADs # https://github.com/SengerM/keithley
from time import sleep
import warnings
from processfriendlylock.CrossProcessLock import CrossProcessNamedLock # https://github.com/SengerM/processfriendlylock
import EasySensirion # https://github.com/SengerM/EasySensirion
# ~ import ElectroAutomatikGmbHPy # https://github.com/SengerM/ElectroAutomatikGmbHPy
# ~ from ElectroAutomatikGmbHPy.ElectroAutomatikGmbHPowerSupply import ElectroAutomatikGmbHPowerSupply # https://github.com/SengerM/ElectroAutomatikGmbHPy
from threading import RLock
from multiprocessing.managers import BaseManager
from pathlib import Path

class TheTCTSetup:
	def __init__(self):
		self._LeCroy = TeledyneLeCroyPy.LeCroyWaveRunner('USB0::1535::4131::2810N60091::0::INSTR')
		
		stages_coordinates = {
			'00003A48': 'x',
			'00003A57': 'y',
			'000038CE': 'z',
		}
		ports_dict = map_coordinates_to_serial_ports(stages_coordinates)
		self._tct = PyticularsTCT.TCT(x_stage_port=ports_dict['x'], y_stage_port=ports_dict['y'], z_stage_port=ports_dict['z'])
		
		self._keithley = Keithley2470SafeForLGADs('USB0::1510::9328::04481179::0::INSTR', polarity = 'negative')
		
		# ~ list_of_Elektro_Automatik_devices_connected = ElectroAutomatikGmbHPy.find_elektro_automatik_devices()
		# ~ if len(list_of_Elektro_Automatik_devices_connected) == 1:
			# ~ self._peltier_DC_power_supply = ElectroAutomatikGmbHPowerSupply(list_of_Elektro_Automatik_devices_connected[0]['port'])
		# ~ else:
			# ~ raise RuntimeError(f'Cannot autodetect the Elektro-Automatik power source because eiter it is not connected to the computer or there is more than one Elektro-Automatik device connected.')
		
		self._sensirion_sensor = EasySensirion.SensirionSensor()
		
		# Hardware specific locks ---
		self._oscilloscope_Lock = RLock()
		self._tct_Lock = RLock()
		self._keithley_Lock = RLock()
		self._sensirion_Lock = RLock()
		self._peltier_DC_power_supply_Lock = RLock()
		
	# Motorized xyz stages ---------------------------------------------
	
	def move_to(self, x:float=None, y:float=None, z:float=None)->None:
		"""Move the TCT stages to the specified position.
		
		Arguments
		---------
		x, y, z: float, optional
			The coordinates for the position. You don't need to specify 
			all of them, but at least one. Non specified coordinates remain
			unchanged.
		"""
		with self._tct_Lock:
			self._tct.stages.move_to(x=x,y=y,z=z)
	
	def get_stages_position(self)->tuple:
		"""Returns the position of the stages as a tuple `(x,y,z)` of floats."""
		with self._tct_Lock:
			return self._tct.stages.position
	
	# Laser ------------------------------------------------------------
	
	def get_laser_status(self)->str:
		"""Return the laser status "on" or "off"."""
		with self._tct_Lock:
			return self._tct.laser.status
	
	def set_laser_status(self, status:str)->None:
		"""Set the laser status.
		
		Arguments
		---------
		status: str
			Either `'on'` or `'off'`.
		"""
		with self._tct_Lock:
			self._tct.laser.status = status
	
	def get_laser_DAC(self)->int:
		"""Returns the laser DAC value."""
		with self._tct_Lock:
			return self._tct.laser.DAC
	
	def set_laser_DAC(self, DAC:int)->None:
		"""Set the value of the DAC for the laser.
		
		Arguments
		---------
		DAC: int
			An integer number between 0 and 1023.
		"""
		with self._tct_Lock:
			self._tct.laser.DAC = DAC
	
	def get_laser_frequency(self)->float:
		"""Returns the laser frequency value."""
		with self._tct_Lock:
			return self._tct.laser.frequency
	
	def set_laser_frequency(self, HZ:float)->None:
		"""Set the value of the frequency for the laser.
		
		Arguments
		---------
		HZ: float
			The frequency in Hertz.
		"""
		with self._tct_Lock:
			self._tct.laser.frequency = HZ
	
	# Bias voltage power supply ----------------------------------------
	
	def measure_bias_voltage(self)->float:
		"""Returns a measure of the bias voltage."""
		with self._keithley_Lock:
			return self._keithley.measure_voltage()
	
	def set_bias_voltage(self, volts:float):
		"""Set the bias voltage.
		
		Arguments
		---------
		volts: float
			The voltage.
		"""
		with self._keithley_Lock:
			self._keithley.set_source_voltage(volts)
	
	def measure_bias_current(self)->float:
		"""Returns a measure of the bias current."""
		with self._keithley_Lock:
			return self._keithley.measure_current()
	
	def get_current_compliance(self)->float:
		"""Returns the current limit of the voltage source in Amperes."""
		with self._keithley_Lock:
			return self._keithley.current_limit
	
	def set_current_compliance(self, amperes:float)->None:
		"""Set the current compliance in the bias power supply.
		
		Arguments
		---------
		amperes: float
			The value for the current limit.
		"""
		with self._keithley_Lock:
			self._keithley.current_limit = amperes
	
	def get_bias_output_status(self)->str:
		"""Returns either `'on'` or `'off'`."""
		with self._keithley_Lock:
			return self._keithley.output
	
	def set_bias_output_status(self, status:str)->None:
		"""Set the bias output to on or off.
		
		Aguments
		--------
		status: str
			Either `'on'` or `'off'`.
		"""
		with self._keithley_Lock:
			self._keithley.output = status
	
	# Oscilloscope -----------------------------------------------------
	
	def configure_oscilloscope_for_two_pulses(self)->None:
		"""Configures the horizontal scale and trigger of the oscilloscope 
		to properly match and acquire the two pulses after the laser
		splitting system we have.
		"""
		with self._oscilloscope_Lock:
			if hasattr(self, '_LeCroy'):
				self._LeCroy.set_trig_source('ext')
				self._LeCroy.set_trig_level('ext', -175e-3) # Totally empiric.
				self._LeCroy.set_trig_coupling('ext', 'DC')
				self._LeCroy.set_trig_slope('ext', 'negative')
				self._LeCroy.set_tdiv('20ns')
				self._LeCroy.set_trig_delay(-30e-9) # Totally empiric.
			elif hasattr(self, '_drs4_evaluation_board'):
				self._drs4_evaluation_board.set_sampling_frequency(Hz=5e9)
				self._drs4_evaluation_board.set_transparent_mode('on')
				self._drs4_evaluation_board.set_input_range(center=0)
				self._drs4_evaluation_board.enable_trigger(True,False) # Don't know what this line does, it was in the example `drs_exam.cpp`.
				self._drs4_evaluation_board.set_trigger_source('ext')
				self._drs4_evaluation_board.set_trigger_delay(seconds=130e-9-40e-9) # Totally empiric number.
			else:
				raise RuntimeError('No oscilloscope found in the setup!')
	
	def configure_oscilloscope_sequence_acquisition(self, n_sequences_per_trigger:int)->None:
		"""Configure the oscilloscope to automatically acquire multiple
		triggers on each trigger.
		
		Arguments
		---------
		n_sequences_per_trigger: int
			Number of "triggers per trigger". If this is 1, the usual behavior
			of the oscilloscope is configured. If this is 2, 3 or more then
			the oscilloscope is configured into "sampling mode sequence"
			so each time it triggers it will actually trigger multiple
			times and use the internal memory of the oscilloscope to
			store the waveforms, thus making it much faster than triggering
			multiple times and retrieving the data from the computer.
		"""
		if not isinstance(n_sequences_per_trigger, int):
			raise TypeError(f'`n_sequences_per_trigger` must be an integer.')
		if n_sequences_per_trigger<=0:
			raise ValueError(f'`n_sequences_per_trigger` must be > 0.')
		with self._oscilloscope_Lock:
			if n_sequences_per_trigger == 1:
				self._LeCroy.sampling_mode_sequence('off')
			else:
				self._LeCroy.sampling_mode_sequence('on', number_of_segments=n_sequences_per_trigger)
	
	def wait_for_trigger(self)->None:
		"""Blocks execution until there is a trigger in the acquisition
		system. Then it is stopped."""
		with self._oscilloscope_Lock:
			if hasattr(self, '_LeCroy'):
				self._LeCroy.wait_for_single_trigger()
			elif hasattr(self, '_drs4_evaluation_board'):
				self._drs4_evaluation_board.wait_for_single_trigger()
			else:
				raise RuntimeError('No oscilloscope found in the setup!')
	
	def get_waveform(self, n_channel:int)->list:
		"""Gets the waveform from the acquisition system for the specified 
		channel.
		
		Arguments
		---------
		n_channel: int
			Number of channel from which to bring the waveform.
		
		Returns
		-------
		waveform: list of dict
			A list of dict, each element of the dictionary being one 
			waveform, of the form:
			```
			[
				{'Time (s)': numpy.array, 'Amplitude (V)': numpy.array}, # This is waveform 0
				{'Time (s)': numpy.array, 'Amplitude (V)': numpy.array}, # Waveform 1
				...
			]
			```
			Each of these waveforms corresponds to each of the "sampling
			mode sequence". If "sampling mode RealTime" is used, then this
			will be a list with only one element.
		"""
		with self._oscilloscope_Lock:
			if hasattr(self, '_LeCroy'):
				waveform_data = self._LeCroy.get_waveform(n_channel=n_channel)['waveforms']
			elif hasattr(self, '_drs4_evaluation_board'):
				waveform_data = self._drs4_evaluation_board.get_waveform(n_channel)
			else:
				raise RuntimeError('No oscilloscope found in the setup!')
		if isinstance(waveform_data, dict):
			waveform_data = [waveform_data]
		for i in range(len(waveform_data)):
			waveform_data[i]['Amplitude (V)'] *= -1
		return waveform_data
	
	def set_oscilloscope_vdiv(self, n_channel:int, vdiv:float)->None:
		"""Sets the oscilloscope's vertical scale.
		
		Arguments
		---------
		n_channel: int
			Number of channel to which to set the vertical scale.
		vdiv: float
			Value for the vertical scale in volts per division.
		"""
		with self._oscilloscope_Lock:
			if hasattr(self, '_LeCroy'):
				self._LeCroy.set_vdiv(n_channel, vdiv)
			elif hasattr(self, '_drs4_evaluation_board'):
				warnings.warn(f'Cannot change VDIV of DRS4 Evaluation Board, it is not implemented.')
			else:
				raise RuntimeError('No oscilloscope found in the setup!')
	
	# Temperature and humidity sensor ----------------------------------
	
	def measure_temperature(self)->float:
		"""Returns a reading of the temperature as a float number in Celsius."""
		with self._sensirion_Lock:
			try:
				return self._sensirion_sensor.temperature
			except Exception as e:
				warnings.warn(f'Cannot measure temperature, reason: {repr(e)}')
				return float('NaN')
	
	def measure_humidity(self)->float:
		"""Returns a reading of the humidity as a float number in %RH."""
		with self._sensirion_Lock:
			try:
				return self._sensirion_sensor.humidity
			except Exception as e:
				warnings.warn(f'Cannot measure humidity, reason: {repr(e)}')
				return float('NaN')
	
	# Peltier power supply ---------------------------------------------
	
	def get_peltier_set_voltage(self)->float:
		"""Return the set voltage of the Peltier array, in Volts as a float number."""
		with self._peltier_DC_power_supply_Lock:
			return self._peltier_DC_power_supply.set_voltage_value
	
	def set_peltier_voltage(self, volts:float)->None:
		"""Set the voltage to the Peltier cells.
		
		Aguments
		--------
		volts: float
			The value for the voltage in volts.
		"""
		with self._peltier_DC_power_supply_Lock:
			self._peltier_DC_power_supply.set_voltage_value = volts
	
	def get_peltier_set_current(self)->float:
		"""Return the set current of the Peltier array, in Amperes as a float number."""
		with self._peltier_DC_power_supply_Lock:
			return self._peltier_DC_power_supply.set_current_value
	
	def set_peltier_current(self, amperes:float)->None:
		"""Set the current to the Peltier cells.
		
		Aguments
		--------
		amperes: float
			The value for the current in Amperes.
		"""
		with self._peltier_DC_power_supply_Lock:
			self._peltier_DC_power_supply.set_current_value = amperes
	
	def measure_peltier_voltage(self)->float:
		"""Return the measured voltage of the Peltier array, in Volts as a float number."""
		with self._peltier_DC_power_supply_Lock:
			return self._peltier_DC_power_supply.measured_voltage
	
	def measure_peltier_current(self)->float:
		"""Return the measured current of the Peltier array, in Amperes as a float number."""
		with self._peltier_DC_power_supply_Lock:
			return self._peltier_DC_power_supply.measured_current
	
	def get_peltier_status(self)->str:
		"""Return 'on' or 'off'."""
		with self._peltier_DC_power_supply_Lock:
			return self._peltier_DC_power_supply.output
	
	def set_peltier_status(self, status:str)->None:
		"""Set the status for the power to the Peltier cells on or off.
		
		Arguments
		---------
		status: str
			Either `'on'` or `'off'`.
		"""
		if not isinstance(status, str):
			raise TypeError('`status` must be a string.')
		if status.lower() == 'on':
			enable = True
		elif status.lower() == 'off':
			enable = False
		else:
			raise ValueError(f'`status` must be either `"on"` or `"off"`, received {repr(status)}.')
		with self._peltier_DC_power_supply_Lock:
			self._peltier_DC_power_supply.enable_output(enable)

class TheTCTSetupWithNamedLocks(TheTCTSetup):
	"""This class wraps the `TheTCTSetup` such that it can be used with
	named locks in a multiprocess environment."""
	def __init__(self):
		super().__init__()
		
		# User named locks ---
		self._bias_voltage_holding_Lock = CrossProcessNamedLock(Path.home())
		self._signal_acquisition_holding_Lock = CrossProcessNamedLock(Path.home())
		self._tct_holding_Lock = CrossProcessNamedLock(Path.home())
		self._temperature_system_holding_Lock = CrossProcessNamedLock(Path.home())
	
	def hold_signal_acquisition(self, who:str):
		"""When this is called in a `with` statement, it will guarantee
		the exclusive control of the signal acquisition system, i.e. the
		oscilloscope.
		
		Arguments
		---------
		who: str
			A string identifying you. This can be whatever you want, but
			you have to use always the same. A good choice is `str(os.getpid())`
			because it will give all your imported modules the same name.
			This is a workaround because, surprisingly,  the Locks in python
			are not multiprocess friendly.
		
		Example
		-------
		```
		with the_setup.hold_signal_acquisition(my_name):
			# Nobody else from other thread can change anything from the oscilloscope, only read it.
		```
		"""
		return self._signal_acquisition_holding_Lock(who)
	
	def hold_control_of_bias(self, who:str):
		"""When this is called in a `with` statement, it will guarantee
		the exclusive control of the bias power supply. No one else will
		be able to act on the power supply, only read from it.
		
		Parameters
		----------
		who: str
			A string identifying you. This can be whatever you want, but
			you have to use always the same. A good choice is `str(os.getpid())`
			because it will give all your imported modules the same name.
			This is a workaround because, surprisingly,  the Locks in python
			are not multiprocess friendly.
		
		Example
		-------
		```
		with the_setup.hold_control_of_bias(my_name):
			# Nobody else from other thread can change the bias conditions for this slot.
			the_setup.set_bias_voltage(volts, my_name) # This will not change unless you change it here.
		```
		"""
		return self._bias_voltage_holding_Lock(who)
	
	def hold_tct_control(self, who:str):
		"""When this is called in a `with` statement, it will guarantee
		the exclusive control of the TCT setup, this is the laser and the
		movable stages.
		
		Parameters
		----------
		who: str
			A string identifying you. This can be whatever you want, but
			you have to use always the same. A good choice is `str(os.getpid())`
			because it will give all your imported modules the same name.
			This is a workaround because, surprisingly,  the Locks in python
			are not multiprocess friendly.
		"""
		return self._tct_holding_Lock(who)
	
	def hold_temperature_control(self, who:str):
		"""When this is called in a `with` statement, it will guarantee
		the exclusive control of the temperature system, i.e. the Peltier
		cells.
		
		Parameters
		----------
		who: str
			A string identifying you. This can be whatever you want, but
			you have to use always the same. A good choice is `str(os.getpid())`
			because it will give all your imported modules the same name.
			This is a workaround because, surprisingly,  the Locks in python
			are not multiprocess friendly.
		"""
		return self._temperature_system_holding_Lock(who)
	
	def move_to(self, who:str, x:float=None, y:float=None, z:float=None)->None:
		"""Move the TCT stages to the specified position.
		
		Arguments
		---------
		x, y, z: float, optional
			The coordinates for the position. You don't need to specify 
			all of them, but at least one. Non specified coordinates remain
			unchanged.
		who: str
			A string identifying you. This can be whatever you want, but
			you have to use always the same. A good choice is `str(os.getpid())`
			because it will give all your imported modules the same name.
			This is a workaround because, surprisingly,  the Locks in python
			are not multiprocess friendly.
		"""
		with self._tct_holding_Lock(who):
			super().move_to(x=x,y=y,z=z)

	def set_laser_status(self, status:str, who:str)->None:
		"""Set the laser status.
		
		Arguments
		---------
		status: str
			Either `'on'` or `'off'`.
		who: str
			A string identifying you. This can be whatever you want, but
			you have to use always the same. A good choice is `str(os.getpid())`
			because it will give all your imported modules the same name.
			This is a workaround because, surprisingly,  the Locks in python
			are not multiprocess friendly.
		"""
		with self._tct_holding_Lock(who):
			super().set_laser_status(status=status)

	def set_laser_DAC(self, DAC:int, who:str)->None:
		"""Set the value of the DAC for the laser.
		
		Arguments
		---------
		DAC: int
			An integer number between 0 and 1023.
		who: str
			A string identifying you. This can be whatever you want, but
			you have to use always the same. A good choice is `str(os.getpid())`
			because it will give all your imported modules the same name.
			This is a workaround because, surprisingly,  the Locks in python
			are not multiprocess friendly.
		"""
		with self._tct_holding_Lock(who):
			super().set_laser_DAC(DAC=DAC)
	
	def set_laser_frequency(self, HZ:float, who:str)->None:
		"""Set the value of the frequency for the laser.
		
		Arguments
		---------
		HZ: float
			The frequency in Hertz.
		who: str
			A string identifying you. This can be whatever you want, but
			you have to use always the same. A good choice is `str(os.getpid())`
			because it will give all your imported modules the same name.
			This is a workaround because, surprisingly,  the Locks in python
			are not multiprocess friendly.
		"""
		with self._tct_holding_Lock(who):
			super().set_laser_frequency(HZ=HZ)

	def set_bias_voltage(self, volts:float, who:str):
		"""Set the bias voltage.
		
		Arguments
		---------
		volts: float
			The voltage.
		who: str
			A string identifying you. This can be whatever you want, but
			you have to use always the same. A good choice is `str(os.getpid())`
			because it will give all your imported modules the same name.
			This is a workaround because, surprisingly,  the Locks in python
			are not multiprocess friendly.
		"""
		with self._bias_voltage_holding_Lock(who):
			super().set_bias_voltage(volts=volts)
	
	def set_bias_output_status(self, status:str, who:str):
		"""Set the bias voltage.
		
		Arguments
		---------
		status: str
			Either `'on'` or `'off'`.
		who: str
			A string identifying you. This can be whatever you want, but
			you have to use always the same. A good choice is `str(os.getpid())`
			because it will give all your imported modules the same name.
			This is a workaround because, surprisingly,  the Locks in python
			are not multiprocess friendly.
		"""
		with self._bias_voltage_holding_Lock(who):
			super().set_bias_output_status(status=status)

	def set_current_compliance(self, amperes:float, who:str)->None:
		"""Set the current compliance in the bias power supply.
		
		Arguments
		---------
		amperes: float
			The value for the current limit.
		who: str
			A string identifying you. This can be whatever you want, but
			you have to use always the same. A good choice is `str(os.getpid())`
			because it will give all your imported modules the same name.
			This is a workaround because, surprisingly,  the Locks in python
			are not multiprocess friendly.
		"""
		with self._bias_voltage_holding_Lock(who):
			super().set_current_compliance(amperes=amperes)

	def configure_oscilloscope_for_two_pulses(self, who:str)->None:
		"""Configures the horizontal scale and trigger of the oscilloscope 
		to properly match and acquire the two pulses after the laser
		splitting system we have.
		
		Arguments
		---------
		who: str
			A string identifying you. This can be whatever you want, but
			you have to use always the same. A good choice is `str(os.getpid())`
			because it will give all your imported modules the same name.
			This is a workaround because, surprisingly,  the Locks in python
			are not multiprocess friendly.
		"""
		with self._signal_acquisition_holding_Lock(who):
			super().configure_oscilloscope_for_two_pulses()
	
	def configure_oscilloscope_sequence_acquisition(self, n_sequences_per_trigger:int, who:str)->None:
		with self._signal_acquisition_holding_Lock(who):
			super().configure_oscilloscope_sequence_acquisition(n_sequences_per_trigger=n_sequences_per_trigger)

	def set_oscilloscope_vdiv(self, n_channel:int, vdiv:float, who:str)->None:
		"""Sets the oscilloscope's vertical scale.
		
		Arguments
		---------
		n_channel: int
			Number of channel to which to set the vertical scale.
		vdiv: float
			Value for the vertical scale in volts per division.
		who: str
			A string identifying you. This can be whatever you want, but
			you have to use always the same. A good choice is `str(os.getpid())`
			because it will give all your imported modules the same name.
			This is a workaround because, surprisingly,  the Locks in python
			are not multiprocess friendly.
		"""
		with self._signal_acquisition_holding_Lock(who):
			super().set_oscilloscope_vdiv(n_channel=n_channel, vdiv=vdiv)
	
	def set_peltier_voltage(self, volts:float, who:str)->None:
		"""Set the voltage to the Peltier cells.
		
		Aguments
		--------
		volts: float
			The value for the voltage in volts.
		who: str
			A string identifying you. This can be whatever you want, but
			you have to use always the same. A good choice is `str(os.getpid())`
			because it will give all your imported modules the same name.
			This is a workaround because, surprisingly,  the Locks in python
			are not multiprocess friendly.
		"""
		with self._temperature_system_holding_Lock(who):
			super().set_peltier_voltage(volts=volts)
	
	def set_peltier_current(self, amperes:float, who:str)->None:
		"""Set the current to the Peltier cells.
		
		Aguments
		--------
		amperes: float
			The value for the current in Amperes.
		who: str
			A string identifying you. This can be whatever you want, but
			you have to use always the same. A good choice is `str(os.getpid())`
			because it will give all your imported modules the same name.
			This is a workaround because, surprisingly,  the Locks in python
			are not multiprocess friendly.
		"""
		with self._temperature_system_holding_Lock(who):
			super().set_peltier_current(amperes=amperes)
	
	def set_peltier_status(self, status:str, who:str)->None:
		"""Set the status for the power to the Peltier cells on or off.
		
		Arguments
		---------
		status: str
			Either `'on'` or `'off'`.
		who: str
			A string identifying you. This can be whatever you want, but
			you have to use always the same. A good choice is `str(os.getpid())`
			because it will give all your imported modules the same name.
			This is a workaround because, surprisingly,  the Locks in python
			are not multiprocess friendly.
		"""
		with self._temperature_system_holding_Lock(who):
			super().set_peltier_status(status=status)
	
class WhoWrapper:
	# https://stackoverflow.com/a/73573455/8849755
	"""This class was designed to wrap `TheTCTSetupWithNamedLocks`. If you
	look into the definition of that class you will see that many methods 
	have an argument that is `who` which specifies the name of whoever
	wants to modify the setup and has locks to avoid a mess. If that
	class is used, each time one of those methods is called the `who` argument
	must be passed, which is annoying. This class wraps the other to automate
	that task. You only give the `who` argument once when creating the
	wrapper and then it will be passed automatically to all methods that
	need it."""
	def __init__(self, object_to_wrap, who:str):
		self._who = who
		self._wrapped_object = object_to_wrap

	def __getattr__(self, __name: str):
		attr = getattr(self._wrapped_object, __name)
		if not callable(attr):
			return attr
		def wrapped(*args, **kwargs):
			try:
				return attr(who=self._who, *args, **kwargs)
			except TypeError as e:
				if all([s in str(e) for s in {'who','got an unexpected keyword argument'}]):
					return attr(*args, **kwargs)
				else:
					raise e
		return wrapped
	
def connect_me_with_the_setup(who:str):
	class TheSetup(BaseManager):
		pass

	TheSetup.register('get_the_setup')
	m = TheSetup(address=('', 50000), authkey=b'abracadabra')
	m.connect()
	the_setup = m.get_the_setup()
	return WhoWrapper(object_to_wrap=the_setup, who=who)

if __name__=='__main__':
	from progressreporting.TelegramProgressReporter import SafeTelegramReporter4Loops # https://github.com/SengerM/progressreporting
	import my_telegram_bots
	
	class TheSetupManager(BaseManager):
		pass
	
	reporter = SafeTelegramReporter4Loops(
		bot_token = my_telegram_bots.robobot.token,
		chat_id = my_telegram_bots.chat_ids['Robobot TCT setup'],
	)
	
	print('Opening the setup...')
	the_setup = TheTCTSetupWithNamedLocks()
	
	TheSetupManager.register('get_the_setup', callable=lambda:the_setup)
	m = TheSetupManager(address=('', 50000), authkey=b'abracadabra')
	s = m.get_server()
	print('Ready!')
	try:
		s.serve_forever()
	except Exception as e:
		reporter.send_message(f'🔥 `TheTCTSetup` crashed! Reason: `{repr(e)}`.')
