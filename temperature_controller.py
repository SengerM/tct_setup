from simple_pid import PID
from time import sleep
from progressreporting.TelegramProgressReporter import TelegramReporter # https://github.com/SengerM/progressreporting
import my_telegram_bots
import time
from simple_pid import PID # https://github.com/m-lundberg/simple-pid

def temperature_controller(set_point_celsius:float, the_setup):
	PID_SAMPLE_TIME = 1
	

	temperature_pid = PID(-.5,-.1,-2)
	temperature_pid.sample_time = PID_SAMPLE_TIME
	temperature_pid.output_limits = (0, 4.2)
	temperature_pid.setpoint = 15

	reporter = telegram_reporter = TelegramReporter(
		telegram_token = my_telegram_bots.robobot.token,
		telegram_chat_id = my_telegram_bots.chat_ids['Robobot TCT setup'],
	)

	with the_setup.hold_temperature_control():
		try:
			the_setup.set_peltier_status('on')
			while True:
				new_current = temperature_pid(the_setup.measure_temperature())
				the_setup.set_peltier_current(new_current)
				time.sleep(PID_SAMPLE_TIME)
		except Exception as e:
			reporter.send_message(f'🔥 Temperature controller crashed!')
			raise e
		finally:
			the_setup.set_peltier_status('off')

def monitor_temperature_control(the_setup):
	s = the_setup

	while True:
		print(f'{s.measure_temperature():.2f} °C, {s.measure_humidity():.2f}%RH | {s.measure_peltier_current():.2f} A, {s.measure_peltier_voltage():.2f} V, {s.get_peltier_status()}')
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
		temperature_controller(15, the_setup)
	elif args.monitor == True:
		monitor_temperature_control(the_setup)
	else:
		print('Nothing is done...')
