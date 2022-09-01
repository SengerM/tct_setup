from simple_pid import PID
from time import sleep
from progressreporting.TelegramProgressReporter import TelegramReporter # https://github.com/SengerM/progressreporting
import my_telegram_bots
import time
from TheSetup import connect_me_with_the_setup
from simple_pid import PID # https://github.com/m-lundberg/simple-pid
import os

def temperature_controller(set_point_celsius:float):
	PID_SAMPLE_TIME = 1
	NAME_TO_ACCESS_TO_THE_SETUP = f'temperature PID controller {os.getpid()}'

	temperature_pid = PID(-.5,-.1,-2)
	temperature_pid.sample_time = PID_SAMPLE_TIME
	temperature_pid.output_limits = (0, 4.2)
	temperature_pid.setpoint = 15

	the_setup = connect_me_with_the_setup()

	reporter = telegram_reporter = TelegramReporter(
		telegram_token = my_telegram_bots.robobot.token,
		telegram_chat_id = my_telegram_bots.chat_ids['Robobot TCT setup'],
	)

	with the_setup.hold_temperature_control(NAME_TO_ACCESS_TO_THE_SETUP):
		try:
			the_setup.set_peltier_status('on', who=NAME_TO_ACCESS_TO_THE_SETUP)
			while True:
				new_current = temperature_pid(the_setup.measure_temperature())
				the_setup.set_peltier_current(new_current, who=NAME_TO_ACCESS_TO_THE_SETUP)
				time.sleep(PID_SAMPLE_TIME)
		except Exception as e:
			reporter.send_message(f'🔥 Temperature controller crashed!')
			raise e
		finally:
			the_setup.set_peltier_status('off', who=NAME_TO_ACCESS_TO_THE_SETUP)

def monitor_temperature_control():
	s = connect_me_with_the_setup()

	while True:
		print(f'{s.measure_temperature():.2f} °C, {s.measure_humidity():.2f}%RH | {s.measure_peltier_current():.2f} A, {s.measure_peltier_voltage():.2f} V, {s.get_peltier_status()}')
		time.sleep(1)

if __name__=='__main__':
	import argparse
	
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
	
	args = parser.parse_args()
	if args.controller == True:
		temperature_controller(15)
	elif args.monitor == True:
		monitor_temperature_control()
	else:
		print('Nothing is done...')
