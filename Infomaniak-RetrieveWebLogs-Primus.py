#!venv/bin/python3

import argparse
import asyncio
import datetime
import json
import logging
import requests
import websockets
from itertools import product



USERNAME = 'YOUR_USER_NAME'
PASSWORD = 'YOUR_PASSWORD'
# Log into the Infomaniak Manager then access the following page to get your account_id
# https://manager.infomaniak.com/v3/api/profile/me
# e.g. for {"id":6789,"account_id":12345,"service_id":1,"service_name":"hosting","customer_name":"example.ch"
# => INFOMANIAK_ACCOUNT_ID = '12345' & the first number for INFOMANIAK_PRODUCT_WEBSITE_IDS is 1234
INFOMANIAK_ACCOUNT_ID = '12345'
# Get the second id for INFOMANIAK_PRODUCT_WEBSITE_IDS by visiting the following site (replace 1234 as appropriate)
# https://manager.infomaniak.com/v3/api/proxypass/web/1234/site
# e.g. {"id":98765,"account_id":12345,"service_id":15,"service_name":"web_hosting","customer_name":"example.ch", ... "parent_id":1234
# => INFOMANIAK_PRODUCT_WEBSITE_IDS would be [('1234', '98765')]
INFOMANIAK_PRODUCT_WEBSITE_IDS = [('1234', '98765')]



class InfomaniakClient():
	def __init__(self, username, password, account_id, website_ids):
		self.username = username
		self.password = password
		self.login_url = 'https://login.infomaniak.com/api/login'
		self.account_id = account_id
		self.website_ids = website_ids
		self.request_count = 0
		self.downloads_count = 0
		self.cookie_jar = None
		self.ws_host = None
		self.ws_client = None
		self.loop = asyncio.get_event_loop()
	
	
	async def login(self):
		logging.info(f'Login...')
		r = requests.post(self.login_url, headers={'Content-Type': 'application/json;charset=utf-8'}, data=json.dumps({'login': self.username, 'password': self.password,'remember_me': '0', 'recaptcha': ''}))
		self.cookie_jar = r.cookies
	
	
	async def get_primus_node_ref(self):
		logging.debug(f'Get Primus references...')
		r = requests.get(f'https://manager.infomaniak.com/v3/{self.account_id}',cookies=self.cookie_jar)
		self.cookie_jar = r.cookies
		# Get the node reference
		c = r.content.decode()
		s = c.find('//node')
		e = c.find('/',s+8)
		self.ws_host = c[s:e].split('//')[1]
		ws_url = 'https:' + c[s:e] + '/primus/info'
		self.ws_config = requests.get(ws_url, cookies=self.cookie_jar).json()
	
	
	async def download_logs(self, msg):
		url = f'https://manager.infomaniak.com/v3/api/download/{msg["container_uuid"]}/{msg["file_uuid"]}'
		logging.info(f'Downloading file {url} ...')
		r = requests.get(url, cookies=self.cookie_jar)
		filename = r.headers['content-disposition'].split('"')[1]
		with open(filename, 'wb') as fd:
			for chunk in r.iter_content(chunk_size=128):
				fd.write(chunk)
				
		self.downloads_count += 1
	
	
	async def get_logs(self, dates):
		logging.info(f'Getting the logs for the following date(s): {dates}')
		await self.login()
		await self.get_primus_node_ref()
		logging.info(f'Setting up WS client...')
		# Random URL under the node is enough...
		self.ws_client = WebSocketClient(f'wss://{self.ws_host}/primus/123/abcvdefdf/websocket', self.loop, "")
		self.ws_client.callback_when_file_ready = self.download_logs
		await self.ws_client.run()

		logging.info(f'Start requesting the logs...')
		for date, logtype, website_tuple in product(dates, ['access', 'error'], self.website_ids):
			url = f'https://manager.infomaniak.com/v3/api/proxypass/web/{website_tuple[0]}/site/{website_tuple[1]}/log/{logtype}/download?date={date}'
			logging.info(f'Sending GET {url}')
			r = requests.get(url, cookies=self.cookie_jar)
			self.request_count += 1
			await self.ws_client.sendPrimusMessage(0, ["register","progress", {"progressUUID": r.json()['data']['progress_id']}] )
			
		while self.downloads_count < self.request_count:
			logging.debug(f'Got {self.downloads_count} downloads completed vs {self.request_count} requests...')
			await asyncio.sleep(15)
			
		logging.debug(f'Got all downloads, stopping the WS client...')
		await self.ws_client.stop()
		logging.info('Done.')



class WebSocketClient():
	def __init__(self, url, loop, cookie):
		self.url = url
		self.loop = loop
		self.cookie = cookie
		self.keep_running = True
		self.callback_when_file_ready = None
		self.connection = None
		self.request_id = 1
	
	async def connect(self):
		logging.debug(f'Connecting WS...')
		# Adding cookies to ws: https://github.com/aaugustin/websockets/issues/420 ; isn't required in this scenario
		self.connection = await websockets.client.connect(self.url, extra_headers=[('Cookie', self.cookie)])
		if self.connection.open:
			logging.debug('Connection stablished. Client correcly connected')
			return self.connection
	
	
	async def sendPrimusMessage(self, type, data):
		ws_request = [{'type': type, 'id': self.request_id, 'data': data}]
		self.request_id += 1
		await self.sendMessage( json.dumps(ws_request) )
	
	async def sendMessage(self, message):
		logging.debug(f'Sending msg {message}...')
		await self.connection.send(message)
	
	
	async def receiveMessage(self):
		while self.keep_running:
			try:
				message = await self.connection.recv()
				logging.debug('Received message from server: ' + str(message))
				try:
					m = str(message)
					if m[:1] == 'a':
						txt_msgs = json.loads(message[1:])
						for txt_msg in txt_msgs:
							json_msg = json.loads(txt_msg)
							if 'data' in json_msg and len(json_msg['data']) == 3 and 'percent' in json_msg['data'][2] and json_msg['data'][2]['percent'] == 100:
								logging.info('File generation done! Unregistering & downloading the file...')
								await self.sendPrimusMessage(0, ["unregister", json_msg['data'][1]])
								asyncio.create_task(self.callback_when_file_ready(json_msg['data'][2]['extra']))
				except Exception as e:
					logging.exception(f'Exception {e} on message {message}')
					#raise e
				
			except websockets.exceptions.ConnectionClosed:
				logging.exception('Connection with server closed')
				break
	
	async def heartbeat(self):
		while self.keep_running:
			try:
				ts = round(datetime.datetime.now().timestamp() * 1000)
				await self.sendMessage(f'["\\"primus::ping::{ts}\\""]')
				await asyncio.sleep(15)
			except websockets.exceptions.ConnectionClosed:
				logging.exception('Connection with server closed')
				break
	
	
	async def run(self):
		logging.debug(f'Running WebsocketClient.run()...')
		await self.connect()
		tasks = [
			asyncio.ensure_future(self.heartbeat()),
			asyncio.ensure_future(self.receiveMessage()),
		]
		# We don't want to block here
		#asyncio.wait(tasks)

	
	async def stop(self):
		logging.debug('Stopping the WS client...')
		self.keep_running = False


if __name__ == '__main__':
	parser = argparse.ArgumentParser(description='Download logs from Infomaniak')
	parser.add_argument('-a', '--all', action='store_true', dest='all', default=False,
		help='Downloads all available logfiles (last 10 days) instead of just the files of the day before')
	parser.add_argument('-d', '--debug', action='store_true', dest='debug', default=False,
		help='Debug level logging (default: INFO)')
	parser.add_argument('-l', '--logfile', dest='logfile', default=None,
		help='Storing the script output into a logfile instead of sending it to stdout')
	opts = parser.parse_args()

	log_config = {'level': logging.INFO, 'format': '%(asctime)s %(name)s %(levelname)s %(message)s'}
	if opts.debug:
		log_config['level'] = logging.DEBUG
	
	if opts.logfile is not None:
		log_config['filename'] = opts.logfile

	logging.basicConfig(**log_config)
	
	days = 1
	if opts.all:
		days = 10
		
	dates = [(datetime.datetime.today()- datetime.timedelta(days=(x+1))).isoformat()[:10] for x in range(days)]
	ic = InfomaniakClient(USERNAME, PASSWORD, INFOMANIAK_ACCOUNT_ID, INFOMANIAK_PRODUCT_WEBSITE_IDS)
	ic.loop.run_until_complete(ic.get_logs(dates))

