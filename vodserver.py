import sys
import socket
import os
import threading
import time
from datetime import datetime

port = 0
BUFSIZE = 1024
content_type_dict = {}
CHUNKSIZE = 5242880
cache = dict()

global count
class HTTPServer:
    def __init__(self, port):
        self.port = port
        self.s = None
        self.createSocket()
        # {uri: ["keep-alive" True /"close" False, 200/206, [-1, -1]/range ]}
        self.conn = dict()

    def parse_request(self, req, connection):
        if not req:
            return
        req = req.decode()
        tmp = req.split("\n")
        connFlag = True
        type = 200
        range = [-1, -1]
        for line in tmp:
            line = line.strip()
            tmpLine = line.split(":")
            if tmpLine[0] == "Connection":
                connStatus = tmpLine[1].strip()
                if connStatus == "close" or connStatus == "Close":
                    connFlag = False
            if tmpLine[0].strip() == "range" or tmpLine[0].strip() == "Range":
                type = 206
                range = (tmpLine[1].split("="))[1].split("-")
                if not range[1]:
                    range = [int(range[0]), -1]
                else:
                    range = [int(range[0]), int(range[1])]

        uri = (tmp[0].split("HTTP")[0])[5:].strip()
        # print("req is: ", req)
        self.conn[uri] = [connFlag, type, range]

        if uri.startswith("confidential"):
            self.handle_forbidden(uri, connection)
            return
        # Terminate flag set by client

        fileName = os.path.join("content", uri)
        # print(fileName)

        if not os.path.exists(fileName):
            self.handle_not_found(uri, connection)
            return

        self.serve_request(fileName, uri, connection)



    def terminate(self, uri, fileName):
        pass

    def handle_not_found(self, uri, connection):
        response = self.get_404_response(uri)
        connection.send(response)

    def handle_forbidden(self, uri, connection):
        response = self.get_403_response(uri)
        connection.send(response.encode())

    def get_403_response(self, uri):
        time_struct = time.localtime()
        current_time = time.strftime('%a, %d %b %Y %H:%M:%S GMT', time_struct)
        time_header = "Date: " + str(current_time) + "\r\n"
        content_type_header = "Content-Type: " + "text/html\r\n"

        if not self.conn[uri][0]:
            conn_header = "Connection: close\r\n"
        else:
            conn_header = "Connection: close\r\n"

        # Reference: Udacity
        payload = "<html>\n<head>\n<style type=text/css>\n\n</style>\n</head>\n\n<body><p>The URI you are requesting is forbidden\n<br><br> \nPermission Denied.</p>\n\n</body>\n</html>\n"
        content_length_header = "Content-Length: " + str(len(payload)) + "\r\n"
        header = "HTTP/1.1 403 Forbidden\r\n" + time_header + content_type_header + content_length_header + conn_header + "\r\n"
        response = header + payload
        return response



    def serve_request(self, fileName, uri, connection):

        header = self.get_header(fileName, uri)
        response = header.encode() + self.get_payload(uri, fileName)
        try:
            connection.send(response)
        except:
            print("broken pipe exception")
        # print("response sent", fileName)

    def get_header(self, fileName, uri):
        type = self.conn[uri][1]
        fileLength = os.path.getsize(fileName)
        if fileLength > CHUNKSIZE:
            type = 206
            self.conn[uri][1] = 206

        if type == 200:
            header = "HTTP/1.1 200 OK\r\n"
        elif type == 206:
            header = "HTTP/1.1 206 Partial Content\r\n"
            # Get Content-Ranges

        # Get Date
        time_struct = time.localtime()
        current_time = time.strftime('%a, %d %b %Y %H:%M:%S GMT', time_struct)
        time_header = "Date: " + str(current_time) + "\r\n"
        # print(time_header)

        # Get Last-Modified
        modtime_epoc = os.path.getmtime(fileName)
        modified_time = datetime.fromtimestamp(modtime_epoc).strftime('%c')
        modified_time = modified_time[:3] + "," + modified_time[3:11] + modified_time[20:24]
        last_modified_header = "Last-Modified: " + modified_time + "\r\n"
        # print(last_modified_header)

        # Get Accept-Ranges
        accept_range_header = "Accept-Ranges: bytes" + "\r\n"

        # Get Content-Length
        if type == 200:
            content_length_header = "Content-Length: " + str(fileLength) + "\r\n"
        elif type == 206:
            content_length_header = "Content-Length: " + str(CHUNKSIZE) + "\r\n"

        # Get Connection
        if not self.conn[uri][0]:
            flag = "close"
            print("close!!!")
        else:
            flag = "close"

        conn_header = "Connection: " + flag + "\r\n"

        # Get content type
        content_type_header = "Content-Type: " + self.get_content_type(fileName)

        if type == 206:
            range = self.conn[uri][2]
            # if range[0] == -1:
                # print("WRONG RANGE FROM REQUEST!!!")
                # pass
            content_range_header = "Content-Range: bytes " + self.get_range(uri, fileName, fileLength) + "\r\n"
            header += content_range_header
            content_length_header = "Content-Length: " + str(self.get_206_length(uri, fileLength)) + "\r\n"
            print("206!!!!!!!!!!!!!!!!!!!!!!!")
        # elif type == 200:
            # content_range_header = "Content-Range: bytes " + str(0) + "/" + str(fileLength - 1) + "\r\n"


        header += time_header + last_modified_header + accept_range_header + content_length_header + conn_header + content_type_header + "\r\n"

            # get range
        print("header: ", header)
        return header

    def get_206_length(self, uri, fileLength):
        range = self.conn[uri][2]
        if range[0] == -1:
            print("206: First request without range or sth wrong")
            range[0] = 0
        if range[1] == -1:
            range[1] = min(fileLength, range[0] + CHUNKSIZE)

        return range[1] - range[0] + 1

    def get_range(self, uri, fileName, fileLength):
        range = self.conn[uri][2]
        if range[0] == -1:
            range[0] = 0
            print("206 sth wrong or first req")
        if range[1] == -1:
            range[1] = min(fileLength - 1, range[0] + CHUNKSIZE - 1)

        partb = str(range[0]) + "-" + str(range[1]) + "/" + str(fileLength)
        return partb

    def get_content_type(self, fileName):
        if fileName.endswith(".txt"):
            return "text/plain\r\n"
        if fileName.endswith(".css"):
            return "text/css\r\n"
        if fileName.endswith(".htm") or fileName.endswith(".html"):
            return "text/hyml\r\n"
        if fileName.endswith(".gif"):
            return "image/gif\r\n"
        if fileName.endswith(".jpg") or fileName.endswith(".jpeg"):
            return "image/jpeg\r\n"
        if fileName.endswith(".png"):
            return "image/png\r\n"
        if fileName.endswith(".mp4"):
            return "video/mp4\r\n"
        if fileName.endswith(".webm") or fileName.endswith(".ogg"):
            return "video/webm\r\n"
        if fileName.endswith(".js"):
            return "application/javascript\r\n"
        else:
            return "application/octet-stream\r\n"

    def get_payload(self, uri, fileName, offset = 0):
        file = open(fileName, "rb")
        type = self.conn[uri][1]
        range = self.conn[uri][2]
        offset = range[0]
        if type == 206:
            file.seek(offset)
            chunk = file.read(CHUNKSIZE)
            print("get 206 payload, length is: ", len(chunk))

            return chunk
        data = file.read(CHUNKSIZE)
        # print("data length: ", len(data))
        return data

    def get_404_response(self, uri):
        time_struct = time.localtime()
        current_time = time.strftime('%a, %d %b %Y %H:%M:%S GMT', time_struct)
        time_header = "Date: " + str(current_time) + "\r\n"
        content_type_header = "Content-Type: " + "text/html\r\n"

        if not self.conn[uri][0]:
            conn_header = "Connection: close\r\n"
        else:
            conn_header = "Connection: close\r\n"
        # Reference: Udacity
        payload = "<html>\n<head>\n<style type=text/css>\n\n</style>\n</head>\n\n<body><p>The URI you are requesting does not exist\n<br><br> \nTry checking the URL in your web browser.</p>\n\n</body>\n</html>\n"
        content_length_header = "Content-Length: " + str(len(payload)) + "\r\n"
        header = "HTTP/1.1 404 Not Found\r\n" + time_header + content_type_header + content_length_header + conn_header + "\r\n"
        response = header + payload
        return response.encode()

    def run(self):
        self.s.listen()
        # ACCEPT is a blocking call

        while True:
            conn, addr = self.s.accept()
            req = conn.recv(BUFSIZE)
            # print("received msg")
            req_handle_thread = threading.Thread(target=self.parse_request, args=(req, conn, ))
            req_handle_thread.start()
            # print(count)






    def createSocket(self):
        # Create socket instance
        self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        # localip = socket.gethostbyname(socket.gethostname())
        localip = "127.0.0.1"

        try:
            self.s.bind((localip, self.port))
        except socket.error as e:
            sys.exit(-1)


if __name__ == "__main__":
    count = 0
    port = int(sys.argv[1])
    # print(type(port))
    server = HTTPServer(port)
    server.run()
