import hashlib,threading,unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from upload_media import upload


class UploadTests(unittest.TestCase):
    def test_preflight_skips_identical_download_and_keeps_original(self):
        class Client:
            def request(self,path,body):
                self.body=body;return {'results':[{'action':'reject','assetId':'already'}]}
        with TemporaryDirectory() as temp:
            path=Path(temp)/'downloaded.png';path.write_bytes(b'original bytes');client=Client()
            with patch('upload_media.upload_file') as transfer:
                self.assertEqual(upload(client,path,threading.Event()),('already',False));transfer.assert_not_called()
            self.assertEqual(client.body['assets'][0]['checksum'],hashlib.sha1(b'original bytes').hexdigest())
            self.assertEqual(path.read_bytes(),b'original bytes')

    def test_new_private_copy_passes_visibility_and_cancellation(self):
        class Client:
            def request(self,*_):return {'results':[{'action':'accept'}]}
        with TemporaryDirectory() as temp:
            path=Path(temp)/'edited.png';path.write_bytes(b'copy');cancel=threading.Event()
            with patch('upload_media.upload_file',return_value='new') as transfer:
                self.assertEqual(upload(Client(),path,cancel,visibility='locked'),('new',True))
                self.assertEqual(transfer.call_args.kwargs,{'visibility':'locked'})
                cancel.set()
                with self.assertRaises(InterruptedError):upload(Client(),path,cancel)

    def test_in_memory_copy_sends_real_png_with_private_visibility(self):
        import json
        from io import BytesIO
        from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
        from threading import Thread
        from urllib.request import build_opener
        from PIL import Image
        from upload_media import upload_bytes
        captured={}
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                captured['body']=self.rfile.read(int(self.headers['Content-Length']))
                captured['hash']=self.headers['x-immich-checksum']
                self.send_response(201);self.end_headers();self.wfile.write(b'{"id":"copy"}')
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=Thread(target=server.serve_forever,daemon=True);thread.start()
        class Client:
            modern_search=True;token='fixture';http=build_opener();base=f'http://127.0.0.1:{server.server_port}'
            def request(self,*args):return {'results':[{'action':'accept'}]}
        stream=BytesIO();Image.new('RGBA',(20,30),'red').save(stream,format='PNG');data=stream.getvalue()
        try:
            with patch('tempfile.mkstemp',side_effect=AssertionError('Edited copies must stay in memory')):
                self.assertEqual(upload_bytes(Client(),data,'edited.png',1234567890,threading.Event(),'locked'),('copy',True))
            self.assertIn(data,captured['body']);self.assertIn(b'name="visibility"\r\n\r\nlocked',captured['body'])
            self.assertEqual(captured['hash'],hashlib.sha1(data).hexdigest())
        finally:server.shutdown();server.server_close()
