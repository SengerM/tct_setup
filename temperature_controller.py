from simple_pid import PID
from time import sleep
from progressreporting.TelegramProgressReporter import TelegramReporter # https://github.com/SengerM/progressreporting
import my_telegram_bots
import time
from TheSetup import connect_me_with_the_setup
from simple_pid import PID # https://github.com/m-lundberg/simple-pid
import os

PID_SAMPLE_TIME = 1
NAME_TO_ACCESS_TO_THE_SETUP = f'temperature PID controller {os.getpid()}'

temperature_pid = PID(-.5,-.1,-2)
temperature_pid.sample_time = PID_SAMPLE_TIME
temperature_pid.output_limits = (0, 4.2)
temperature_pid.setpoint = -20

the_setup = connect_me_with_the_setup()

with the_setup.hold_temperature_control(NAME_TO_ACCESS_TO_THE_SETUP):
	try:
		the_setup.set_peltier_status('on', who=NAME_TO_ACCESS_TO_THE_SETUP)
		while True:
			new_current = temperature_pid(the_setup.measure_temperature())
			the_setup.set_peltier_current(new_current, who=NAME_TO_ACCESS_TO_THE_SETUP)
			time.sleep(PID_SAMPLE_TIME)
	finally:
		the_setup.set_peltier_status('off', who=NAME_TO_ACCESS_TO_THE_SETUP)
