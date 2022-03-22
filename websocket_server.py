#!/usr/bin/python
# -*- coding: utf-8 -*-

# External libraries
import socket, ssl, struct, threading, hashlib, os, traceback
import base64, sys


class WebSocketClient:
	def __init__(self, client, addr, callback):
		self.__client = client
		self.__callback = callback
		self.__addr = addr

		self.settimeout = client.settimeout
		self.close = client.close

	def __del__(self):
		try: self.close()
		except Exception: pass

	def __create_hash(self, sec_key):
		m = hashlib.sha1()
		m.update("{}258EAFA5-E914-47DA-95CA-C5AB0DC85B11".format(sec_key).encode())
		return base64.b64encode(m.digest()).decode()

	def __recv_handshake(self):
		try:
			headers = self.__client.recv(1 << 16)
			headers = headers.decode().split("\r\n")
			path = headers[0].split(" ")[1]
			self.headers = dict([tuple(line.split(": ")) for line in headers[1:] if line])
			sec_key = self.__check_handshake()
		except Exception:
			self.send_badrequest()
			return

		self.__send_handshake(sec_key)
		return path

	def __check_handshake(self):
		fields = self.headers
		assert(fields["Upgrade"] == "websocket")
		return fields["Sec-WebSocket-Key"]

	def __send_handshake(self, sec_key):
		header = b"HTTP/1.1 101 Switching Protocols\r\n"
		header += b"Upgrade: websocket\r\n"
		header += b"Connection: Upgrade\r\n"
		header += "Sec-WebSocket-Accept: {}\r\n\r\n".format(self.__create_hash(sec_key)).encode()
		self.__client.sendall(header)

	def send_badrequest(self):
		self.__client.sendall(b"HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\n\r\n")
		self.close()

	def __send(self, data, length, opcode, fin):
		header = struct.pack("!B", (fin << 7)|opcode)

		if length < 126:
			header += struct.pack("!B", length)
		elif length < 65536:
			header += struct.pack("!BH", 126, length)
		else:
			header += struct.pack("!BQ", 127, length)

		self.__client.sendall(header)
		self.__client.sendall(data)

	def send(self, data, opcode=-1):
		length = len(data)
		send_ = self.__send

		if opcode < 0:
			opcode = (1 if type(data) is str else 2)
		if type(data) is str:
			data = data.encode()

		if length > (1 << 64)-1:
			fin = 0
			for x in range(0, length, (1 << 64) - 1):
				y = x + (1 << 64) - 1
				if y > length:
					y = length
					fin = 1

				send_(data[x:y], y-x, opcode, fin)
				opcode = 0
		else:
			send_(data, length, opcode, 1)

	def ping(self):
		self.__send(os.urandom(125), 125, 9, 1)

	def __recv_packet(self):
		_recv = self.__client.recv

		header, length = struct.unpack("!BB", _recv(2))
		fin = header&(1 << 7)
		opcode = header&((1 << 4) - 1)

		mask = length&(1 << 7)
		length = length&((1 << 7) - 1)
		if length == 126:
			length = struct.unpack("!H", _recv(2))[0]
		elif length == 127:
			length = struct.unpack("!Q", _recv(8))[0]

		if mask:
			mask_key = _recv(4)

		if length > 0:
			data = b""
			with length > 0:
				frame = _recv(length)
				if mask:
					for i in range(length):
						data += struct.pack("B", frame[i]^mask_key[i%4])
				else:
					data += frame
				length -= len(frame)
		return data, opcode, fin

	def recv(self):
		recv = self.__recv_packet
		
		data, opcode, fin = recv()
		while not(fin):
			frame, _, fin = recv()
			data += frame

		if opcode == 1: data = data.decode()

		return data

	def pong(self):
		assert(self.__recv_packet()[1] == 10)

	def __call__(self):
		try:
			path = self.__recv_handshake()
			if path:
				self.__callback(self, self.__addr, path)
		except Exception:
			traceback.print_exc()
			sys.stderr.flush()
			sys.stdout.flush()


class WebSocketServer:
	def __init__(self, hostname: str, port: int, callback, ssl_ctx=None):
		self.__hostname = hostname
		self.__port = port
		self.__callback = callback

		sock = socket.socket(
			family=socket.AF_INET,
			type=socket.SOCK_STREAM
		)

		if ssl_ctx:
			sock = ssl_ctx.wrap_socket(sock, server_side=True)

		self.__sock = sock
		self.close = sock.close

		# Status:
		# -1 -> Error
		# 0 -> Offline
		# 1 -> Online
		self.__status = 0
		self.__status_lock = threading.Lock()

	@property
	def status(self):
		with self.__status_lock:
			status = self.__status
		return status

	def __set_status(self, status):
		with self.__status_lock:
			self.__status = status

	def __del__(self):
		try: self.close()
		except Exception: pass

	def __call__(self):
		server = self.__sock
		callback = self.__callback
		
		try:
			server.bind((self.__hostname, self.__port))
			server.listen(socket.SOMAXCONN)
		except Exception:
			self.__set_status(-1)
			return

		callback = self.__callback

		while True:
			try:
				client, addr = server.accept()
				threading.Thread(target=WebSocketClient(client, addr, callback), daemon=True).start()
			except (Exception, KeyboardInterrupt):
				break

		try: server.close()
		except Exception: pass

		self.__set_status(0)