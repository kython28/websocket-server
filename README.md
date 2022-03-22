
# websocket-server
A simple websocket server for python3 (support pypy3)

# Usage

To create your websocket server in python you just have to do the following:
```python
#!/usr/bin/python3
# -*- coding: utf-8 -*-

from websocket_server import WebSocketServer
import time

def callback(client, addr, path):
  while True:
    client.send(str(time.time())) # We send timestamp to the client
	
	
    # We receive the response from the client
    client_response = client.recv()
    print(client_response)
	
    # If we want ....
    client.ping() # We send ping
    client.pong() # We look forward to pong from the client
 
    time.sleep(0.5) # Pause

WebSocketServer("localhost", 8080, callback)()
```

In case you want to use ssl, you must do the following:
```Python
import ssl

# ...

ssl_context = ssl.SSLContext(ssl.PROTOCOL_SSLv23)
ssl_context.load_cert_chain(
	"cert.pem", keyfile="privkey.pem"
)

WebSocketServer("localhost", 8080, callback, ssl_context)()
```
