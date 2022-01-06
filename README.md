# Infomaniak-RetrieveWebLogs-Primus

This Python 3 script automates the download of the web access and error logs from an Infomaniak based hosting.

It was written as replacement to [Infomaniak-RetrieveWebLogs](https://github.com/AlexandreHerzog/Infomaniak-RetrieveWebLogs), which suddenly stopped working mid April 2020 (and started working again on September 30th, a few days after the completion of this script's first version...).


## Prerequisites
Machine with Python 3 and the requirements listed in [requirements.txt](requirements.txt).


## Getting started
1. _OPTIONAL BUT RECOMMENDED_ Create and activate a new Python 3 virtual environment
   `python3 -m venv Infomaniak-RetrieveWebLogs-Primus`
2. Install the required modules
   `pip install -r requirements.txt`
3. Edit [Infomaniak-RetrieveWebLogs-Primus.py](Infomaniak-RetrieveWebLogs-Primus.py) to update the following placeholders:
	- [USERNAME] & [PASSWORD] with the email address and password of a user allowed to log into the Infomaniak Manager to view the web logs.
	- [INFOMANIAK_ACCOUNT_ID] & [INFOMANIAK_PRODUCT_WEBSITE_IDS] referring to your website (see the details in the script itself).
4. Run the script as desired!
   ```
	usage: Infomaniak-RetrieveWebLogs-Primus.py [-h] [-a] [-d] [-l LOGFILE]

	Download logs from Infomaniak

	optional arguments:
	  -h, --help            show this help message and exit
	  -a, --all             Downloads all available logfiles (last 10 days)
							instead of just the files of the day before
	  -d, --debug           Debug level logging (default: INFO)
	  -l LOGFILE, --logfile LOGFILE
							Storing the script output into a logfile instead of
							sending it to stdout
   ```