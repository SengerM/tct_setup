from simple_pid import PID
from time import sleep
from progressreporting.TelegramProgressReporter import TelegramReporter # https://github.com/SengerM/progressreporting
import my_telegram_bots
import time
from simple_pid import PID # https://github.com/m-lundberg/simple-pid

def temperature_controller(set_point_celsius:float, the_setup, temperature_tolerance_for_warning:float=1, temperature_tolerance_before_shutting_down:float=10, seconds_before_warnings_and_protections_enter_into_effect:float=60*3):
	PID_SAMPLE_TIME = 1

	temperature_pid = PID(-.5,-.1,-2)
	temperature_pid.sample_time = PID_SAMPLE_TIME
	temperature_pid.output_limits = (0, 4.8)
	temperature_pid.setpoint = set_point_celsius

	reporter = telegram_reporter = TelegramReporter(
		telegram_token = my_telegram_bots.robobot.token,
		telegram_chat_id = my_telegram_bots.chat_ids['Robobot TCT setup'],
	)

	with the_setup.hold_temperature_control():
		try:
			the_setup.set_peltier_status('on')
			start_time = time.time()
			while True:
				T = the_setup.measure_temperature()
				new_current = temperature_pid(T)
				the_setup.set_peltier_current(new_current)
				time.sleep(PID_SAMPLE_TIME)
				
				if time.time()-start_time > seconds_before_warnings_and_protections_enter_into_effect:
					temperature_drift_from_setpoint = ((T-set_point_celsius)**2)**.5
					if temperature_drift_from_setpoint > temperature_tolerance_for_warning:
						reporter.send_message(f'❗ Temperature has drifted too much from set point!\nMeasured T: {T:.2f} °C\nSet point: {temperature_pid.setpoint:.2f} °C')
					if temperature_drift_from_setpoint > temperature_tolerance_before_shutting_down:
						the_setup.set_peltier_status('off')
						raise RuntimeError(f'Temperature has drifted more than {temperature_tolerance_before_shutting_down} °C from set point, the system will be shut down!') 
		except Exception as e:
			reporter.send_message(f'🔥 Temperature controller crashed!\n\nReason:\n{e}')
			raise e
		finally:
			the_setup.set_peltier_status('off')

def monitor_temperature_control(the_setup):
	s = the_setup

	while True:
		print(f'{s.measure_temperature():.2f} °C, {s.measure_humidity():.2f} %RH | {s.measure_peltier_current():.2f} A, {s.measure_peltier_voltage():.2f} V, {s.measure_peltier_current()*s.measure_peltier_voltage():.2f} W, {s.get_peltier_status()}')
		time.sleep(1)

if __name__=='__main__':
	import argparse
	import os
	from TheSetup import connect_me_with_the_setup
	
	parser = argparse.ArgumentParser()
	parser.add_argument(
		'--controller',
		help = 'Use this option to run the daemon.',
		dest = 'controller',
		action = 'store_true'
	)
	parser.add_argument(
		'--monitor',
		help = 'Use this option to run the daemon.',
		dest = 'monitor',
		action = 'store_true'
	)
	
	the_setup = connect_me_with_the_setup(f'temperature PID controller {os.getpid()}')
	
	args = parser.parse_args()
	if args.controller == True:
		temperature_controller(set_point_celsius=-20, the_setup=the_setup)
	elif args.monitor == True:
		monitor_temperature_control(the_setup)
	else:
		print('Nothing is done...')
