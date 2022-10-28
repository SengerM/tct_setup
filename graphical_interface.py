import tkinter as tk
import tkinter.messagebox
import numpy as np
import numbers
import threading
import time

class CoordinatesFrame(tk.Frame):
	def __init__(self, parent, coordinates_name=None, *args, **kwargs):
		tk.Frame.__init__(self, parent, *args, **kwargs)
		self.parent = parent
		
		if coordinates_name != None:
			tk.Label(self, text = f'{coordinates_name}:').grid()
		self.entries_coordinates = {}
		entries_frame = tk.Frame(self)
		entries_frame.grid()
		for idx,coord in enumerate(['x', 'y', 'z']):
			tk.Label(entries_frame, text = f'{coord} (µm) = ').grid(
				row = idx,
				column = 0,
				pady = 2,
			)
			self.entries_coordinates[coord] = tk.Entry(entries_frame, validate = 'key')
			self.entries_coordinates[coord].grid(
				row = idx,
				column = 1,
				pady = 2,
			)
			self.entries_coordinates[coord].insert(0,'?')
			
	def get_coordinates(self):
		coords = []
		for coord in ['x', 'y', 'z']: 
			try:
				coords.append(float(self.entries_coordinates[coord].get())*1e-6)
			except ValueError:
				coords.append(self.entries_coordinates[coord].get())
		return tuple(coords)
	
	def set_coordinates(self, x=None, y=None, z=None):
		for xyz,coord in zip([x,y,z],['x', 'y', 'z']):
			if xyz == None:
				continue
			if not isinstance(xyz, numbers.Number):
				raise TypeError(f'Coordinates must be numbers, received {xyz} of type {type(xyz)}')
			self.entries_coordinates[coord].delete(0,'end')
			self.entries_coordinates[coord].insert(0,int(xyz*1e6))

class CoordinatesControl(tk.Frame):
	def __init__(self, parent, the_setup, coordinates_name=None, *args, **kwargs):
		tk.Frame.__init__(self, parent, *args, **kwargs)
		self.parent = parent
		
		self.the_setup = the_setup
		
		self.coordinates = CoordinatesFrame(parent=self,coordinates_name=coordinates_name)
		self.coordinates.grid()
		
		self.jump_to_position_btn = tk.Button(self,text = 'Go to this position', command = self.jump_to_position_btn_command)
		self.jump_to_position_btn.grid()
		
	def jump_to_position_btn_command(self):
		position_to_go_to = self.coordinates.get_coordinates()
		for val in position_to_go_to:
			try:
				float(val)
			except:
				tk.messagebox.showerror(message = f'Check your input. Coordinates must be float numbers, received "{val}"')
				return
		print(f'Moving stages to {position_to_go_to}...')
		self.the_setup.move_to(**{xyz:v for xyz,v in zip(['x','y','z'],position_to_go_to)})
		new_pos = self.the_setup.get_stages_position()
		print(f'Stages moved, new position is {new_pos}')
		self.coordinates.set_coordinates(*new_pos)
	
	def get_coordinates(self):
		return self.coordinates.get_coordinates()
	
	def set_coordinates(self, x=None, y=None, z=None):
		self.coordinates.set_coordinates(x,y,z)

class CoordinatesMemory(tk.Frame):
	def __init__(self, parent, the_setup, coordinates_name=None, *args, **kwargs):
		tk.Frame.__init__(self, parent, *args, **kwargs)
		self.parent = parent
		
		self.the_setup = the_setup
		self.coordinates_control = CoordinatesControl(self, the_setup, coordinates_name=coordinates_name)
		self.coordinates_control.grid()
		self.store_position_btn = tk.Button(self, text = 'Store current position', command = self.store_current_position_command)
		self.store_position_btn.grid()
	
	def store_current_position_command(self):
		current_pos = self.the_setup.get_stages_position()
		self.coordinates_control.set_coordinates(*current_pos)
		print(f'Stored current position...')
	
	def get_coordinates(self):
		return self.coordinates_control.get_coordinates()
	
	def set_coordinates(self, x=None, y=None, z=None):
		self.coordinates_control.set_coordinates(x,y,z)

class StagesJoystick(tk.Frame):
	def __init__(self, parent, the_setup, current_coordinates_display, *args, **kwargs):
		tk.Frame.__init__(self, parent, *args, **kwargs)
		self.parent = parent
		
		self.the_setup = the_setup
		self.current_coordinates_display = current_coordinates_display
		
		step_frame = tk.Frame(self)
		controls_frame = tk.Frame(self)
		step_frame.grid()
		controls_frame.grid()
		xy_frame = tk.Frame(controls_frame)
		z_frame = tk.Frame(controls_frame)
		xy_frame.grid(row=0,column=0)
		z_frame.grid(row=0,column=1)
		tk.Label(step_frame, text='xy step (µm) = ').grid(row=0,column=0)
		tk.Label(step_frame, text='z step (µm) = ').grid(row=1,column=0)
		
		self.xy_step_entry = tk.Entry(step_frame)
		self.xy_step_entry.grid(row=0,column=1)
		self.xy_step_entry.insert(0,'1')
		self.xy_step_entry.bind('<Left>', lambda x: self.move_command('x','-'))
		self.xy_step_entry.bind('<Right>', lambda x: self.move_command('x','+'))
		self.xy_step_entry.bind('<Up>', lambda x: self.move_command('y','+'))
		self.xy_step_entry.bind('<Down>', lambda x: self.move_command('y','-'))
		self.xy_step_entry.bind('<Control_R>', lambda x: self.move_command('z','-'))
		self.xy_step_entry.bind('<Shift_R>', lambda x: self.move_command('z','+'))
		
		self.z_step_entry = tk.Entry(step_frame)
		self.z_step_entry.grid(row=1,column=1)
		self.z_step_entry.insert(0,'100')
		self.z_step_entry.bind('<Left>', lambda x: self.move_command('x','-'))
		self.z_step_entry.bind('<Right>', lambda x: self.move_command('x','+'))
		self.z_step_entry.bind('<Up>', lambda x: self.move_command('y','+'))
		self.z_step_entry.bind('<Down>', lambda x: self.move_command('y','-'))
		self.z_step_entry.bind('<Control_R>', lambda x: self.move_command('z','-'))
		self.z_step_entry.bind('<Shift_R>', lambda x: self.move_command('z','+'))
		
		self.buttons = {}
		for xyz in ['x', 'y', 'z']:
			self.buttons[xyz] = {}
			for direction in ['-','+']:
				self.buttons[xyz][direction] = tk.Button(
					xy_frame if xyz in ['x','y'] else z_frame,
					text = f'{direction}{xyz}',
				)
				self.buttons[xyz][direction]['command'] = lambda xyz=xyz,direction=direction: self.move_command(xyz,direction)
		self.buttons['x']['-'].grid(row=1,column=0)
		self.buttons['x']['+'].grid(row=1,column=2)
		self.buttons['y']['+'].grid(row=0,column=1)
		self.buttons['y']['-'].grid(row=2,column=1)
		self.buttons['z']['-'].grid(row=0)
		self.buttons['z']['+'].grid(row=1)
	
	def move_command(self, coordinate, direction):
		try:
			step = float(self.xy_step_entry.get())*1e-6 if coordinate in ['x','y'] else float(self.z_step_entry.get())*1e-6
		except:
			tk.messagebox.showerror(message = f'Check your input in "step". It must be a float but you have entered "{self.step_entry.get()}"')
			return
		print(f'Moving {step*1e6} µm in {direction}{coordinate}...')
		move = [0,0,0]
		for idx,xyz in enumerate(['x', 'y', 'z']):
			if xyz == coordinate:
				move[idx] = step
				if direction == '-':
					move[idx] *= -1
		self.the_setup.move_to(**{xyz:(current+d) for xyz,current,d in zip(['x','y','z'],self.the_setup.get_stages_position(),tuple(move))})
		new_pos = self.the_setup.get_stages_position()
		print(f'Stages moved, new position is {new_pos}')
		self.current_coordinates_display.set_coordinates(*new_pos)

class StagesControlGraphicalInterface_main(tk.Frame):
	def __init__(self, parent, the_setup, *args, **kwargs):
		tk.Frame.__init__(self, parent, *args, **kwargs)
		self.parent = parent
		
		main_frame = tk.Frame(self)
		main_frame.grid()
		current_position_frame = tk.Frame(main_frame)
		controls_frame = tk.Frame(main_frame)
		current_position_frame.grid()
		controls_frame.grid()
		
		current_coordinates = CoordinatesControl(current_position_frame, the_setup=the_setup, coordinates_name='Current position')
		current_coordinates.grid()
		current_coordinates.coordinates.set_coordinates(*the_setup.get_stages_position())
		
		joystick = StagesJoystick(parent=controls_frame, the_setup=the_setup, current_coordinates_display=current_coordinates)
		joystick.grid(pady=20)
		
		for k in [1,2]:
			memory = CoordinatesMemory(
				parent = main_frame, 
				the_setup = the_setup,
				coordinates_name = f'Position memory #{k}',
			)
			memory.grid(pady=20)
			memory.set_coordinates(*the_setup.get_stages_position())

class graphical_ParticularsLaserStatusDisplay(tk.Frame):
	def __init__(self, parent, the_setup, *args, **kwargs):
		tk.Frame.__init__(self, parent, *args, **kwargs)
		self.parent = parent
		self._auto_update_interval = 1 # seconds
		
		self.the_setup = the_setup
		
		frame = tk.Frame(self)
		frame.grid(pady=5)
		tk.Label(frame, text = 'Laser is').grid()
		self.status_label = tk.Label(frame, text = '?')
		self.status_label.grid()
		
		frame = tk.Frame(self)
		frame.grid(pady=5)
		tk.Label(frame, text = 'DAC').grid()
		self.DAC_label = tk.Label(frame, text = '?')
		self.DAC_label.grid()
		
		frame = tk.Frame(self)
		frame.grid(pady=5)
		tk.Label(frame, text = 'Frequency').grid()
		self.frequency_label = tk.Label(frame, text = '?')
		self.frequency_label.grid()
		
		def thread_function():
			while True:
				try:
					self.update_display()
				except:
					pass
				time.sleep(1)
		
		threading.Thread(target=thread_function, daemon=True).start()
		
	def update_display(self):
		self.status_label.config(text=f'{repr(self.the_setup.get_laser_status())}')
		self.DAC_label.config(text=f'{self.the_setup.get_laser_DAC()}')
		self.frequency_label.config(text=f'{self.the_setup.get_laser_frequency():.0f} Hz')
	
class graphical_ParticularsLaserControlInput(tk.Frame):
	def __init__(self, parent, the_setup, *args, **kwargs):
		tk.Frame.__init__(self, parent, *args, **kwargs)
		self.parent = parent
		
		self.the_setup = the_setup
		
		entries_frame = tk.Frame(self)
		entries_frame.grid(
			pady = 2
		)
		
		inputs_frame = tk.Frame(entries_frame)
		inputs_frame.grid()
		
		tk.Label(inputs_frame, text = f'DAC ').grid(
			row = 0,
			column = 0,
			pady = 2,
		)
		self.DAC_entry = tk.Entry(inputs_frame, validate = 'key')
		self.DAC_entry.grid(
			row = 0,
			column = 1,
			pady = 2,
		)
		for key in {'<Return>','<KP_Enter>'}:
			self.DAC_entry.bind(key, self.update_DAC)
		
		tk.Label(inputs_frame, text = f'Frequency ').grid(
			row = 1,
			column = 0,
			pady = 2,
		)
		self.frequency_entry = tk.Entry(inputs_frame, validate = 'key')
		self.frequency_entry.grid(
			row = 1,
			column = 1,
			pady = 2,
		)
		for key in {'<Return>','<KP_Enter>'}:
			self.frequency_entry.bind(key, self.update_frequency)
		
		self.status_button = tk.Button(entries_frame, text='Turn on' if self.the_setup.get_laser_status()=='off' else 'Turn off', command=self._status_button_clicked)
		self.status_button.grid(
			pady = 22,
		)
		
	def _status_button_clicked(self):
		if self.the_setup.get_laser_status() == 'on':
			self.the_setup.set_laser_status('off')
		elif self.the_setup.get_laser_status() == 'off':
			self.the_setup.set_laser_status('on')
		self.status_button.config(text='Turn on' if self.the_setup.get_laser_status()=='off' else 'Turn off')
	
	def update_DAC(self, event=None):
		try:
			DAC_to_set = int(self.DAC_entry.get())
		except ValueError:
			tk.messagebox.showerror(message = f'Check your input. DAC must be an integer number, received {repr(self.DAC_entry.get())}.')
			return
		try:
			self.the_setup.set_laser_DAC(DAC_to_set)
		except Exception as e:
			tk.messagebox.showerror(message = f'Cannot update DAC. Reason: {repr(e)}.')
	
	def update_frequency(self, event=None):
		try:
			frequency_to_set = float(self.frequency_entry.get())
		except ValueError:
			tk.messagebox.showerror(message = f'Check your input. Frequency must be a float number, received {repr(self.frequency_entry.get())}.')
			return
		try:
			self.the_setup.set_laser_frequency(frequency_to_set)
		except Exception as e:
			tk.messagebox.showerror(message = f'Cannot update frequency. Reason: {repr(e)}.')

class LaserControllerGraphicalInterface_main(tk.Frame):
	def __init__(self, parent, the_setup, *args, **kwargs):
		tk.Frame.__init__(self, parent, *args, **kwargs)
		self.parent = parent
		
		main_frame = tk.Frame(self)
		main_frame.grid(padx=5,pady=5)
		display = graphical_ParticularsLaserStatusDisplay(main_frame, the_setup)
		display.grid(pady=5)
		graphical_ParticularsLaserControlInput(main_frame, the_setup).grid(pady=0)
		
		self._display = display
	
	def terminate(self):
		self._display.terminate()

class TemperatureMonitor(tk.Frame):
	def __init__(self, parent, the_setup, *args, **kwargs):
		tk.Frame.__init__(self, parent, *args, **kwargs)
		self.parent = parent
		
		self.the_setup = the_setup
		
		frame = tk.Frame(self)
		frame.grid(pady=5)
		tk.Label(frame, text = 'Temperature: ').grid()
		self.temperature_label = tk.Label(frame, text = '?')
		self.temperature_label.grid()
		
		frame = tk.Frame(self)
		frame.grid(pady=5)
		tk.Label(frame, text = ' Humidity: ').grid()
		self.humidity_label = tk.Label(frame, text = '?')
		self.humidity_label.grid()
		
		frame = tk.Frame(self)
		frame.grid(pady=5)
		tk.Label(frame, text = ' Peltier: ').grid()
		self.peltier_IV_label = tk.Label(frame, text = '?')
		self.peltier_IV_label.grid()
		
		def thread_function():
			while True:
				time.sleep(1)
				self.update_display()
		
		threading.Thread(target=thread_function, daemon=True).start()
	
	def update_display(self):
		self.temperature_label.config(text=f'{self.the_setup.measure_temperature():.2f} °C')
		self.humidity_label.config(text=f'{self.the_setup.measure_humidity():.2f} %RH')
		self.peltier_IV_label.config(text=f'{self.the_setup.get_peltier_status()}, {self.the_setup.measure_peltier_voltage()*self.the_setup.measure_peltier_current():.2f} W')

class BiasVoltageGraphicalControl(tk.Frame):
	def __init__(self, parent, the_setup, *args, **kwargs):
		tk.Frame.__init__(self, parent, *args, **kwargs)
		self.parent = parent
		self.the_setup = the_setup
		
		frame = tk.Frame(self)
		frame.grid()
		
		tk.Label(frame, text = f'Voltage (V)').grid()
		self.voltage_entry = tk.Entry(frame)
		self.voltage_entry.grid(row=0,column=1)
		
		tk.Label(frame, text = f'Current limit (µA)').grid(row=1,column=0)
		self.current_limit_entry = tk.Entry(frame)
		self.current_limit_entry.grid(row=1,column=1)
		
		self.status_button = tk.Button(frame, text='Turn on' if self.the_setup.get_bias_output_status()=='off' else 'Turn off', command=self._status_button_clicked)
		self.status_button.grid(
			pady = 22,
		)
		
	def _status_button_clicked(self):
		if self.the_setup.get_bias_output_status() == 'on':
			self.the_setup.set_bias_output_status('off')
		elif self.the_setup.get_bias_output_status() == 'off':
			self.the_setup.set_bias_output_status('on')
		self.status_button.config(text='Turn on' if self.the_setup.get_bias_output_status()=='off' else 'Turn off')
		
		def set_voltage():
			try:
				voltage = float(self.voltage_entry.get())
			except ValueError:
				tk.messagebox.showerror(message = f'Check your input. Voltage must be a float number, received "{self.voltage_entry.get()}".')
				return
			print('Please wait while the voltage is being changed...')
			self.the_setup.set_bias_voltage(volts=voltage)
			print('Voltage has been changed!')
		
		def set_current_limit():
			try:
				current = float(self.current_limit_entry.get())
			except ValueError:
				tk.messagebox.showerror(message = f'Check your input. The current limit must be a float number, received {repr(self.current_limit_entry.get())}.')
				return
			print(f'Changing current limit to {current} µA...')
			self.the_setup.set_current_compliance(amperes=current*1e-6)
			print('Current limit has been changed!')
		
		def voltage_entry_enter_keybind_function(event=None):
			def thread_function():
				self.voltage_entry.config(state='disabled')
				set_voltage()
				self.voltage_entry.config(state='normal')
			threading.Thread(target=thread_function).start()
		
		self.voltage_entry.bind('<Return>', voltage_entry_enter_keybind_function)
		self.voltage_entry.bind('<KP_Enter>', voltage_entry_enter_keybind_function)
		
		def current_limit_entry_enter_keybind_function(event=None):
			def thread_function():
				self.current_limit_entry.config(state='disabled')
				set_current_limit()
				self.current_limit_entry.config(state='normal')
			threading.Thread(target=thread_function).start()
		
		self.current_limit_entry.bind('<Return>', current_limit_entry_enter_keybind_function)
		self.current_limit_entry.bind('<KP_Enter>', current_limit_entry_enter_keybind_function)

class BiasVoltageGraphicalDisplay(tk.Frame):
	def __init__(self, parent, the_setup, *args, **kwargs):
		tk.Frame.__init__(self, parent, *args, **kwargs)
		self.parent = parent
		self.the_setup = the_setup
		
		frame = tk.Frame(self)
		frame.grid(pady=10)
		tk.Label(frame, text = 'Measured voltage: ').grid()
		self.measured_voltage_label = tk.Label(frame, text = '?')
		self.measured_voltage_label.grid()
		
		frame = tk.Frame(self)
		frame.grid(pady=10)
		tk.Label(frame, text = 'Current limit: ').grid()
		self.current_compliance_label = tk.Label(frame, text = '?')
		self.current_compliance_label.grid()
		
		frame = tk.Frame(self)
		frame.grid(pady=10)
		tk.Label(frame, text = 'Measured current: ').grid()
		self.measured_current_label = tk.Label(frame, text = '?')
		self.measured_current_label.grid()
		
		frame = tk.Frame(self)
		frame.grid(pady=10)
		tk.Label(frame, text = 'Bias voltage is: ').grid()
		self.status_label = tk.Label(frame, text = '?')
		self.status_label.grid()
		
		def thread_function():
			while True:
				time.sleep(1)
				self.update_display()
		
		threading.Thread(target=thread_function, daemon=True).start()
		
	def update_display(self):
		self.measured_voltage_label.config(text=f'{self.the_setup.measure_bias_voltage():.2f} V')
		self.current_compliance_label.config(text=f'{self.the_setup.get_current_compliance()*1e6:.3f} µA')
		self.measured_current_label.config(text=f'{self.the_setup.measure_bias_current()*1e6:.6f} µA')
		self.status_label.config(text=f'{self.the_setup.get_bias_output_status()}')
	
if __name__ == '__main__':
	from TheSetup import connect_me_with_the_setup
	import os
	
	X_PADDING = 33
	
	the_setup = connect_me_with_the_setup(who=f'graphical interface PID:{os.getpid()}')
	
	root = tk.Tk()
	root.title('TCT setup control')
	main_frame = tk.Frame(root)
	main_frame.grid(padx=20,pady=20)
	main_frame.grid()
	tk.Label(main_frame, text = 'TCT setup control', font=("Georgia", 22, "bold")).grid(pady=22)
	widgets_frame = tk.Frame(main_frame)
	widgets_frame.grid()
	
	stages_widget = StagesControlGraphicalInterface_main(widgets_frame, the_setup)
	stages_widget.grid(
		row = 0,
		column = 0,
		sticky = 'n',
	)
	laser_controller_widget = LaserControllerGraphicalInterface_main(widgets_frame, the_setup)
	laser_controller_widget.grid(
		row = 0,
		column = 1,
		padx = (X_PADDING,0),
		sticky = 'n',
	)
	
	temperature_monitor = TemperatureMonitor(widgets_frame, the_setup)
	temperature_monitor.grid(
		row = 0,
		column = 2,
		padx = (X_PADDING,0),
		sticky = 'n',
	)
	
	bias_monitor_frame = tk.Frame(widgets_frame)
	bias_monitor_frame.grid(
		row = 0,
		column = 3,
		padx = (X_PADDING,0),
		sticky = 'n',
	)
	bias_monitor = BiasVoltageGraphicalDisplay(bias_monitor_frame, the_setup)
	bias_monitor.grid(
		row = 0,
		column = 0,
		sticky = 'n',
	)
	bias_control = BiasVoltageGraphicalControl(bias_monitor_frame, the_setup)
	bias_control.grid(
		row = 1,
		column = 0,
		sticky = 'n',
	)
	
	print(f'Waiting to acquire control of hardware...')
	with the_setup.hold_tct_control():
		print(f'Control of hardware acquired!')
		root.mainloop()
