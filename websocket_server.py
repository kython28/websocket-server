#!/usr/bin/python3
# -*- coding: utf-8 -*-

import socket, ssl, struct, threading, os, signal, time, base64, hashlib

class WebsocketClient:
	def __init__(self, client, addr, callback, hostname):
		self.__client = client
		self.__addr = addr
		self.__callback = callback
		self.__hostname = hostname

	def __create_hash(self, sec_key):
		m = hashlib.sha1()
		m.update("{}258EAFA5-E914-47DA-95CA-C5AB0DC85B11".format(sec_key).encode())
		return base64.b64encode(m.digest()).decode()

	def __recv_handshake(self):
		try:
			headers = self.__client.recv(65536)
			
			headers = headers.decode().split("\r\n")
			self.__path = headers[0].split(" ")[1]
			sec_key = self.__check_handshake(headers[1:])	
		except Exception:
			self.__send_badrequest()
			return False
		self.__send_handshake(sec_key)
		return True

	def __check_handshake(self, headers):
		n = 0
		fields = dict([tuple(line.split(": ")) for line in headers if line])
		if fields["Upgrade"] != "websocket":
			raise Exception
		return fields["Sec-WebSocket-Key"]

	def __send_handshake(self, sec_key):
		header = "HTTP/1.1 101 Switching Protocols\r\n"
		header += "Upgrade: websocket\r\n"
		header += "Connection: Upgrade\r\n"
		header += "Sec-WebSocket-Accept: {}\r\n\r\n".format(self.__create_hash(sec_key))

		self.__client.send(header.encode())

	def __send_badrequest(self):
		self.__client.send(b"HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\n\r\n")

	def __send(self, data, opcode, fin):
		data_length = len(data)
		payload = struct.pack("!B", (fin << 7)|opcode)

		if data_length < 126:
			payload += struct.pack("!B", data_length)
		elif data_length < (1 << 16):
			payload += struct.pack("!BH", 126, data_length)
		else:
			payload += struct.pack("!BQ", 127, data_length)
		payload += data
		self.__client.send(payload)

	def send(self, data):
		data_length = len(data)
		max_size = (1 << 64) - 1
		fin = 0
		opcode = (1 if type(data) is str else 2)
		data = data.encode()
		for x in range(0, data_length, max_size):
			y = x+max_size
			if y > data_length:
				y = data_length
				fin = 1
			self.__send(data, opcode, fin)
			opcode = 0

	def ping(self):
		self.__send(os.urandom(125), 9, 1)

	def __recv(self):
		data = b""
		hg = True
		_opcode = 0
		while True:
			header, length = struct.unpack("!BB", self.__client.recv(2))
			fin = header&(1 << 7)
			opcode = header&((1 << 4) - 1)
			if hg:
				_opcode = opcode

			mask = length&(1 << 7)
			length = length&((1 << 7) - 1)
			if length == 126:
				length = struct.unpack("!H", self.__client.recv(2))[0]
			elif length == 127:
				length = struct.unpack("!Q", self.__client.recv(8))[0]

			if mask:
				mask_key = self.__client.recv(4)

			if length > 0:
				frame = self.__client.recv(length)
				if mask:
					for i in range(length):
						data += struct.pack("B", frame[i]^mask_key[i%4])
				else:
					data += frame
			if fin: break
			hg = False

		if _opcode == 1:
			data = data.decode()

		return data, _opcode

	def recv(self):
		return self.__recv()[0]

	def pong(self):
		data, opcode = self.__recv()
		if opcode != 10:
			raise Exception

	def __call__(self):
		if self.__recv_handshake():
			self.__callback(self, self.__path, self.__addr)
		self.__client.close()


def runNewClient(*opt):
	WebsocketClient(*opt)()

class WebsocketServer:
	def __init__(self, hostname, port, callback, ssl_ctx=None):
		self.__hostname = hostname
		self.__port = port
		self.__callback = callback
		self.__ssl_ctx = ssl_ctx
		self.__fd = []

	def __del__(self):
		for fd in self.__fd:
			fd.close()

	def __call__(self):
		sock = socket.socket(
			family=socket.AF_INET,
			type=socket.SOCK_STREAM
		)

		sock.settimeout(0.1)
		sock.bind((self.__hostname, self.__port))
		sock.listen(1)

		self.__fd.append(sock)

		if self.__ssl_ctx:
			server = self.__ssl_ctx.wrap_socket(sock, server_side=True)
			self.__fd.append(server)
		else: server = sock
		
		callback = self.__callback
		hostname = self.__hostname
		if self.__port != 80:
			hostname += ":"+str(self.__port)
		while True:
			try:
				client, addr = server.accept()
				threading.Thread(target=runNewClient, args=(client, addr, callback, hostname)).start()
			except socket.timeout:
				pass
			except Exception:
				pass