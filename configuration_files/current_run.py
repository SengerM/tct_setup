from pathlib import Path
from the_bureaucrat.bureaucrats import RunBureaucrat # https://github.com/SengerM/the_bureaucrat

Alberto = RunBureaucrat(Path.home()/'measurements_data/20221018_TI-LGADs')
Alberto.create_run()
